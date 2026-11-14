"""Turning an uploaded .osz into a Qlute beatmap set, and rewriting a set's metadata later.

A submitted set ends up exactly like a set crawled from osu! by /Storage/regen (grabnew.py + recheck.py):
    <storage>/songs/<setid> <artist> - <title>.osz      what the game downloads
    <storage>/song_assets/<setid>/<beatmapid>.osu      chart the server judges replays with
    <storage>/song_assets/<setid>/preview.ogg, bg.jpg  website / browse previews
    one `beatmaps` row per difficulty
so recheck.py keeps working on it. The stored values (Level, BPM, pp...) are worked out the same way recheck.py
does, and the .osu files in the .osz get their BeatmapID / BeatmapSetID rewritten to the ids the server gave
them, so scores set on them can be submitted.

Only osu!mania 4K difficulties are kept (the same rule as recheck.py).
"""
import io
import os
import re
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image

import Chikara.ppv2calc as ppv2calc
from Chikara.settings import storage_root
from dbview.models import Beatmap, Beatmapset, Score

from .models import Submission

# Uploaded sets and their difficulties get ids from here up. osu! is around 2.5M sets / 5M maps, so they
# never meet, and it still fits the int(11) columns and the game's int ids.
SUBMIT_ID_BASE = 1_000_000_000

MAX_OSZ_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_BYTES = 400 * 1024 * 1024
MAX_MEMBERS = 1000
MAX_OSU_BYTES = 5 * 1024 * 1024
MAX_DIFFICULTIES = 40
MAX_FIELD = {"Title": 200, "TitleUnicode": 200, "Artist": 200, "ArtistUnicode": 200, "Creator": 100,
             "Version": 100, "Source": 200, "Tags": 1000}

# same as /Storage/regen/recheck.py
LEVEL_WEIGHT = 0.0084
TIME_CAP = 120

Image.MAX_IMAGE_PIXELS = 60_000_000


class SubmitError(Exception):
    """Something the uploader can fix; the text is shown to them as is."""


def songs_dir():
    return os.path.join(storage_root, "songs")


def assets_dir(setid):
    return os.path.join(storage_root, "song_assets", str(setid))


def level_rating(objects, seconds):
    return ((objects + 1) * LEVEL_WEIGHT) / ((seconds + 1) / TIME_CAP)


def clean(value, key):
    """One line of printable text, cut to the field's limit."""
    value = "".join(c for c in str(value or "") if c.isprintable()).strip()
    return value[:MAX_FIELD.get(key, 200)]


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


# ---------------------------------------------------------------- .osu parsing

@dataclass
class Chart:
    member: str  # path inside the .osz
    lines: list  # text lines, "\n" endings (universal newlines, like recheck.py reads them)
    meta: dict = field(default_factory=dict)  # [Metadata] key -> value
    general: dict = field(default_factory=dict)
    mode: str = "0"
    keys: str = ""
    od: int = 0
    bpm: int = 0
    notes: int = 0
    length_ms: int = 0
    background: str = ""
    video: str = ""  # file name of the background video, if any
    storyboard: bool = False  # storyboard commands in [Events]
    beatmapid: int = 0  # given by the server

    @property
    def version(self):
        return self.meta.get("Version", "")

    @property
    def is_mania_4k(self):
        return self.mode == "3" and self.keys == "4"

    def text(self):
        return "".join(self.lines)


def read_lines(data: bytes):
    try:
        return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig").readlines()
    except UnicodeDecodeError:
        raise SubmitError("A difficulty file isn't UTF-8 text. Re-save it in your editor and try again.")


