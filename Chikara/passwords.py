"""Password storage for Qlute accounts.

The game (and the website's login cookie) send SHA-256(password) as hex. We used to store that hex as is,
which is unsalted. Now we store a salted, slow Django hash *of that SHA-256 hex*
("pbkdf2_sha256$<iterations>$<salt>$<hash>"), so the game keeps working unchanged.

Old rows still holding a bare 64-char SHA-256 hex still log in; the website then asks the player to pick a new
password, and saving it stores the salted form (see change_password in Chikara/views.py).
"""
import hashlib
import hmac
from collections import OrderedDict
from threading import Lock

from django.contrib.auth.hashers import check_password, make_password

from dbview.models import User

# The slow hash runs once per (account hash, credential) per process; after that a success is remembered here,
# so pages that check the login cookie several times per request don't each pay for PBKDF2.
_CACHE_SIZE = 4096
_verified = OrderedDict()
_lock = Lock()


def prehash(plain):
    """What the game sends: SHA-256 hex of the typed password."""
    return hashlib.sha256((plain or "").encode("utf-8")).hexdigest()


def is_legacy(stored):
    """True for the old unsalted SHA-256 hex."""
    return bool(stored) and "$" not in stored


def make(sha_hex):
    """The value to store in users.password for this SHA-256 hex."""
    return make_password(sha_hex.strip().lower())


def _cache_key(stored, sha_hex):
    return hashlib.sha256(f"{stored}\0{sha_hex}".encode("utf-8")).digest()


def verify(stored, sha_hex):
    if not stored or not sha_hex:
        return False
    sha_hex = sha_hex.strip().lower()
    if is_legacy(stored):
        return hmac.compare_digest(stored.lower().encode("utf-8"), sha_hex.encode("utf-8"))
    key = _cache_key(stored, sha_hex)
    with _lock:
        if key in _verified:
            _verified.move_to_end(key)
            return True
    if not check_password(sha_hex, stored):
        return False
    with _lock:
        _verified[key] = True
        while len(_verified) > _CACHE_SIZE:
            _verified.popitem(last=False)
    return True


def user_for(username, sha_hex):
    """The User these credentials belong to, or None."""
    if not username or username in ("None", "Guest") or not sha_hex:
        return None
    user = User.objects.filter(username=username).first()
    if user is None or not verify(user.password, sha_hex):
        return None
    return user
