"""Site content the team manages from the admin panel: home-screen notices and card borders.

Images live in the storage folder (served by DataURL): notices in events/, card borders in cardborders/.
Uploads are opened with Pillow and re-encoded, so only real images are ever written.
"""
import os
import re
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

from Chikara.settings import DataURL, storage_root
from dbview.models import User
from .models import CardBorder, Notice

BORDER_SIZE = (230, 80)
NOTICE_MAX_SIDE = 2048
MAX_UPLOAD = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


class BadImage(ValueError):
    pass


def url_of(path):
    return f"{DataURL.rstrip('/')}/{path.lstrip('/')}"


def _folder(name):
    path = os.path.join(storage_root, name)
    os.makedirs(path, exist_ok=True)
    return path


def _open(upload):
    if upload is None:
        raise BadImage("Pick an image to upload.")
    if upload.size > MAX_UPLOAD:
        raise BadImage("That image is too big (8 MB max).")
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise BadImage("That file isn't an image we can read (use PNG or JPEG).")
    return ImageOps.exif_transpose(img)


def _save(img, folder, prefix):
    """Writes PNG when the image has transparency, else JPEG. Returns the storage-relative path."""
    rgba = img.convert("RGBA")
    transparent = rgba.getextrema()[3][0] < 255
    name = f"{prefix}-{secrets.token_hex(4)}.{'png' if transparent else 'jpg'}"
    path = os.path.join(_folder(folder), name)
    if transparent:
        rgba.save(path, "PNG", optimize=True)
    else:
        rgba.convert("RGB").save(path, "JPEG", quality=92)
    return f"{folder}/{name}"


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "image"


def _remove(path, folder):
    """Deletes a stored file, but only inside the expected folder."""
    if not path or not path.startswith(folder + "/") or "/" in path[len(folder) + 1:] or ".." in path:
        return
    try:
        os.remove(os.path.join(storage_root, path))
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- notices

def notice_json(n):
    return {"id": n.id, "image": url_of(n.image), "text": n.text, "redirect": n.redirect,
            "position": n.position, "active": n.active, "created_by": n.created_by,
            "created": int(n.created.timestamp()) if n.created else 0}


def save_notice_image(upload, text):
    img = _open(upload)
    if max(img.size) > NOTICE_MAX_SIDE:
        img.thumbnail((NOTICE_MAX_SIDE, NOTICE_MAX_SIDE), Image.LANCZOS)
    return _save(img, "events", _slug(text))


def delete_notice(n):
    _remove(n.image, "events")
    n.delete()


def game_notices():
    """The list apiv2/getnotice has always returned: [{url, text, redirect}]."""
    return [{"url": url_of(n.image), "text": n.text, "redirect": n.redirect}
            for n in Notice.objects.filter(active=True).order_by("position", "id")]


# ---------------------------------------------------------------- card borders

def border_json(b, users=None):
    j = {"id": b.id, "name": b.name, "url": url_of(b.image), "active": b.active}
    if users is not None:
        j["users"] = users
    return j


def save_border_image(upload, name):
    img = _open(upload)
    if img.size != BORDER_SIZE:
        raise BadImage(f"Card borders must be exactly {BORDER_SIZE[0]}x{BORDER_SIZE[1]} pixels; "
                       f"this one is {img.size[0]}x{img.size[1]}.")
    # Borders are drawn over the player card, so keep them PNG (with or without transparency).
    rgba = img.convert("RGBA")
    filename = f"{_slug(name)}-{secrets.token_hex(4)}.png"
    rgba.save(os.path.join(_folder("cardborders"), filename), "PNG", optimize=True)
    return f"cardborders/{filename}"


def border_users(b):
    return User.objects.filter(cardborder="/" + b.image).count()


def delete_border(b):
    """Players wearing it go back to no border."""
    User.objects.filter(cardborder="/" + b.image).update(cardborder=None)
    _remove(b.image, "cardborders")
    b.delete()
