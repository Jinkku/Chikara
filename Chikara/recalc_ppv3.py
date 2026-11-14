"""
One-shot recalculation to pp v3 + competitive score (see PP_SCORE_DESIGN.md).

Run from /Storage/Chikara after `python manage.py migrate dbview`:

    python -m Chikara.recalc_ppv3 --dry-run     # compute everything, write nothing, print a summary
    python -m Chikara.recalc_ppv3               # write it
    python -m Chikara.recalc_ppv3 --jobs 8      # parallel replay simulation

Steps:
  1. beatmaps.pp      <- NoMod SS pp of every chart, beatmaps.Level <- level from that pp (1..100)
  2. every score row  <- re-play its replay: judgement counts, combo, pp, max pp, score
                         (rows without a replay keep their counts, get 0 pp and the legacy score)
  3. every player     <- ranked_points (0.95^n over the best 100), weighted accuracy, ranking

Replaces rebuildpp.py and rebuildscores.py, which use the old pp formula.
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Chikara.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from Chikara import ppv2calc  # noqa: E402
from dbview.models import Beatmap, Score, User  # noqa: E402

PP_WEIGHT = 0.95
PP_TOP_SCORES = 100
from Chikara.settings import storage_root as STORAGE  # noqa: E402  (same root views.py uses)


def _legacy_score(sc):
    """Old accuracy-only score, for rows that have no replay to re-play."""
    total = (sc.max or 0) + (sc.great or 0) + (sc.meh or 0) + (sc.bad or 0)
    if total <= 0:
        return 0
    acc = ((sc.max or 0) + (sc.great or 0) // 2 + (sc.meh or 0) // 3) / total
    return int(round(acc * 1_000_000 * ppv2calc.get_multiplier(sc.mods or "", sc.speed_multi or 1)))


def _map_pp(chartfile):
    try:
        return ppv2calc.calculate_ppv2(beatmap_file=STORAGE + chartfile).max_pp, None
    except Exception as err:  # noqa: BLE001
        return None, f"{type(err).__name__}: {err}"


def _replay(job):
    score_id, replay, chart, mods, speed = job
    try:
        r = ppv2calc.calculate_ppv2(replay, chart, mods=mods, speed=speed)
        return score_id, (r.perfect, r.great, r.meh, r.bad, r.max_combo, r.points, r.max_points, r.score), None
    except Exception as err:  # noqa: BLE001
        return score_id, None, f"{type(err).__name__}: {err}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="compute everything, write nothing")
    ap.add_argument("--jobs", type=int, default=1, help="parallel replay simulations")
    ap.add_argument("--skip-maps", action="store_true", help="don't recompute beatmaps.pp")
    args = ap.parse_args()
    pool = ProcessPoolExecutor(args.jobs) if args.jobs > 1 else None
    run = (lambda fn, it: pool.map(fn, it, chunksize=16)) if pool else map
    print(f"storage root: {STORAGE!r}  ({'dry run' if args.dry_run else 'WRITING'}, {args.jobs} job(s))", flush=True)

    def progress(label, i, total):
        if i % 250 == 0 or i == total:
            print(f"  {label}: {i}/{total}", flush=True)

    # 1. beatmaps
    maps = {b.beatmapid: b for b in Beatmap.objects.all()}
    if not args.skip_maps:
        changed = failed = 0
        items = [b for b in maps.values() if b.chartfile]
        print(f"rating {len(items)} beatmaps...", flush=True)
        for i, (b, (pp, err)) in enumerate(zip(items, run(_map_pp, [b.chartfile for b in items])), 1):
            progress("maps", i, len(items))
            if err:
                failed += 1
                print(f"[map] {b.beatmapid} {b.chartfile}: {err}")
                continue
            b.pp = pp
            b.Level = ppv2calc.level_from_pp(pp)
            changed += 1
        if not args.dry_run:
            Beatmap.objects.bulk_update(items, ["pp", "Level"], batch_size=500)
        print(f"beatmaps: {changed} rated, {failed} failed")

    # 2. scores
    scores = list(Score.objects.all())
    jobs, no_replay = [], []
    for sc in scores:
        b = maps.get(sc.beatmap_id)
        replay = STORAGE + sc.replay_path if sc.replay_path else None
        if b is None:
            sc.ranked = 0
            no_replay.append(sc)
        elif replay and os.path.isfile(replay) and b.chartfile:
            sc.ranked = b.ranked
            jobs.append((sc.id, replay, STORAGE + b.chartfile, sc.mods or "", sc.speed_multi or 1))
        else:
            sc.ranked = b.ranked
            no_replay.append(sc)
    by_id = {sc.id: sc for sc in scores}
    failed = 0
    print(f"re-playing {len(jobs)} of {len(scores)} scores ({len(no_replay)} have no replay file)...", flush=True)
    for i, (score_id, res, err) in enumerate(run(_replay, jobs), 1):
        progress("scores", i, len(jobs))
        sc = by_id[score_id]
        if err:
            failed += 1
            print(f"[score] {score_id} {sc.username} map {sc.beatmap_id}: {err}")
            no_replay.append(sc)
            continue
        sc.max, sc.great, sc.meh, sc.bad, sc.combo, points, maxpoints, sc.score = res
        sc.points = points if sc.ranked else 0.000000001
        sc.maxpoints = maxpoints if sc.ranked else 0.01
        sc.version = ppv2calc.PP_VERSION
    for sc in no_replay:
        sc.points = 0
        sc.score = _legacy_score(sc)
    if pool:
        pool.shutdown()
    print(f"scores: {len(jobs) - failed} re-played, {len(no_replay)} without a usable replay (0 pp), {failed} failed")

    # 3. players
    best = {}
    for sc in scores:
        if sc.ranked == 1 and sc.username:
            best.setdefault(sc.username, []).append(sc)
    users = list(User.objects.all())
    for u in users:
        plays = sorted(best.get(u.username, []), key=lambda s: s.points or 0, reverse=True)
        seen, top = set(), []
        for s in plays:  # one play per map
            if s.beatmap_id not in seen:
                seen.add(s.beatmap_id)
                top.append(s)
            if len(top) >= PP_TOP_SCORES:
                break
        pp = acc = wsum = 0.0
        w = 1.0
        for s in top:
            pp += (s.points or 0) * w
            total = (s.max or 0) + (s.great or 0) + (s.meh or 0) + (s.bad or 0)
            if total:
                acc += ((s.max or 0) + (s.great or 0) / 2 + (s.meh or 0) / 3) / total * w
            wsum += w
            w *= PP_WEIGHT
        u.ranked_points = int(round(pp))
        u.accuracy = round(acc / wsum * 100, 2) if wsum else 0
    ordered = sorted((u for u in users if not u.restricted), key=lambda u: u.ranked_points or 0, reverse=True)
    for i, u in enumerate(ordered, 1):
        u.ranking = i

    print("top 10:")
    for u in ordered[:10]:
        print(f"  #{u.ranking:<3} {u.username:20s} {u.ranked_points:>7,}pp  {u.accuracy:6.2f}%")

    if args.dry_run:
        print("dry run: nothing written")
        return
    with transaction.atomic():
        Score.objects.bulk_update(scores, ["max", "great", "meh", "bad", "combo", "points", "maxpoints", "score",
                                           "version", "ranked"], batch_size=500)
        User.objects.bulk_update(users, ["ranked_points", "accuracy", "ranking"], batch_size=500)
    print("written")


if __name__ == "__main__":
    main()
