from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dbview', '0007_score_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='bannerpath',
            field=models.TextField(blank=True, null=True),
        ),
    ]
