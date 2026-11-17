"""The community rules (static/html/rules.html) as the moderation tools see them.

Every report category, warning, ban and profile reset points at one of these sections, so what the team does
always lines up with what the rules page says. Keys are the section anchors on /rules (e.g. /rules#fairplay).
"""
SECTIONS = [
    ("accounts", "1. Accounts"),
    ("fairplay", "2. Fair play"),
    ("conduct", "3. Conduct & chat"),
    ("multiplayer", "4. Multiplayer"),
    ("profiles", "5. Names & profiles"),
    ("beatmaps", "6. Beatmaps"),
]
NAMES = dict(SECTIONS)

# which rule section a report category is about (moderation.models.Report.CATEGORIES)
CATEGORY_RULE = {
    "account": "accounts",
    "cheating": "fairplay",
    "chat": "conduct",
    "spam": "conduct",
    "multiplayer": "multiplayer",
    "profile": "profiles",
    "beatmap": "beatmaps",
}


def clean(rule):
    return rule if rule in NAMES else ""


def label(rule):
    """'2. Fair play', or '' for none."""
    return NAMES.get(rule, "")


def link(rule):
    return f"/rules#{rule}" if rule in NAMES else "/rules"
