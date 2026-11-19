"""
Server-side performance (pp v3) and score calculator.

The judging is an exact mirror of the Qlute client's mania judging, so a replay
gets the same judgements on the server as it did in-game. The client side lives in
Qlute/Script/Gameplay/Gameplay.cs (ProcessInputFrame / MissPass / JudgeDiff) and
Qlute/Script/Gameplay/PerformanceCalculator.cs (difficulty, pp, score, mod
multipliers). Change both together. The server is authoritative: the client's
numbers are only a preview.

Judging model (unchanged from v2):
  * Every replay line "t,col" is a key press processed on the game frame at
    song time t (whole ms). Consecutive lines with the same t are one frame.
  * Each frame, in order:
      1. late misses: every unhit note with min(t, song_end) - note_time > MISS_LATE_MS
      2. each press: spam check (< SPAM_COOLDOWN_MS since the last accepted press
         in that column -> forced miss on the column's first unhit note)
      3. each accepted press is taken by the first unhit note in its column
         (note order) and judged by diff = t - note_time
  * When the song ends, unhit notes with song_end - note_time > MISS_LATE_MS miss.

pp v3 (see PP_SCORE_DESIGN.md next to this file):
  * Star rating from rate-adjusted strain (jack + density), so DT/HT change the
    difficulty itself instead of a flat pp multiplier.
  * Max pp from stars with a capped length bonus (no length farming).
  * Play pp = max pp * accuracy curve * miss curve. Misses no longer divide all
    pp earned so far, so a miss costs the same wherever it happens.

Score:
  * NoMod scale is 0 .. 1,000,000 (an SS is exactly 1,000,000).
    900,000 accuracy portion + 100,000 combo portion.
  * Mods scale it by the score multiplier (DT 1.25x -> 1,150,000 max, NF -> 500,000).
  * The base score is two integer ratios (exact in IEEE doubles), so client
    and server agree to the point.
"""
import math
import re
import statistics
from dataclasses import dataclass, field

PP_VERSION = 3


@dataclass
class GameplayResult:
    perfect: int = 0
    great: int = 0
    meh: int = 0
    bad: int = 0
    combo: int = 0
    max_combo: int = 0
    note_count: int = 0
    pp: float = 0.0          # pp of this play (mods included). Same as `points`.
    max_pp: float = 0.0      # pp of an SS on this map with these mods
    points: float = 0.0      # pp of this play (kept for older callers)
    max_points: float = 0.0  # same as max_pp (kept for older callers)
    score: int = 0           # 0..1,000,000 on NoMod, times the score multiplier with mods
    star_rating: float = 0.0
    multiplier: float = 1.0  # score multiplier
    rate: float = 1.0
    bad_combo: int = 0
    health: int = 150
    unstable_rate: float = 0.0
    hit_log: list = field(default_factory=list)  # [(note_time, column, offset_ms)] of every hit, in order
    combo_portion_num: int = 0   # internal: sum of weight * min(combo, COMBO_CAP)

    @property
    def accuracy(self) -> float:
        """Matches C# ReloadAccuracy: (max + great/2 + meh/3) / total"""
        total = self.perfect + self.great + self.meh + self.bad
        if total == 0:
            return 0.0
        return (self.perfect + (self.great / 2) + (self.meh / 3)) / total


# ---------------------------------------------------------------------------
# Constants (keep in sync with the client)
# ---------------------------------------------------------------------------

SPAM_COOLDOWN_MS = 80     # Gameplay.SPAM_COOLDOWN_MS
MISS_LATE_MS = 206        # Gameplay.MISS_LATE_MS
NODE_SIZE = 54            # Gameplay.nodeSize
PERFECT_JUDGE_MIN = 120   # SettingsOperator.PerfectJudgeMin
MAX_HEALTH = 150          # HealthBar.MaxHealth

# Score weights in tenths so score stays integer: 1, 0.7, 0.3, 0.
# All Perfect = 1,000,000, all Great = 700,000, all Meh = 300,000 on NoMod.
W_PERFECT, W_GREAT, W_MEH = 10, 7, 3

