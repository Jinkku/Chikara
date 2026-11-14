from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dbview', '0005_catalog_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='bio',
            field=models.TextField(blank=True, null=True),
        ),
    ]
