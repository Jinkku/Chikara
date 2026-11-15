"""Favourites and comments on beatmap sets (website beatmap page + profile, the game's beatmap info + profile).

  GET  apiv2/favorites?user=NAME&page=N   -> {"username", "count", "sets": [catalog set]}  (no user: yourself)
  GET  apiv2/favorites/SETID              -> {"count": N, "favorited": bool}  (favorited only when logged in)
  POST apiv2/favorites/add/SETID          -> {"ok": true, "favorited": true, "count": N}
  POST apiv2/favorites/remove/SETID       -> {"ok": true, "favorited": false, "count": N}

  GET  apiv2/comments/SETID?page=N        -> {"total": N, "page": N, "per_page": N, "comments": [comment]}
  POST apiv2/comments/SETID               -> {"ok": true, "comment": comment}   body: JSON or form {text, beatmapid?}
  POST apiv2/comments/delete/ID           -> {"ok": true}   (the author, or the Qlute team)

A comment: {"id", "username", "pfp", "text", "created" (unix), "beatmapid", "can_delete"}.
Auth is the same as apiv2/friends: the game's Username + Password headers, or the website's login cookies
(+ "X-Chikara: 1" for POSTs).
"""
import json
import urllib.parse
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from dbview.models import Beatmap, User
from moderation import service as moderation
from .models import BeatmapComment, FavoriteBeatmap

FAVORITES_PER_PAGE = 50
COMMENTS_PER_PAGE = 30
MAX_COMMENT = 1000
MAX_FAVORITES = 2000
COMMENT_GAP = timedelta(seconds=10)  # at most one comment per 10 seconds...
COMMENTS_PER_HOUR = 30               # ...and 30 an hour


def _error(reason, status=400):
    return JsonResponse({"error": 1, "reason": reason}, status=status)