# Score
SCORE_ACC_PORTION = 900_000
SCORE_COMBO_PORTION = 100_000
COMBO_CAP = 400           # combo stops adding weight after this, so one miss costs the same anywhere

# Difficulty (strain model)
SECTION_MS = 400.0        # strain peaks are taken per 400 ms of real (rate-adjusted) time
INDIVIDUAL_DECAY = 0.125  # per-column strain left after 1 s (jacks)
OVERALL_DECAY = 0.30      # whole-hand strain left after 1 s (density / streams / chords)
INDIVIDUAL_ADD = 2.0
OVERALL_ADD = 1.0
PEAK_WEIGHT = 0.90        # sorted section peaks are summed with this decay
STAR_SCALE = 0.028

# Performance
PP_SCALE = 1.243         # 1.13 (Hommarju - Slluuddggee [Slliimmee] SS = 124pp, its osu!mania value) + 10%
PP_STAR_POWER = 2.8
LENGTH_BONUS_MAX = 0.15   # up to +15% ...
LENGTH_BONUS_NOTES = 2000 # ... reached at this many notes, flat after
GREAT_BASE = 0.999        # each (length-normalised) Great keeps 99.9% of the pp
MEH_BASE = 0.995          # each Meh keeps 99.5%
MISS_BASE = 0.98          # each miss keeps 98%
MISS_NORMAL_NOTES = 1000  # maps longer than this get a lighter per-miss penalty

PP_MOD_FACTOR = {         # pp only; rate mods are handled by the star rating
    "NF": 0.90,
    "SL": 1.04,
    "BT": 1.08,
    "AM": 0.50,
}
SCORE_MOD_FACTOR = {      # score only, applied in this order after the rate factor
    "NF": 0.50,
    "SL": 1.05,
    "BT": 1.15,
    "AM": 0.50,
}
MOD_ORDER = ("NF", "SL", "BT", "AM")


# ---------------------------------------------------------------------------
# Mods
# ---------------------------------------------------------------------------

def get_rate(mods: str, speed: float = 1.0) -> float:
    """Playback rate, rounded to 0.01 so client floats and server text agree."""
    mods = mods or ""
    if "DT" not in mods and "HT" not in mods:
        return 1.0
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(speed) or speed <= 0:
        return 1.0
    return math.floor(speed * 100.0 + 0.5) / 100.0


def rate_score_factor(rate: float) -> float:
    """Continuous: 1.25x -> 1.15, 1.5x -> 1.30, 0.75x -> 0.65, 0.5x -> 0.30."""
    if rate > 1.0:
        return 1.0 + 0.6 * (rate - 1.0)
    if rate < 1.0:
        return max(0.1, 1.0 - 1.4 * (1.0 - rate))
    return 1.0


def get_multiplier(mods: str, speed: float = 1.0) -> float:
    """Score multiplier. `mods` is the client's alias string (e.g. "NFDT")."""
    mods = mods or ""
    m = rate_score_factor(get_rate(mods, speed))
    for mod in MOD_ORDER:
        if mod in mods:
            m *= SCORE_MOD_FACTOR[mod]
    return m


def pp_mod_factor(mods: str) -> float:
    mods = mods or ""
    m = 1.0
    for mod in MOD_ORDER:
        if mod in mods:
            m *= PP_MOD_FACTOR[mod]
    return m


# ---------------------------------------------------------------------------
# Difficulty and performance
# ---------------------------------------------------------------------------

