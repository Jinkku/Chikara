from django.db import models

# Usernames are stored as plain strings, like the scores and online tables do.


class StaffMember(models.Model):
    """The Qlute team. Being on it grants the team medal and access to the admin panel (website + game)."""
    ROLE_MOD = "mod"
    ROLE_ADMIN = "admin"
    ROLES = [(ROLE_MOD, "Moderator"), (ROLE_ADMIN, "Admin")]

    username = models.CharField(max_length=255, unique=True)
    role = models.CharField(max_length=16, choices=ROLES, default=ROLE_MOD)
    added_by = models.CharField(max_length=256, blank=True, default="")
    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class Report(models.Model):
    CATEGORIES = [
        ("cheating", "Cheating"),
        ("profile", "Inappropriate name or profile"),
        ("chat", "Chat abuse / harassment"),
        ("multiplayer", "Multiplayer abuse"),
        ("spam", "Spam"),
        ("other", "Other"),
    ]
    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"
    STATUSES = [(STATUS_OPEN, "Open"), (STATUS_RESOLVED, "Resolved"), (STATUS_DISMISSED, "Dismissed")]
    SOURCES = [("web", "Website"), ("game", "Game")]

    reporter = models.CharField(max_length=256, db_index=True)
    target = models.CharField(max_length=256, db_index=True)
    category = models.CharField(max_length=16, choices=CATEGORIES, default="other")
    details = models.TextField(blank=True, default="")
    context = models.CharField(max_length=512, blank=True, default="")  # e.g. "score 1234" or a quoted chat line
    source = models.CharField(max_length=8, choices=SOURCES, default="web")
    status = models.CharField(max_length=16, choices=STATUSES, default=STATUS_OPEN, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    handled_by = models.CharField(max_length=256, blank=True, default="")
    handled_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")  # what the team did about it

    def __str__(self):
        return f"#{self.id} {self.reporter} -> {self.target} ({self.category}, {self.status})"


class Ban(models.Model):
    """A ban restricts the account (users.restricted) until it expires or is lifted. expires=None means permanent."""
    username = models.CharField(max_length=256, db_index=True)
    reason = models.TextField()
    issued_by = models.CharField(max_length=256)
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(null=True, blank=True)
    report = models.ForeignKey(Report, null=True, blank=True, on_delete=models.SET_NULL, related_name="bans")
    # Still restricting the account. Cleared when it expires (checked lazily) or is lifted early.
    enforced = models.BooleanField(default=True, db_index=True)
    lifted_by = models.CharField(max_length=256, blank=True, default="")
    lifted_at = models.DateTimeField(null=True, blank=True)
    lift_note = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.username}: {self.reason[:40]} ({'permanent' if self.expires is None else self.expires})"


class Notice(models.Model):
    """A banner on the game's home screen (apiv2/getnotice). image is relative to the storage folder, e.g. "events/x.png"."""
    image = models.CharField(max_length=255)
    text = models.CharField(max_length=200, blank=True, default="")
    redirect = models.CharField(max_length=500, blank=True, default="")  # opened when the banner is clicked
    position = models.IntegerField(default=0, db_index=True)  # lower shows first
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=256, blank=True, default="")

    def __str__(self):
        return f"#{self.id} {self.text or self.image}"


class CardBorder(models.Model):
    """A card border players can pick in their settings (users.cardborder = "/" + image). Always 230x80."""
    name = models.CharField(max_length=64)
    image = models.CharField(max_length=255)  # relative to the storage folder, e.g. "cardborders/x.png"
    active = models.BooleanField(default=True)  # inactive: hidden from the picker, people using it keep it
    supporter_only = models.BooleanField(default=False)  # a supporter perk: hidden on players without supporter perks
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=256, blank=True, default="")

    def __str__(self):
        return self.name


class NewsPost(models.Model):
    """A news post on the website (/news). Written by the Qlute team (mods and admins) in the admin panel.
    body is osu!-style BBCode (Chikara/bbcode.py), like profile bios."""
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300, blank=True, default="")  # one line for the list and previews
    body = models.TextField(blank=True, default="")
    image = models.CharField(max_length=500, blank=True, default="")  # cover image url (https://...)
    author = models.CharField(max_length=256)
    published = models.BooleanField(default=True, db_index=True)  # False = draft, only the team sees it
    pinned = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)
    edited_by = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        db_table = 'news_posts'

    def __str__(self):
        return f"#{self.id} {self.title}"


class Supporter(models.Model):
    """Someone who supports Qlute (granted by an admin, e.g. after a donation). Perks: a profile banner and the
    supporter badge. `expires` None = forever. The Qlute team gets the perks too, without a row here."""
    username = models.CharField(max_length=255, unique=True)
    expires = models.DateTimeField(null=True, blank=True)
    granted_by = models.CharField(max_length=256, blank=True, default="")
    granted = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    note = models.CharField(max_length=300, blank=True, default="")

    def active(self, now=None):
        from django.utils import timezone
        return self.expires is None or self.expires > (now or timezone.now())

    def __str__(self):
        return f"{self.username} (until {self.expires or 'forever'})"


class SupportOrder(models.Model):
    """A supporter tag checkout through Xsolla (moderation/payments.py). Made when the buyer presses Buy;
    Xsolla's order_paid webhook marks it paid and grants the time, order_canceled takes it back."""
    STATUS_PENDING, STATUS_PAID, STATUS_CANCELED = "pending", "paid", "canceled"
    buyer = models.CharField(max_length=255, db_index=True)
    recipient = models.CharField(max_length=255, db_index=True)   # == buyer unless it's a gift
    sku = models.CharField(max_length=64)
    months = models.IntegerField()
    xsolla_order_id = models.BigIntegerField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=16, default=STATUS_PENDING, db_index=True)
    sandbox = models.BooleanField(default=False)
    amount = models.CharField(max_length=32, blank=True, default="")    # what Xsolla says was paid, e.g. "4.00 USD"
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"#{self.id} {self.buyer} -> {self.recipient} {self.months}m ({self.status})"
