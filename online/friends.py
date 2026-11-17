"""Friends: apiv2/friends... (used by the game and the website).

One-way like osu!: adding someone puts them on your list; if they add you back you're mutual friends.

  GET  apiv2/friends              -> {"friends": [player + "mutual"], "followers": N}
  POST apiv2/friends/add/NAME     -> {"ok": true, "mutual": bool}
  POST apiv2/friends/remove/NAME  -> {"ok": true}

Auth is the same as apiv2/mod/...: the game's Username + Password headers, or the website's login cookies
(+ "X-Chikara: 1" for POSTs, so other sites can't post with the cookies).
"""
import urllib.parse

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from dbview.models import User
from moderation.service import request_user
from .models import Friend

MAX_FRIENDS = 500


def friend_names(username):
    return list(Friend.objects.filter(username=username).values_list("friend", flat=True))


def is_friend(username, other):
    return bool(username and other) and Friend.objects.filter(username=username, friend=other).exists()


def friends_json(username):
    from Chikara import privacy
    from Chikara.views import _player_json  # the same player fields getonline / getuser use
    names = friend_names(username)
    back = set(Friend.objects.filter(username__in=names, friend=username).values_list("username", flat=True))
    users = User.objects.filter(username__in=names, restricted=False)
    viewer = privacy.Viewer(username=username)
    rows = []
    for u in users:
        p = _player_json(u, viewer)
        p["mutual"] = u.username in back
        rows.append(p)
    rows.sort(key=lambda p: (not p["online"], p["username"].lower()))
    return rows


def add_friend(me, name):
    """Returns (mutual, error)."""
    target = User.objects.filter(username=name).first()
    if target is None:
        return False, f"There's no player called {name}."
    if target.username == me.username:
        return False, "You can't add yourself."
    if me.restricted:
        return False, "Restricted accounts can't add friends."
    if target.restricted:
        return False, f"{target.username} can't be added right now."
    from moderation.service import SUPPORTER_LIMITS, limit_for
    limit = limit_for(me.username, "friends")
    if Friend.objects.filter(username=me.username).count() >= limit:
        more = "" if limit > MAX_FRIENDS else f" (supporters can have {SUPPORTER_LIMITS['friends'][1]})"
        return False, f"You can have at most {limit} friends{more}."
    Friend.objects.get_or_create(username=me.username, friend=target.username)
    # Being added isn't announced (no website notification, no game popup); the other player sees it in their
    # friends list / followers count.
    return is_friend(target.username, me.username), None


def remove_friend(me, name):
    Friend.objects.filter(username=me.username, friend=name).delete()


@csrf_exempt
def api(request, action=""):
    parts = [urllib.parse.unquote(p) for p in action.strip("/").split("/") if p]
    write = request.method == "POST"
    me = request_user(request, write=write)
    if me is None:
        return JsonResponse({"error": 1, "reason": "Log in first."}, status=401)
    if not parts and request.method == "GET":
        return JsonResponse({"friends": friends_json(me.username),
                             "followers": Friend.objects.filter(friend=me.username).count()})
    if len(parts) == 2 and write and parts[0] in ("add", "remove"):
        if parts[0] == "add":
            mutual, err = add_friend(me, parts[1])
            if err:
                return JsonResponse({"error": 1, "reason": err}, status=400)
            if mutual:  # "Social Butterfly" counts mutual friends, for both of you
                from .medals import check
                check(me.username)
                check(parts[1])
            return JsonResponse({"ok": True, "mutual": mutual})
        remove_friend(me, parts[1])
        return JsonResponse({"ok": True})
    return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