def star_rating(notes, rate: float = 1.0) -> float:
    """
    `notes`: (column, time_ms) of the map (real columns, not Random-mod ones).
    Every note decays the strains by the real time since the previous note, then
    adds to its own column (jacks) and to the overall strain (density, chords).
    The highest strain in every 400 ms section is kept; the sorted peaks are
    summed with weight 0.9^k, so a map's hardest parts dominate and length only
    adds a little.
    """
    if not notes:
        return 0.0
    objs = sorted((t, col) for col, t in notes)
    individual = [0.0, 0.0, 0.0, 0.0]
    overall = 0.0
    peaks: list[float] = []
    prev_t = objs[0][0] / rate
    section_end = prev_t + SECTION_MS
    peak = 0.0
    for t_raw, col in objs:
        t = t_raw / rate
        while t > section_end:
            peaks.append(peak)
            peak = 0.0
            section_end += SECTION_MS
        dt = (t - prev_t) / 1000.0
        if dt > 0:
            ind_decay = INDIVIDUAL_DECAY ** dt
            for c in range(4):
                individual[c] *= ind_decay
            overall *= OVERALL_DECAY ** dt
        individual[col] += INDIVIDUAL_ADD
        overall += OVERALL_ADD
        strain = individual[col] + overall
        if strain > peak:
            peak = strain
        prev_t = t
    peaks.append(peak)
    peaks.sort(reverse=True)
    total = 0.0
    weight = 1.0
    for p in peaks:
        total += p * weight
        weight *= PEAK_WEIGHT
    return total * STAR_SCALE


def max_performance(stars: float, note_count: int, mods: str = "") -> float:
    """pp of an SS."""
    if note_count <= 0:
        return 0.0
    length_bonus = 1.0 + LENGTH_BONUS_MAX * min(1.0, note_count / LENGTH_BONUS_NOTES)
    return PP_SCALE * max(stars - 0.15, 0.05) ** PP_STAR_POWER * length_bonus * pp_mod_factor(mods)


# Scaled with PP_SCALE (+10%), so a map keeps the same level as before the pp boost.
LEVEL_MIN_PP = 5.5       # Lv 1 at exactly 5.5 pp, Lv 0 below
LEVEL_MAX_PP = 1650.0    # Lv 100 at 1650 pp (and higher above it)
LEVEL_CURVE = 0.8        # < 1: levels rise faster at low pp (Lv 7 = 55-65pp, Lv 50 = ~690pp)


def level_from_pp(pp: float) -> int:
    """Map level from its NoMod SS pp. Exact mirror of the game's PerformanceCalculator.LevelFromPp:
    (int)(1 + 99 * ((pp - 5.5) / 1644.5) ^ 0.8), truncated, no clamping (maps over 1650pp go past Lv 100).
    Below 5.5pp the power of a negative number is NaN in C#, which .NET (9+) converts to 0: those maps are Lv 0."""
    if pp is None or pp != pp:
        return 0
    x = (pp - LEVEL_MIN_PP) / (LEVEL_MAX_PP - LEVEL_MIN_PP)
    if x < 0:
        return 0
    return int(1.0 + 99.0 * x ** LEVEL_CURVE)


def performance(max_pp: float, note_count: int, perfect: int, great: int, meh: int, bad: int) -> float:
    """pp of a play. Order-independent: only the judgement counts matter.
    Notes that were never judged (replay ended early) count as misses."""
    if note_count <= 0:
        return 0.0
    bad = max(bad, note_count - perfect - great - meh)
    norm = min(1.0, MISS_NORMAL_NOTES / note_count)
    great_factor = GREAT_BASE ** (great * norm)
    meh_factor = MEH_BASE ** (meh * norm)
    miss_factor = MISS_BASE ** (bad * norm)
    return max_pp * great_factor * meh_factor * miss_factor


def combo_portion_max(note_count: int) -> int:
    """W_PERFECT * sum(min(i, COMBO_CAP) for i in 1..note_count), closed form."""
    n = note_count
    if n <= COMBO_CAP:
        s = n * (n + 1) // 2
    else:
        s = COMBO_CAP * (COMBO_CAP + 1) // 2 + (n - COMBO_CAP) * COMBO_CAP
    return W_PERFECT * s


