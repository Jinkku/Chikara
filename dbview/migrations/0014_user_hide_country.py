from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dbview', '0013_user_country'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='hide_country',
            field=models.BooleanField(default=False),
        ),
    ]
