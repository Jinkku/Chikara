"""Rebuild the profile graph history (rank / pp / ranked score per day) from the scores table.

    python manage.py backfill_stat_history [--days 90] [--overwrite]
"""
from django.core.management.base import BaseCommand

from Chikara import stathistory


class Command(BaseCommand):
    help = "Fill stat_history for past days from existing scores, then snapshot today."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=stathistory.DAYS)
        parser.add_argument("--overwrite", action="store_true", help="replace days that already have a row")

    def handle(self, *args, **opts):
        n = stathistory.backfill(days=opts["days"], overwrite=opts["overwrite"])
        self.stdout.write(f"wrote {n} history rows")