def compute_score(note_count: int, perfect: int, great: int, meh: int, bad: int,
                  combo_portion_num: int, multiplier: float) -> int:
    """Every miss takes off one perfect note's accuracy value (SCORE_ACC_PORTION / note_count);
    the score never goes below 0."""
    if note_count <= 0:
        return 0
    acc_num = W_PERFECT * perfect + W_GREAT * great + W_MEH * meh
    acc_den = W_PERFECT * note_count
    combo_den = combo_portion_max(note_count)
    miss_num = W_PERFECT * max(bad, 0)
    # Every numerator/denominator is an integer below 2^53, so each division is one
    # correctly rounded IEEE double op: C# gets the exact same bits.
    base = (SCORE_ACC_PORTION * acc_num) / acc_den + (SCORE_COMBO_PORTION * combo_portion_num) / combo_den
    base -= (SCORE_ACC_PORTION * miss_num) / acc_den
    if base < 0:
        base = 0.0
    return int(math.floor(base * multiplier + 0.5))


# ---------------------------------------------------------------------------
# .NET System.Random(seed) (the legacy seeded algorithm), for the Random mod
# ---------------------------------------------------------------------------

class DotNetRandom:
    MBIG = 2147483647
    MSEED = 161803398

    def __init__(self, seed: int):
        seed_array = [0] * 56
        subtraction = self.MBIG if seed == -2147483648 else abs(seed)
        mj = self.MSEED - subtraction
        seed_array[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            seed_array[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += self.MBIG
            mj = seed_array[ii]
        for _ in range(1, 5):
            for i in range(1, 56):
                seed_array[i] -= seed_array[1 + (i + 30) % 55]
                if seed_array[i] < 0:
                    seed_array[i] += self.MBIG
        self._seed = seed_array
        self._inext = 0
        self._inextp = 21

    def _internal_sample(self) -> int:
        inext = self._inext + 1
        if inext >= 56:
            inext = 1
        inextp = self._inextp + 1
        if inextp >= 56:
            inextp = 1
        ret = self._seed[inext] - self._seed[inextp]
        if ret == self.MBIG:
            ret -= 1
        if ret < 0:
            ret += self.MBIG
        self._seed[inext] = ret
        self._inext = inext
        self._inextp = inextp
        return ret

    def next(self, min_value: int, max_value: int) -> int:
        return int(self._internal_sample() * (1.0 / self.MBIG) * (max_value - min_value)) + min_value


# ---------------------------------------------------------------------------
# Beatmap parsing (mirrors the client)
# ---------------------------------------------------------------------------

def _try_float(s: str):
    try:
        return float(s.strip())
    except ValueError:
        return None


def _try_int(s: str):
    s = s.strip()
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s)
    return None


def _parse_beatmap(lines: list[str]):
    """OD and song end time (last hit object time)."""
    od = 0.0
    last_note_time = 0
    in_hit = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line == "[HitObjects]":
            in_hit = True
            continue
        if line.startswith("["):
            in_hit = False
            continue
        if not in_hit and ":" in line:
            key, value = line.split(":", 1)
            if key.strip() == "OverallDifficulty":
                v = _try_float(value)
                od = v if v is not None else 0.0
        if in_hit:
            parts = re.split(r"[,:]", line)
            if len(parts) < 3:
                continue
            note_time = _try_int(parts[2])
            if note_time is not None:
                last_note_time = note_time
    return od, last_note_time


def _shuffled_columns(seed: int) -> list[int]:
    """Gameplay.ShuffledColumns: Random mod = the 4 columns shuffled once (Fisher-Yates on .NET Random(seed)),
    rerolled until it isn't the unshuffled order (at most 32 tries)."""
    rnd = DotNetRandom(seed)
    cols = [0, 1, 2, 3]
    for _attempt in range(32):
        for i in range(len(cols) - 1, 0, -1):
            j = rnd.next(0, i + 1)
            cols[i], cols[j] = cols[j], cols[i]
        if cols != [0, 1, 2, 3]:
            break
    return cols


def _load_notes(lines: list[str], random_seed, legacy_random: bool = True):
    """
    Gameplay.ReloadBeatmap: (column, time) in file order, duplicates
    (same time + column) skipped, Random mod columns from the replay seed.
    Replays with a "#Random: columns" line shuffle whole columns; older ones (legacy_random) gave every note its
    own random column.
    """
    notes: list[tuple[int, int]] = []
    seen = set()
    shuffle = _shuffled_columns(random_seed) if random_seed is not None and not legacy_random else None
    rnd = DotNetRandom(random_seed) if random_seed is not None and shuffle is None else None
    in_hit = False
    for raw in lines:
        if raw.strip() == "[HitObjects]":
            in_hit = True
            continue
        if not in_hit:
            continue
        if not raw.strip() or raw.startswith("["):
            break
        section = re.split(r"[:,]", raw)
        t = int(section[2].strip())
        if rnd is not None:
            col = rnd.next(0, 4)
        else:
            col = min(3, max(0, math.floor(int(section[0].strip()) * 4 / 512.0)))
            if shuffle is not None:
                col = shuffle[col]
        if (t, col) in seen:
            continue
        seen.add((t, col))
        notes.append((col, t))
    return notes


def _read_lines(path_or_lines):
    if isinstance(path_or_lines, (list, tuple)):
        return list(path_or_lines)
    if hasattr(path_or_lines, "readlines"):
        return path_or_lines.readlines()
    with open(path_or_lines, encoding="utf-8-sig", errors="replace") as f:
        return f.read().split("\n")


def _parse_replay(lines: list[str]):
    header: dict[str, str] = {}
    presses: list[tuple[int, int]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if ": " in line:
                k, v = line[1:].split(": ", 1)
                header[k.strip()] = v.strip()
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        t, col = _try_int(parts[0]), _try_int(parts[1])
        if t is None or col is None or not 0 <= col < 4:
            continue
        presses.append((t, col))
    return header, presses


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_ppv2(
    replay_file: str = "",
    beatmap_file: str = "",
    beatmap_text_compressed="",
    mods: str | None = None,
    speed: float | None = None,
    **_ignored,
) -> GameplayResult:
    """
    Re-plays `replay_file` on `beatmap_file` exactly like the client and rates it.

    `mods` / `speed` default to the replay's #Mods / #Multiplier header.
    With no replay, returns the map's SS values (pp = max_pp, score = SS score).
    """
    osu_lines = _read_lines(beatmap_text_compressed if beatmap_text_compressed != "" else beatmap_file)
    header, presses = ({}, []) if replay_file == "" else _parse_replay(_read_lines(replay_file))

    if mods is None:
        mods = header.get("Mods", "")
    if speed is None:
        speed = _try_float(header.get("Multiplier", "1")) or 1.0
    mods = mods or ""
    rate = get_rate(mods, speed)
    mult = get_multiplier(mods, speed)

    od, song_end = _parse_beatmap(osu_lines)
    map_notes = _load_notes(osu_lines, None)
    n = len(map_notes)
    stars = star_rating(map_notes, rate)
    max_pp = max_performance(stars, n, mods)

    if replay_file == "":
        # Only the map's values were asked for (beatmap import): no need to simulate a play.
        ss = compute_score(n, n, 0, 0, 0, combo_portion_max(n), mult)
        return GameplayResult(note_count=n, pp=max_pp, max_pp=max_pp, points=max_pp,
                              max_points=max_pp, score=ss, star_rating=stars,
                              multiplier=mult, rate=rate, perfect=n, max_combo=n)

    seed = None
    if "RND" in mods:
        seed = _try_int(header.get("Seed", "")) or 0
    random_columns = header.get("Random", "") == "columns"  # newer replays: Random shuffles whole columns
    notes = map_notes if seed is None else _load_notes(osu_lines, seed, legacy_random=not random_columns)

    result = _simulate(notes, presses, od, song_end)
    result.note_count = n
    result.star_rating = stars
    result.rate = rate
    result.multiplier = mult
    result.max_pp = result.max_points = max_pp
    result.pp = result.points = performance(max_pp, n, result.perfect, result.great, result.meh, result.bad)
    result.score = compute_score(n, result.perfect, result.great, result.meh, result.bad, result.combo_portion_num, mult)
    return result


def _simulate(notes, presses, od, song_end) -> GameplayResult:
    result = GameplayResult(health=MAX_HEALTH)

    # Judge windows (Gameplay._EnterTree): OD is truncated to int, float32 scale.
    import struct

    def f32(x: float) -> float:
        return struct.unpack("f", struct.pack("f", x))[0]

    scale = f32(f32(1.0) - f32(int(od) / f32(10.0)))
    pw = int(max(16.0, f32(PERFECT_JUDGE_MIN * scale)))
    gw = pw * 4
    mw = pw * 6

    def add_hit(weight: int):
        result.combo += 1
        result.combo_portion_num += weight * min(result.combo, COMBO_CAP)
        result.bad_combo = 0

    def judge(diff: int) -> bool:
        x = diff + NODE_SIZE
        if -pw - 5 < x < pw + 15:
            result.perfect += 1
            add_hit(W_PERFECT)
            result.health = min(MAX_HEALTH, result.health + 5 * (result.combo // 100) + 1)
        elif -(gw // 2) - 5 < x < (gw // 2) + 15:
            result.great += 1
            add_hit(W_GREAT)
            result.health = min(MAX_HEALTH, result.health + 3 * (result.combo // 300) + 1)
        elif -(mw // 2) - 15 < x < (mw // 2) + 15:
            result.meh += 1
            add_hit(W_MEH)
            result.health = min(MAX_HEALTH, result.health + 1 * (result.combo // 500) + 1)
        else:
            return False
        hit_offsets.append(float(diff))
        return True

    hit = [False] * len(notes)
    by_col: list[list[int]] = [[], [], [], []]
    for i, (col, _) in enumerate(notes):
        by_col[col].append(i)
    col_ptr = [0, 0, 0, 0]               # first possibly-unhit index in by_col
    by_time = sorted(range(len(notes)), key=lambda i: notes[i][1])
    miss_ptr = 0
    last_press = [None, None, None, None]
    hit_offsets: list[float] = []

    def miss(i: int):
        result.bad += 1
        result.combo = 0
        result.bad_combo += 1
        result.health = max(0, result.health - 5 * result.bad_combo)
        hit[i] = True

    def first_unhit(col: int):
        lst = by_col[col]
        p = col_ptr[col]
        while p < len(lst) and hit[lst[p]]:
            p += 1
        col_ptr[col] = p
        return lst[p] if p < len(lst) else None

    def miss_pass(t: int):
        nonlocal miss_ptr
        limit = min(t, song_end) - MISS_LATE_MS   # note_time < limit -> miss
        while miss_ptr < len(by_time) and notes[by_time[miss_ptr]][1] < limit:
            i = by_time[miss_ptr]
            if not hit[i]:
                miss(i)
            miss_ptr += 1

    k = 0
    while k < len(presses):
        t = presses[k][0]
        frame = []
        while k < len(presses) and presses[k][0] == t:
            frame.append(presses[k][1])
            k += 1

        miss_pass(t)
        accepted = [False] * 4
        for col in frame:
            lp = last_press[col]
            if lp is not None and 0 <= t - lp < SPAM_COOLDOWN_MS:
                i = first_unhit(col)
                if i is not None:
                    miss(i)
                continue
            last_press[col] = t
            accepted[col] = True
        # Hits in note order (the client loops notes in order).
        targets = sorted(i for i in (first_unhit(c) for c in range(4) if accepted[c]) if i is not None)
        for i in targets:
            if judge(t - notes[i][1]):
                result.hit_log.append((notes[i][1], notes[i][0], t - notes[i][1]))
                hit[i] = True
        result.max_combo = max(result.max_combo, result.combo)

    miss_pass(song_end)

    result.unstable_rate = round(statistics.pstdev(hit_offsets) * 10.0, 2) if len(hit_offsets) >= 2 else 0.0
    return result
