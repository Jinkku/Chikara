"""News: /news (list), /news/<id> (a post). The Qlute team (mods and admins) writes them in the admin panel.

Team API (apiv2/mod/...):
    GET  news                      -> every post, drafts too
    POST news/save    {"id"?, "title", "summary", "body", "image", "published", "pinned"} -> {"ok", "post"}
    POST news/delete  {"id"}
    POST news/preview {"body"}     -> {"html"}
"""
import json
import re
import urllib.parse

from django.http import HttpResponse, JsonResponse
from django.utils.html import escape

from Chikara.bbcode import to_html, to_plain
from . import service
from .models import NewsPost

BODY_MAX = 20000
PER_PAGE = 12


def _url(value):
    value = str(value or "").strip()
    return value if re.match(r"^https?://[^\s<>\"']+$", value, re.IGNORECASE) else ""


def _text(value, limit):
    return "".join(c for c in str(value or "") if c.isprintable() or c == "\n").strip()[:limit]


def _date(dt):
    return f"{dt.day} {dt.strftime('%B %Y')}"


def summary_of(p):
    return p.summary or _clip(to_plain(p.body), 220)


def _clip(text, n):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0] + "…"


def visible(request):
    """Published posts, plus drafts for the team."""
    me = service.request_user(request)
    team = me is not None and not me.restricted and service.is_staff(me.username)
    q = NewsPost.objects.all() if team else NewsPost.objects.filter(published=True)
    return q, team


def post_json(p):
    return {"id": p.id, "title": p.title, "summary": p.summary, "body": p.body, "image": p.image, "author": p.author,
            "published": p.published, "pinned": p.pinned, "created": int(p.created.timestamp()),
            "updated": int(p.updated.timestamp()), "edited_by": p.edited_by}


# ---------------------------------------------------------------- cards (also used on the home page)

def card(p, big=False):
    cover = f'<span class="nw-cover" style="background-image:url(\'{escape(p.image)}\')"></span>' if p.image else \
        '<span class="nw-cover nw-cover-none"><span>Q</span></span>'
    flags = ""
    if p.pinned:
        flags += '<span class="nw-flag pin">Pinned</span>'
    if not p.published:
        flags += '<span class="nw-flag draft">Draft</span>'
    return (f'<a class="nw-card{" nw-card-big" if big else ""}" href="/news/{p.id}">{cover}<span class="nw-card-body">'
            f'<span class="nw-meta">{flags}<span>{_date(p.created)}</span><span>by {escape(p.author)}</span></span>'
            f'<span class="nw-card-title">{escape(p.title)}</span>'
            f'<span class="nw-card-sum">{escape(summary_of(p))}</span></span></a>')


def latest_html(limit=3):
    posts = list(NewsPost.objects.filter(published=True).order_by("-pinned", "-created")[:limit])
    if not posts:
        return '<p class="nw-empty">No news yet!</p>'
    return '<div class="nw-list nw-list-compact">' + "".join(card(p) for p in posts) + \
        '</div><a class="nw-all" href="/news">All news &rsaquo;</a>'


# ---------------------------------------------------------------- pages

def _page(request, title, body, status=200, **seo):
    from Chikara.views import BASE_DIR, STATIC_ROOT, header
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/news.css?v=1">', title=title, **seo)
    html += body + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html, status=status)


