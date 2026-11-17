import os
import re
import secrets
import urllib.parse

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponse
from django.utils.html import escape
from PIL import Image, ImageOps, UnidentifiedImageError

from Chikara.settings import DataURL, NoProfilePictureURL, SUPPORT_URL, storage_root
from Chikara.views import BASE_DIR, STATIC_ROOT, _banner_url as banner_url, _pfp_url, checklogin, header
from dbview.models import User
from moderation import service as moderation
from moderation.models import CardBorder


def usersettings(request):
    username = request.COOKIES.get('username')
    if checklogin(username, request.COOKIES.get('password'))[0]:
        user = User.objects.filter(username=username).first()
        html = header(request, title="Qlute - User settings", robots="noindex, nofollow", customhead="""
    <link rel="stylesheet" href="/static/css/usersettings.css?v=13">
    <script src="/static/script/usersettings.js?v=14"></script>""") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/usersettings.html").read() \
            .replace("{avatar}", escape(_pfp_url(user.pfppath if user else None))) \
            .replace("{banner}", escape(banner_url(user.bannerpath if user else None))) \
            .replace("{bannerperk}", banner_perk_html(user)) \
            .replace("{countryblock}", country_html(user)) \
            .replace("{privacyblock}", privacy_html(user)) \
            .replace("{usernameblock}", username_html(user)) \
            .replace("{borderperks}", "1" if user and moderation.has_supporter_perks(user.username) else "") \
            .replace("{bannerlocked}", "" if user and moderation.has_supporter_perks(user.username) else "1") \
            .replace("{username}", escape(username)) \
            .replace("{cardborder}", escape((user.cardborder or "") if user else "")) \
            .replace("{profileurl}", "/user/" + escape(urllib.parse.quote(username))) \
            .replace("{dataurl}", escape(DataURL.rstrip("/")))
        return HttpResponse(html)
    else:
        return HttpResponseForbidden("Please login...",)


def country_html(user):
    """Settings: your country, where you've played from, and which countries you may switch to (Chikara/countries.py)."""
    from Chikara import countries
    if user is None:
        return ""
    if countries.name(user.country):
        since = f" since {user.country_set.strftime('%-d %B %Y')}" if user.country_set else ""
        h = (f'<p class="country-now">{countries.flag(user.country, "lg")}<b>{escape(countries.name(user.country))}</b>'
             f'<span class="avatar-rules">{since}</span></p>')
    else:
        h = '<p class="country-now"><b>Not set yet</b> <span class="avatar-rules">it fills in by itself the next time you play or visit the site</span></p>'
    opts = countries.options(user)
    if opts:
        h += '<ul class="country-list">'
        for o in opts:
            act = (f'<button type="button" class="avatar-btn country-switch" data-country="{o["code"]}">Switch to {escape(o["name"])}</button>'
                   if o["ok"] else f'<span class="avatar-rules">{escape(o["reason"])}</span>')
            h += (f'<li>{countries.flag(o["code"])}<span class="country-name">{escape(o["name"])}</span>'
                  f'<span class="avatar-rules">played from here on {o["days"]} day{"s" if o["days"] != 1 else ""}</span>{act}</li>')
        h += '</ul>'
    h += (f'<p class="avatar-rules">Your country is set from where you play. Moved? You can switch to another country once you\'ve '
          f'played from there for {countries.CHANGE_AFTER_DAYS // 30} months (on most of the days you played, and recently), and at most '
          f'once every {countries.CHANGE_AFTER_DAYS // 30} months. If something\'s wrong, ask the Qlute team.</p>'
          '<p class="avatar-status" id="country-status"></p>')
    return h


PRIVACY_OPTIONS = [  # (users field, title, description) shown as switches under Privacy, saved at apiv2/privacy
    ("appear_offline", "Appear offline",
     "Nobody sees you online, what you're playing, or when you were last on. You can still play and chat as usual."),
    ("hide_activity", "Hide what I'm playing",
     "People see that you're online, but not the song you're playing."),
    ("presence_friends_only", "Only friends see when I'm online",
     "Only the people on your friends list see that you're online, what you're playing and when you were last on."),
    ("hide_country", "Hide my country",
     "Your flag won't show on your profile or in the rankings, and you won't be counted in the country ranking."),
]
PRESENCE_FIELDS = {"appear_offline", "hide_activity", "presence_friends_only"}


