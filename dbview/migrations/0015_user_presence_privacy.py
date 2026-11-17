from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dbview', '0014_user_hide_country'),
    ]

    operations = [
        migrations.AddField(model_name='user', name='appear_offline', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='user', name='hide_activity', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='user', name='presence_friends_only', field=models.BooleanField(default=False)),
    ]
