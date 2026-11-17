"""Username changes, osu!-style.

- Supporters (and the team) change their own name in settings (POST apiv2/username), at most once every
  RENAME_COOLDOWN_DAYS. Like banners, it's a supporter perk (moderation.service.has_supporter_perks).
- Old names are kept (dbview.UsernameChange) and shown on the profile as "previously known as". /user/<old name>
  still leads to the profile.
- An old name stays reserved for its owner for NAME_HOLD_DAYS: only they can take it back, nobody else can sign
  up with it or rename to it (so nobody can pose as them right after a rename).
- The team can rename anyone (rules: Names & profiles) with POST apiv2/mod/rename. Those renames skip the cooldown
  and, by default, hide the old name: it isn't shown publicly and nobody can use it again.
- Name rules (like osu!): 3-15 characters, letters, numbers, spaces, _ - [ ]; no spaces at the ends, no double
  spaces, and not both spaces and underscores. Names are compared ignoring case, and with space = underscore.

A rename rewrites the name everywhere it's stored (RENAMED below) in one transaction. Passwords don't depend on
the name. The player's open game connections are closed with a message, so they log in again with the new name.
"""
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

RENAME_COOLDOWN_DAYS = 30
NAME_HOLD_DAYS = 180
MIN_LEN, MAX_LEN = 3, 15
RESERVED = {"none", "guest", "qlute", "admin", "moderator", "system", "anti-cheat", "[anti-cheat]"}
_ALLOWED = re.compile(r"[A-Za-z0-9_\-\[\] ]+")

# (app label, model, fields): every place a player's name is stored
RENAMED = [
    ("dbview", "User", ["username"]),
    ("dbview", "Score", ["username"]),
    ("chat", "Message", ["author"]),
    ("moderation", "StaffMember", ["username", "added_by"]),
    ("moderation", "Report", ["reporter", "target", "handled_by"]),
    ("moderation", "Ban", ["username", "issued_by", "lifted_by"]),
    ("moderation", "Warning", ["username", "issued_by"]),
    ("moderation", "Notice", ["created_by"]),
    ("moderation", "CardBorder", ["created_by"]),
    ("moderation", "NewsPost", ["author", "edited_by"]),
    ("moderation", "Supporter", ["username", "granted_by"]),
    ("moderation", "SupportOrder", ["buyer", "recipient"]),
    ("online", "PrivateChatRoom", ["owner"]),
    ("online", "PrivateChatMember", ["username"]),
    ("online", "PrivateChatInvite", ["username"]),
    ("online", "OnlineSession", ["username"]),
    ("online", "MultiplayerRoom", ["host"]),
    ("online", "Friend", ["username", "friend"]),
    ("online", "DirectChat", ["low_name", "high_name"]),
    ("online", "FavoriteBeatmap", ["username"]),
    ("online", "BeatmapComment", ["username"]),
    ("online", "Notification", ["username", "actor"]),
    ("online", "MedalUnlock", ["username"]),
    ("online", "MedalBaseline", ["username"]),
    ("submissions", "Submission", ["owner", "edited_by"]),
    ("submissions", "UploadSession", ["username"]),
    ("submissions", "BeatmapClaim", ["username", "handled_by"]),
]


def key(name):
    """Two names are the same if this matches (case, and space vs underscore, don't count)."""
    return (name or "").strip().lower().replace(" ", "_")


def problem(name):
    """Why `name` can't be used as a username, or "" if its shape is fine."""
    if not name or name != name.strip():
        return "Usernames can't start or end with a space."
    if not MIN_LEN <= len(name) <= MAX_LEN:
        return f"Usernames are {MIN_LEN} to {MAX_LEN} characters."
    if not _ALLOWED.fullmatch(name):
        return "Use letters, numbers, spaces, and _ - [ ] only."
    if "  " in name:
        return "No double spaces."
    if " " in name and "_" in name:
        return "Use spaces or underscores, not both."
    if key(name) in RESERVED:
        return "That name is reserved."
    return ""