def news_list(request, command=""):
    from Chikara.views import SiteURL
    try:
        pg = max(1, int(command.strip("/") or 1))
    except ValueError:
        pg = 1
    q, team = visible(request)
    total = q.count()
    posts = list(q.order_by("-pinned", "-created")[(pg - 1) * PER_PAGE:pg * PER_PAGE])
    h = '<div class="infoboxcontainer" id="news-page"><div class="infoboxtitle"><p>news</p></div>'
    h += '<section class="infobox column nw-section spacebottom">'
    h += '<div class="nw-head"><h1>News</h1>'
    if team:
        h += '<a class="nw-btn" href="/admin#news=new">+ Write a post</a>'
    h += '</div>'
    if not posts:
        h += '<p class="nw-empty">No news yet!</p>'
    else:
        first = posts[0] if pg == 1 else None
        if first:
            h += card(first, big=True)
        rest = posts[1:] if first else posts
        if rest:
            h += '<div class="nw-list">' + "".join(card(p) for p in rest) + '</div>'
    pages = max(1, -(-total // PER_PAGE))
    if pages > 1:
        h += '<nav class="nw-pages">'
        if pg > 1:
            h += f'<a href="/news/page/{pg - 1}">&lsaquo; Newer</a>'
        h += f'<span>Page {pg} of {pages}</span>'
        if pg < pages:
            h += f'<a href="/news/page/{pg + 1}">Older &rsaquo;</a>'
        h += '</nav>'
    h += '</section></div>'
    return _page(request, "Qlute - news" + (f" (page {pg})" if pg > 1 else ""), h, canonical=SiteURL + "/news",
                 description="News and updates about Qlute, the free rhythm game: new features, events and announcements.")


def news_post(request, post_id):
    from Chikara.views import SiteURL, NOINDEX, _pfp_url
    from dbview.models import User
    q, team = visible(request)
    p = q.filter(id=post_id).first()
    if p is None:
        h = ('<div class="infoboxcontainer" id="news-page"><div class="infoboxtitle"><p>news</p></div>'
             '<section class="infobox column nw-section spacebottom"><p class="nw-empty">That news post doesn\'t exist.</p>'
             '<a class="nw-all" href="/news">All news &rsaquo;</a></section></div>')
        return _page(request, "Qlute - news not found", h, status=404, robots=NOINDEX)
    author = User.objects.filter(username=p.author).first()
    h = '<div class="infoboxcontainer" id="news-page"><div class="infoboxtitle"><p>news</p></div>'
    h += '<article class="infobox column nw-post spacebottom">'
    if p.image:
        h += f'<div class="nw-post-cover" style="background-image:url(\'{escape(p.image)}\')"></div>'
    h += '<div class="nw-post-inner">'
    flags = ('<span class="nw-flag draft">Draft: only the team can see this</span>' if not p.published else "") + \
            ('<span class="nw-flag pin">Pinned</span>' if p.pinned else "")
    if flags:
        h += f'<div class="nw-meta">{flags}</div>'
    h += f'<h1 class="nw-post-title">{escape(p.title)}</h1>'
    pfp = escape(_pfp_url(author.pfppath if author else None))
    who = f'/user/{author.id}' if author else '#'
    h += (f'<div class="nw-byline"><a href="{who}"><img src="{pfp}" alt="" width="36" height="36"><b>{escape(p.author)}</b></a>'
          f'<span>{_date(p.created)}</span>'
          f'{f"<span>edited {_date(p.updated)}</span>" if p.edited_by and p.updated.date() != p.created.date() else ""}')
    if team:
        h += f'<a class="nw-btn nw-btn-quiet" href="/admin#news={p.id}">Edit</a>'
    h += '</div>'
    h += f'<div class="nw-body bb">{to_html(p.body)}</div>'
    h += '<a class="nw-all" href="/news">&lsaquo; All news</a></div></article></div>'
    return _page(request, f"{escape(p.title)} - Qlute news", h, canonical=f"{SiteURL}/news/{p.id}",
                 description=escape(summary_of(p)), image=p.image or None, robots=None if p.published else NOINDEX)


# ---------------------------------------------------------------- team API (wired in moderation/views.py)

def _body(request):
    try:
        d = json.loads(request.body or b"{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def news_view(request, me, staff, args):
    return JsonResponse({"results": [post_json(p) for p in NewsPost.objects.order_by("-pinned", "-created")[:200]]})


def news_edit_view(request, me, staff, args):
    action = args[0] if args else ""
    d = _body(request)
    if action == "preview":
        return JsonResponse({"html": to_html(_text(d.get("body"), BODY_MAX))})
    if action == "delete":
        p = NewsPost.objects.filter(id=d.get("id")).first() if str(d.get("id", "")).isdigit() else None
        if p is None:
            return JsonResponse({"error": "That post doesn't exist."}, status=404)
        print(f"[news] {me.username} deleted #{p.id} {p.title!r}")
        p.delete()
        return JsonResponse({"ok": True})
    if action != "save":
        return JsonResponse({"error": "Unknown action."}, status=404)
    title = _text(d.get("title"), 200).replace("\n", " ")
    if not title:
        return JsonResponse({"error": "Give the post a title."}, status=400)
    image = str(d.get("image") or "").strip()
    if image and not _url(image):
        return JsonResponse({"error": "The cover image has to be a link starting with https://"}, status=400)
    if d.get("id"):
        p = NewsPost.objects.filter(id=d.get("id")).first() if str(d.get("id")).isdigit() else None
        if p is None:
            return JsonResponse({"error": "That post doesn't exist."}, status=404)
        p.edited_by = me.username
    else:
        p = NewsPost(author=me.username)
    p.title = title
    p.summary = _text(d.get("summary"), 300).replace("\n", " ")
    p.body = _text(d.get("body"), BODY_MAX)
    p.image = image
    p.published = bool(d.get("published", True))
    p.pinned = bool(d.get("pinned"))
    p.save()
    print(f"[news] {me.username} saved #{p.id} {p.title!r} ({'published' if p.published else 'draft'})")
    return JsonResponse({"ok": True, "post": post_json(p)})
