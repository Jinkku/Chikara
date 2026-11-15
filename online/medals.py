"""Medal unlocks: when each player first earned each medal, and which ones the game still has to pop up.

Medals are still worked out live from a player's stats (Chikara/views.py getmedals(), Chikara/MEDALS.md). This only
records the first time each one shows up as earned (online.models.MedalUnlock), so:
  * the game can show a "Medal unlocked!" popup exactly once per medal (`seen`),
  * the website gets a "medal" notification (bell + toast) the moment it's recorded,
  * profiles can say when a medal was earned.
A medal that's lost later (e.g. dropping out of the Top 100) keeps its unlock row; earning it again doesn't pop up again.

The first check for a player (MedalBaseline) records what they already had as seen, without popups or notifications.

  GET apiv2/medals/new   -> {"medals": [medal]}   unlocks the game hasn't shown yet (oldest first), now marked shown
  GET apiv2/medals       -> {"medals": [medal + "achieved" bool]}   every medal, for the logged-in player
A medal: {"id" (index), "title", "desc", "hint" (how to earn it), "achieved_at" (unix, 0 = not earned)}.
Auth is the same as apiv2/friends: the game's Username + Password headers, or the website's login cookies.
Score submissions (apiv2/ss) also check and send the new ones in their reply's "medals".
"""
from django.http import JsonResponse
from django.utils import timezone

from moderation import service as moderation
from .models import MedalBaseline, MedalUnlock


def catalog(username):
    """[(index, title, desc, hint, earned)] for every medal, in getmedals() order."""
    from Chikara import views
    extra_hints = {t: h for t, _d, h, _k in views.EXTRA_MEDALS}
    return [(i, t, d, views.MEDAL_HINTS.get(t) or extra_hints.get(t) or d, bool(g))
            for i, (t, d, g) in enumerate(views.getmedals(username))]


def _ts(dt):
    return int(dt.timestamp()) if dt else 0


def medal_json(index, title, desc, hint, achieved):
    return {"id": index, "title": title, "desc": desc, "hint": hint, "achieved_at": _ts(achieved)}


def unlock_times(username):
    """{medal index: datetime first earned}."""
    return dict(MedalUnlock.objects.filter(username=username).values_list("medal", "achieved"))


def sync(username, rows=None):
    """Records the medals `username` has earned since the last check and notifies the website about them.
    Returns the newly recorded MedalUnlock rows (none on a player's very first check, which is silent)."""
    if not username:
        return []
    from dbview.models import User
    if User.objects.filter(username=username, restricted=True).exists():
        return []  # restricted accounts don't collect medals
    rows = rows if rows is not None else catalog(username)
    have = set(MedalUnlock.objects.filter(username=username).values_list("medal", flat=True))
    first = not MedalBaseline.objects.filter(username=username).exists()
    now = timezone.now()
    new = []
    for index, title, desc, _hint, earned in rows:
        if not earned or index in have:
            continue
        row, created = MedalUnlock.objects.get_or_create(
            username=username, medal=index, defaults={"title": title[:128], "achieved": now, "seen": first})
        if created and not first:
            new.append(row)
            from .notifications import push
            push(username, "medal", "Qlute", f"Medal unlocked: {title}! {desc}", f"/user/{username}#medals")
    if first:
        MedalBaseline.objects.get_or_create(username=username)
    return new


def check(username):
    """sync() for places where medals might have just been earned (a favourite, a friend, a comment...).
    Never fails the caller."""
    try:
        sync(username)
    except Exception as e:
        print(f"[medals] couldn't check {username}: {e}")


def take_unseen(username):
    """sync(), then the unlocks the game hasn't shown yet, marked shown. Each one is handed out once even when two
    requests race (only the request whose update flips `seen` gets it)."""
    rows = catalog(username)
    sync(username, rows)
    info = {i: (t, d, h) for i, t, d, h, _e in rows}
    out = []
    for u in MedalUnlock.objects.filter(username=username, seen=False).order_by("achieved", "medal"):
        if MedalUnlock.objects.filter(id=u.id, seen=False).update(seen=True) and u.medal in info:
            title, desc, hint = info[u.medal]
            out.append(medal_json(u.medal, title, desc, hint, u.achieved))
    return out


def take_unseen_safe(username):
    try:
        return take_unseen(username)
    except Exception as e:
        print(f"[medals] couldn't check {username}: {e}")
        return []


def api(request, action=""):
    parts = [p for p in action.strip("/").split("/") if p]
    if request.method != "GET":
        return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
    me = moderation.request_user(request)
    if me is None:
        return JsonResponse({"error": 1, "reason": "Log in first."}, status=401)
    if parts == ["new"]:
        return JsonResponse({"medals": take_unseen(me.username)})
    if not parts:
        rows = catalog(me.username)
        sync(me.username, rows)
        times = unlock_times(me.username)
        return JsonResponse({"medals": [dict(medal_json(i, t, d, h, times.get(i)), achieved=e) for i, t, d, h, e in rows]})
    return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
