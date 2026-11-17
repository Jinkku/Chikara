"""apiv2/submit/... : uploading beatmap sets and editing their metadata. Used by the game and the website.

Auth like apiv2/mod: the game's Username + Password headers, or the website's login cookies (+ "X-Chikara: 1"
on POSTs). Replies are JSON; failures are {"error": "..."} with a 4xx status.

Uploading (game only: requests with the website's cookies are refused; the web server refuses bodies over 1 MB,
so the .osz goes up in pieces):
    POST start           {"size": bytes, "name": "x.osz"}  -> {"token", "chunk_size"}
    POST chunk/<token>   raw bytes, ?offset=N (bytes already sent)  -> {"received"}
    POST finish/<token>  -> {"ok", "setid", "updated", "beatmaps": [{"file", "version", "beatmapid"}],
                             "skipped": [file names], "removed": [difficulty names], "url"}
Uploading a set again (its .osu files still carry the BeatmapSetID it got) updates it, while it's unranked.

Editing:
    GET  info/<setid>     -> who may edit, the editable fields, the difficulties
    POST edit/<setid>     {"title", "title_unicode", "artist", "artist_unicode", "tags", "source",
                           "mapper", "genre", "language" (catalog ids), "nsfw" (explicit),
                           "difficulties": {beatmapid: name}, team only: "ranked"}
    GET  mine             -> your submitted sets
"""
import json
import os
import secrets
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone

from Chikara import catalog
from Chikara.settings import storage_root
from dbview.models import Beatmap
from moderation import service as moderation

from . import osz
from .models import Submission, UploadSession

CHUNK_SIZE = 768 * 1024
SESSION_TTL = timedelta(hours=2)
RANKED_CHOICES = {0: "Unranked", 1: "Ranked", 2: "Special"}


def fail(text, status=400):
    return JsonResponse({"error": text}, status=status)


def tmp_dir():
    path = os.path.join(storage_root, "submit_tmp")
    os.makedirs(path, exist_ok=True)
    return path


def part_path(token):
    return os.path.join(tmp_dir(), f"{token}.part")


def drop_session(s):
    try:
        os.remove(part_path(s.token))
    except FileNotFoundError:
        pass
    s.delete()


def expire_sessions():
    for s in UploadSession.objects.filter(created__lt=timezone.now() - SESSION_TTL):
        drop_session(s)