def _int(value, fallback=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def parse_chart(member, data: bytes):
    c = Chart(member=member, lines=read_lines(data))
    section = ""
    first_timing = True
    for raw in c.lines:
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section in ("General", "Metadata", "Difficulty"):
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if section == "General":
                c.general.setdefault(key, value)
                if key == "Mode":
                    c.mode = value
            elif section == "Metadata":
                c.meta[key] = value
            elif key == "CircleSize":
                c.keys = value
            elif key == "OverallDifficulty":
                c.od = _int(value)
        elif section == "Events":
            parts = line.split(",")
            if not c.background and line.startswith("0,0,") and len(parts) >= 3:
                c.background = parts[2].strip().strip('"')
            elif parts[0] in ("Video", "1") and len(parts) >= 3:
                c.video = parts[2].strip().strip('"')
            elif parts[0] in ("Sprite", "Animation", "4", "6"):
                c.storyboard = True
        elif section == "TimingPoints" and first_timing:
            parts = line.split(",")
            if len(parts) >= 2:
                first_timing = False
                try:
                    beat = float(parts[1])
                    c.bpm = int(60000 // beat) if beat else 0
                except ValueError:
                    pass
        elif section == "HitObjects":
            parts = line.split(",")
            c.notes += 1
            if len(parts) >= 3:
                t = _int(parts[2], -1)
                if t > c.length_ms:
                    c.length_ms = t
    return c


def set_metadata(lines, values):
    """Sets keys in [Metadata] (adding them, or the section, when missing). Returns new lines."""
    out = list(lines)
    start = next((i for i, l in enumerate(out) if l.strip() == "[Metadata]"), None)
    if start is None:
        # put a fresh section before [Difficulty] (or at the end)
        at = next((i for i, l in enumerate(out) if l.strip() == "[Difficulty]"), len(out))
        out[at:at] = ["[Metadata]\n", "\n"]
        start = at
    end = next((i for i in range(start + 1, len(out)) if out[i].strip().startswith("[")), len(out))
    pending = dict(values)
    for i in range(start + 1, end):
        key, sep, _ = out[i].partition(":")
        if sep and key.strip() in pending:
            out[i] = f"{key.strip()}:{pending.pop(key.strip())}\n"
    if pending:
        at = end
        while at - 1 > start and not out[at - 1].strip():
            at -= 1  # before the blank lines that end the section
        out[at:at] = [f"{k}:{v}\n" for k, v in pending.items()]
    return out


# ---------------------------------------------------------------- reading an upload

def _find(names, wanted):
    """Zip member for a file name an .osu refers to (osu! is case-insensitive about these)."""
    if not wanted:
        return None
    wanted = wanted.replace("\\", "/").lower()
    for n in names:
        if n.lower() == wanted:
            return n
    return None


def open_upload(path):
    """(zip, [mania 4K charts], [skipped .osu names]). Raises SubmitError."""
    if os.path.getsize(path) > MAX_OSZ_BYTES:
        raise SubmitError(f"That beatmap is too big ({MAX_OSZ_BYTES // (1024 * 1024)} MB max).")
    if not zipfile.is_zipfile(path):
        raise SubmitError("That file isn't an .osz (zip) beatmap.")
    z = zipfile.ZipFile(path)
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS:
        raise SubmitError("That beatmap has too many files in it.")
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise SubmitError("That beatmap is too big once unpacked.")
    for i in infos:
        n = i.filename
        if n.startswith("/") or "\\" in n or ".." in n.split("/") or ":" in n:
            raise SubmitError(f"The file name '{n}' in that beatmap isn't allowed.")
    charts, skipped = [], []
    for i in infos:
        if not i.filename.lower().endswith(".osu"):
            continue
        if i.file_size > MAX_OSU_BYTES:
            raise SubmitError(f"{os.path.basename(i.filename)} is too big for a difficulty file.")
        c = parse_chart(i.filename, z.read(i))
        if not c.is_mania_4k:
            skipped.append(i.filename)
            continue
        charts.append(c)
    return z, charts, skipped


def check_charts(z, charts):
    if not charts:
        raise SubmitError("There's no osu!mania 4K difficulty in that beatmap. Qlute only takes 4K maps.")
    if len(charts) > MAX_DIFFICULTIES:
        raise SubmitError(f"That set has too many difficulties ({MAX_DIFFICULTIES} max).")
    names = z.namelist()
    seen = set()
    for c in charts:
        label = c.version or os.path.basename(c.member)
        if not c.version:
            raise SubmitError(f"{os.path.basename(c.member)} has no difficulty name (Version).")
        if c.version.lower() in seen:
            raise SubmitError(f"Two difficulties are called '{c.version}'. Give each one its own name.")
        seen.add(c.version.lower())
        if not c.meta.get("Title") or not c.meta.get("Artist"):
            raise SubmitError(f"[{label}] needs a title and an artist.")
        if c.notes < 1:
            raise SubmitError(f"[{label}] has no notes.")
        audio = c.general.get("AudioFilename", "")
        if not _find(names, audio):
            raise SubmitError(f"[{label}] uses the song file '{audio}', which isn't in the beatmap.")


# ---------------------------------------------------------------- writing a set

@contextmanager
def submit_lock():
    """One upload/edit at a time across every server process (ids, file names)."""
    if connection.vendor != "mysql":  # tests on SQLite: one process anyway
        yield
        return
    with connection.cursor() as cur:
        cur.execute("SELECT GET_LOCK('qlute_beatmap_submit', 60)")
        if cur.fetchone()[0] != 1:
            raise SubmitError("The server is busy with other uploads. Try again in a minute.")
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK('qlute_beatmap_submit')")


def next_set_id():
    a = Beatmap.objects.filter(beatmapsetid__gte=SUBMIT_ID_BASE).aggregate(m=Max("beatmapsetid"))["m"] or 0
    b = Submission.objects.aggregate(m=Max("beatmapsetid"))["m"] or 0
    return max(SUBMIT_ID_BASE - 1, a, b) + 1


def next_map_id():
    a = Beatmap.objects.filter(beatmapid__gte=SUBMIT_ID_BASE).aggregate(m=Max("beatmapid"))["m"] or 0
    return max(SUBMIT_ID_BASE - 1, a) + 1


def write_osz(z, dest, replaced, drop=()):
    """Copies zip `z` to `dest`, with `replaced` {member: text} and without the `drop` members."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".upload-", suffix=".part")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():
                if info.filename in drop or info.is_dir():
                    continue
                if info.filename in replaced:
                    out.writestr(info.filename, replaced[info.filename].encode("utf-8"))
                else:
                    # audio / images are already compressed: store them as they were
                    with z.open(info) as src, out.open(zipfile.ZipInfo(info.filename, info.date_time), "w") as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def export_preview(z, member, start_ms, out_path):
    """10 s ogg preview from the song's PreviewTime, like recheck.py."""
    suffix = os.path.splitext(member)[1] or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        with z.open(member) as src:
            while chunk := src.read(1 << 20):
                tmp.write(chunk)
        tmp.flush()
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{max(0, start_ms) / 1000:.3f}",
                        "-t", "10", "-i", tmp.name, "-vn", "-c:a", "libvorbis", "-b:a", "96k", out_path],
                       check=True, timeout=120)


