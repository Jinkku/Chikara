"""Websocket login for the game: same credentials the HTTP API uses (Username + Password headers,
the password being the SHA-256 hash the game stores; checked against the salted hash, Chikara/passwords.py)."""
import urllib.parse

from channels.db import database_sync_to_async
from django.http.cookie import parse_cookie
from django.conf import settings
from Chikara.settings import SiteURL

from Chikara import passwords
from dbview.models import User, Hashes


def scope_headers(scope):
    return {k.decode("latin1").lower(): v.decode("utf-8", "replace") for k, v in scope.get("headers", [])}


WEB_FEATURES = {"ban", "dm", "friends"}


def same_site(h):
    """True when a browser opened this socket from one of our own pages (cookie logins only count then,
    so another site can't open a chat socket with a visitor's cookies)."""
    origin = urllib.parse.urlsplit(h.get("origin", ""))
    if not origin.netloc:
        return False
    return origin.netloc.lower() in {h.get("host", "").lower(), urllib.parse.urlsplit(SiteURL).netloc.lower()}


def credentials(scope):
    """(username, password hash, from the website). The game sends Username + Password headers;
    the website's chat page sends its login cookies instead."""
    h = scope_headers(scope)
    username = h.get("username", "").strip()
    if username:
        return username, h.get("password", "").strip(), False
    if not same_site(h):
        return "", "", False
    cookies = parse_cookie(h.get("cookie", ""))
    return cookies.get("username", "").strip(), cookies.get("password", "").strip(), True


def is_web(scope):
    return credentials(scope)[2]


@database_sync_to_async
def authenticate(scope):
    """Returns (username, None) on success or (None, reason)."""
    h = scope_headers(scope)
    username, password, web = credentials(scope)
    if not username or username in ("None", "Guest") or not password:
        return None, "Log in to use online features."
    user = passwords.user_for(username, password)
    if user is None:
        return None, "Your login is invalid. Please log in again."
    if user.restricted:
        # A timed ban may have just run out; that unrestricts the account.
        from moderation.service import active_ban, ban_message
        ban = active_ban(user.username)
        if User.objects.filter(id=user.id, restricted=True).exists():
            return None, ban_message(ban)
    if getattr(settings, "ONLINE_REQUIRE_GAME_HASH", False) and not web:
        parts = h.get("user-agent", "").split("-", 1)
        if len(parts) < 2 or not Hashes.objects.filter(hash=parts[1]).exists():
            return None, "This version of Qlute isn't supported online. Please update."
    return user.username, None


@database_sync_to_async
def restricted_login(scope):
    """For a client that can show bans live: (username, ban message, expiry unix ms or None) when the login is right
    but the account is restricted, else None."""
    username, password, _ = credentials(scope)
    user = passwords.user_for(username, password)
    if user is None or not user.restricted:
        return None
    from moderation.service import active_ban, ban_message
    ban = active_ban(user.username)
    if not User.objects.filter(id=user.id, restricted=True).exists():
        return None  # it just ran out
    expires = int(ban.expires.timestamp() * 1000) if ban and ban.expires else None
    return user.username, ban_message(ban), expires


def features(scope):
    """What the client says it understands ("Features: ban,dm,friends"); old clients send nothing.
    The website's chat page understands all of those."""
    if is_web(scope):
        return set(WEB_FEATURES)
    return {f.strip() for f in scope_headers(scope).get("features", "").split(",") if f.strip()}


def clean(text, max_len, fallback=None):
    if not isinstance(text, str):
        return fallback
    text = "".join(c for c in text if c.isprintable()).strip()[:max_len]
    return text or fallback
