"""Fills beatmaps.filehash for every map (python manage.py beatmaphashes [--workers N]).

Run once after migrating, and any time after bulk changes to the chart files. Maps whose hash is already current are
skipped (only their file is stat'ed). Maps are also hashed on demand (Chikara/beatmaphash.py), but a map whose
.osu has no BeatmapID can only be found by its hash, so it has to be hashed before a player asks for it.

Hashing runs on several threads (default 4): reading files and hashlib's SHA-256 release the GIL, so the threads
really run at the same time. Each thread uses its own database connection and closes it when it's done.
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand
from django.db import connection

from Chikara import beatmaphash
from dbview.models import Beatmap


class Command(BaseCommand):
    help = "Hash every beatmap's chart file (beatmaps.filehash), so the game's copies can be recognised."

    def add_arguments(self, parser):
        parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1),
                            help="threads hashing at the same time (default: 4, or fewer cores)")

    def handle(self, *args, **options):
        workers = max(1, options["workers"])
        rows = list(Beatmap.objects.exclude(chartfile="").only("id", "chartfile", "filehash", "filehash_mtime"))
        total = len(rows)
        lock = threading.Lock()
        counts = {"done": 0, "missing": 0, "seen": 0}

        def work(chunk):
            try:
                for row in chunk:
                    ok = beatmaphash.current_hash(row) is not None
                    with lock:
                        counts["done" if ok else "missing"] += 1
                        counts["seen"] += 1
                        if counts["seen"] % 1000 == 0:
                            self.stdout.write(f"{counts['seen']}/{total}")
            finally:
                connection.close()  # this thread's own connection

        # One slice per thread (every Nth row), so each thread keeps a single connection for the whole run.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for f in [pool.submit(work, rows[i::workers]) for i in range(workers)]:
                f.result()  # re-raise a thread's error here
        self.stdout.write(self.style.SUCCESS(
            f"{counts['done']} hashed, {counts['missing']} without a chart file ({workers} threads)"))
