"""Notices used to be "every file in <storage>/events". Keep showing those, now as editable Notice rows."""
import os

from django.db import migrations

IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def import_notices(apps, schema_editor):
    Notice = apps.get_model("moderation", "Notice")
    if Notice.objects.exists():
        return
    from Chikara.settings import storage_root
    folder = os.path.join(storage_root, "events")
    if not os.path.isdir(folder):
        return
    for i, name in enumerate(sorted(os.listdir(folder))):
        if name.lower().endswith(IMAGE_EXTS):
            Notice.objects.create(image="events/" + name, text=os.path.splitext(name)[0][:200], position=i,
                                  created_by="(imported)")


class Migration(migrations.Migration):
    dependencies = [("moderation", "0002_cardborder_notice")]
    operations = [migrations.RunPython(import_notices, migrations.RunPython.noop)]
