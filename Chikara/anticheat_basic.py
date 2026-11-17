"""Basic anti-cheat for score submissions, used when the private Chikara/anticheat.py isn't installed.

The server already re-plays every replay (ppv2calc), so judgements, combo, pp and score can't be faked.
This adds a few simple checks on the replay itself. Each check ends up as

  pass   nothing wrong
  flag   suspicious: the score is kept and the team gets a report to look at
  fail   the score is refused and the team gets a report in the admin panel (with every check as evidence)
  skip   not enough data to judge

  Replay player / map / mods   the replay was recorded by this player, on this map, with these mods
  Copied replay                the presses aren't an exact copy of another player's replay of the same map
  Timing                       the hits aren't all on the exact same millisecond offset (plain autoplay)
  pp jump                      one play isn't worth more than max(25% of their pp, 600pp)
  Level jump                   a map far above the levels they usually play is flagged (score kept, team reviews)

Set AUTO_BAN = True to also ban (permanently, or BAN_HOURS) when a check fails; by default the team decides.
To write your own, copy this file to Chikara/anticheat.py (git-ignored) and change it: views.py uses that one first.
"""
import os
from dataclasses import dataclass, field

from django.utils import timezone

from Chikara import ppv2calc

REPORTER = "[anti-cheat]"
AUTO_BAN = False
BAN_HOURS = None          # None = permanent (only with AUTO_BAN)
MIN_HITS = 100            # the timing check needs this many hits
MIN_UR = 5                # unstable rate below this (every hit within ~0.5 ms): autoplay
MOD_ALIASES = ("AT", "DT", "HT", "SL", "BT", "RND", "NF")
LEVEL_JUMP_ADD = 20         # a play above Lv max(usual + this, usual x LEVEL_JUMP_RATIO) is flagged ("usual": the
LEVEL_JUMP_RATIO = 2.0      # 90th percentile level of their last LEVEL_JUMP_PLAYS plays at LEVEL_JUMP_ACC+ accuracy)
LEVEL_JUMP_ACC = 0.80       # only plays at this accuracy count, both the new one and the earlier ones
LEVEL_JUMP_PLAYS = 50
LEVEL_JUMP_MIN_PLAYS = 10


@dataclass
class Verdict:
    checks: list = field(default_factory=list)   # [{"check", "status", "value", "limit"}]
    reject: str = ""                             # message for the player; empty = accepted
    ban_reason: str = ""
    duplicate: bool = False                      # the player re-sent their own replay: quietly refused

    def add(self, check, status, value, limit=""):
        self.checks.append({"check": check, "status": status, "value": str(value), "limit": str(limit)})

    @property
    def failed(self):
        return [c for c in self.checks if c["status"] == "fail"]

    @property
    def flagged(self):
        return [c for c in self.checks if c["status"] == "flag"]

    @property
    def ban(self):
        return bool(self.ban_reason)


def parse(replay_text):
    """(header dict, [(time_ms, column), ...]) from the replay text the game uploaded."""
    return ppv2calc._parse_replay(replay_text.split("\n"))


def _mods(s):
    return {m for m in MOD_ALIASES if m in (s or "")}


def _shifted_copy(a, b):
    """True if `a` is `b` with every press moved by the same amount (or not moved at all)."""
    if len(a) != len(b) or not a:
        return False
    shift = a[0][0] - b[0][0]
    return all(x[1] == y[1] and x[0] - y[0] == shift for x, y in zip(a, b))


def check(user, header, presses, result, beatmap_id, beatmapset_id, mods, speed, others,
          ranked=0, pp_limit=None, now=None, history=None, levels=None):
    """Run every check on one submission (same call as the private module).

    result:    ppv2calc.GameplayResult from re-playing the replay (None if the chart couldn't be read)
    others:    [(username, presses), ...] stored replays of the same map
    pp_limit:  most pp one play may give this player (ranked maps only)
    """
    v = Verdict()
    me = (user or "").casefold()

    rec = header.get("Username") or "?"
    v.add("Replay player", "pass" if rec.casefold() == me else "fail", rec, user)
    v.add("Replay map", "pass" if header.get("BeatmapID") == str(beatmap_id) else "fail",
          header.get("BeatmapID") or "?", beatmap_id)
    v.add("Replay mods", "pass" if _mods(header.get("Mods")) == _mods(mods) else "fail",
          header.get("Mods") or "none", mods or "none")

    copied_from = ""
    for other_user, other in others:
        if _shifted_copy(presses, other):
            if (other_user or "").casefold() == me:
                v.duplicate = True
            elif not copied_from:
                copied_from = other_user
    v.add("Copied replay", "fail" if copied_from else "pass",
          f"same presses as {copied_from}'s replay" if copied_from else f"no copy ({len(others)} replays compared)")

    hits = (result.perfect + result.great + result.meh) if result else 0
    if result and hits >= MIN_HITS:
        v.add("Timing (unstable rate)", "fail" if result.unstable_rate < MIN_UR else "pass",
              f"{result.unstable_rate} over {hits} hits", f"{MIN_UR}+")
    else:
        v.add("Timing (unstable rate)", "skip", f"{hits} hits", f"{MIN_HITS}+ hits")

    _level_jump(v, result, levels)

    if result and ranked and pp_limit is not None:
        v.add("pp jump", "fail" if result.points > pp_limit else "pass", f"{result.points:.0f}pp", f"{pp_limit:.0f}pp max")

    if v.duplicate:
        v.reject = "This replay was already submitted."
    elif v.failed:
        v.reject = "This play was rejected by the anti-cheat."
        v.ban_reason = f"Cheating detected by the anti-cheat: {', '.join(c['check'] for c in v.failed)} (map {beatmap_id})"
    return v


