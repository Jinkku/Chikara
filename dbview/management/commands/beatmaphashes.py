"""Fills beatmaps.filehash for every map (python manage.py beatmaphashes).

Run once after migrating, and any time after bulk changes to the chart files. Maps whose hash is already current are
skipped (only their file is stat'ed). Maps are also hashed on demand (Chikara/beatmaphash.py), but a map whose
.osu has no BeatmapID can only be found by its hash, so it has to be hashed before a player asks for it.
"""
from django.core.management.base import BaseCommand

from Chikara import beatmaphash
from dbview.models import Beatmap


class Command(BaseCommand):
    help = "Hash every beatmap's chart file (beatmaps.filehash), so the game's copies can be recognised."

    def handle(self, *args, **options):
        done = missing = 0
        rows = Beatmap.objects.exclude(chartfile="").only("id", "chartfile", "filehash", "filehash_mtime")
        total = rows.count()
        for i, row in enumerate(rows.iterator(chunk_size=500), 1):
            if beatmaphash.current_hash(row):
                done += 1
            else:
                missing += 1
            if i % 1000 == 0:
                self.stdout.write(f"{i}/{total}")
        self.stdout.write(self.style.SUCCESS(f"{done} hashed, {missing} without a chart file"))
