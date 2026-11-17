"""Player level from total ranked score.

Early levels come quickly and each one takes a bit more score than the last, up to level 100 at LEVEL_100_SCORE;
after 100 every level costs the same flat amount (like osu!):

    score needed for level n (n <= 100) = A * (n - 1)^2,  A = LEVEL_100_SCORE / 99^2  (~102k)
    level n > 100                       = LEVEL_100_SCORE + (n - 100) * AFTER_100

    Lv 2 ~100k (about one play), Lv 10 ~8.3M, Lv 25 ~59M, Lv 50 ~245M, Lv 100 1B, then +20M per level.

The server is the source of truth: the game shows the "level" / "level_pct" it's sent (score submits, login,
profiles). Medals for reaching level 50 / 100 earned under the old formula (score / 2M) are kept (views.py).
"""
import math

LEVEL_100_SCORE = 1_000_000_000
AFTER_100 = 20_000_000
A = LEVEL_100_SCORE / 99 ** 2


def score_for(level):
    """Total ranked score needed to reach `level` (level 1 = 0)."""
    if level <= 1:
        return 0
    if level <= 100:
        return int(math.ceil(A * (level - 1) ** 2))
    return LEVEL_100_SCORE + (level - 100) * AFTER_100


def level_float(score):
    """Level with the progress into it as a fraction, e.g. 12.37."""
    score = max(0, score or 0)
    if score >= LEVEL_100_SCORE:
        return 100 + (score - LEVEL_100_SCORE) / AFTER_100
    return 1 + math.sqrt(score / A)


def level(score):
    """Whole level, 1 and up."""
    lv = int(level_float(score))
    while score_for(lv + 1) <= (score or 0):  # guard against float rounding at exact boundaries
        lv += 1
    return max(1, lv)


def progress(score):
    """{"level", "pct" (0-99 into the next level), "into", "needed" (score into / for this level), "next" (total for next)}."""
    lv = level(score)
    lo, hi = score_for(lv), score_for(lv + 1)
    into = max(0, (score or 0) - lo)
    span = max(1, hi - lo)
    return {"level": lv, "pct": min(99, int(into * 100 / span)), "into": into, "needed": span, "next": hi}
