"""Beatmap takedowns (rules: Beatmaps, "content that infringes copyright may be taken down").

Taking a set down hides it everywhere players find maps: the catalog and search (so also recommendations and
profiles), the sitemap, favourites, its page, and the game's difficulty list. New scores, comments and re-uploads
for it are refused. Its .osz download is moved out of the served storage folder into KEEP_DIR, so the old link
stops working. Everything else (difficulties, chart files, scores) is kept, so the team can restore it.
"""
import os
import shutil

from django.db.models import Q

from Chikara.settings import storage_root
from . import rules
from .models import TakenDown

KEEP_DIR = os.path.join(os.path.dirname(storage_root.rstrip("/")), "Chikara-takedowns")


def hidden_ids():
    """A subquery of the taken-down set ids, for .exclude(beatmapsetid__in=...)."""
    return TakenDown.objects.values("beatmapsetid")


def visible(qs):
    """`qs` (Beatmap rows) without taken-down sets."""
    return qs.exclude(beatmapsetid__in=hidden_ids())


def is_down(setid):
    return bool(setid) and TakenDown.objects.filter(beatmapsetid=setid).exists()


def _set_rows(setid):
    from dbview.models import Beatmap
    return Beatmap.objects.filter(beatmapsetid=setid)


def take_down(setid, reason, rule, by):
    """Returns (TakenDown, error)."""
    from submissions.models import Submission
    rows = list(_set_rows(setid))
    if not rows:
        return None, f"There's no beatmap set {setid}."
    if is_down(setid):
        return None, "That set is already taken down."
    moved = []
    os.makedirs(KEEP_DIR, exist_ok=True)
    for path in sorted({b.beatmapfile for b in rows if b.beatmapfile}):
        src = storage_root + path.lstrip("/")
        if os.path.isfile(src):
            dest = os.path.join(KEEP_DIR, os.path.basename(src))
            shutil.move(src, dest)
            moved.append([path, dest])
    title = f"{rows[0].artist} - {rows[0].title}"
    t = TakenDown.objects.create(beatmapsetid=setid, title=title, reason=reason, rule=rules.clean(rule) or "beatmaps",
                                 by=by, moved=moved)
    _changed()
    owner = Submission.objects.filter(beatmapsetid=setid).values_list("owner", flat=True).first()
    if owner:
        from online.notifications import push
        push(owner, "moderation", "Qlute team",
             f"Your beatmap set {title} was taken down ({rules.label(t.rule)}): {reason}", rules.link(t.rule))
    print(f"[moderation] {by} took down set {setid} ({title}): {reason}")
    return t, None


def restore(setid, by):
    """Puts a taken-down set back. Returns an error or ""."""
    t = TakenDown.objects.filter(beatmapsetid=setid).first()
    if t is None:
        return "That set isn't taken down."
    for served, kept in t.moved or []:
        dest = storage_root + served.lstrip("/")
        if os.path.isfile(kept) and not os.path.exists(dest):
            shutil.move(kept, dest)
    t.delete()
    _changed()
    print(f"[moderation] {by} restored set {setid}")
    return ""


def _changed():
    try:
        from Chikara import views
        views._sitemap_cache["xml"] = ""
    except Exception:
        pass


def json(t):
    return {"setid": t.beatmapsetid, "title": t.title, "reason": t.reason, "rule": t.rule,
            "rule_text": rules.label(t.rule), "by": t.by, "created": int(t.created.timestamp()), "files": len(t.moved or [])}
