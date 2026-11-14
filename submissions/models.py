from django.db import models


class Submission(models.Model):
    """A beatmap set a player uploaded (from the game or the website). Sets crawled from osu! have no row here.

    Uploaded sets get ids from SUBMIT_ID_BASE up (see osz.py), far above osu!'s ids, so the two never clash.
    """
    beatmapsetid = models.IntegerField(primary_key=True)
    owner = models.CharField(max_length=256, db_index=True)
    filename = models.TextField(blank=True, default="")  # the .osz in <storage>/songs/
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    uploads = models.IntegerField(default=1)  # 1 + times the owner re-uploaded it
    edited_by = models.CharField(max_length=256, blank=True, default="")  # last metadata edit on the website
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'beatmap_submissions'

    def __str__(self):
        return f"{self.beatmapsetid} by {self.owner}"


class UploadSession(models.Model):
    """An .osz being sent in pieces (the web server refuses request bodies over 1 MB)."""
    token = models.CharField(max_length=32, unique=True)
    username = models.CharField(max_length=256, db_index=True)
    size = models.BigIntegerField()  # total bytes the client said it will send
    received = models.BigIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'beatmap_upload_sessions'


class BeatmapClaim(models.Model):
    """Someone asking to own a set that was crawled from osu!.

    They prove it by logging into osu!: the claim is only made when their osu! account is the set's creator.
    The Qlute team then accepts it (they become the owner, like an uploader) or declines it.
    """
    PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"
    STATUSES = [(PENDING, "Pending"), (ACCEPTED, "Accepted"), (DECLINED, "Declined")]

    beatmapsetid = models.IntegerField(db_index=True)
    username = models.CharField(max_length=256, db_index=True)  # the Qlute account
    osu_user_id = models.IntegerField()
    osu_username = models.CharField(max_length=64, blank=True, default="")
    set_creator = models.CharField(max_length=64, blank=True, default="")  # creator name on osu! at the time
    status = models.CharField(max_length=16, choices=STATUSES, default=PENDING, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    handled_by = models.CharField(max_length=256, blank=True, default="")
    handled_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        db_table = 'beatmap_claims'

    def __str__(self):
        return f"{self.username} claims {self.beatmapsetid} ({self.status})"
