"""Recomputes beatmaps.Level from beatmaps.pp with the game's level formula (Chikara/ppv2calc.py level_from_pp,
mirrored from Qlute's PerformanceCalculator.LevelFromPp: no 1..100 clamp, Lv 0 below 5pp). Only the formula
changed, so the stored pp is reused; nothing is re-rated."""
from django.db import migrations


def recompute(apps, schema_editor):
    from Chikara.ppv2calc import level_from_pp
    Beatmap = apps.get_model("dbview", "Beatmap")
    changed = []
    for b in Beatmap.objects.only("id", "pp", "Level").iterator(chunk_size=2000):
        level = level_from_pp(b.pp)
        if b.Level != level:
            b.Level = level
            changed.append(b)
    Beatmap.objects.bulk_update(changed, ["Level"], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("dbview", "0010_user_stattime_index"),
    ]

    operations = [
        migrations.RunPython(recompute, migrations.RunPython.noop),
    ]