def body(request):
    try:
        data = json.loads(request.body or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def can_edit(me, setid):
    """(allowed, is_team, is_owner)."""
    if me is None or me.restricted:
        return False, False, False
    owner = Submission.objects.filter(beatmapsetid=setid, owner=me.username).exists()
    team = moderation.is_staff(me.username)
    return owner or team, team, owner


# ---------------------------------------------------------------- entry point

def api(request, action):
    parts = [p for p in action.split("/") if p]
    if not parts:
        return fail("Unknown action.", 404)
    name, args = parts[0], parts[1:]
    write = request.method == "POST"
    me = moderation.request_user(request, write=write)

    if name == "info" and not write and len(args) == 1 and args[0].isdigit():
        return info_view(me, int(args[0]))
    if name == "claim" and not write and len(args) == 1 and args[0].isdigit():
        from .claims import status_view
        return status_view(me, int(args[0]))
    if me is None:
        return fail("Log in first.", 401)
    if name == "mine" and not write:
        return mine_view(me)
    if not write:
        return fail("Unknown action.", 404)
    if me.restricted:
        return fail("Restricted accounts can't submit or edit beatmaps.", 403)
    if name in ("start", "chunk", "finish", "cancel") and not request.META.get("HTTP_USERNAME"):
        # Uploads only come from the game (Username/Password headers), never from the website's login cookies.
        return fail("Beatmaps can only be submitted from the game.", 403)
    if name == "start" and not args:
        return start_view(request, me)
    if name == "chunk" and len(args) == 1:
        return chunk_view(request, me, args[0])
    if name == "finish" and len(args) == 1:
        return finish_view(request, me, args[0])
    if name == "cancel" and len(args) == 1:
        s = UploadSession.objects.filter(token=args[0], username=me.username).first()
        if s:
            drop_session(s)
        return JsonResponse({"ok": True})
    if name == "edit" and len(args) == 1 and args[0].isdigit():
        return edit_view(request, me, int(args[0]))
    return fail("Unknown action.", 404)


# ---------------------------------------------------------------- upload

def start_view(request, me):
    expire_sessions()
    data = body(request)
    try:
        size = int(data.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return fail("Pick a beatmap to upload.")
    if size > osz.MAX_OSZ_BYTES:
        return fail(f"That beatmap is too big ({osz.MAX_OSZ_BYTES // (1024 * 1024)} MB max).")
    if UploadSession.objects.filter(username=me.username).count() >= 2:
        # the oldest one was probably abandoned
        drop_session(UploadSession.objects.filter(username=me.username).order_by("created").first())
    s = UploadSession.objects.create(token=secrets.token_hex(16), username=me.username, size=size)
    open(part_path(s.token), "wb").close()
    return JsonResponse({"token": s.token, "chunk_size": CHUNK_SIZE})


def chunk_view(request, me, token):
    s = UploadSession.objects.filter(token=token, username=me.username).first()
    if s is None:
        return fail("That upload has expired. Start it again.", 404)
    try:
        offset = int(request.GET.get("offset", request.META.get("HTTP_OFFSET", "")))
    except ValueError:
        return fail("Missing offset.")
    data = request.body
    if offset != s.received:
        # a retried piece: tell the client where to carry on from
        return JsonResponse({"received": s.received, "error": "Wrong offset."}, status=409)
    if not data or len(data) > CHUNK_SIZE * 2 or s.received + len(data) > s.size:
        return fail("That piece of the upload is the wrong size.")
    with open(part_path(token), "ab") as f:
        f.write(data)
    s.received += len(data)
    s.save(update_fields=["received"])
    return JsonResponse({"received": s.received})


def finish_view(request, me, token):
    s = UploadSession.objects.filter(token=token, username=me.username).first()
    if s is None:
        return fail("That upload has expired. Start it again.", 404)
    if s.received != s.size:
        return fail(f"The upload isn't complete yet ({s.received} of {s.size} bytes).")
    try:
        result = osz.submit(part_path(token), me.username, staff=moderation.is_staff(me.username))
    except osz.SubmitError as e:
        return fail(str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return fail(f"The server couldn't process that beatmap ({type(e).__name__}).", 500)
    finally:
        drop_session(s)
    print(f"[submit] {me.username} {'updated' if result.updated else 'submitted'} set {result.setid} "
          f"({len(result.beatmaps)} difficulties)")
    from online.medals import check
    check(me.username)  # "Mapper"
    return JsonResponse(result.json())


# ---------------------------------------------------------------- info / edit

def info_view(me, setid):
    rows = list(Beatmap.objects.filter(beatmapsetid=setid).order_by("Level", "notecount"))
    if not rows:
        return fail("That beatmap set doesn't exist.", 404)
    sub = Submission.objects.filter(beatmapsetid=setid).first()
    allowed, team, owner = can_edit(me, setid)
    first = rows[0]
    data = {
        "setid": setid,
        "submitted": sub is not None,
        "owner": sub.owner if sub else "",
        "mapper_user": catalog.mapper_users([(setid, first.mapper)]).get(setid, ""),
        "uploaded": int(sub.created.timestamp()) if sub else 0,
        "updated": int(sub.updated.timestamp()) if sub else 0,
        "edited_by": sub.edited_by if sub else "",
        "can_edit": allowed,
        "team": team,
        "can_edit_mapper": allowed,  # the uploader or the team; nobody else gets the edit panel at all
        "ranked": first.ranked,
    }
    if allowed:
        data["fields"] = {
            "title": first.title, "title_unicode": first.title_unicode, "artist": first.artist,
            "artist_unicode": first.artist_unicode, "tags": first.tags or "", "mapper": first.mapper,
            "source": first.source or "",
        }
        data["fields"].update(genre=first.genre or catalog.UNSPECIFIED, language=first.language or catalog.UNSPECIFIED,
                              nsfw=bool(first.nsfw), video=bool(first.video), storyboard=bool(first.storyboard))
        data["genres"] = [{"id": i, "name": n} for i, n in catalog.GENRES]
        data["languages"] = [{"id": i, "name": n} for i, n in catalog.LANGUAGES]
        data["difficulties"] = [{"beatmapid": r.beatmapid, "version": r.difficulty, "level": r.Level} for r in rows]
        data["ranked_choices"] = [{"id": k, "text": v} for k, v in RANKED_CHOICES.items()] if team else []
    return JsonResponse(data)


def edit_view(request, me, setid):
    allowed, team, owner = can_edit(me, setid)
    if not allowed:
        return fail("Only the person who submitted this set or the Qlute team can edit it.", 403)
    from moderation import takedowns
    if takedowns.is_down(setid) and not team:
        return fail("This set was taken down by the Qlute team, so it can't be edited.", 403)
    data = body(request)
    changes = {}
    for key in osz.SET_FIELDS + ("mapper",):  # can_edit: only the uploader or the team gets here
        if key in data:
            changes[key] = osz.clean(data[key], osz.OSU_KEY[key])
    if team and "ranked" in data:
        try:
            ranked = int(data["ranked"])
        except (TypeError, ValueError):
            return fail("Pick a ranked status.")
        if ranked not in RANKED_CHOICES:
            return fail("Pick a ranked status.")
        changes["ranked"] = ranked
    for key, names in (("genre", catalog.GENRE_NAMES), ("language", catalog.LANGUAGE_NAMES)):
        if key in data:
            value = data[key]
            if not isinstance(value, int) or value not in names:
                return fail(f"Pick a {key}.")
            changes[key] = value
    if "nsfw" in data:
        changes["nsfw"] = bool(data["nsfw"])
    versions = data.get("difficulties") or {}
    if not isinstance(versions, dict):
        return fail("Bad difficulty list.")
    try:
        versions = {int(k): v for k, v in versions.items() if isinstance(v, str)}
    except ValueError:
        return fail("Bad difficulty list.")
    # leave out what didn't change, so the files are only rewritten when needed
    rows = list(Beatmap.objects.filter(beatmapsetid=setid))
    if not rows:
        return fail("That beatmap set doesn't exist.", 404)

    def changed(key, value):
        if key in ("ranked", "genre", "language", "nsfw"):
            current = (lambda r: bool(r.nsfw)) if key == "nsfw" else \
                (lambda r: getattr(r, key) or catalog.UNSPECIFIED) if key in ("genre", "language") else (lambda r: r.ranked)
            return any(current(r) != value for r in rows)
        return value != (getattr(rows[0], key) or "")

    changes = {k: v for k, v in changes.items() if changed(k, v)}
    names = {r.beatmapid: r.difficulty for r in rows}
    versions = {k: v for k, v in versions.items() if k in names and osz.clean(v, "Version") != names[k]}
    if not changes and not versions:
        return JsonResponse({"ok": True, "changed": 0})
    try:
        osz.edit_set(setid, changes, versions, me.username)
    except osz.SubmitError as e:
        return fail(str(e))
    print(f"[submit] {me.username} edited set {setid}: {sorted(changes)} {len(versions)} difficulty name(s)")
    return JsonResponse({"ok": True, "changed": len(changes) + len(versions)})


def mine_view(me):
    subs = list(Submission.objects.filter(owner=me.username).order_by("-updated")[:200])
    rows = {}
    for b in Beatmap.objects.filter(beatmapsetid__in=[s.beatmapsetid for s in subs]).order_by("Level"):
        rows.setdefault(b.beatmapsetid, []).append(b)
    out = []
    for s in subs:
        diffs = rows.get(s.beatmapsetid, [])
        first = diffs[0] if diffs else None
        out.append({
            "setid": s.beatmapsetid, "title": first.title if first else "", "artist": first.artist if first else "",
            "ranked": first.ranked if first else 0, "difficulties": [d.difficulty for d in diffs],
            "background": first.backgroundpath if first else "",
            "uploaded": int(s.created.timestamp()), "updated": int(s.updated.timestamp()),
        })
    return JsonResponse({"results": out})
