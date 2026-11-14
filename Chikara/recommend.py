"""Recommended difficulties: what a player should try next, from how they did on their best plays.

Used by apiv2/search?recommended=1 (Chikara/catalog.py): the game's Browse screen and the website's
/beatmaps page, "Recommended" category.

How the target is found (pp v3, see PP_SCORE_DESIGN.md):
  * Take the player's best TOP_PLAYS ranked plays (by pp), weighted 0.95^n like their total pp.
  * Each play says "this player can earn this many pp". The target is a map where a solid play
    (about 80% of its SS pp, e.g. ~95% accuracy with a miss or two) earns that much: pp x PUSH.
    Using the pp actually earned means a weak attempt on a far too hard map doesn't drag the
    target up, and a near-SS pushes it ~25% past that map.
  * Recommended difficulties: ranked, NoMod SS pp within RANGE of the target, not played yet;
    closest to the target first.
New players (no ranked plays yet) get NEW_PLAYER_PP, about Lv 4.
"""
import Chikara.ppv2calc as ppv2calc
from dbview.models import Score

TOP_PLAYS = 20
WEIGHT = 0.95
NEW_PLAYER_PP = 25.0
RANGE = (0.80, 1.25)      # min / max SS pp, as a share of the target
PUSH = 1.25               # target SS pp = earned pp x 1.25 (a solid play gets ~80% of a map's SS pp)


def profile(username):
    """The player's recommendation range (also sent to clients so they can explain it)."""
    plays = []
    if username:
        plays = list(Score.objects.filter(username=username, ranked=1, points__gt=0)
                     .order_by("-points").values_list("points", flat=True)[:TOP_PLAYS])
    num = den = 0.0
    w = 1.0
    for pp in plays:
        num += w * pp * PUSH
        den += w
        w *= WEIGHT
    target = num / den if den else NEW_PLAYER_PP
    low, high = max(1.0, target * RANGE[0]), target * RANGE[1]
    return {
        "target_pp": round(target, 1),
        "min_pp": round(low, 1),
        "max_pp": round(high, 1),
        "level": ppv2calc.level_from_pp(target),
        "min_level": ppv2calc.level_from_pp(low),
        "max_level": ppv2calc.level_from_pp(high),
        "based_on": len(plays),
    }