def username_html(user):
    """Settings: change your username (Chikara/accounts.py), with the names you had before."""
    from Chikara import accounts
    if user is None:
        return ""
    wait = accounts.next_change(user.id)
    perk = moderation.has_supporter_perks(user.username)
    if perk:
        h = '<p class="banner-perk on">&#9829; Supporter perk &middot; thank you for supporting Qlute!</p>'
    else:
        h = (f'<p class="banner-perk">&#9829; Changing your username is a supporter perk. '
             f'<a href="{escape(SUPPORT_URL)}" target="_blank" rel="noopener">Become a supporter</a></p>')
    h += '<div class="username-row">'
    if user.restricted:
        h += '<p class="avatar-rules">Restricted accounts can\'t change their name.</p>'
    elif not perk:
        h += f'<input type="text" class="username-input" value="{escape(user.username)}" disabled aria-label="Username">'
    elif wait:
        h += (f'<input type="text" class="username-input" value="{escape(user.username)}" disabled>'
              f'<p class="avatar-rules">You can change your name again from {wait.strftime("%-d %B %Y")}.</p>')
    else:
        h += (f'<input type="text" class="username-input" id="username-new" value="{escape(user.username)}" '
              f'maxlength="{accounts.MAX_LEN}" autocomplete="off" spellcheck="false" aria-label="New username">'
              '<button type="button" class="avatar-btn" id="username-save">Change name</button>')
    h += '</div>'
    old = accounts.previous_names(user.id)
    if old:
        h += f'<p class="avatar-rules">Previously known as: {escape(", ".join(old))}</p>'
    h += (f'<p class="avatar-rules">{accounts.MIN_LEN} to {accounts.MAX_LEN} characters: letters, numbers, spaces, and _ - [ ]. '
          f'You can change it once every {accounts.RENAME_COOLDOWN_DAYS} days. Your old name shows on your profile, and stays '
          f'yours for {accounts.NAME_HOLD_DAYS // 30} months, so nobody else can take it. After changing it, log in to the game '
          'with the new name.</p><p class="avatar-status" id="username-status"></p>')
    return h


def username(request):
    """POST apiv2/username {"username": new}: rename yourself (Chikara/accounts.py). Sets the new login cookie."""
    import json
    from Chikara import accounts
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their name."}, status=403)
    if not moderation.has_supporter_perks(user.username):
        return JsonResponse({"error": "Changing your username is a supporter perk."}, status=403)
    wait = accounts.next_change(user.id)
    if wait:
        return JsonResponse({"error": f"You can change your name again from {wait.strftime('%-d %B %Y')}."}, status=403)
    try:
        new = str(json.loads(request.body or b"{}").get("username") or "")
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Couldn't read that."}, status=400)
    why = accounts.rename(user, new, by=user.username)
    if why:
        return JsonResponse({"error": why}, status=400)
    response = JsonResponse({"ok": True, "username": new, "profile": f"/user/{user.id}"})
    if request.COOKIES.get("username"):
        response.set_cookie("username", new, max_age=31536000)  # the website login is the name + password cookies
    return response


def privacy_html(user):
    """Settings: privacy switches (Chikara/privacy.py, countries.py)."""
    if user is None:
        return ""
    h = ""
    for field, title, desc in PRIVACY_OPTIONS:
        h += (f'<label class="privacy-option" for="privacy-{field}">'
              f'<span class="privacy-text"><span class="privacy-title">{escape(title)}</span>'
              f'<span class="avatar-rules">{escape(desc)}</span></span>'
              f'<input type="checkbox" class="toggle" role="switch" id="privacy-{field}" data-setting="{field}"'
              + (' checked' if getattr(user, field) else '') + '></label>')
    return h + ('<p class="avatar-rules">The Qlute team can still see all of this. Your friends list is the people you\'ve added.</p>'
                '<p class="avatar-status" id="privacy-status"></p>')


