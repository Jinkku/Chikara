"""Moderation rules shared by the website, the game API and the online websockets.

A ban sets users.restricted while it is enforced. Timed bans run out lazily: whenever a restricted account
logs in (website, game or online), or a team member opens the admin panel, expired bans are cleared and the
account is unrestricted if nothing else is holding it. Accounts restricted by hand (no Ban row) are never
touched.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from dbview.models import User
from .models import Ban, Report, StaffMember

MAX_BAN_HOURS = 24 * 365 * 10
REPORTS_PER_HOUR = 10


# ---------------------------------------------------------------- who is asking

def _check(username, password):
    if not username or username in ("None", "Guest") or not password:
        return None
    user = User.objects.filter(username=username, password=password).first()
    if user is None or user.password != password:
        return None
    return user


def request_user(request, write=False):
    """The logged-in account behind a request, or None.

    The game sends Username + Password headers. The website sends its login cookies; for anything that
    changes data it must also send "X-Chikara: 1", which a cross-site form can't do (CSRF guard).
    """
    username = request.META.get("HTTP_USERNAME")
    if username:
        return _check(username, request.META.get("HTTP_PASSWORD", ""))
    if write and request.META.get("HTTP_X_CHIKARA") != "1":
        return None
    return _check(request.COOKIES.get("username"), request.COOKIES.get("password"))


def staff_of(username):
    if not username:
        return None
    return StaffMember.objects.filter(username=username).first()


def is_staff(username):
    return bool(username) and StaffMember.objects.filter(username=username).exists()


def is_admin(username):
    return bool(username) and StaffMember.objects.filter(username=username, role=StaffMember.ROLE_ADMIN).exists()


# ---------------------------------------------------------------- bans

def refresh(username):
    """Ends this account's expired bans and unrestricts it if no ban is left. Returns the active ban or None."""
    now = timezone.now()
    with transaction.atomic():
        expired = Ban.objects.select_for_update().filter(username=username, enforced=True, expires__lte=now)
        ended = expired.update(enforced=False)
        # The ban that ends last (permanent first) is the one the player is told about.
        active = (Ban.objects.filter(username=username, enforced=True)
                  .order_by(F("expires").desc(nulls_first=True)).first())
        lifted = bool(ended) and active is None
        if lifted:
            User.objects.filter(username=username).update(restricted=False)
    if lifted:
        notify_unrestricted(username)
    return active


def expire_all():
    names = set(Ban.objects.filter(enforced=True, expires__lte=timezone.now()).values_list("username", flat=True))
    for name in names:
        refresh(name)


def active_ban(username):
    return refresh(username) if username else None


def ban(username, reason, hours, by, report=None):
    """hours: None/0 = permanent."""
    expires = timezone.now() + timedelta(hours=hours) if hours else None
    with transaction.atomic():
        b = Ban.objects.create(username=username, reason=reason, issued_by=by, expires=expires, report=report)
        User.objects.filter(username=username).update(restricted=True)
    kick_online(username, ban_message(b))
    return b


def unban(username, by, note=""):
    now = timezone.now()
    with transaction.atomic():
        lifted = Ban.objects.filter(username=username, enforced=True).update(
            enforced=False, lifted_by=by, lifted_at=now, lift_note=note)
        User.objects.filter(username=username).update(restricted=False)
    notify_unrestricted(username)
    return lifted


def ban_message(b):
    """What the banned player sees in the game and on the website."""
    if b is None:
        return "Your account is restricted.\nYou can't submit scores or interact with the community until it's lifted."
    if b.expires is None:
        when = "This restriction is permanent."
    else:
        when = f"It ends in {time_left(b.expires)} ({b.expires.strftime('%Y-%m-%d %H:%M')} UTC)."
    return f"Your account is restricted.\nReason: {b.reason}\n{when}"


def time_left(expires):
    secs = max(0, int((expires - timezone.now()).total_seconds()))
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if secs >= size:
            n = secs // size
            return f"{n} {unit}{'' if n == 1 else 's'}"
    return "less than a minute"


def kick_online(username, text):
    """Tells a freshly banned player's game right away (it shows the ban; old games just lose online chat)."""
    _tell(username, {"type": "chat.kick", "text": text})


def notify_unrestricted(username):
    """Tells the player's game the restriction is over (games that can show bans keep a socket open for this)."""
    _tell(username, {"type": "chat.unrestricted"})


def _tell(username, event):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from online.chat_consumer import user_group
        uid = User.objects.filter(username=username).values_list("id", flat=True).first()
        layer = get_channel_layer()
        if uid is not None and layer is not None:
            async_to_sync(layer.group_send)(user_group(uid), event)
    except Exception as e:  # the ban / unban itself already happened; never fail it over chat
        print(f"[moderation] couldn't tell {username}'s game: {e}")


# ---------------------------------------------------------------- reports

def can_report(reporter):
    since = timezone.now() - timedelta(hours=1)
    return Report.objects.filter(reporter=reporter, created__gte=since).count() < REPORTS_PER_HOUR


def file_report(reporter, target, category, details, context, source):
    """Creates a report, or adds to the reporter's still-open report about the same player."""
    valid = dict(Report.CATEGORIES)
    category = category if category in valid else "other"
    existing = Report.objects.filter(reporter=reporter, target=target, status=Report.STATUS_OPEN).first()
    if existing:
        existing.category = category
        existing.details = (existing.details + "\n---\n" + details).strip()[:4000]
        if context:
            existing.context = context
        existing.save()
        return existing, False
    return Report.objects.create(reporter=reporter, target=target, category=category, details=details,
                                 context=context, source=source), True