def _similar(name):
    """A filter for names equal to `name` ignoring space vs underscore (case is ignored by the database)."""
    return Q(**{"username__iexact": name}) | Q(**{"username__iexact": name.replace(" ", "_")}) | \
        Q(**{"username__iexact": name.replace("_", " ")})


def taken(name, for_user_id=None):
    """Why `name` is unavailable to this player (None = new account), or ""."""
    from dbview.models import User, UsernameChange
    k = key(name)
    other = User.objects.filter(_similar(name)).exclude(id=for_user_id or 0).values_list("username", flat=True)
    if any(key(n) == k for n in other):
        return "That name is taken."
    held = timezone.now() - timedelta(days=NAME_HOLD_DAYS)
    for row in UsernameChange.objects.filter(Q(old_name__iexact=name) | Q(old_name__iexact=name.replace(" ", "_"))
                                             | Q(old_name__iexact=name.replace("_", " "))):
        if key(row.old_name) != k:
            continue
        if row.hidden:
            return "That name can't be used."
        if row.user_id != for_user_id and row.created >= held:
            return "That name was used by another player recently."
    return ""


def history(user_id, include_hidden=False):
    from dbview.models import UsernameChange
    rows = UsernameChange.objects.filter(user_id=user_id).order_by("-created")
    return list(rows if include_hidden else rows.filter(hidden=False))


def previous_names(user_id):
    """Old names to show publicly, newest first, without the current one or repeats."""
    from dbview.models import User
    current = key(User.objects.filter(id=user_id).values_list("username", flat=True).first())
    out, seen = [], {current}
    for row in history(user_id):
        if key(row.old_name) not in seen:
            seen.add(key(row.old_name))
            out.append(row.old_name)
    return out


def next_change(user_id):
    """When this player may rename themselves again (None = now). Only their own renames count."""
    from dbview.models import UsernameChange
    last = UsernameChange.objects.filter(user_id=user_id, forced=False).order_by("-created").first()
    if last is None:
        return None
    when = last.created + timedelta(days=RENAME_COOLDOWN_DAYS)
    return when if when > timezone.now() else None


def resolve_old(name):
    """The user id an old, public name belonged to (for /user/<old name>), or None."""
    from dbview.models import UsernameChange
    row = UsernameChange.objects.filter(old_name=name, hidden=False).order_by("-created").first()
    return row.user_id if row else None


def rename(user, new, by, forced=False, hide_old=False, reason=""):
    """Rename `user` to `new` everywhere. Returns "" on success, else why not. Callers check permissions."""
    from django.apps import apps
    from dbview.models import Beatmap, User, UsernameChange
    from submissions.models import Submission
    new = new or ""
    why = problem(new)
    if why:
        return why
    old = user.username
    if new == old:
        return "That's already the name."
    why = taken(new, for_user_id=user.id)
    if why:
        return why
    with transaction.atomic():
        if User.objects.filter(id=user.id).values_list("username", flat=True).first() != old:
            return "The name changed in the meantime; reload and try again."
        # uploaded sets show the uploader as mapper: follow the rename where it still says the old name
        sets = list(Submission.objects.filter(owner=old).values_list("beatmapsetid", flat=True))
        Beatmap.objects.filter(beatmapsetid__in=sets, mapper=old).update(mapper=new)
        for app, model, fields in RENAMED:
            m = apps.get_model(app, model)
            for f in fields:
                m.objects.filter(**{f: old}).update(**{f: new})
        UsernameChange.objects.create(user_id=user.id, old_name=old, new_name=new, by=by, forced=forced,
                                      hidden=hide_old, reason=reason)
    _after_rename(user.id, old, new)
    print(f"[accounts] {by} renamed {old!r} -> {new!r}{' (forced)' if forced else ''}{' (old name hidden)' if hide_old else ''}")
    return ""


def _after_rename(user_id, old, new):
    """Caches keyed by name, and the player's open game connections (they log in again with the new name)."""
    try:
        from moderation import service
        service.supporters_changed()
        text = f"Your username is now {new}. Please log in again with your new name."
        service._tell_id(user_id, {"type": "chat.renamed", "text": text})
        service.kick_relay(user_id, text)
    except Exception as e:
        print(f"[accounts] after renaming {old} -> {new}: {e}")