def export_background(data, out_path, quality=70, max_width=1280):
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if max_width and img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)), Image.LANCZOS)
    img.save(out_path, "JPEG", quality=quality, optimize=True)


@dataclass
class Result:
    setid: int
    updated: bool
    beatmaps: list  # [{"file", "version", "beatmapid"}]
    skipped: list
    removed: list

    def json(self):
        return {"ok": True, "setid": self.setid, "updated": self.updated, "beatmaps": self.beatmaps,
                "skipped": self.skipped, "removed": self.removed, "url": f"/beatmapset/{self.setid}"}


def submit(path, username, staff=False):
    """Adds (or, for the owner, updates) the set in the uploaded .osz at `path`. Returns a Result."""
    z, charts, skipped = open_upload(path)
    with z:
        check_charts(z, charts)
        with submit_lock():
            return _submit_locked(z, charts, skipped, username, staff)


def _submit_locked(z, charts, skipped, username, staff):
    # Which set is this? The .osu files carry the set id the server gave them on the first upload.
    claimed = [_int(c.meta.get("BeatmapSetID"), 0) for c in charts]
    claimed = max(set(claimed), key=claimed.count)
    sub = Submission.objects.filter(beatmapsetid=claimed).first() if claimed > 0 else None
    existing = []
    if sub is not None:
        if sub.owner != username and not staff:
            raise SubmitError("That beatmap set was submitted by someone else. "
                              "Remove the BeatmapSetID line from the difficulties to submit it as a new set.")
        existing = list(Beatmap.objects.filter(beatmapsetid=claimed))
        if any(b.ranked != 0 for b in existing) and not staff:
            raise SubmitError("This set is already ranked, so it can't be updated any more. "
                              "Ask the Qlute team if something needs fixing.")
        setid = claimed
    elif claimed > 0 and Beatmap.objects.filter(beatmapsetid=claimed).exists():
        raise SubmitError("That beatmap set is already on Qlute. Only maps you made yourself can be submitted.")
    else:
        if not staff:
            since = timezone.now() - timedelta(days=1)
            if Submission.objects.filter(owner=username, created__gte=since).count() >= 10:
                raise SubmitError("You've submitted 10 new sets today. Try again tomorrow.")
        setid = next_set_id()

    # Difficulty ids: keep the ones this set already has (matched by id, then by name).
    by_id = {b.beatmapid: b for b in existing}
    by_name = {b.difficulty.strip().lower(): b for b in existing}
    used = set()
    new_id = next_map_id()
    for c in charts:
        own = by_id.get(_int(c.meta.get("BeatmapID"), 0)) or by_name.get(c.version.lower())
        if own is not None and own.beatmapid not in used:
            c.beatmapid = own.beatmapid
        else:
            c.beatmapid = new_id
            new_id += 1
        used.add(c.beatmapid)
    removed = [b for b in existing if b.beatmapid not in used]

    # Mapper: players can't pick it in the .osu, it's always the uploader's name. Only the team uploads with the
    # file's Creator. An update keeps the set's current mapper, which the owner / team may have changed on the website.
    if staff:
        mapper = None  # each difficulty keeps its own Creator
    elif existing:
        mapper = existing[0].mapper or (sub.owner if sub else username)
    else:
        mapper = username
    for c in charts:
        c.meta["Creator"] = clean(mapper if mapper is not None else (c.meta.get("Creator") or username), "Creator")

    first = charts[0]
    title, artist = first.meta.get("Title", ""), first.meta.get("Artist", "")
    filename = safe_name(f"{setid} {artist} - {title}")[:200] + ".osz"
    replaced = {}
    for c in charts:
        c.lines = set_metadata(c.lines, {"BeatmapID": c.beatmapid, "BeatmapSetID": setid, "Creator": c.meta["Creator"]})
        replaced[c.member] = c.text()

    # ---- files
    write_osz(z, os.path.join(songs_dir(), filename), replaced, drop=set(skipped))
    if sub is not None and sub.filename and sub.filename != filename:
        try:
            os.remove(os.path.join(songs_dir(), sub.filename))
        except FileNotFoundError:
            pass
    adir = assets_dir(setid)
    os.makedirs(adir, exist_ok=True)
    for c in charts:
        with open(os.path.join(adir, f"{c.beatmapid}.osu"), "w", encoding="utf-8") as f:
            f.write(replaced[c.member])
    for b in removed:
        try:
            os.remove(os.path.join(adir, f"{b.beatmapid}.osu"))
        except FileNotFoundError:
            pass
    names = z.namelist()
    has_preview = has_bg = False
    try:
        export_preview(z, _find(names, first.general.get("AudioFilename")), _int(first.general.get("PreviewTime"), 0),
                       os.path.join(adir, "preview.ogg"))
        has_preview = True
    except Exception as e:
        print(f"[submit] preview for set {setid} failed: {e}")
    bg = next((_find(names, c.background) for c in charts if _find(names, c.background)), None)
    if bg:
        try:
            export_background(z.read(bg), os.path.join(adir, "bg.jpg"))
            has_bg = True
        except Exception as e:
            print(f"[submit] background for set {setid} failed: {e}")

    # ---- set details for the catalog. Video / storyboard come from the files (the game leaves videos out of
    # uploads, so usually no video); genre, language and explicit are kept from the set's current rows.
    has_video = any(_find(names, c.video) for c in charts)
    has_storyboard = any(c.storyboard for c in charts) or any(n.lower().endswith(".osb") for n in names)
    keep = existing[0] if existing else None

    # ---- database
    now = timezone.now()
    with transaction.atomic():
        for c in charts:
            row = by_id.get(c.beatmapid) or Beatmap(beatmapid=c.beatmapid, beatmapsetid=setid, ranked=0, playcount=0)
            row.title = clean(c.meta.get("Title"), "Title")
            row.title_unicode = clean(c.meta.get("TitleUnicode") or c.meta.get("Title"), "TitleUnicode")
            row.artist = clean(c.meta.get("Artist"), "Artist")
            row.artist_unicode = clean(c.meta.get("ArtistUnicode") or c.meta.get("Artist"), "ArtistUnicode")
            row.difficulty = clean(c.version, "Version")
            row.mapper = c.meta["Creator"]
            row.tags = clean(c.meta.get("Tags"), "Tags")
            row.source = clean(c.meta.get("Source"), "Source")
            row.BPM = c.bpm
            row.pp = ppv2calc.calculate_ppv2(beatmap_text_compressed=c.lines).max_pp
            row.notecount = c.notes
            row.Level = ppv2calc.level_from_pp(row.pp)  # Lv 1 <= 5pp ... Lv 100 >= 1500pp
            row.Length = int(round(c.length_ms * 0.001))
            row.Accuracy = c.od
            row.beatmapfile = "/songs/" + filename
            row.backgroundpath = f"/song_assets/{setid}/bg.jpg" if has_bg or row.backgroundpath else ""
            row.previewpath = f"/song_assets/{setid}/preview.ogg" if has_preview or row.previewpath else ""
            row.chartfile = f"/song_assets/{setid}/{c.beatmapid}.osu"
            row.video = has_video
            row.storyboard = has_storyboard
            if keep is not None:
                row.genre, row.language, row.nsfw = keep.genre, keep.language, keep.nsfw
            row.save()
        Beatmap.objects.filter(beatmapsetid=setid, beatmapid__in=[b.beatmapid for b in removed]).delete()
        if sub is None:
            sub = Submission.objects.create(beatmapsetid=setid, owner=username, filename=filename)
        else:
            sub.filename = filename
            sub.uploads += 1
            sub.updated = now
            sub.save()

    return Result(
        setid=setid, updated=bool(existing), skipped=[os.path.basename(s) for s in skipped],
        beatmaps=[{"file": c.member, "version": c.version, "beatmapid": c.beatmapid} for c in charts],
        removed=[b.difficulty for b in removed],
    )


