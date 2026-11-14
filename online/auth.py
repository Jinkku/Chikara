"""Websocket login for the game: same credentials the HTTP API uses (Username + Password headers,
the password being the SHA-256 hash the game stores)."""
from channels.db import database_sync_to_async
from django.conf import settings

from dbview.models import User, Hashes


def scope_headers(scope):
    return {k.decode("latin1").lower(): v.decode("utf-8", "replace") for k, v in scope.get("headers", [])}


@database_sync_to_async
def authenticate(scope):
    """Returns (username, None) on success or (None, reason)."""
    h = scope_headers(scope)
    username = h.get("username", "").strip()
    password = h.get("password", "").strip()
    if not username or username in ("None", "Guest") or not password:
        return None, "Log in to use online features."
    user = User.objects.filter(username=username, password=password).first()
    if user is None or user.password != password:
        return None, "Your login is invalid. Please log in again."
    if user.restricted:
        # A timed ban may have just run out; that unrestricts the account.
        from moderation.service import active_ban, ban_message
        ban = active_ban(user.username)
        if User.objects.filter(id=user.id, restricted=True).exists():
            return None, ban_message(ban)
    if getattr(settings, "ONLINE_REQUIRE_GAME_HASH", False):
        parts = h.get("user-agent", "").split("-", 1)
        if len(parts) < 2 or not Hashes.objects.filter(hash=parts[1]).exists():
            return None, "This version of Qlute isn't supported online. Please update."
    return user.username, None


@database_sync_to_async
def restricted_login(scope):
    """For a client that can show bans live: (username, ban message, expiry unix ms or None) when the login is right
    but the account is restricted, else None."""
    h = scope_headers(scope)
    username, password = h.get("username", "").strip(), h.get("password", "").strip()
    user = User.objects.filter(username=username, password=password).first() if username and password else None
    if user is None or user.password != password or not user.restricted:
        return None
    from moderation.service import active_ban, ban_message
    ban = active_ban(user.username)
    if not User.objects.filter(id=user.id, restricted=True).exists():
        return None  # it just ran out
    expires = int(ban.expires.timestamp() * 1000) if ban and ban.expires else None
    return user.username, ban_message(ban), expires


def features(scope):
    """What the client says it understands ("Features: ban,dm,friends"); old clients send nothing."""
    return {f.strip() for f in scope_headers(scope).get("features", "").split(",") if f.strip()}


def clean(text, max_len, fallback=None):
    if not isinstance(text, str):
        return fallback
    text = "".join(c for c in text if c.isprintable()).strip()[:max_len]
    return text or fallback