def _int(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _set_exists(setid):
    return Beatmap.objects.filter(beatmapsetid=setid).exists()


def favorite_count(setid):
    return FavoriteBeatmap.objects.filter(beatmapsetid=setid).count()


# ---------------------------------------------------------------- favourites

def add_favorite_info(sets, username=None):
    """Give each apiv2/search-shaped set its "favourite_count" and "favorited" (by `username`), in two queries."""
    from django.db.models import Count
    ids = [st["id"] for st in sets]
    counts = dict(FavoriteBeatmap.objects.filter(beatmapsetid__in=ids).values("beatmapsetid")
                  .annotate(n=Count("id")).values_list("beatmapsetid", "n"))
    mine = set(FavoriteBeatmap.objects.filter(username=username, beatmapsetid__in=ids)
               .values_list("beatmapsetid", flat=True)) if username else set()
    for st in sets:
        st["favourite_count"] = counts.get(st["id"], 0)
        st["favorited"] = st["id"] in mine
    return sets

def favorite_sets(username, page=0):
    """The sets `username` favourited, newest favourite first, in apiv2/search's card shape."""
    from Chikara.catalog import set_json
    ids = list(FavoriteBeatmap.objects.filter(username=username).order_by("-created", "-id")
               .values_list("beatmapsetid", flat=True)[page * FAVORITES_PER_PAGE:(page + 1) * FAVORITES_PER_PAGE])
    diffs = {}
    for row in Beatmap.objects.filter(beatmapsetid__in=ids).order_by("Level", "notecount").values():
        diffs.setdefault(row["beatmapsetid"], []).append(row)
    return [set_json(diffs[i]) for i in ids if i in diffs]  # sets removed from the server drop out


def _favorites(request, parts, me, write):
    from Chikara.catalog import add_mapper_user
    if not parts:  # someone's list
        name = (request.GET.get("user") or "").strip() or (me.username if me else "")
        if not name:
            return _error("Log in first, or say whose favourites (?user=NAME).", 401)
        owner = User.objects.filter(username=name).first()
        if owner is None:
            return _error(f"There's no player called {name}.", 404)
        if owner.restricted and not (me and (me.username == owner.username or moderation.is_staff(me.username))):
            return JsonResponse({"username": owner.username, "count": 0, "sets": []})
        page = max(0, _int(request.GET.get("page"), 0))
        return JsonResponse({
            "username": owner.username,
            "count": FavoriteBeatmap.objects.filter(username=owner.username).count(),
            "sets": add_mapper_user(add_favorite_info(favorite_sets(owner.username, page), me.username if me else None)),
        })

    if len(parts) == 1 and not write:  # one set's count (+ whether you favourited it)
        setid = _int(parts[0])
        if setid is None:
            return _error("Unknown beatmap set.", 404)
        mine = bool(me) and FavoriteBeatmap.objects.filter(username=me.username, beatmapsetid=setid).exists()
        return JsonResponse({"count": favorite_count(setid), "favorited": mine})

    if len(parts) == 2 and write and parts[0] in ("add", "remove"):
        if me is None:
            return _error("Log in to favourite beatmaps.", 401)
        setid = _int(parts[1])
        if setid is None or not _set_exists(setid):
            return _error("That beatmap set isn't on Qlute.", 404)
        if parts[0] == "add":
            if me.restricted:
                return _error("Restricted accounts can't favourite beatmaps.", 403)
            limit = moderation.limit_for(me.username, "favorites")
            if FavoriteBeatmap.objects.filter(username=me.username).count() >= limit:
                more = "" if limit > MAX_FAVORITES else f" (supporters can have {moderation.SUPPORTER_LIMITS['favorites'][1]})"
                return _error(f"You can have at most {limit} favourites{more}.")
            FavoriteBeatmap.objects.get_or_create(username=me.username, beatmapsetid=setid)
        else:
            FavoriteBeatmap.objects.filter(username=me.username, beatmapsetid=setid).delete()
        return JsonResponse({"ok": True, "favorited": parts[0] == "add", "count": favorite_count(setid)})

    return _error("Unknown request.", 404)


# ---------------------------------------------------------------- comments

def comment_json(c, me=None, pictures=None):
    from Chikara.views import _pfp_url
    pfp = (pictures or {}).get(c.username)
    if pfp is None:
        pfp = _pfp_url(User.objects.filter(username=c.username).values_list("pfppath", flat=True).first())
    return {
        "id": c.id,
        "username": c.username,
        "pfp": pfp,
        "text": c.text,
        "created": int(c.created.timestamp()),
        "beatmapid": c.beatmapid,
        "can_delete": bool(me) and (me.username == c.username or moderation.is_staff(me.username)),
        "supporter": moderation.is_supporter(c.username),
    }


def _body(request):
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body or b"{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    return request.POST


def clean_text(text):
    """Trims, unifies newlines and squeezes long runs of blank lines."""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, blank = [], 0
    for line in lines:
        line = line.rstrip()
        blank = blank + 1 if not line else 0
        if blank <= 1:
            out.append(line)
    return "\n".join(out).strip()


def post_comment(me, setid, text, beatmapid=None):
    """Returns (comment, error)."""
    if me.restricted:
        return None, "Restricted accounts can't comment."
    text = clean_text(text)
    if not text:
        return None, "Write something first."
    if len(text) > MAX_COMMENT:
        return None, f"Comments can be at most {MAX_COMMENT} characters."
    if not _set_exists(setid):
        return None, "That beatmap set isn't on Qlute."
    now = timezone.now()
    mine = BeatmapComment.objects.filter(username=me.username)
    if mine.filter(created__gt=now - COMMENT_GAP).exists():
        return None, "You're commenting too fast. Wait a few seconds."
    if mine.filter(created__gt=now - timedelta(hours=1)).count() >= COMMENTS_PER_HOUR:
        return None, "You've posted a lot of comments this hour. Try again later."
    if beatmapid is not None and not Beatmap.objects.filter(beatmapsetid=setid, beatmapid=beatmapid).exists():
        beatmapid = None
    comment = BeatmapComment.objects.create(beatmapsetid=setid, beatmapid=beatmapid, username=me.username, text=text)
    _notify_owner(me.username, setid, text)
    return comment, None


def _notify_owner(author, setid, text):
    """Tells whoever uploaded (or claimed) the set that it got a comment."""
    from submissions.models import Submission
    from .notifications import push
    owner = Submission.objects.filter(beatmapsetid=setid).values_list("owner", flat=True).first()
    if owner:
        title = Beatmap.objects.filter(beatmapsetid=setid).values_list("title", flat=True).first() or f"set #{setid}"
        snippet = " ".join(text.split())
        snippet = snippet if len(snippet) <= 80 else snippet[:79] + "…"
        push(owner, "comment", author, f'{author} commented on {title}: "{snippet}"', f"/beatmapset/{setid}#bm-comments-section")


def _comments(request, parts, me, write):
    if len(parts) == 2 and parts[0] == "delete" and write:
        if me is None:
            return _error("Log in first.", 401)
        c = BeatmapComment.objects.filter(id=_int(parts[1], -1)).first()
        if c is None:
            return _error("That comment is already gone.", 404)
        if c.username != me.username and not moderation.is_staff(me.username):
            return _error("You can only delete your own comments.", 403)
        c.delete()
        return JsonResponse({"ok": True})

    setid = _int(parts[0]) if len(parts) == 1 else None
    if setid is None:
        return _error("Unknown request.", 404)

    if write:
        if me is None:
            return _error("Log in to comment.", 401)
        data = _body(request)
        c, err = post_comment(me, setid, data.get("text"), _int(data.get("beatmapid")))
        if err:
            return _error(err)
        return JsonResponse({"ok": True, "comment": comment_json(c, me)})

    from Chikara.views import _pfp_url
    page = max(0, _int(request.GET.get("page"), 0))
    # Comments from accounts that are restricted now are hidden, like their profiles. Two queries on purpose:
    # a subquery on `users` compares usernames across tables with different collations, which MySQL refuses
    # ("Illegal mix of collations"); plain value lists take the column's own collation.
    rows = BeatmapComment.objects.filter(beatmapsetid=setid)
    authors = list(rows.values_list("username", flat=True).distinct())
    hidden = list(User.objects.filter(username__in=authors, restricted=True).values_list("username", flat=True))
    if hidden:
        rows = rows.exclude(username__in=hidden)
    total = rows.count()
    rows = list(rows.order_by("-created", "-id")[page * COMMENTS_PER_PAGE:(page + 1) * COMMENTS_PER_PAGE])
    pictures = {u: _pfp_url(p) for u, p in User.objects.filter(username__in={c.username for c in rows})
                .values_list("username", "pfppath")}
    return JsonResponse({
        "total": total,
        "page": page,
        "per_page": COMMENTS_PER_PAGE,
        "comments": [comment_json(c, me, pictures) for c in rows],
    })


@csrf_exempt
def api(request, kind, action=""):
    parts = [urllib.parse.unquote(p) for p in action.strip("/").split("/") if p]
    write = request.method == "POST"
    me = moderation.request_user(request, write=write)
    if kind == "favorites":
        return _favorites(request, parts, me, write)
    return _comments(request, parts, me, write)