def privacy(request):
    """POST apiv2/privacy {"appear_offline": true, ...}: change any of the privacy switches (PRIVACY_OPTIONS)."""
    import json
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "Couldn't read that."}, status=400)
    fields = {f for f, _, _ in PRIVACY_OPTIONS}
    change = {k: v is True for k, v in data.items() if k in fields}
    if not change:
        return JsonResponse({"error": "Nothing to change."}, status=400)
    User.objects.filter(id=user.id).update(**change)
    if PRESENCE_FIELDS & change.keys():
        _refresh_chat_presence(user.username)
    return JsonResponse({"ok": True, **change})


def _refresh_chat_presence(username):
    """Tell everyone in online chat about this player again, so the new privacy settings apply right away
    (online/chat_consumer.py: people who may no longer see them get "online": false)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from online.chat_consumer import PRESENCE_GROUP, is_online
        if is_online(username):
            async_to_sync(get_channel_layer().group_send)(PRESENCE_GROUP, {
                "type": "chat.presence", "user": username, "online": True, "private": True, "refresh": True})
    except Exception:
        import sentry_sdk
        sentry_sdk.capture_exception()


def country(request):
    """POST apiv2/country {"country": "XX"}: switch your country, if your history there allows it (Chikara/countries.py).
    POST apiv2/country {"hide": true|false}: hide or show your country to other players."""
    import json
    from Chikara import countries
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "Couldn't read that."}, status=400)
    if "hide" in data:  # privacy is allowed for everyone, restricted or not
        hide = data["hide"] is True
        User.objects.filter(id=user.id).update(hide_country=hide)
        return JsonResponse({"ok": True, "hide": hide})
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their country."}, status=403)
    code = str(data.get("country") or "").upper()
    ok, why = countries.can_change(user, code)
    if not ok:
        return JsonResponse({"error": why}, status=403)
    countries.set_country(user.id, code)
    return JsonResponse({"ok": True, "country": code, "name": countries.name(code)})


def banner_perk_html(user):
    """The line above the banner picker: a thank-you for supporters, the way to unlock it for everyone else."""
    from moderation.models import Supporter
    if user is None:
        return ""
    if moderation.has_supporter_perks(user.username):
        row = Supporter.objects.filter(username=user.username).first()
        if row is not None and row.active():
            until = "forever" if row.expires is None else "until " + row.expires.strftime("%-d %B %Y")
            return f'<p class="banner-perk on">&#9829; Supporter perk &middot; thank you for supporting Qlute! (supporter {until})</p>'
        return '<p class="banner-perk on">&#9829; Supporter perk (included for the Qlute team)</p>'
    saved = " Your banner is saved and comes back as soon as you're a supporter again." if user.bannerpath else ""
    return (f'<p class="banner-perk">&#9829; Profile banners are a supporter perk.{saved} '
            f'<a href="{escape(SUPPORT_URL)}" target="_blank" rel="noopener">Become a supporter</a></p>')


# ---------------------------------------------------------------- avatar upload: POST apiv2/avatar
# Avatars live in <storagepath>/pfp/, which DataURL (data.jinkku.moe) serves; users.pfppath = "/pfp/<file>".
# Every upload gets a new file name so browsers and the game don't keep showing a cached old picture.
AVATAR_SIZE = 256
AVATAR_MAX_BYTES = 4 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


def _avatar_dir():
    path = os.path.join(storage_root, "pfp")
    os.makedirs(path, exist_ok=True)
    return path


def _delete_uploaded(user_id, pfppath):
    """Removes an avatar file this endpoint made earlier (never hand-placed ones like shala.jpg)."""
    m = re.fullmatch(rf"/pfp/({user_id}-[0-9a-f]{{8}}\.(?:png|jpg))", pfppath or "")
    if m:
        try:
            os.remove(os.path.join(_avatar_dir(), m.group(1)))
        except FileNotFoundError:
            pass


def avatar(request):
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their avatar."}, status=403)

    if request.POST.get("remove") == "1":
        _delete_uploaded(user.id, user.pfppath)
        User.objects.filter(id=user.id).update(pfppath=NoProfilePictureURL)
        return JsonResponse({"ok": True, "url": NoProfilePictureURL})

    upload = request.FILES.get("avatar")
    if upload is None:
        return JsonResponse({"error": "Pick an image to upload."}, status=400)
    if upload.size > AVATAR_MAX_BYTES:
        return JsonResponse({"error": "That image is too big (4 MB max)."}, status=400)
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return JsonResponse({"error": "That file isn't an image we can read (use PNG, JPEG, GIF or WebP)."}, status=400)

    img = ImageOps.exif_transpose(img)  # phone photos come in sideways otherwise
    img = ImageOps.fit(img.convert("RGBA"), (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)  # centre crop to a square
    transparent = img.getextrema()[3][0] < 255
    name = f"{user.id}-{secrets.token_hex(4)}.{'png' if transparent else 'jpg'}"
    path = os.path.join(_avatar_dir(), name)
    if transparent:
        img.save(path, "PNG", optimize=True)
    else:
        img.convert("RGB").save(path, "JPEG", quality=90)

    old = user.pfppath
    User.objects.filter(id=user.id).update(pfppath="/pfp/" + name)
    _delete_uploaded(user.id, old)
    return JsonResponse({"ok": True, "url": _pfp_url("/pfp/" + name)})


# ---------------------------------------------------------------- profile banner: POST apiv2/banner
# Banners live in <storagepath>/banners/ (served by DataURL like avatars); users.bannerpath = "/banners/<file>".
# Centre-cropped to BANNER_SIZE (the profile hero shows it with background-size: cover). New name every upload.
BANNER_SIZE = (1600, 500)
BANNER_MAX_BYTES = 8 * 1024 * 1024


def _banner_dir():
    path = os.path.join(storage_root, "banners")
    os.makedirs(path, exist_ok=True)
    return path


def _delete_banner(user_id, bannerpath):
    """Removes a banner file this endpoint made earlier."""
    m = re.fullmatch(rf"/banners/({user_id}-[0-9a-f]{{8}}\.jpg)", bannerpath or "")
    if m:
        try:
            os.remove(os.path.join(_banner_dir(), m.group(1)))
        except FileNotFoundError:
            pass


def banner(request):
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their banner."}, status=403)
    if request.POST.get("remove") != "1" and not moderation.has_supporter_perks(user.username):
        return JsonResponse({"error": "Profile banners are a supporter perk. Thank you for considering it <3"}, status=403)

    if request.POST.get("remove") == "1":
        _delete_banner(user.id, user.bannerpath)
        User.objects.filter(id=user.id).update(bannerpath=None)
        return JsonResponse({"ok": True, "url": ""})

    upload = request.FILES.get("banner")
    if upload is None:
        return JsonResponse({"error": "Pick an image to upload."}, status=400)
    if upload.size > BANNER_MAX_BYTES:
        return JsonResponse({"error": "That image is too big (8 MB max)."}, status=400)
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return JsonResponse({"error": "That file isn't an image we can read (use PNG, JPEG, GIF or WebP)."}, status=400)

    img = ImageOps.exif_transpose(img)
    rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, (34, 30, 39))  # transparent parts get the site's background colour
    flat.paste(rgba, mask=rgba.split()[3])
    flat = ImageOps.fit(flat, BANNER_SIZE, Image.LANCZOS)  # centre crop to the banner shape
    name = f"{user.id}-{secrets.token_hex(4)}.jpg"
    flat.save(os.path.join(_banner_dir(), name), "JPEG", quality=88, optimize=True, progressive=True)

    old = user.bannerpath
    User.objects.filter(id=user.id).update(bannerpath="/banners/" + name)
    _delete_banner(user.id, old)
    return JsonResponse({"ok": True, "url": banner_url("/banners/" + name)})


# ---------------------------------------------------------------- card border: POST apiv2/cardborder {"id": N}  (0 = none)
BIO_MAX = 3000


def bio(request, action=""):
    """POST apiv2/bio {"text": "..."}: your profile's "About me", osu!-style BBCode (empty clears it).
    POST apiv2/bio/preview {"text": "..."}: the HTML it would show, without saving."""
    import json
    from online.beatmapsocial import clean_text
    from Chikara.bbcode import to_html
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    if action == "preview":
        try:
            text = str(json.loads(request.body or b"{}").get("text") or "")[:BIO_MAX * 2]
        except (ValueError, AttributeError):
            text = ""
        return JsonResponse({"html": to_html(text)})
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their bio."}, status=403)
    try:
        text = clean_text(json.loads(request.body or b"{}").get("text"))
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Couldn't read that."}, status=400)
    limit = moderation.limit_for(user.username, "bio")
    if len(text) > limit:
        more = "" if limit > BIO_MAX else f" (supporters get {moderation.SUPPORTER_LIMITS['bio'][1]})"
        return JsonResponse({"error": f"Your bio can be at most {limit} characters{more}."}, status=400)
    User.objects.filter(id=user.id).update(bio=text or None)
    return JsonResponse({"ok": True, "bio": text, "html": to_html(text)})


def cardborder(request):
    import json
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    if user.restricted:
        return JsonResponse({"error": "Restricted accounts can't change their card border."}, status=403)
    try:
        border_id = int(json.loads(request.body or b"{}").get("id") or 0)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Pick a card border."}, status=400)
    if border_id == 0:
        User.objects.filter(id=user.id).update(cardborder=None)
        return JsonResponse({"ok": True, "id": 0})
    border = CardBorder.objects.filter(id=border_id, active=True).first()
    if border is None:
        return JsonResponse({"error": "That card border isn't available."}, status=404)
    if border.supporter_only and not moderation.has_supporter_perks(user.username):
        return JsonResponse({"error": "That card border is a supporter perk <3"}, status=403)
    User.objects.filter(id=user.id).update(cardborder="/" + border.image)
    return JsonResponse({"ok": True, "id": border.id})


# ---------------------------------------------------------------- password: GET /changepassword, POST apiv2/password
# Accounts still on the old unsalted SHA-256 are sent here right after logging in on the website (login.js).
PASSWORD_MIN = 8
PASSWORD_MAX = 256


def change_password_page(request):
    from Chikara import passwords
    user = moderation.request_user(request)
    if user is None:
        # Usually a player coming from the game's "change your password" notice: show the site (with its login
        # button); login.js sends old-hash accounts back here once they're in.
        html = header(request, title="Qlute - change password", robots="noindex, nofollow")
        html += '<div class="warning-box"><p>Log in to change your password.</p></div>'
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
        return HttpResponse(html, status=403)
    legacy = passwords.is_legacy(user.password)
    intro = ("We've upgraded how passwords are stored. Please choose a new password to keep your account secure."
             if legacy else "Choose a new password for your account.")
    html = header(request, title="Qlute - change password", robots="noindex, nofollow")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/changepassword.html").read() \
        .replace("{intro}", escape(intro)) \
        .replace("{currenthidden}", "hidden" if legacy else "")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def password(request):
    """POST apiv2/password {"current": "...", "new": "..."}: stores the new password salted and updates the login
    cookie. "current" is only needed when the account is already on the salted hash (the old-hash prompt comes
    straight after a login)."""
    import json
    from Chikara import passwords
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    user = moderation.request_user(request, write=True)
    if user is None:
        return JsonResponse({"error": "Log in first."}, status=401)
    try:
        body = json.loads(request.body or b"{}")
        current, new = str(body.get("current") or ""), str(body.get("new") or "")
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Couldn't read that."}, status=400)
    if not passwords.is_legacy(user.password) and not passwords.verify(user.password, passwords.prehash(current)):
        return JsonResponse({"error": "Your current password is wrong."}, status=403)
    if not PASSWORD_MIN <= len(new) <= PASSWORD_MAX:
        return JsonResponse({"error": f"Your new password needs {PASSWORD_MIN} to {PASSWORD_MAX} characters."}, status=400)
    new_sha = passwords.prehash(new)
    if passwords.verify(user.password, new_sha):
        return JsonResponse({"error": "Pick a password different from your old one."}, status=400)
    User.objects.filter(id=user.id).update(password=passwords.make(new_sha))
    response = JsonResponse({"ok": True})
    response.set_cookie("password", new_sha, max_age=31536000)
    return response
