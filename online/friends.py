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
    from Chikara.views import _player_json  # the same player fields getonline / getuser use
    names = friend_names(username)
    back = set(Friend.objects.filter(username__in=names, friend=username).values_list("username", flat=True))
    users = User.objects.filter(username__in=names, restricted=False)
    rows = []
    for u in users:
        p = _player_json(u)
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
    _, created = Friend.objects.get_or_create(username=me.username, friend=target.username)
    mutual = is_friend(target.username, me.username)
    if created:
        notify(target.id, {"type": "chat.friend", "user": me.username, "added": True, "mutual": mutual})
        from .notifications import push
        push(target.username, "friend", me.username,
             f"{me.username} added you as a friend" + (" back! You're mutual friends now." if mutual else "."),
             f"/user/{me.username}")
    return mutual, None


def remove_friend(me, name):
    Friend.objects.filter(username=me.username, friend=name).delete()


def notify(user_id, event):
    """Tells the player's open game (online chat socket) right away. Never fails the request over it."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from .chat_consumer import user_group
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(user_group(user_id), event)
    except Exception as e:
        print(f"[friends] couldn't notify user {user_id}: {e}")


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
            return JsonResponse({"ok": True, "mutual": mutual})
        remove_friend(me, parts[1])
        return JsonResponse({"ok": True})
    return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