def player_levels(user, before=None, exclude_path=None):
    """Map levels (with their mods, ppv2calc.level_from_pp) of the player's latest LEVEL_JUMP_PLAYS stored plays
    at LEVEL_JUMP_ACC+ accuracy, newest first. `before`: only plays older than this (re-checking a stored score)."""
    from dbview.models import Score
    rows = Score.objects.filter(username=user, maxpoints__gt=1)
    if before is not None:
        rows = rows.filter(created__lt=before)
    if exclude_path:
        from Chikara.settings import storage_root
        rows = rows.exclude(replay_path=exclude_path[len(storage_root):] if exclude_path.startswith(storage_root) else exclude_path)
    out = []
    for mp, p, g, m, b in rows.order_by("-created").values_list("maxpoints", "max", "great", "meh", "bad")[:LEVEL_JUMP_PLAYS]:
        n = (p or 0) + (g or 0) + (m or 0) + (b or 0)
        if n and ((p or 0) + (g or 0) / 2 + (m or 0) / 3) / n >= LEVEL_JUMP_ACC:
            out.append(ppv2calc.level_from_pp(mp))
    return out


def _level_jump(v, result, levels):
    """Flag a play far above the levels this player usually plays (e.g. usually Lv 1-20, suddenly Lv 65)."""
    if not result or levels is None:
        return
    level = ppv2calc.level_from_pp(result.max_pp)
    if len(levels) < LEVEL_JUMP_MIN_PLAYS:
        v.add("Level jump", "skip", f"{len(levels)} earlier plays at {LEVEL_JUMP_ACC:.0%}+", f"{LEVEL_JUMP_MIN_PLAYS}+ plays")
        return
    usual = sorted(levels)[int(len(levels) * 0.9)]  # their 90th percentile: the top of what they usually play
    limit = max(usual + LEVEL_JUMP_ADD, int(usual * LEVEL_JUMP_RATIO))
    if result.accuracy < LEVEL_JUMP_ACC:
        v.add("Level jump", "pass", f"Lv {level} at {result.accuracy:.1%} (usually up to Lv {usual})",
              f"only judged at {LEVEL_JUMP_ACC:.0%}+ accuracy")
        return
    v.add("Level jump", "flag" if level > limit else "pass",
          f"Lv {level} at {result.accuracy:.1%}, usually up to Lv {usual}", f"up to Lv {limit}")


def stored_replays(beatmap_id, exclude_path=None):
    """[(username, presses)] of the stored replays of a map."""
    from Chikara.settings import storage_root
    from dbview.models import Score
    out = []
    for name, path in Score.objects.filter(beatmap_id=beatmap_id).exclude(replay_path=None).values_list("username", "replay_path"):
        full = storage_root + path
        if full == exclude_path or not os.path.isfile(full):
            continue
        try:
            out.append((name, ppv2calc._parse_replay(ppv2calc._read_lines(full))[1]))
        except OSError:
            pass
    return out


def player_urs(user, exclude_path=None):
    return None  # the basic version doesn't compare against the player's own history


def accepted(user, result=None):
    pass


def act(user, verdict, beatmap_id, map_name, replay_name, pp=None, acc=None):
    """Report a refused or flagged play to the team (every check as evidence); ban too if AUTO_BAN and refused.
    Returns the ban message for the game when the player was banned, else ""."""
    if verdict.duplicate or not (verdict.failed or verdict.flagged):
        return ""
    try:
        from moderation import service
        refused = bool(verdict.failed)
        banned = refused and AUTO_BAN and not service.is_staff(user)
        what = "Banned" if banned else "Refused" if refused else "Flagged (score kept)"
        details = [f"{what}: {map_name or 'map'} ({beatmap_id})"]
        details += [f"- {c['check']}: {c['value']}" for c in verdict.failed + verdict.flagged]
        rep, _ = service.file_report(REPORTER, user, "cheating", "\n".join(details),
                                     f"replay {os.path.basename(replay_name)}"[:512], "system")
        rep.evidence = (rep.evidence or []) + [{
            "at": int(timezone.now().timestamp()), "map": beatmap_id, "map_name": map_name or "",
            "replay": os.path.basename(replay_name), "outcome": "banned" if banned else "refused" if refused else "flagged",
            "checks": verdict.checks,
        }]
        rep.save(update_fields=["evidence"])
        if banned:
            return service.ban_message(service.ban(user, verdict.ban_reason, BAN_HOURS, REPORTER, report=rep))
    except Exception:
        import sentry_sdk
        sentry_sdk.capture_exception()
    return ""


def score_review(sc):
    """The basic checks on a stored score, for the score page (team only). No bot likelihood in this version."""
    from Chikara.settings import storage_root
    from dbview.models import Beatmap
    if not sc.replay_path:
        return {"error": "This score has no replay to check."}
    path = storage_root + sc.replay_path
    b = Beatmap.objects.filter(beatmapid=sc.beatmap_id).first()
    if not b or not b.chartfile or not os.path.isfile(path):
        return {"error": "The replay or the beatmap file is missing."}
    try:
        res = ppv2calc.calculate_ppv2(path, storage_root + b.chartfile, mods=sc.mods or "", speed=sc.speed_multi or 1)
    except Exception as err:
        return {"error": f"Couldn't re-play it: {type(err).__name__}"}
    header, presses = ppv2calc._parse_replay(ppv2calc._read_lines(path))
    v = check(sc.username, header, presses, res, sc.beatmap_id, sc.beatmapset_id, sc.mods, sc.speed_multi,
              stored_replays(sc.beatmap_id, exclude_path=path), levels=player_levels(sc.username, before=sc.created))
    return {"percent": None, "factors": [], "checks": [c for c in v.checks if c["check"] != "pp jump"]}
