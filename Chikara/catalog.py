"""The beatmap catalog: apiv2/search (website /beatmaps, the game's Browse screen, multiplayer lookups).

GET apiv2/search, every parameter optional:
    query     words; each one must match the title, artist (either spelling), mapper, tags, source,
              a difficulty name or an id. It can also hold osu!-style filters (parse_query), matched per difficulty:
                numbers  bpm, length (seconds, or 2:30 / 3m / 90s), level (lv), pp (SS pp), od, notes, plays
                         with = != > >= < <=     e.g.  bpm>180  length<2:00  level>=30  od=8
                text     mapper (creator), artist, title, diff (difficulty), source, tag  with = (contains) or != (not)
                         e.g.  mapper=sotarks  diff="another"  artist!=camellia
                status   status=ranked / special / unranked (r / s / u): overrides the status parameter
              Anything that isn't a valid filter is searched as a normal word.
    status    1 ranked (default), 2 or 4 special (the game sends 2, the website 4), 0 unranked
    uploader  NAME: only the sets NAME submitted, any status (the website's "Yours" tab)
    genre     osu! genre id (GENRES); 1 also matches sets nobody filled in
    language  osu! language id (LANGUAGES); same
    explicit  "hide" leaves out explicit sets (default: show)
    extra     comma list of "video", "storyboard": the set must have each
    played    "played" / "unplayed": sets the logged-in player has (no) scores on
    recommended  1: ranked difficulties matched to the logged-in player's skill (Chikara/recommend.py),
              not played yet; replaces status/uploader/played. Sort "match" (closest first) is its default.
              The range used is in the X-Qlute-Recommend response header (JSON) and each difficulty in
              range has "recommended": true.
    sort      newest (default), title, artist, mapper, difficulty, bpm, length, plays
    dir       "asc" / "desc" (each sort has its own default)
    page      0, 1, ... (PER_PAGE sets each)
Reply: a list of sets, each with its difficulties, in the shape the game's Browse screen reads.
GET apiv2/beatmapfilters: the genre / language / sort lists, for building the filter UI.
"""
import json

from django.db.models import F, Max, Min, Q, Sum
from django.db.models.functions import Abs
from django.http import JsonResponse

from Chikara.settings import DataURL
from dbview.models import Beatmap, Score

PER_PAGE = 50

# osu!'s ids (the API's genre_id / language_id), in the order the filters show them.
GENRES = [(1, "Unspecified"), (2, "Video Game"), (3, "Anime"), (4, "Rock"), (5, "Pop"), (6, "Other"), (7, "Novelty"),
          (9, "Hip Hop"), (10, "Electronic"), (11, "Metal"), (12, "Classical"), (13, "Folk"), (14, "Jazz")]
LANGUAGES = [(2, "English"), (3, "Japanese"), (4, "Chinese"), (6, "Korean"), (7, "French"), (8, "German"),
             (11, "Italian"), (10, "Spanish"), (9, "Swedish"), (12, "Russian"), (13, "Polish"), (5, "Instrumental"),
             (1, "Unspecified"), (14, "Other")]
GENRE_NAMES = dict(GENRES)
LANGUAGE_NAMES = dict(LANGUAGES)
UNSPECIFIED = 1

# sort -> (annotation over a set's difficulties, default direction is descending)
SORTS = {
    "newest": (Max("created"), True),
    "title": (Max("title"), False),
    "artist": (Max("artist"), False),
    "mapper": (Max("mapper"), False),
    "difficulty": (Max("Level"), True),
    "bpm": (Max("BPM"), True),
    "length": (Max("Length"), True),
    "plays": (Sum("playcount"), True),
}
SORT_NAMES = [("newest", "Newest"), ("title", "Title"), ("artist", "Artist"), ("mapper", "Mapper"),
              ("difficulty", "Difficulty"), ("bpm", "BPM"), ("length", "Length"), ("plays", "Plays")]


def filters(request):
    return JsonResponse({
        "genres": [{"id": i, "name": n} for i, n in GENRES],
        "languages": [{"id": i, "name": n} for i, n in LANGUAGES],
        "sorts": [{"id": i, "name": n, "desc": SORTS[i][1]} for i, n in SORT_NAMES],
    })


def _int(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _status_q(status):
    if status in (2, 4):  # Special: the game asks for 2, the website for 4
        return Q(ranked__in=(2, 4))
    if status == 0:
        return Q(ranked__lte=0)  # unranked + unknown
    return Q(ranked=status)


# typed filters in the search box (osu!-style): key, operator, value; values with spaces go in "quotes"
import re as _re

_TOKEN = _re.compile(r'(\w+(?:>=|<=|!=|>|<|=|:)"[^"]*")|("[^"]*")|(\S+)')
_FILTER = _re.compile(r'^(\w+)(>=|<=|!=|>|<|=|:)(.*)$')
_NUMBERS = {"bpm": "BPM", "length": "Length", "len": "Length", "level": "Level", "lv": "Level", "pp": "pp",
            "od": "Accuracy", "notes": "notecount", "objects": "notecount", "plays": "playcount"}
_TEXTS = {"mapper": ("mapper",), "creator": ("mapper",), "artist": ("artist", "artist_unicode"),
          "title": ("title", "title_unicode"), "diff": ("difficulty",), "difficulty": ("difficulty",),
          "version": ("difficulty",), "source": ("source",), "tag": ("tags",), "tags": ("tags",)}
_STATUSES = {"ranked": 1, "r": 1, "special": 4, "s": 4, "loved": 4, "unranked": 0, "u": 0, "graveyard": 0}
_LOOKUP = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}


