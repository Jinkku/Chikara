from django.db import models
from django.db.models import Func, F
from Chikara.settings import NoProfilePictureURL

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
    score = models.BigIntegerField(null=True, blank=True)  # competitive score (pp v3): 0..1,000,000 NoMod, x mod multiplier
    version = models.IntegerField(null=False, blank=False, default=2)
    speed_multi = models.FloatField(null=False, blank=False, default=1)
    replay_path = models.TextField(null=True, blank=True)
    ranked = models.IntegerField(null=False, blank=False, default=0)
    
    class Meta:
        db_table = 'scores'
        indexes = [models.Index(fields=['beatmap_id', 'ranked', '-score'], name='scores_map_score_idx')]
class User(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=256, null=True, blank=True)
    email_address = models.CharField(max_length=256, null=True, blank=True)
    password = models.CharField(max_length=128, null=True, blank=True)  # salted hash of SHA-256(password), Chikara/passwords.py; old rows: bare SHA-256 hex
    created = models.DateTimeField(auto_now_add=True)
    stattime = models.IntegerField(null=True, blank=True, db_index=True)
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
    money = models.FloatField(null=True, blank=True, default=0)
    accuracy = models.FloatField(null=True, blank=True)
    pfppath = models.TextField(null=False, blank=False, default=NoProfilePictureURL)
    restricted = models.BooleanField(null=False, blank=False, default=False)
    cardborder = models.TextField(null=True, blank=True)
    bio = models.TextField(null=True, blank=True)  # "About me" on the profile, set on the website's settings page
    bannerpath = models.TextField(null=True, blank=True)  # profile banner, "/banners/<file>" under DataURL (usersettings.banner)

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
    ranked = models.IntegerField(null=False, blank=False, default=0)
    created = models.DateTimeField(auto_now_add=True)
    mapper = models.TextField(null=False, blank=True)
    beatmapid = models.IntegerField(null=False, blank=False, default=0)
    beatmapsetid = models.IntegerField(null=False, blank=False, default=0, db_index=True)
    playcount = models.IntegerField(null=False, blank=False, default=0)
    pp = models.FloatField(null=True, blank=True)
    beatmapfile = models.TextField(null=False, blank=True)
    notecount = models.IntegerField(null=False, blank=False, default=0)
    Level = models.IntegerField(null=False, blank=False, default=0)
    Length = models.IntegerField(null=False, blank=False, default=0)
    Accuracy = models.FloatField(null=False, blank=False, default=0)
    backgroundpath = models.TextField(null=False, blank=True)
    previewpath = models.TextField(null=False, blank=True)
    chartfile = models.TextField(null=False, blank=True)
    tags = models.TextField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)  # .osu [Metadata] Source / osu! API source
    # Set-level details for the catalog filters (osu! ids, see Chikara/catalog.py). Copied from `beatmapsets` by
    # grabnew.py for osu! sets, set by the uploader / team for submitted ones. Nullable so recheck.py's INSERTs,
    # which don't name them, keep working; NULL = unknown (shown as Unspecified / no).
    genre = models.IntegerField(null=True, blank=True)
    language = models.IntegerField(null=True, blank=True)
    nsfw = models.BooleanField(null=True, blank=True)  # explicit content
    video = models.BooleanField(null=True, blank=True)
    storyboard = models.BooleanField(null=True, blank=True)


    class Meta:
        db_table = 'beatmaps'
class Beatmapset(models.Model):
    """osu! API metadata per set, written by regen/grabnew.py when a set is downloaded."""
    beatmapsetid = models.IntegerField(primary_key=True)
    artist = models.TextField(null=False, blank=True)
    artist_unicode = models.TextField(null=False, blank=True)
    title = models.TextField(null=False, blank=True)
    title_unicode = models.TextField(null=False, blank=True)
    tags = models.TextField(null=False, blank=True)
    status = models.IntegerField(null=False, default=0)  # raw osu! status: -2 graveyard .. 4 loved
    ranked = models.IntegerField(null=False, default=0)  # qlute legend: 1 ranked, 2 special, 0 unranked
    ranked_date = models.DateTimeField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)
    genre = models.IntegerField(null=True, blank=True)  # osu! genre_id
    language = models.IntegerField(null=True, blank=True)  # osu! language_id
    nsfw = models.BooleanField(null=True, blank=True)
    video = models.BooleanField(null=True, blank=True)
    storyboard = models.BooleanField(null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    fetched = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'beatmapsets'
class Hashes(models.Model):
    ostype = models.TextField(null=True, blank=True)
    hash = models.TextField(null=True, blank=True)
    class Meta:
        db_table = 'hashes'
class StatHistory(models.Model):
    """One row per player per day: rank, pp and ranked score, for the profile's 90-day graph (Chikara/stathistory.py)."""
    user_id = models.IntegerField(db_index=True)
    date = models.DateField()
    rank = models.IntegerField(null=True, blank=True)
    points = models.IntegerField(default=0)
    score = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'stat_history'
        unique_together = (('user_id', 'date'),)
