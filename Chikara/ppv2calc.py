import math
import re
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameplayResult:
    perfect: int = 0
    great: int = 0
    meh: int = 0
    bad: int = 0
    combo: int = 0
    max_combo: int = 0
    pp: float = 0.0
    max_pp: float = 0.0
    bad_combo: int = 0
    health: float = 100.0
    unstable_rate: float = 0.0

    @property
    def accuracy(self) -> float:
        """Matches C# ReloadAccuracy: (max + great/2 + meh/3) / total"""
        total = self.perfect + self.great + self.meh + self.bad
        if total == 0:
            return 0.0
        return (self.perfect + (self.great / 2) + (self.meh / 3)) / total


def _heal(health: float, amount: float) -> float:
    return min(100.0, health + amount)


def _damage(health: float, amount: float) -> float:
    return max(0.0, health - amount)


# ---------------------------------------------------------------------------
# Spam protection
# ---------------------------------------------------------------------------

# Minimum ms between accepted key-down events per column.
# Matches the C# SPAM_COOLDOWN_MS = 80f constant.
SPAM_COOLDOWN_MS: float = 80.0


def _is_spam(
    col: int,
    event_time_ms: int,
    last_press_time: list[float],
) -> bool:
    """
    Returns True if this key-down on `col` arrived too soon after the last
    accepted one (i.e. the player is spamming).
    Updates last_press_time in-place when the press is accepted.
    """
    elapsed = event_time_ms - last_press_time[col]
    if 0 <= elapsed < SPAM_COOLDOWN_MS:
        return True
    last_press_time[col] = float(event_time_ms)
    return False


# ---------------------------------------------------------------------------
# Unstable Rate
# ---------------------------------------------------------------------------

def _compute_unstable_rate(hit_offsets: list[float]) -> float:
    """
    UR = std_dev(hit_offsets) * 10  — matches osu!mania convention.
    Each offset is (actual_hit_time - note_time) in ms;
    negative = early, positive = late.
    Returns 0.0 when fewer than 2 hits have been recorded.
    """
    if len(hit_offsets) < 2:
        return 0.0
    return statistics.pstdev(hit_offsets) * 10.0


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

def check_judge(
    timing_diff: int,
    perfect_window: int,
    great_window: int,
    meh_window: int,
    note_ppv2xp: float,
    result: GameplayResult,
    hit_offsets: list[float],
    missed: bool = False,
) -> int:
    """
    Mirrors C# checkjudge().

    C# window setup (from _Ready):
        PerfectJudge = PerfectJudgeMin - min(5 * OD, 50)
        GreatJudge   = PerfectJudge * 4
        MehJudge     = PerfectJudge * 6

    C# hit condition (symmetric around HitPoint):
        Perfect: abs(diff) < PerfectJudge
        Great:   abs(diff) < GreatJudge / 2  (= PerfectJudge * 2)
        Meh:     abs(diff) < MehJudge / 2    (= PerfectJudge * 3)

    Returns: 0=Perfect, 1=Great, 2=Meh, 3=Miss, 4=No judgement

    hit_offsets is updated in-place for Perfect/Great/Meh hits so that
    unstable rate can be computed afterwards via _compute_unstable_rate().
    """
    abs_diff = abs(timing_diff)

    if not missed and abs_diff < perfect_window:
        result.perfect += 1
        result.combo += 1
        result.max_combo = max(result.max_combo, result.combo)
        result.pp += note_ppv2xp
        result.bad_combo = 0
        result.health = _heal(result.health, (5 * (result.combo / 100)) + 1)
        hit_offsets.append(float(timing_diff))
        return 0

    elif not missed and abs_diff < great_window / 2:
        result.great += 1
        result.combo += 1
        result.max_combo = max(result.max_combo, result.combo)
        result.pp += note_ppv2xp * 0.6
        result.bad_combo = 0
        result.health = _heal(result.health, (3 * (result.combo / 300)) + 1)
        hit_offsets.append(float(timing_diff))
        return 1

    elif not missed and abs_diff < meh_window / 2:
        result.meh += 1
        result.combo += 1
        result.max_combo = max(result.max_combo, result.combo)
        result.pp += note_ppv2xp * 0.3
        result.bad_combo = 0
        result.health = _heal(result.health, (1 * (result.combo / 500)) + 1)
        hit_offsets.append(float(timing_diff))
        return 2

    elif missed:
        result.bad += 1
        result.combo = 0
        result.pp = max(0.0, result.pp / 1.2)
        result.bad_combo += 1
        result.health = _damage(result.health, 5 * result.bad_combo)
        return 3

    else:
        return 4


# ---------------------------------------------------------------------------
# Spam-miss helper
# ---------------------------------------------------------------------------

