"""Claiming a beatmap set crawled from osu!: "this is my map".

    GET /osu/claim/<setid>   (logged in on the website) -> osu! login page
    GET /osu/callback        osu! sends the player back here. We ask osu! who they are and who made the set;
                             only when it's the same osu! account is a claim made. The Qlute team then
                             accepts it (the player becomes the set's owner, like an uploader) or declines it.

    GET  apiv2/submit/claim/<setid>         -> can I claim this set / where is my claim at
    team (apiv2/mod/...):
    GET  claims?status=pending|closed&page=
    POST claims/<id>/accept|decline {"note"}
"""
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.html import escape

from Chikara import settings
from dbview.models import Beatmap
from moderation import service as moderation

from .models import BeatmapClaim, Submission
from .osz import SUBMIT_ID_BASE

OSU = "https://osu.ppy.sh"
STATE_SALT = "qlute.osu-claim"
STATE_COOKIE = "osu_claim_state"
STATE_MAX_AGE = 600  # seconds the player has to finish logging into osu!
PAGE = 50


def configured():
    return bool(settings.osu_oauth_id and settings.osu_oauth_secret)


def redirect_uri():
    from Chikara.views import SiteURL
    return SiteURL + "/osu/callback"


def claimable(setid, me):
    """(ok, reason). Who may start a claim on this set."""
    if me is None:
        return False, "Log in to claim this beatmap."
    if me.restricted:
        return False, "Restricted accounts can't claim beatmaps."
    if setid >= SUBMIT_ID_BASE:
        return False, "This set was uploaded to Qlute, not taken from osu!."
    if not Beatmap.objects.filter(beatmapsetid=setid).exists():
        return False, "That beatmap set doesn't exist."
    sub = Submission.objects.filter(beatmapsetid=setid).first()
    if sub is not None:
        return False, "You already own this set." if sub.owner == me.username else f"This set already belongs to {sub.owner}."
    if BeatmapClaim.objects.filter(beatmapsetid=setid, username=me.username, status=BeatmapClaim.PENDING).exists():
        return False, "Your claim is waiting for the Qlute team."
    if not configured():
        return False, "Claiming isn't set up on this server yet."
    return True, ""


# ---------------------------------------------------------------- osu! OAuth

def _post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _get(path, token):
    req = urllib.request.Request(OSU + "/api/v2" + path, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def start(request, setid):
    me = moderation.request_user(request)
    ok, reason = claimable(setid, me)
    if not ok:
        return page(request, "Can't claim this map", reason, setid)
    nonce = secrets.token_urlsafe(24)
    state = signing.dumps({"u": me.username, "s": setid, "n": nonce}, salt=STATE_SALT)
    url = OSU + "/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": settings.osu_oauth_id, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": "public identify", "state": state,
    })
    resp = HttpResponseRedirect(url)
    resp.set_cookie(STATE_COOKIE, nonce, max_age=STATE_MAX_AGE, httponly=True, secure=request.is_secure(), samesite="Lax")
    return resp


