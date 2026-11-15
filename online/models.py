from django.db import models

# Online chat + multiplayer state. Usernames are stored as plain strings, like the scores table does.
# Chat messages themselves live in chat.Message (room = "#general" for public channels, "p<id>" for private rooms).


class PrivateChatRoom(models.Model):
    title = models.CharField(max_length=40)
    owner = models.CharField(max_length=256)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def key(self):
        return f"p{self.id}"

    def __str__(self):
        return f"{self.key} {self.title}"


class PrivateChatMember(models.Model):
    room = models.ForeignKey(PrivateChatRoom, on_delete=models.CASCADE, related_name="members")
    username = models.CharField(max_length=256)
    joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "username"], name="online_unique_member")]


class PrivateChatInvite(models.Model):
    room = models.ForeignKey(PrivateChatRoom, on_delete=models.CASCADE, related_name="invites")
    username = models.CharField(max_length=256)
    inviter = models.CharField(max_length=256)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "username"], name="online_unique_invite")]


class OnlineSession(models.Model):
    """One open chat websocket. A user is online while any of their sessions pinged recently."""
    username = models.CharField(max_length=256, db_index=True)
    channel_name = models.CharField(max_length=200, unique=True)
    last_seen = models.DateTimeField(db_index=True)


class MultiplayerRoom(models.Model):
    """Listing for an online room. The room itself runs on the host's game; the server only relays packets."""
    name = models.CharField(max_length=64)
    host = models.CharField(max_length=256)
    host_channel = models.CharField(max_length=200, unique=True)
    players = models.IntegerField(default=1)
    phase = models.IntegerField(default=0)
    beatmap = models.CharField(max_length=300, blank=True, default="")
    proto = models.IntegerField(default=0)
    game_version = models.CharField(max_length=32, blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(db_index=True)

    def __str__(self):
        return f"#{self.id} {self.name} ({self.host})"


class Friend(models.Model):
    """`username` added `friend` (one-way, like osu!). Both ways = mutual friends."""
    username = models.CharField(max_length=256, db_index=True)
    friend = models.CharField(max_length=256, db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["username", "friend"], name="online_unique_friend")]

    def __str__(self):
        return f"{self.username} -> {self.friend}"


class DirectChat(models.Model):
    """A one-to-one conversation. Its messages are chat.Message rows with room = key ("d<low id>-<high id>").
    Each side can hide it from their list; a new message shows it again."""
    low_id = models.IntegerField()
    high_id = models.IntegerField()
    low_name = models.CharField(max_length=256)
    high_name = models.CharField(max_length=256)
    hidden_low = models.BooleanField(default=False)
    hidden_high = models.BooleanField(default=False)
    updated = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["low_id", "high_id"], name="online_unique_dm")]

    @property
    def key(self):
        return f"d{self.low_id}-{self.high_id}"

    def other(self, user_id):
        return self.high_name if user_id == self.low_id else self.low_name

    def __str__(self):
        return f"{self.key} {self.low_name} / {self.high_name}"


class FavoriteBeatmap(models.Model):
    """`username` favourited beatmap set `beatmapsetid` (shown on their profile)."""
    username = models.CharField(max_length=256, db_index=True)
    beatmapsetid = models.IntegerField(db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["username", "beatmapsetid"], name="online_unique_favorite")]


class BeatmapComment(models.Model):
    """A comment on a beatmap set's page (website + the game's beatmap info)."""
    beatmapsetid = models.IntegerField(db_index=True)
    beatmapid = models.IntegerField(null=True, blank=True)  # the difficulty that was open when posting, if any
    username = models.CharField(max_length=256, db_index=True)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"#{self.id} {self.username} on {self.beatmapsetid}"


class Notification(models.Model):
    """Something that happened to `username` (shown under the bell in the website header).
    Messages from the same person stack into one unread row (`count`) instead of piling up."""
    KINDS = ["friend", "invite", "dm", "comment", "supporter", "medal"]
    username = models.CharField(max_length=256)
    kind = models.CharField(max_length=16)
    actor = models.CharField(max_length=256, blank=True, default="")
    text = models.CharField(max_length=300)
    link = models.CharField(max_length=300, blank=True, default="")
    count = models.IntegerField(default=1)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["username", "read"], name="online_notif_user_read")]

    def __str__(self):
        return f"{self.username}: {self.text}"


class MedalUnlock(models.Model):
    """The first time `username` earned medal number `medal` (its index in Chikara/views.py getmedals()).
    Medals themselves are still worked out live (MEDALS.md); this records when each one was first earned, so the
    game can pop it up once (`seen`: the game has shown it) and profiles can show the date."""
    username = models.CharField(max_length=256, db_index=True)
    medal = models.IntegerField()
    title = models.CharField(max_length=128)   # at the time it was earned, for reading the table by hand
    achieved = models.DateTimeField()
    seen = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["username", "medal"], name="online_unique_medal_unlock")]

    def __str__(self):
        return f"{self.username}: {self.title}"


class MedalBaseline(models.Model):
    """Players whose medals have been recorded at least once. The first check records everything they already had
    without popping it up, so existing players don't get a pile of old medals after the update."""
    username = models.CharField(max_length=255, unique=True)  # MariaDB: unique CharFields max 255
    created = models.DateTimeField(auto_now_add=True)
