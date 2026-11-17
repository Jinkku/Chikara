"""Daily rank / pp / ranked score history for the profile graph (dbview.StatHistory, one row per player per day).

- snapshot()   writes today's row for every ranked player: called after each ranked score submit (ranks shift
               for everyone, not just the player) and lazily once a day from the profile page.
- backfill()   rebuilds past days from the scores table (manage.py backfill_stat_history), so the graph
               has data straight away instead of filling up over 90 days.
- history()    the last N days for one player, oldest first, for the graph.
"""
import datetime
from collections import defaultdict

from django.db import transaction

from dbview.models import Score, StatHistory, User

PP_TOP_SCORES = 100  # same as views.PP_TOP_SCORES / recalc_ppv3
PP_WEIGHT = 0.95
DAYS = 90

_last_snapshot = None  # date of the last snapshot() in this process, so the profile page only triggers one a day


def _ranked_users():
    return list(User.objects.filter(restricted=False, ranked_points__gt=0).only("id", "username", "ranked_points", "ranked_score"))


def _write(day, rows):
    """rows: {user_id: (rank, points, score)} -> upsert that day's StatHistory rows."""
    existing = {h.user_id: h for h in StatHistory.objects.filter(date=day, user_id__in=list(rows))}
    new, changed = [], []
    for uid, (rank, points, score) in rows.items():
        h = existing.get(uid)
        if h is None:
            new.append(StatHistory(user_id=uid, date=day, rank=rank, points=points, score=score))
        elif (h.rank, h.points, h.score) != (rank, points, score):
            h.rank, h.points, h.score = rank, points, score
            changed.append(h)
    with transaction.atomic():
        StatHistory.objects.bulk_create(new, batch_size=500)
        StatHistory.objects.bulk_update(changed, ["rank", "points", "score"], batch_size=500)


def snapshot(day=None):
    """Today's rank / pp / ranked score for every ranked player. Rank is the position on /ranking (by pp)."""
    global _last_snapshot
    day = day or datetime.date.today()
    users = sorted(_ranked_users(), key=lambda u: (-(u.ranked_points or 0), u.username or ""))
    _write(day, {u.id: (i, u.ranked_points or 0, u.ranked_score or 0) for i, u in enumerate(users, 1)})
    _last_snapshot = day


def ensure_today():
    """Snapshot once a day even when nobody submits (rank can't change then, but the graph gets its point)."""
    if _last_snapshot != datetime.date.today():
        try:
            snapshot()
        except Exception:
            pass


def _pp(plays):
    """pp from a player's ranked plays: best play per map, top PP_TOP_SCORES, 0.95^n weighting (recalc_ppv3)."""
    seen, total, w = set(), 0.0, 1.0
    for s in sorted(plays, key=lambda s: s.points or 0, reverse=True):
        if s.beatmap_id in seen:
            continue
        seen.add(s.beatmap_id)
        total += (s.points or 0) * w
        w *= PP_WEIGHT
        if len(seen) >= PP_TOP_SCORES:
            break
    return int(round(total))


def backfill(days=DAYS, overwrite=False):
    """Rebuild the last `days` days from the scores table.

    pp is recomputed from the ranked plays set up to the end of each day. Ranked score counts down from the
    player's current total, taking off the score of each ranked play set after that day (older totals were
    added up under earlier score formulas, so this keeps the line ending on today's real number).
    Days that already have a row are kept unless overwrite=True. Returns the number of rows written.
    """
    today = datetime.date.today()
    users = {u.username: u for u in _ranked_users()}
    plays = defaultdict(list)
    for s in Score.objects.filter(ranked=1, username__in=list(users)).only(
            "username", "beatmap_id", "points", "score", "created").order_by("created"):
        plays[s.username].append(s)

    have = set() if overwrite else set(
        StatHistory.objects.filter(date__gte=today - datetime.timedelta(days=days)).values_list("user_id", "date"))
    written = 0
    for back in range(days, 0, -1):  # today itself comes from snapshot()
        day = today - datetime.timedelta(days=back)
        end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time())
        stats = []
        for name, u in users.items():
            before = [s for s in plays[name] if s.created < end]
            if not before:
                continue
            later = sum(s.score or 0 for s in plays[name] if s.created >= end)
            stats.append((u, _pp(before), max(0, (u.ranked_score or 0) - later)))
        stats = [x for x in stats if x[1] > 0]
        stats.sort(key=lambda x: (-x[1], x[0].username or ""))
        rows = {u.id: (i, pp, score) for i, (u, pp, score) in enumerate(stats, 1) if (u.id, day) not in have}
        if rows:
            _write(day, rows)
            written += len(rows)
    snapshot()
    return written


def history(user_id, days=DAYS):
    """[{"d": "YYYY-MM-DD", "rank": n|None, "pp": n, "score": n}, ...] oldest first, last `days` days."""
    since = datetime.date.today() - datetime.timedelta(days=days - 1)
    return [{"d": h.date.isoformat(), "rank": h.rank, "pp": h.points, "score": h.score}
            for h in StatHistory.objects.filter(user_id=user_id, date__gte=since).order_by("date")]