# ---------------------------------------------------------------- metadata edits (website / game)

SET_FIELDS = ("title", "title_unicode", "artist", "artist_unicode", "tags", "source")
OSU_KEY = {"title": "Title", "title_unicode": "TitleUnicode", "artist": "Artist", "artist_unicode": "ArtistUnicode",
           "tags": "Tags", "source": "Source", "mapper": "Creator"}


def edit_set(setid, changes, versions, by):
    """changes: {field: value} for SET_FIELDS (+ "mapper", "ranked" when the caller may); versions: {beatmapid: name}.

    Updates the beatmaps rows, the .osu files inside the .osz and the server's chart files, plus the names stored
    on scores. Returns the number of difficulties changed.
    """
    rows = list(Beatmap.objects.filter(beatmapsetid=setid))
    if not rows:
        raise SubmitError("That beatmap set doesn't exist.")
    ids = {r.beatmapid for r in rows}
    versions = {int(k): clean(v, "Version") for k, v in (versions or {}).items() if int(k) in ids}
    if any(not v for v in versions.values()):
        raise SubmitError("Difficulty names can't be empty.")
    final = {r.beatmapid: versions.get(r.beatmapid, r.difficulty) for r in rows}
    if len({v.strip().lower() for v in final.values()}) != len(final):
        raise SubmitError("Two difficulties can't have the same name.")
    for key in ("title", "artist", "mapper"):
        if key in changes and not changes[key]:
            raise SubmitError(f"The {key} can't be empty.")

    osu = {OSU_KEY[k]: v for k, v in changes.items() if k in OSU_KEY}
    with submit_lock():
        # ---- the .osz (what players download) and the server's chart copies
        osz = os.path.join(storage_root, rows[0].beatmapfile.lstrip("/")) if rows[0].beatmapfile else ""
        if (osu or versions) and osz and os.path.isfile(osz):
            with zipfile.ZipFile(osz) as z:
                replaced = {}
                for info in z.infolist():
                    if not info.filename.lower().endswith(".osu") or info.file_size > MAX_OSU_BYTES:
                        continue
                    c = parse_chart(info.filename, z.read(info))
                    bid = _int(c.meta.get("BeatmapID"), 0)
                    if bid not in ids:
                        continue
                    values = dict(osu)
                    if bid in versions:
                        values["Version"] = versions[bid]
                    replaced[info.filename] = "".join(set_metadata(c.lines, values))
                if replaced:
                    write_osz(z, osz, replaced)
        for r in rows:
            values = dict(osu)
            if r.beatmapid in versions:
                values["Version"] = versions[r.beatmapid]
            path = os.path.join(storage_root, (r.chartfile or "").lstrip("/"))
            if values and r.chartfile and os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
                with open(path, "w", encoding="utf-8") as f:
                    f.write("".join(set_metadata(lines, values)))

        # ---- database
        with transaction.atomic():
            for r in rows:
                for k in ("title", "title_unicode", "artist", "artist_unicode", "tags", "source", "mapper"):
                    if k in changes:
                        setattr(r, k, changes[k])
                for k in ("ranked", "genre", "language", "nsfw"):
                    if k in changes:
                        setattr(r, k, changes[k])
                if r.beatmapid in versions:
                    r.difficulty = versions[r.beatmapid]
                r.save()
                score_fields = {}
                if "title" in changes:
                    score_fields["beatmapname"] = changes["title"]
                if "artist" in changes:
                    score_fields["artist"] = changes["artist"]
                if r.beatmapid in versions:
                    score_fields["beatmapdiff"] = versions[r.beatmapid]
                if score_fields:
                    Score.objects.filter(beatmap_id=r.beatmapid).update(**score_fields)
            # osu! sets: grabnew.py --meta-only copies `beatmapsets` onto `beatmaps`, so change it there too
            meta = {k: changes[k] for k in ("title", "title_unicode", "artist", "artist_unicode", "tags", "source",
                                            "ranked", "genre", "language", "nsfw") if k in changes}
            if meta:
                Beatmapset.objects.filter(beatmapsetid=setid).update(**meta)
            Submission.objects.filter(beatmapsetid=setid).update(edited_by=by, edited_at=timezone.now())
    return len(rows)
