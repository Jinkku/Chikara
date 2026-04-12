import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
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

SPAM_COOLDOWN_MS: float = 80.0


def _is_spam(
    col: int,
    event_time_ms: float,
    last_press_time: list[float],
) -> bool:
    elapsed = event_time_ms - last_press_time[col]
    if 0 <= elapsed < SPAM_COOLDOWN_MS:
        return True
    last_press_time[col] = float(event_time_ms)
    return False


# ---------------------------------------------------------------------------
# Unstable Rate
# ---------------------------------------------------------------------------

def _compute_unstable_rate(hit_offsets: list[float]) -> float:
    if len(hit_offsets) < 2:
        return 0.0
    return statistics.pstdev(hit_offsets) * 10.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_ppv2(
    replay_file: str = "",
    beatmap_file: str = "",
    beatmap_text_compressed="",
    frame_lag_ms: int = 10,
) -> GameplayResult:
    """
    Bugs fixed vs. the original implementation
    -------------------------------------------
    FIX 1 - round() instead of int() for PerfectJudge
        Python float64 gives 120 * 0.2 = 23.9999, so int() truncates to 23.
        C# float32 gives 24. Using round() matches C#.

    FIX 2 - great and meh windows halved
        C# checkjudge uses GreatJudge/2 and MehJudge/2 as the actual radii.
        The original code passed the full x4/x6 values, making windows twice
        as wide.

    FIX 3 - nodeSize=54 pixel offset applied to hit windows
        C# checkjudge tests (timing + nodeSize) relative to HitPoint.
        nodeSize=54 px = 54 ms at scrollspeed=1, shifting the entire window
        ~54 ms early. The asymmetric windows below encode this correctly.

    FIX 4 - spam check removed from the "too early" branch
        Previously _is_spam()/_trigger_spam_miss() were called for every frame
        predating the current note's window. _trigger_spam_miss() hunts forward
        and marks a future note as missed, corrupting the score. Early frames
        are now simply skipped.

    FIX 5 - per-column frame pointers instead of one shared replay_idx
        One shared index caused frames from column 0 to advance past frames
        that column 2 still needed.

    FIX 6 - frame_lag_ms applied to all frame times
        In Godot 4, _Input fires before _Process, so the est stored in the
        replay is stale by ~one game frame (~10 ms at 60 fps) relative to the
        est used by checkjudge.

    FIX 7 - phantom notes at song end not counted as misses
        The C# game ends the scene before its loop reaches the last 2 notes.
        They scroll off silently with no miss recorded.
    """
    PP_BASE     = 0.045
    MAX_PERFECT = 120
    NODE_SIZE   = 54
    FUDGE_P     = 5
    FUDGE_M     = 15

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
    diff_start  = osu_lines.index("[Difficulty]\n") + 1
    event_start = osu_lines.index("[Events]\n")
    od = 0.0
    for line in osu_lines[diff_start:event_start]:
        if line.startswith("OverallDifficulty"):
            od = float(line.split(":")[1].strip())
            break

    # FIX 1: round() matches C# (int)(float32) truncation.
    scale = 1 - (od / 10)
    PW = max(16, round(MAX_PERFECT * scale))  # PerfectJudge        e.g. 24 at OD8
    GW = round(PW * 4) // 2                  # GreatJudge / 2      e.g. 48
    MW = round(PW * 6) // 2                  # MehJudge  / 2       e.g. 72

    # FIX 2 + FIX 3: asymmetric windows in replay-diff space.
    #
    # C# checkjudge tests (timing + nodeSize) against +/-(judge + fudge) around
    # HitPoint, where timing = est - note_osu_time + HitPoint. Substituting:
    #
    #   diff = replay_t - note_osu_time   (negative = early, positive = late)
    #
    #   Perfect : -(PW + FUDGE_P + NODE_SIZE) < diff < PW + FUDGE_P - NODE_SIZE
    #   Great   : -(GW + FUDGE_P + NODE_SIZE) < diff < GW + FUDGE_P - NODE_SIZE
    #   Meh     : -(MW + FUDGE_M + NODE_SIZE) < diff < MW + FUDGE_M - NODE_SIZE
    #
    # At OD8: Perfect in (-83,-25), Great in (-107,-1), Meh in (-141,+33)
    P_LO = -(PW + FUDGE_P + NODE_SIZE)
    P_HI =   PW + FUDGE_P - NODE_SIZE
    G_LO = -(GW + FUDGE_P + NODE_SIZE)
    G_HI =   GW + FUDGE_P - NODE_SIZE
    M_LO = -(MW + FUDGE_M + NODE_SIZE)
    M_HI =   MW + FUDGE_M - NODE_SIZE

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

        notes.append((col, t_ms, PP_BASE * multi_pp))

    result        = GameplayResult()
    result.max_pp = round(sum(n[2] for n in notes), 4)

    if standalone:
        result.pp = result.max_pp
        return result

    # FIX 5: per-column frame lists.
    # FIX 4 (lead-in): drop frames with t < 0 — they predate all notes.
    # FIX 6: apply frame_lag_ms to every frame time.
    frames_by_col: dict[int, list[int]] = defaultdict(list)
    for line in raw_replay:
        line = line.strip()
        if line and not line.startswith("#"):
            t, key = line.split(",")
            t_int  = int(t)
            if t_int >= 0:
                frames_by_col[int(key)].append(t_int + frame_lag_ms)
    for c in range(4):
        frames_by_col[c].sort()

    # ── Main judge loop ───────────────────────────────────────────────────────
    last_press_time: list[float] = [float('-inf')] * 4
    frame_ptr:       dict[int, int] = {c: 0 for c in range(4)}
    note_hit:        list[bool]     = [False] * len(notes)
    hit_offsets:     list[float]    = []

    # FIX 7: detect song end for phantom note handling.
    song_end_ms = notes[-1][1] if notes else 0

    for note_idx, (col, note_time, ppv2xp) in enumerate(notes):
        if note_hit[note_idx]:
            continue

        col_frames = frames_by_col[col]
        ptr        = frame_ptr[col]

        # FIX 4: skip early frames with NO spam check.
        while ptr < len(col_frames) and col_frames[ptr] - note_time < M_LO:
            ptr += 1
        frame_ptr[col] = ptr

        judged = False

        if ptr < len(col_frames):
            r_time = col_frames[ptr]
            diff   = r_time - note_time

            if diff <= M_HI:
                orig_r = r_time - frame_lag_ms
                if _is_spam(col, orig_r, last_press_time):
                    # Spam-miss: consume the first unhit note in this column.
                    for idx, (nc, _, pv) in enumerate(notes):
                        if nc == col and not note_hit[idx]:
                            result.bad      += 1
                            result.combo     = 0
                            result.pp        = max(0.0, result.pp - pv * 4)
                            result.bad_combo += 1
                            result.health    = _damage(result.health, 5 * result.bad_combo)
                            note_hit[idx]    = True
                            break
                    frame_ptr[col] = ptr + 1
                    judged = True
                else:
                    frame_ptr[col] = ptr + 1
                    # FIX 2 + FIX 3: asymmetric range checks replace abs_diff < window.
                    if P_LO < diff < P_HI:
                        result.perfect   += 1
                        result.combo     += 1
                        result.max_combo  = max(result.max_combo, result.combo)
                        result.pp        += ppv2xp
                        result.bad_combo  = 0
                        result.health     = _heal(result.health, (5 * (result.combo / 100)) + 1)
                        hit_offsets.append(float(diff))
                        judged = True

                    elif G_LO < diff < G_HI:
                        result.great     += 1
                        result.combo     += 1
                        result.max_combo  = max(result.max_combo, result.combo)
                        result.pp        += ppv2xp * 0.6
                        result.bad_combo  = 0
                        result.health     = _heal(result.health, (3 * (result.combo / 300)) + 1)
                        hit_offsets.append(float(diff))
                        judged = True

                    elif M_LO < diff < M_HI:
                        result.meh       += 1
                        result.combo     += 1
                        result.max_combo  = max(result.max_combo, result.combo)
                        result.pp        += ppv2xp * 0.3
                        result.bad_combo  = 0
                        result.health     = _heal(result.health, (1 * (result.combo / 500)) + 1)
                        hit_offsets.append(float(diff))
                        judged = True

                    note_hit[note_idx] = judged

        if not judged:
            # FIX 7: phantom note — no frames left for this column and the note
            # is at or near song end. C# ends the scene before reaching it, so
            # no miss is recorded.
            if ptr >= len(col_frames) and note_time >= song_end_ms - beat_length * 2:
                note_hit[note_idx] = True
                continue

            # Regular miss.
            result.bad       += 1
            result.combo      = 0
            result.pp         = max(0.0, result.pp / 1.2)
            result.bad_combo += 1
            result.health     = _damage(result.health, 5 * result.bad_combo)
            note_hit[note_idx] = True

    # ── Unstable Rate ─────────────────────────────────────────────────────────
    result.unstable_rate = round(_compute_unstable_rate(hit_offsets), 2)

    result.pp     = round(max(0.0, result.pp), 4)
    result.max_pp = round(result.max_pp, 4)
    return result


