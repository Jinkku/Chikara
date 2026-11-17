"""Presence privacy: who may see that a player is online, what they're playing, and when they were last on.

Settings (users table, set at apiv2/privacy from the website's settings page):
  appear_offline         nobody else sees them online: no dot, no "Playing ...", no "last seen", not in online lists
  hide_activity          others see them as "Online", but not what they're playing
  presence_friends_only  only the people on their friends list (people they added) see any of it

Network compatibility: to anyone who may not see it, a hidden player looks exactly like an offline player
(online false, status "", last_seen 0, left out of online lists), so every API / websocket message keeps its
shape and older game builds work unchanged. The player always sees themselves, and the admin panel sees all.
"""
from django.db.models import Q

_UNSET = object()
PRIVATE = Q(appear_offline=True) | Q(hide_activity=True) | Q(presence_friends_only=True)


def is_private(u):
    return bool(u.appear_offline or u.hide_activity or u.presence_friends_only)


class Viewer:
    """Who is looking. Built from a request (game headers or website login cookies) or a known username.
    The login is only checked the first time a private player actually needs it."""

    def __init__(self, request=None, username=_UNSET):
        self._request = request
        self._name = username
        self._added_me = None

    @property
    def name(self):
        if self._name is _UNSET:
            from moderation.service import request_user
            u = request_user(self._request) if self._request is not None else None
            self._name = u.username if u else None
        return self._name

    def added_me(self):
        """Players who have this viewer on their friends list."""
        if self._added_me is None:
            from online.models import Friend
            self._added_me = (set(Friend.objects.filter(friend=self.name).values_list("username", flat=True))
                              if self.name else set())
        return self._added_me

    def sees_online(self, u):
        if not (u.appear_offline or u.presence_friends_only):
            return True
        if self.name and self.name == u.username:
            return True
        if u.appear_offline:
            return False
        return u.username in self.added_me()

    def sees_activity(self, u):
        if not self.sees_online(u):
            return False
        return not u.hide_activity or (self.name is not None and self.name == u.username)


NOBODY = Viewer(username=None)


def presence(u, viewer, now, window):
    """(online, status, last_seen) of player `u` as `viewer` may see it; hidden = (False, "", 0)."""
    viewer = viewer or NOBODY
    if not viewer.sees_online(u):
        return False, "", 0
    online = u.stattime is not None and now - u.stattime <= window
    status = (u.status or "") if online and viewer.sees_activity(u) else ""
    return online, status, u.stattime or 0


def visible(users, viewer):
    """The players in `users` that `viewer` may see online (for online lists)."""
    viewer = viewer or NOBODY
    return [u for u in users if viewer.sees_online(u)]


# ---------------------------------------------------------------- chat websocket (online/chat_consumer.py)

def visible_names(names, viewer_name):
    """Usernames from an online list that `viewer_name` may see."""
    from dbview.models import User
    names = list(names)
    hidden = User.objects.filter(username__in=names).filter(Q(appear_offline=True) | Q(presence_friends_only=True))
    if not hidden.exists():
        return names
    v = Viewer(username=viewer_name)
    drop = {u.username for u in hidden.only("username", "appear_offline", "presence_friends_only") if not v.sees_online(u)}
    return [n for n in names if n not in drop]


def is_hidden_name(username):
    from dbview.models import User
    return User.objects.filter(username=username).filter(Q(appear_offline=True) | Q(presence_friends_only=True)).exists()


def may_see_name(username, viewer_name):
    from dbview.models import User
    u = User.objects.filter(username=username).only("username", "appear_offline", "presence_friends_only").first()
    return u is None or Viewer(username=viewer_name).sees_online(u)


def visible_q(viewer):
    """A filter for querysets of players: only those `viewer` may see online."""
    viewer = viewer or NOBODY
    q = ~Q(appear_offline=True) & (~Q(presence_friends_only=True) | Q(username__in=list(viewer.added_me())))
    return q | Q(username=viewer.name) if viewer.name else q