def callback(request):
    try:
        state = signing.loads(request.GET.get("state", ""), salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature:
        return page(request, "That link expired", "Start the claim again from the beatmap page.")
    setid = int(state["s"])
    me = moderation.request_user(request)
    if (me is None or me.username != state["u"]
            or not secrets.compare_digest(request.COOKIES.get(STATE_COOKIE, ""), state["n"])):
        return page(request, "Something didn't match", "Log into Qlute in this browser and start the claim again.", setid)
    if request.GET.get("error"):
        return page(request, "Claim cancelled", "You didn't let Qlute see your osu! account, so nothing was claimed.", setid)
    ok, reason = claimable(setid, me)
    if not ok:
        return page(request, "Can't claim this map", reason, setid)
    try:
        token = _post_form(OSU + "/oauth/token", {
            "client_id": settings.osu_oauth_id, "client_secret": settings.osu_oauth_secret, "code": request.GET.get("code", ""),
            "grant_type": "authorization_code", "redirect_uri": redirect_uri(),
        })["access_token"]
        osu_me = _get("/me", token)
        osu_set = _get(f"/beatmapsets/{setid}", token)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(f"[claim] osu! request failed for {me.username} / set {setid}: {e}")
        return page(request, "osu! didn't answer", "We couldn't check with osu! right now. Try again in a bit.", setid)

    osu_id, creator_id = osu_me.get("id"), osu_set.get("user_id")
    osu_name, creator = osu_me.get("username", ""), osu_set.get("creator", "")
    if not osu_id or osu_id != creator_id:
        print(f"[claim] refused: {me.username} (osu! {osu_name} #{osu_id}) tried set {setid} by {creator} #{creator_id}")
        return page(request, "That's not your map",
                    f"You logged into osu! as <b>{escape(osu_name)}</b>, but this set was made by <b>{escape(creator or 'someone else')}</b>. "
                    "Only the osu! account that created a set can claim it.", setid, bad=True)
    BeatmapClaim.objects.create(beatmapsetid=setid, username=me.username, osu_user_id=osu_id,
                                osu_username=osu_name[:64], set_creator=creator[:64])
    print(f"[claim] {me.username} (osu! {osu_name} #{osu_id}) claimed set {setid}")
    resp = page(request, "Claim sent!",
                f"osu! confirmed you're <b>{escape(osu_name)}</b>, the creator of this set. "
                "The Qlute team will accept or decline your claim soon; check back on the beatmap page.", setid, good=True)
    resp.delete_cookie(STATE_COOKIE)
    return resp


def page(request, title, text, setid=None, good=False, bad=False):
    from Chikara.views import BASE_DIR, STATIC_ROOT, NOINDEX, header
    html = header(request, title=f"Qlute - {escape(title)}", robots=NOINDEX)
    back = f'<a class="claim-back" href="/beatmapset/{int(setid)}">&lsaquo; Back to the beatmap</a>' if setid else ""
    tone = "good" if good else "bad" if bad else ""
    html += f'''<div class="infoboxcontainer"><div class="infoboxtitle"><p>beatmap claim</p></div>
        <div class="infobox column verticalpadding spacebottom claim-result {tone}">
            <h1>{escape(title)}</h1><p>{text}</p>{back}
        </div></div>
        <style>
        .claim-result {{ gap: 12px; padding-top: 30px !important; padding-bottom: 30px !important; text-align: center; align-items: center; }}
        .claim-result h1 {{ margin: 0; font-size: 26px; }}
        .claim-result p {{ margin: 0; max-width: 560px; color: #ffffffcc; line-height: 1.5; }}
        .claim-result.good h1 {{ color: #9ff0c0; }} .claim-result.bad h1 {{ color: #ff9a9a; }}
        .claim-back {{ margin-top: 6px; padding: 8px 16px; border-radius: 999px; background: #f3baff; color: #221E27 !important; font-weight: bold; }}
        </style>'''
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


# ---------------------------------------------------------------- JSON

def status_view(me, setid):
    ok, reason = claimable(setid, me)
    mine = BeatmapClaim.objects.filter(beatmapsetid=setid, username=me.username).order_by("-created").first() if me else None
    sub = Submission.objects.filter(beatmapsetid=setid).first()
    return JsonResponse({
        "can_claim": ok, "reason": reason, "osu_set": setid < SUBMIT_ID_BASE, "owner": sub.owner if sub else "",
        "mine": {"status": mine.status, "note": mine.note, "created": int(mine.created.timestamp())} if mine else None,
    })


def claim_json(c):
    first = Beatmap.objects.filter(beatmapsetid=c.beatmapsetid).first()
    return {
        "id": c.id, "setid": c.beatmapsetid, "username": c.username, "osu_user_id": c.osu_user_id,
        "osu_username": c.osu_username, "set_creator": c.set_creator, "status": c.status,
        "created": int(c.created.timestamp()), "handled_by": c.handled_by,
        "handled_at": int(c.handled_at.timestamp()) if c.handled_at else 0, "note": c.note,
        "title": f"{first.artist} - {first.title}" if first else f"Set {c.beatmapsetid}",
        "background": first.backgroundpath if first else "",
        "owner": getattr(Submission.objects.filter(beatmapsetid=c.beatmapsetid).first(), "owner", ""),
    }


def claims_view(request, me, staff, args):
    status = request.GET.get("status") or "pending"
    try:
        pg = max(0, int(request.GET.get("page") or 0))
    except ValueError:
        pg = 0
    q = BeatmapClaim.objects.filter(status=BeatmapClaim.PENDING) if status == "pending" else \
        BeatmapClaim.objects.exclude(status=BeatmapClaim.PENDING)
    q = q.order_by("created" if status == "pending" else "-handled_at")
    rows = list(q[pg * PAGE:(pg + 1) * PAGE])
    return JsonResponse({"results": [claim_json(c) for c in rows], "page_size": PAGE,
                         "pending": BeatmapClaim.objects.filter(status=BeatmapClaim.PENDING).count()})


def claims_edit_view(request, me, staff, args):
    if len(args) != 2 or not args[0].isdigit() or args[1] not in ("accept", "decline"):
        return JsonResponse({"error": "Unknown action."}, status=404)
    c = BeatmapClaim.objects.filter(id=int(args[0])).first()
    if c is None:
        return JsonResponse({"error": "That claim doesn't exist."}, status=404)
    if c.status != BeatmapClaim.PENDING:
        return JsonResponse({"error": f"That claim was already {c.status}."}, status=400)
    try:
        note = str(json.loads(request.body or b"{}").get("note") or "")[:500].strip()
    except (ValueError, AttributeError):
        note = ""
    now = timezone.now()
    if args[1] == "accept":
        sub = Submission.objects.filter(beatmapsetid=c.beatmapsetid).first()
        if sub is not None and sub.owner != c.username:
            return JsonResponse({"error": f"This set already belongs to {sub.owner}."}, status=400)
        if sub is None:
            Submission.objects.create(beatmapsetid=c.beatmapsetid, owner=c.username, filename="")
        c.status = BeatmapClaim.ACCEPTED
        # nobody else can have it now
        BeatmapClaim.objects.filter(beatmapsetid=c.beatmapsetid, status=BeatmapClaim.PENDING).exclude(id=c.id).update(
            status=BeatmapClaim.DECLINED, handled_by=me.username, handled_at=now, note="Another claim was accepted.")
    else:
        c.status = BeatmapClaim.DECLINED
    c.handled_by, c.handled_at, c.note = me.username, now, note
    c.save()
    print(f"[claim] {me.username} {c.status} claim #{c.id}: {c.username} -> set {c.beatmapsetid}")
    return JsonResponse({"ok": True, "claim": claim_json(c)})
