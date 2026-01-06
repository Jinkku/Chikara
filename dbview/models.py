from django.db import models
from django.db.models import Func, F

class UnixTimestamp(Func):
    function = 'UNIX_TIMESTAMP'
    output_field = models.IntegerField()
class Score(models.Model):
    id = models.AutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=256, null=True, blank=True)
    beatmapname = models.CharField(max_length=256, null=True, blank=True)
    artist = models.TextField(null=True, blank=True)
    points = models.FloatField(null=True, blank=True)
    combo = models.IntegerField(null=True, blank=True)
    beatmap_id = models.IntegerField(null=True, blank=True)
    beatmapset_id = models.IntegerField(null=True, blank=True)
    max = models.IntegerField(null=True, blank=True)
    great = models.IntegerField(null=True, blank=True)
    meh = models.IntegerField(null=True, blank=True)
    bad = models.IntegerField(null=True, blank=True)
    beatmapdiff = models.CharField(max_length=256, null=True, blank=True)
    mods = models.CharField(max_length=48, null=True, blank=True)
    maxpoints = models.FloatField(null=True, blank=True)
    speed_multi = models.FloatField(null=False, blank=False, default=1)
    replay_path = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'scores'  
class User(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=256, null=True, blank=True)
    email_address = models.CharField(max_length=256, null=True, blank=True)
    password = models.CharField(max_length=64, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    stattime = models.IntegerField(null=True, blank=True)
    playtime = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    ranked_score = models.IntegerField(null=True, blank=True)
    ranked_points = models.IntegerField(null=True, blank=True)
    max = models.IntegerField(null=True, blank=True)
    great = models.IntegerField(null=True, blank=True)
    meh = models.IntegerField(null=True, blank=True)
    bad = models.IntegerField(null=True, blank=True)
    max_combo = models.IntegerField(null=True, blank=True)
    ranking = models.IntegerField(null=True, blank=True)
    money = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    
    class Meta:
        db_table = 'users'

class Beatmap(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.TextField(null=False, blank=True)
    title_unicode = models.TextField(null=False, blank=True)
    artist = models.TextField(null=False, blank=True)
    artist_unicode = models.TextField(null=False, blank=True)
    difficulty = models.TextField(null=False, blank=True)
    BPM = models.IntegerField(null=False, blank=True)
    ranked = models.IntegerField(null=False, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    mapper = models.TextField(null=False, blank=True)
    beatmapid = models.IntegerField(null=False, blank=True)
    beatmapsetid = models.IntegerField(null=False, blank=True)
    notecount = models.IntegerField(null=False, blank=True)
    pp = models.FloatField(null=True, blank=True)
    playcount = models.IntegerField(null=False, blank=True)
    beatmapfile = models.TextField(null=False, blank=True)

    
    class Meta:
        db_table = 'beatmaps' 