from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dbview', '0006_user_bio'),
    ]

    operations = [
        migrations.AddField(
            model_name='score',
            name='score',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='score',
            index=models.Index(fields=['beatmap_id', 'ranked', '-score'], name='scores_map_score_idx'),
        ),
    ]