def _trigger_spam_miss(
    col: int,
    notes: list[tuple[int, int, float]],
    note_hit: list[bool],
    result: GameplayResult,
) -> None:
    """
    Mirrors C# TriggerSpamMiss(): finds the first unhit visible note in
    `col` and registers a forced miss.
    """
    for idx, (note_col, _note_time, ppv2xp) in enumerate(notes):
        if note_col == col and not note_hit[idx]:
            result.bad += 1
            result.combo = 0
            result.pp = max(0.0, result.pp - (ppv2xp * 4))
            result.bad_combo += 1
            result.health = _damage(result.health, 5 * result.bad_combo)
            note_hit[idx] = True
            break


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_ppv2(
    replay_file: str = "",
    beatmap_file: str = "",
    beatmap_text_compressed="",
) -> GameplayResult:
    PP_BASE = 0.045
    MAX_PERFECT = 105  # C#: PerfectJudgeMin

    standalone = replay_file == ""
    if not standalone:
        with open(replay_file) as f:
            raw_replay = f.readlines()

    if beatmap_text_compressed == "":
        with open(beatmap_file) as f:
            osu_lines = f.readlines()
    else:
        if hasattr(beatmap_text_compressed, 'readlines'):
            osu_lines = beatmap_text_compressed.readlines()
        else:
            osu_lines = beatmap_text_compressed

    # ── Parse timing point ────────────────────────────────────────────────────
    tp_start = osu_lines.index("[TimingPoints]\n") + 1
    ho_start = osu_lines.index("[HitObjects]\n")
    beat_length = float(osu_lines[tp_start].split(",")[1])

    # ── Parse Overall Difficulty → judge windows ──────────────────────────────
    diff_start = osu_lines.index("[Difficulty]\n") + 1
    event_start = osu_lines.index("[Events]\n")
    od = 0.0
    for line in osu_lines[diff_start:event_start]:
        if line.startswith("OverallDifficulty"):
            od = float(line.split(":")[1].strip())
            break

    # Matches C# _Ready():
    #   PerfectJudge = PerfectJudgeMin - min(5 * OD, 50)  → e.g. OD8 → 65ms
    #   GreatJudge   = PerfectJudge * 4
    #   MehJudge     = PerfectJudge * 6
    perfect_window = MAX_PERFECT - min(5 * od, 50)
    great_window   = perfect_window * 4
    meh_window     = perfect_window * 6

    if not standalone:
        # ── Parse replay frames: (time_ms, key) ──────────────────────────────
        replay_frames: list[tuple[int, int]] = []
        for line in raw_replay:
            line = line.strip()
            if line and not line.startswith("#"):
                t, key = line.split(",")
                replay_frames.append((int(t), int(key)))

    # ── Parse hit objects → (column, time_ms, ppv2xp) ────────────────────────
    notes: list[tuple[int, int, float]] = []
    multi_pp  = 1
    last_pp_t = -1

    for line in osu_lines[ho_start + 1:]:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[,:]', line)
        col   = int(math.floor(int(parts[0]) * 4 / 512.0))
        t_ms  = int(parts[2])

        if t_ms < last_pp_t + beat_length:
            multi_pp += 1
        else:
            last_pp_t = t_ms
            multi_pp  = 1

        ppv2xp = PP_BASE * multi_pp
        notes.append((col, t_ms, ppv2xp))

    result    = GameplayResult()
    result.max_pp = round(sum(n[2] for n in notes), 4)

    # ── Main judge loop ───────────────────────────────────────────────────────
    if not standalone:
        # Spam protection: track last accepted key-down time per column (ms).
        # Initialised to -inf so the first press is always accepted.
        last_press_time: list[float] = [float('-inf')] * 4

        # Track which notes have already been hit/missed (for spam-miss lookup).
        note_hit: list[bool] = [False] * len(notes)

        # Accumulate hit offsets for UR calculation.
        hit_offsets: list[float] = []

        replay_idx = 0
        for note_idx, (col, note_time, ppv2xp) in enumerate(notes):
            if note_hit[note_idx]:
                continue  # already consumed by a spam-miss

            judged = False

            while replay_idx < len(replay_frames):
                r_time, r_key = replay_frames[replay_idx]
                diff = r_time - note_time

                if diff < -meh_window / 2:
                    # Frame is too early — check spam before advancing
                    if _is_spam(r_key, r_time, last_press_time):
                        _trigger_spam_miss(r_key, notes, note_hit, result)
                    replay_idx += 1
                    continue

                if diff <= meh_window / 2:
                    # Frame is inside the hit window
                    if _is_spam(r_key, r_time, last_press_time):
                        # Spammed key → force miss, skip this frame
                        _trigger_spam_miss(r_key, notes, note_hit, result)
                        replay_idx += 1
                        judged = True  # note was consumed as spam-miss
                        break

                    judge = check_judge(
                        timing_diff    = diff,
                        perfect_window = perfect_window,
                        great_window   = great_window,
                        meh_window     = meh_window,
                        note_ppv2xp    = ppv2xp,
                        result         = result,
                        hit_offsets    = hit_offsets,
                    )
                    if judge != 4:
                        note_hit[note_idx] = True
                        replay_idx += 1
                        judged = True
                    break

                break  # frame is past meh window → note will be missed

            if not judged:
                check_judge(
                    timing_diff    = 0,
                    perfect_window = perfect_window,
                    great_window   = great_window,
                    meh_window     = meh_window,
                    note_ppv2xp    = ppv2xp,
                    result         = result,
                    hit_offsets    = hit_offsets,
                    missed         = True,
                )
                note_hit[note_idx] = True

        # ── Unstable Rate ─────────────────────────────────────────────────────
        # std_dev(hit_offsets) * 10, matching osu!mania convention.
        # Only perfect/great/meh hits contribute; misses and spam-misses do not.
        result.unstable_rate = round(_compute_unstable_rate(hit_offsets), 2)

    result.pp     = round(max(0.0, result.pp), 4)
    result.max_pp = round(result.max_pp, 4)
    return result