def _number(key, text):
    """A filter value as a number; length also takes 2:30, 3m, 90s."""
    text = text.strip().lower()
    if key in ("length", "len"):
        m = _re.fullmatch(r"(\d+):(\d{1,2})", text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        m = _re.fullmatch(r"(\d+(?:\.\d+)?)(m|s)", text)
        if m:
            return float(m.group(1)) * (60 if m.group(2) == "m" else 1)
    n = float(text)
    if n != n or n in (float("inf"), float("-inf")):  # nan / inf aren't numbers a database can compare
        raise ValueError(text)
    return n


def parse_query(query):
    """Split the search box into (plain words, [Q filters], status override or None). At most 10 of each."""
    words, filters, status = [], [], None
    for m in _TOKEN.finditer(query or ""):
        token = (m.group(0) or "").strip()
        f = _FILTER.match(token)
        if f:
            key, op, value = f.group(1).lower(), f.group(2), f.group(3).strip().strip('"')
            op = "=" if op == ":" else op
            if key in _NUMBERS and value:
                try:
                    n = _number(key, value)
                except ValueError:
                    n = None
                if n is not None:
                    field = _NUMBERS[key]
                    if op == "=":
                        filters.append(Q(**{field: n}))
                    elif op == "!=":
                        filters.append(~Q(**{field: n}))
                    else:
                        filters.append(Q(**{f"{field}__{_LOOKUP[op]}": n}))
                    continue
            elif key in _TEXTS and value and op in ("=", "!="):
                q = Q()
                for field in _TEXTS[key]:
                    q |= Q(**{f"{field}__icontains": value})
                filters.append(q if op == "=" else ~q)
                continue
            elif key == "status" and op == "=" and value.lower() in _STATUSES:
                status = _STATUSES[value.lower()]
                continue
        words.append(token.strip('"'))
    return [w for w in words if w][:10], filters[:10], status


def search(request):
    g = request.GET
    from moderation import takedowns
    rows = takedowns.visible(Beatmap.objects.all())  # taken-down sets never show (moderation/takedowns.py)
    words, typed_filters, typed_status = parse_query(g.get("query"))

    rec = None
    rec_rows = None
    uploader = (g.get("uploader") or "").strip()
    if g.get("recommended") in ("1", "true"):
        from Chikara import recommend
        from moderation import service as moderation
        me = moderation.request_user(request)
        rec = recommend.profile(me.username if me else None)
        rows = rows.filter(ranked=1)
        rec_rows = rows.filter(pp__gte=rec["min_pp"], pp__lte=rec["max_pp"])
        if me is not None:
            rec_rows = rec_rows.exclude(beatmapid__in=Score.objects.filter(username=me.username).values("beatmap_id"))
    elif uploader:
        from submissions.models import Submission
        rows = rows.filter(beatmapsetid__in=Submission.objects.filter(owner=uploader).values("beatmapsetid"))
        if typed_status is not None:
            rows = rows.filter(_status_q(typed_status))
        elif g.get("status") not in (None, ""):  # a profile's Ranked / Special tabs; the "Yours" tab sends none
            rows = rows.filter(_status_q(_int(g.get("status"), 1)))
    else:
        rows = rows.filter(_status_q(typed_status if typed_status is not None else _int(g.get("status"), 1)))
    status_rows = rows  # every difficulty of a matching set is shown, not just the ones the words matched
    if rec_rows is not None:
        rows = rec_rows

    for f in typed_filters:  # bpm>180, mapper=..., level>=30: a set shows when one of its difficulties matches
        rows = rows.filter(f)
    for word in words:
        rows = rows.filter(
            Q(title__icontains=word) | Q(title_unicode__icontains=word) |
            Q(artist__icontains=word) | Q(artist_unicode__icontains=word) |
            Q(mapper__icontains=word) | Q(tags__icontains=word) | Q(source__icontains=word) |
            Q(difficulty__icontains=word) | Q(beatmapid__icontains=word) | Q(beatmapsetid__icontains=word)
        )

    genre = _int(g.get("genre"))
    if genre:
        rows = rows.filter(Q(genre=genre) | Q(genre__isnull=True)) if genre == UNSPECIFIED else rows.filter(genre=genre)
    language = _int(g.get("language"))
    if language:
        rows = rows.filter(Q(language=language) | Q(language__isnull=True)) if language == UNSPECIFIED \
            else rows.filter(language=language)
    if g.get("explicit") == "hide":
        rows = rows.exclude(nsfw=True)
    extra = set((g.get("extra") or "").split(","))
    if "video" in extra:
        rows = rows.filter(video=True)
    if "storyboard" in extra:
        rows = rows.filter(storyboard=True)

    played = g.get("played")
    if played in ("played", "unplayed") and rec is None:
        from moderation import service as moderation
        me = moderation.request_user(request)
        if me is not None:
            mine = Score.objects.filter(username=me.username).values("beatmapset_id")
            rows = rows.filter(beatmapsetid__in=mine) if played == "played" else rows.exclude(beatmapsetid__in=mine)

    if rec is not None and g.get("sort") in (None, "", "match"):
        key, desc = Min(Abs(F("pp") - rec["target_pp"])), False  # closest to the player's target first
    else:
        sort = g.get("sort") if g.get("sort") in SORTS else "newest"
        key, desc = SORTS[sort]
    if g.get("dir") in ("asc", "desc"):
        desc = g.get("dir") == "desc"
    page = max(0, _int(g.get("page"), 0))
    sets = (rows.values("beatmapsetid").annotate(k=key)
            .order_by(("-k" if desc else "k"), ("-beatmapsetid" if desc else "beatmapsetid"))
            [page * PER_PAGE:(page + 1) * PER_PAGE])
    ids = [s["beatmapsetid"] for s in sets]

    diffs = {}
    for a in status_rows.filter(beatmapsetid__in=ids).order_by("Level", "notecount").values():
        diffs.setdefault(a["beatmapsetid"], []).append(a)
    out = [set_json(diffs[i]) for i in ids if i in diffs]
    from moderation import service as moderation
    from online.beatmapsocial import add_favorite_info
    viewer = moderation.request_user(request)
    add_favorite_info(out, viewer.username if viewer else None)
    add_mapper_user(out)
    if rec is None:
        return JsonResponse(out, safe=False)
    picked = set(rows.filter(beatmapsetid__in=ids).values_list("beatmapid", flat=True))
    for st in out:
        for d in st["beatmaps"]:
            d["recommended"] = d["id"] in picked
    response = JsonResponse(out, safe=False)
    response["X-Qlute-Recommend"] = json.dumps(rec)
    return response


def mapper_users(sets):
    """{set id: the Qlute account the mapper name links to} for sets with an owner who is the mapper:
    an accepted osu! claim (proved to be the creator), or an upload whose mapper name is the uploader's."""
    from submissions.models import BeatmapClaim, Submission
    ids = [setid for setid, _ in sets]
    owners = dict(Submission.objects.filter(beatmapsetid__in=ids).values_list("beatmapsetid", "owner"))
    claimed = set(BeatmapClaim.objects.filter(beatmapsetid__in=owners, status=BeatmapClaim.ACCEPTED)
                  .values_list("beatmapsetid", flat=True))
    out = {}
    for setid, mapper in sets:
        owner = owners.get(setid)
        if owner and (setid in claimed or (mapper or "").strip().lower() == owner.lower()):
            out[setid] = owner
    return out


def add_mapper_user(sets):
    """Give each apiv2/search-shaped set its "mapper_user" ("" when the mapper has no linked Qlute account)."""
    linked = mapper_users([(st["id"], st["creator"]) for st in sets])
    for st in sets:
        st["mapper_user"] = linked.get(st["id"], "")
    return sets


def set_json(rows):
    a = rows[0]
    cover = DataURL + a["backgroundpath"]
    return {
        "id": a["beatmapsetid"],
        "bpm": a["BPM"],
        "title": a["title"],
        "title_unicode": a["title_unicode"],
        "artist": a["artist"],
        "artist_unicode": a["artist_unicode"],
        "creator": a["mapper"],
        "preview_url": DataURL + a["previewpath"],
        "download_url": DataURL + a["beatmapfile"],
        "covers": {"cover": cover, "card": cover, "list": cover, "slimcover": cover},
        "source": a["source"] or "",
        "tags": a["tags"] or "",
        "genre": a["genre"] or UNSPECIFIED,
        "genre_name": GENRE_NAMES.get(a["genre"] or UNSPECIFIED, "Unspecified"),
        "language": a["language"] or UNSPECIFIED,
        "language_name": LANGUAGE_NAMES.get(a["language"] or UNSPECIFIED, "Unspecified"),
        "nsfw": bool(a["nsfw"]),
        "video": bool(a["video"]),
        "storyboard": bool(a["storyboard"]),
        "play_count": sum(r["playcount"] for r in rows),
        "last_updated": int(a["created"].timestamp()),
        "beatmaps": [{
            "id": r["beatmapid"],
            "level": r["Level"],
            "count_circles": r["notecount"],
            "count_sliders": 0,
            "max_combo": r["notecount"],
            "ranked": r["ranked"],
            "total_length": r["Length"],
            "version": r["difficulty"],
            "bpm": r["BPM"],
            "pp": r["pp"],
            "playcount": r["playcount"],
        } for r in rows],
    }
