"""Recognising a player's copy of a beatmap by the hash of its .osu file.

The game sends the hash of the .osu it plays (Qlute: Script/Singleton/BeatmapHash.cs) with leaderboard requests and
score submissions. A copy that was edited (or is older/newer than the server's) has a different hash, so it gets no
leaderboard and its scores aren't accepted. When a chart file is rewritten, its old hash is kept (BeatmapHashHistory),
so a copy with an old hash is reported as outdated and the game offers to update it. The beatmap/set ids the game
sends are only a hint, used to tell "your copy differs from ours" apart from "we don't know this map".

The hash is SHA-256 of the file's bytes with a leading UTF-8 BOM removed and CRLF / lone CR turned into LF. The
server keeps charts with "\\n" endings (recheck.py and submissions read them with universal newlines), while the .osz
players download usually has CRLF; line endings don't change the chart, any other edit changes the hash.
"""
import hashlib
import os

from Chikara.settings import storage_root
from dbview.models import Beatmap, BeatmapHashHistory

OK, OUTDATED, MODIFIED, UNKNOWN = "ok", "outdated", "modified", "unknown"


def normalize(data: bytes) -> bytes:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(normalize(data)).hexdigest()


def chart_path(row):
    return os.path.join(storage_root, (row.chartfile or "").lstrip("/")) if row.chartfile else ""


def current_hash(row):
    """The hash of the row's chart file as it is now. Stored on the row; hashed again only when the file changed
    (the hash it had before goes into BeatmapHashHistory, so copies of the old version are recognised as outdated)."""
    path = chart_path(row)
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    if row.filehash and row.filehash_mtime == mtime:
        return row.filehash
    with open(path, "rb") as f:
        h = hash_bytes(f.read())
    if row.filehash and row.filehash != h:
        BeatmapHashHistory.objects.get_or_create(beatmap=row.id, filehash=row.filehash)
    Beatmap.objects.filter(id=row.id).update(filehash=h, filehash_mtime=mtime)
    row.filehash, row.filehash_mtime = h, mtime
    return h


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def find(filehash, beatmapid=None, beatmapsetid=None):
    """(row, status) for the game's copy of a map. The row is the server's map (None only for UNKNOWN):
    OK        the copy is the server's chart
    OUTDATED  the copy is an older version of that map's chart (update it)
    MODIFIED  the hinted ids are a map we have, but the copy is neither its chart nor an older one (edited)
    UNKNOWN   not a map the server has"""
    filehash = (filehash or "").strip().lower()
    if len(filehash) != 64:
        return None, UNKNOWN
    for row in Beatmap.objects.filter(filehash=filehash):
        if current_hash(row) == filehash:  # the stored hash may be from before the chart was rewritten
            return row, OK
    beatmapid, beatmapsetid = _int(beatmapid), _int(beatmapsetid)
    if beatmapid > 0:
        rows = Beatmap.objects.filter(beatmapid=beatmapid)
        if beatmapsetid > 0:
            rows = rows.filter(beatmapsetid=beatmapsetid)
        rows = list(rows)
        for row in rows:  # not hashed yet (new rows), or hashed before the file changed (logs the old hash)
            if current_hash(row) == filehash:
                return row, OK
    else:
        rows = []
    for old in BeatmapHashHistory.objects.filter(filehash=filehash).order_by("-replaced").values_list("beatmap", flat=True):
        row = Beatmap.objects.filter(id=old).first()
        if row is not None and current_hash(row) != filehash:
            return row, OUTDATED
    if rows:
        return rows[0], MODIFIED
    return None, UNKNOWN
