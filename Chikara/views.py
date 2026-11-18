from django.utils import timezone
from django.shortcuts import render, HttpResponse
import sentry_sdk
import traceback
from django.http import JsonResponse
from django.utils.html import escape
from Chikara.settings import BASE_DIR, STATIC_ROOT, REPLAYS,storage_root,client_id,client_secret, DataURL, AssetPath, SongFilePath, CheaterCardBorder, SiteURL
from django.db.models import Q
from random import randint
import json,hashlib
import urllib.parse
import sys,time,datetime,os,re
from ossapi import Ossapi
from dbview.models import *
import json
import Chikara.ppv2calc as ppv2calc
from moderation import service as moderation
from Chikara import passwords
starttime=timezone.now().timestamp()
perfbom=0.035
pulseinflation = 1.2
dedipoints=0.00000727
maxperf=800
nom=2
bio = "test"
pointsbase=1
allowspoof=0
restrictionnotice = "Your profile is restricted\nYou can't submit scores or interact with the community until it's lifted."
gradecolour=(81, 149, 194),(114, 123, 179),(105, 173, 99),(113, 85, 173),(173, 136, 61),(168, 70, 50),(20,20,20)
modsaliasab='AT','DT','HT','SL','BT','RND','NF' # Mods Alias
medals=("The End","You've made it"),("Baby Steps","Welcome to the Game"),(">~<","Impressive"),('Psycho','Dang you can read that?!'),('Welcome back Veteran','Glad to see you back'),('D-Ranker','Unrhythmic'),('S-Ranker','Like to show off. huh?'),('Supporter','Thanks for supporting Qlute! 💖'),('Sniper','First Comes, First Serve!'),('BreakThrough','Unstoppable'),('Top 100','You are the chosen one'),('Top 50','Almost There'),('Top 10','Grab some Popcorn 🍿'),('Top 1,000','Still a Virgin at this game are you?'),("Making the game better", "You are making the community better!"),("Team Moderator", "Keeping Qlute fun and fair for everyone") # Medals
# How to earn each original medal: the profile's hover hint (their descriptions are flavour text). Keep in step with
# getmedals() and MEDALS.md.
MEDAL_HINTS = {
    "The End": "Climb all the way to global rank #1. Nobody above you. Nobody.",
    "Baby Steps": "Earn your very first pp (more than 1). Everyone starts somewhere!",
    ">~<": "Chain a combo of over 1,000 without dropping it",
    "Psycho": "Clear a ranked Lv 30+ difficulty with Random and Double Time at 1.5x or faster, 70%+ accuracy",
    "Welcome back Veteran": "Come back and play after 30 days or more away",
    "D-Ranker": "Miss over 1,000 notes in total. A badge of honour, honestly",
    "S-Ranker": "Land over 1,000 Perfect hits in total",
    "Supporter": "Become a Qlute supporter (the Support page). Thank you <3",
    "Sniper": "Be the first to clear a ranked map that at least 2 other players clear after you (70%+ accuracy)",
    "BreakThrough": "Gain 100 pp or more within 7 days",
    "Top 100": "Break into the global top 100",
    "Top 50": "Push your way into the global top 50",
    "Top 10": "Crack the global top 10 and enjoy the show",
    "Top 1,000": "Sneak into the global top 1,000",
    "Making the game better": "Join the Qlute team and help build the game",
    "Team Moderator": "Become a Qlute moderator and keep the peace",
}
# More medals, appended so the ones above keep their index. (title, description, how to earn = hover hint, rule key);
# the rules are in _extra_medal_checks(). Skill medals marked "clean" only count _medal_clears().
EXTRA_MEDALS = (
    ("Getting Hooked", "Just one more map... right?", "Submit 50 plays", "plays50"),
    ("No Life", "Touch grass? Never heard of it", "Submit 1,000 plays", "plays1000"),
    ("Rising Star", "Someone's been practising \u2728", "Reach 100 pp", "pp100"),
    ("Elite", "Your keyboard fears you", "Reach 1,000 pp", "pp1000"),
    ("Seasoned", "Halfway to triple digits!", "Reach level 50", "level50"),
    ("Centurion", "Triple digits, baby!", "Reach level 100", "level100"),
    ("Flawless", "Not a single hair out of place", "SS a ranked map, every hit Perfect (no HT, NF or slowdowns)", "ss"),
    ("Unbreakable", "Your combo has plot armour", "Full combo a ranked Lv 30+ difficulty (no HT, NF or slowdowns)", "fc30"),
    ("Sharpshooter", "Do you even miss?", "Keep 98%+ overall accuracy over 50+ plays", "acc98"),
    ("Combo Monster", "Om nom nom, combos", "Hit a 3,000 combo", "combo3000"),
    ("Deep End", "No floaties allowed \U0001F3CA", "Clear a ranked Lv 50+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "lv50"),
    ("Into the Abyss", "It stared back. You didn't blink.", "Clear a ranked Lv 70+ difficulty, the black ones, with 70%+ accuracy (no HT, NF or slowdowns)", "lv70"),
    ("Marathon", "Your chair has your shape now", "Play for 24 hours in total", "playtime24"),
    ("Mapper", "Making the notes instead of hitting them", "Upload a beatmap set, or get an osu! claim accepted", "mapper"),
    ("Ranked Mapper", "Officially certified banger \U0001F3B6", "Own a beatmap set that gets ranked", "rankedmapper"),
    ("Collector", "Gotta favourite 'em all", "Favourite 10 beatmap sets", "fav10"),
    ("Social Butterfly", "The more the merrier! \U0001F98B", "Have 5 mutual friends (you've both added each other)", "friends5"),
    ("Critic", "Everyone's a critic... and so are you", "Post 10 comments on beatmaps", "comments10"),
    # 34-40: more play-based medals
    ("Oops", "Did you even press anything?", "Submit a play where every single note was a miss", "allmiss"),
    ("So Close", "One. Single. Miss.", "Clear a ranked map with exactly one miss and 95%+ accuracy (no HT, NF or slowdowns)", "onemiss"),
    ("Speed Demon", "Gotta go fast \U0001F4A8", "Clear a ranked Lv 20+ difficulty with DT at 1.5x or faster, 70%+ accuracy", "speed15"),
    ("Slowpoke", "Taking it nice and slow \U0001F422", "Submit a play at 0.75x speed or slower", "slow"),
    ("Big Leagues", "Now we're talking", "Reach 500 pp", "pp500"),
    ("Perfectionist", "Ten out of ten, every time", "SS 10 different ranked maps, every hit Perfect (no HT, NF or slowdowns)", "ss10"),
    ("Dedicated", "Qlute is your second home", "Submit 5,000 plays", "plays5000"),
    # 41-46: secret medals the game reports itself (POST apiv2/medals/claim/<name>, online/medals.py CLIENT_MEDALS)
    ("Cheat Code", "30 lives? In this economy?", "Some codes never get old... \u2191\u2191\u2193\u2193", "client:konami"),
    ("Rage Quit", "The keyboard had it coming", "Quit a map from the pause menu after missing 20+ notes", "client:ragequit"),
    ("Pause Addict", "Hold on, let me get a drink", "Pause 10 times in one play", "client:pauses"),
    ("Night Owl", "Sleep is for the weak \U0001F989", "Finish a play between 2 and 5 in the morning", "client:nightowl"),
    ("Silent Disco", "Who needs music anyway?", "Finish a play with the game's volume all the way down", "client:muted"),
    ("Doki Doki", "Listening to Qlute's heartbeat \U0001F493", "Hover the logo on the main menu and just... listen for a while", "client:heartbeat"),
    # 47+: map level medals, pass and full combo every 10 levels (Deep End = Lv 50 pass, Into the Abyss = Lv 70 pass,
    # Unbreakable = Lv 30 FC already exist). Same clean-clear rules as the skill medals.
    ("Warming Up", "The keyboard's getting warm", "Clear a ranked Lv 10+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass10"),
    ("Finding the Rhythm", "Tap tap tap, it's clicking", "Clear a ranked Lv 20+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass20"),
    ("Getting Serious", "No more warm-up maps", "Clear a ranked Lv 30+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass30"),
    ("Over the Hill", "It's all downhill from here. Right?", "Clear a ranked Lv 40+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass40"),
    ("Uncharted Waters", "Here be dragons \U0001F409", "Clear a ranked Lv 60+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass60"),
    ("Event Horizon", "Even light can't escape these notes", "Clear a ranked Lv 80+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass80"),
    ("Beyond Reason", "Your fingers have left the chat", "Clear a ranked Lv 90+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass90"),
    ("Summit", "Nothing left to climb \U0001F3D4", "Clear a ranked Lv 100+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass100"),
    ("Clean Sweep", "Not a single note dropped", "Full combo a ranked Lv 10+ difficulty (no HT, NF or slowdowns)", "fc10"),
    ("Steady Hands", "Calm, cool, collected", "Full combo a ranked Lv 20+ difficulty (no HT, NF or slowdowns)", "fc20"),
    ("Iron Focus", "Blink and you'll miss it. You didn't.", "Full combo a ranked Lv 40+ difficulty (no HT, NF or slowdowns)", "fc40"),
    ("Untouchable", "The misses can't find you", "Full combo a ranked Lv 50+ difficulty (no HT, NF or slowdowns)", "fc50"),
    ("Zero Gravity", "Floating through the chaos", "Full combo a ranked Lv 60+ difficulty (no HT, NF or slowdowns)", "fc60"),
    ("Abyss Walker", "You walked out of the deep without a scratch", "Full combo a ranked Lv 70+ difficulty (no HT, NF or slowdowns)", "fc70"),
    ("Perfect Storm", "Thunder, lightning, zero misses \u26A1", "Full combo a ranked Lv 80+ difficulty (no HT, NF or slowdowns)", "fc80"),
    ("Mythical", "People will tell stories about this one", "Full combo a ranked Lv 90+ difficulty (no HT, NF or slowdowns)", "fc90"),
    ("Absolute", "There is nothing beyond this", "Full combo a ranked Lv 100+ difficulty (no HT, NF or slowdowns)", "fc100"),
    # mod introductions: clear a ranked map with each mod (any speed), 70%+ accuracy
    ("Double Trouble", "Twice the speed, twice the fun", "Clear a ranked map with Double Time, 70%+ accuracy", "mod:DT"),
    ("Taking It Easy", "Half the speed, all of the vibes", "Clear a ranked map with Half Time, 70%+ accuracy", "mod:HT"),
    ("Shuffle Mode", "Who put that note there?", "Clear a ranked map with Random, 70%+ accuracy", "mod:RND"),
    ("Sliced and Diced", "Chop chop \U0001F52A", "Clear a ranked map with Slice, 70%+ accuracy", "mod:SL"),
    ("Lights Out", "Who needs to see the notes anyway?", "Clear a ranked map with Black-out, 70%+ accuracy", "mod:BT"),
    ("Safety Net", "Failing is optional now", "Clear a ranked map with No-Fail, 70%+ accuracy", "mod:NF"),
    # map level medals for the first steps: pass and full combo at every level 1-9
    ("Hello World", "Your very first clear 🌟", "Clear a ranked Lv 1+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass1"),
    ("Tiny Steps", "One foot in front of the other", "Clear a ranked Lv 2+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass2"),
    ("Getting the Hang of It", "Oh, so THAT'S how it works", "Clear a ranked Lv 3+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass3"),
    ("Feeling It", "The rhythm is taking over", "Clear a ranked Lv 4+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass4"),
    ("High Five", "✋ Up top!", "Clear a ranked Lv 5+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass5"),
    ("On a Roll", "Can't stop, won't stop", "Clear a ranked Lv 6+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass6"),
    ("Lucky Seven", "Jackpot 🎰", "Clear a ranked Lv 7+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass7"),
    ("Eight Beat", "Four on the floor, twice", "Clear a ranked Lv 8+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass8"),
    ("Cloud Nine", "Floating after that one", "Clear a ranked Lv 9+ difficulty with 70%+ accuracy (no HT, NF or slowdowns)", "pass9"),
    ("Spotless Start", "Not a single miss, from day one", "Full combo a ranked Lv 1+ difficulty (no HT, NF or slowdowns)", "fc1"),
    ("Double Clean", "Two levels in, still spotless", "Full combo a ranked Lv 2+ difficulty (no HT, NF or slowdowns)", "fc2"),
    ("Hat Trick", "Three's a charm 🎩", "Full combo a ranked Lv 3+ difficulty (no HT, NF or slowdowns)", "fc3"),
    ("Four on the Floor", "Every beat, right on time", "Full combo a ranked Lv 4+ difficulty (no HT, NF or slowdowns)", "fc4"),
    ("Clean Hands", "Not a smudge on that combo", "Full combo a ranked Lv 5+ difficulty (no HT, NF or slowdowns)", "fc5"),
    ("Six Pack", "Your combo's been working out", "Full combo a ranked Lv 6+ difficulty (no HT, NF or slowdowns)", "fc6"),
    ("Seventh Heaven", "Combo bliss", "Full combo a ranked Lv 7+ difficulty (no HT, NF or slowdowns)", "fc7"),
    ("Figure Eight", "Smooth as ice ⛸", "Full combo a ranked Lv 8+ difficulty (no HT, NF or slowdowns)", "fc8"),
    ("Nine Lives", "...and you didn't need a single one", "Full combo a ranked Lv 9+ difficulty (no HT, NF or slowdowns)", "fc9"),
)

# How the profile groups medals, in this order; inside a group they show in this order (easiest first).
MEDAL_CATEGORIES = (
    ("Progress", ("Baby Steps", "Getting Hooked", "Rising Star", "Big Leagues", "Elite", "Seasoned", "Centurion",
                  "Marathon", "No Life", "Dedicated")),
    ("Ranking", ("Top 1,000", "Top 100", "Top 50", "Top 10", "The End")),
    ("Skill", (">~<", "Combo Monster", "S-Ranker", "Flawless", "Perfectionist", "So Close", "Sharpshooter",
               "D-Ranker", "Oops", "Sniper", "BreakThrough", "Psycho")),
    ("Map level: Pass", ("Hello World", "Tiny Steps", "Getting the Hang of It", "Feeling It", "High Five", "On a Roll", "Lucky Seven", "Eight Beat", "Cloud Nine",
                         "Warming Up", "Finding the Rhythm", "Getting Serious", "Over the Hill", "Deep End",
                         "Uncharted Waters", "Into the Abyss", "Event Horizon", "Beyond Reason", "Summit")),
    ("Map level: Full combo", ("Spotless Start", "Double Clean", "Hat Trick", "Four on the Floor", "Clean Hands", "Six Pack", "Seventh Heaven", "Figure Eight", "Nine Lives",
                               "Clean Sweep", "Steady Hands", "Unbreakable", "Iron Focus", "Untouchable",
                               "Zero Gravity", "Abyss Walker", "Perfect Storm", "Mythical", "Absolute")),
    ("Mods", ("Double Trouble", "Taking It Easy", "Shuffle Mode", "Sliced and Diced", "Lights Out", "Safety Net",
              "Speed Demon", "Slowpoke")),
    ("Community", ("Mapper", "Ranked Mapper", "Collector", "Social Butterfly", "Critic", "Welcome back Veteran")),
    ("Team & support", ("Supporter", "Making the game better", "Team Moderator")),
    ("Secret", ("Cheat Code", "Rage Quit", "Pause Addict", "Night Owl", "Silent Disco", "Doki Doki")),
)
_MEDAL_PLACE = {t: (ci, ti) for ci, (_c, titles) in enumerate(MEDAL_CATEGORIES) for ti, t in enumerate(titles)}


def _short_num(n):
    """1,234 / 12.3k / 4.5M / 1.2B"""
    n = max(0, int(n))
    for size, unit in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k")):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + unit
    return f"{n:,}"


def medal_category(title):
    """(category name, sort key) of a medal; anything not listed goes last under "Other"."""
    ci, ti = _MEDAL_PLACE.get(title, (len(MEDAL_CATEGORIES), 0))
    return (MEDAL_CATEGORIES[ci][0] if ci < len(MEDAL_CATEGORIES) else "Other"), (ci, ti)
# Medals the game reports itself: {claim name: medal index}. Earned = the unlock row exists (online.MedalUnlock).
CLIENT_MEDALS = {key.split(":", 1)[1]: len(medals) + i for i, (_t, _d, _h, key) in enumerate(EXTRA_MEDALS)
                 if key.startswith("client:")}
leveltemp=0.0000005 # the old linear level (score / 2M); levels now come from Chikara/levels.py
from Chikara import levels as player_levels
# pp v3 ranking (see PP_SCORE_DESIGN.md)
PP_WEIGHT = 0.95        # n-th best play counts 0.95^n
PP_TOP_SCORES = 100     # plays that count towards a player's pp
PP_JUMP_RATIO = 0.25    # a single play worth more than this share of the player's pp ...
PP_JUMP_FLOOR = 600     # ... and more than this many pp is treated as cheating (restricts the player)
TEAM_MEDAL=14 # "Making the game better": given to the Qlute team (moderation.StaffMember)
MOD_MEDAL=15 # "Team Moderator": team members with the moderator role
username='0' # Guest mode
issignin=False # Sign in state
allowsubmissions = 1
simulatedpp=23000
simulatedrank=10000000

def fetch_beatmap(beatmapidset, beatmapid):
    api = Ossapi(client_id, client_secret)

    if int(beatmapidset) == 0 or int(beatmapid) == 0:
        return None, "", 0, 0

    try:
        beatset = api.beatmapset(int(beatmapidset))
    except ValueError:
        return None, "", 0, 0

    difficulty = ""
    bpm = 0
    exists = False

    for a in beatset.beatmaps:
        if int(beatmapid) == a.id:
            exists = True
            difficulty = a.version
            bpm = a.bpm
            break

    if not exists:
        return None, "", 0, 0

    if 0 < beatset.ranked.value < 4:
        ranked = 1
    elif beatset.ranked == 4:
        ranked = 2
    else:
        ranked = 0

    return beatset, difficulty, bpm, ranked


testhash = "2c21d9b8dbaf3427201da3ef82e70affaa9267ef670ee39c99ce7105a415d9f2"
def checkgamehash(request):
    agent = request.META.get("HTTP_USER_AGENT", "")
    game = agent.split("-")
    if "GodotEngine" in agent:
        return ("Qlute", False)
    tmp = Hashes.objects.values().filter(hash = game[1]).first()
    if tmp != None:
        return (game[0], (tmp["hash"] == game[1]) )
    else:
        return (game[0], False )
def getspp(offset=0,limit=0):
    tols=offset
    tan=0
    pp=28000+(len(open('userlist').read().rstrip('\n').split('\n')))
    pp-=(2*tols)*tols
    tab=0
    st=8.5
    tick=0
    shutdown=0
    if not limit:
        limit=len(open('userlist').read().rstrip('\n').split('\n'))
    elif limit==-1:
        shutdown=1
    else:
        limit=limit+offset
    if allowspoof and not shutdown:
        for a in open('userlist').read().rstrip('\n').split('\n')[::-1][offset:limit]:
            tols+=1
            name=a
            pp-=2*tols
            if pp<1:
                pp=0
                break
            yield name,pp



SITEMAP_PAGES = (("/", "1.0", "daily"), ("/download", "0.9", "weekly"), ("/beatmaps", "0.9", "daily"),
                 ("/ranking", "0.8", "daily"), ("/search", "0.5", "weekly"), ("/news", "0.7", "weekly"),
                 ("/rules", "0.4", "monthly"), ("/dmca", "0.2", "yearly"))
SITEMAP_MAX_SETS = 40000  # one sitemap file holds at most 50,000 urls
SITEMAP_MAX_PLAYERS = 5000
_sitemap_cache = {"at": 0, "xml": ""}


def sitemap(request):
    """The public pages + every beatmap set page, built from the database (cached for an hour)."""
    from django.db.models import Max
    now = time.time()
    if not _sitemap_cache["xml"] or now - _sitemap_cache["at"] > 3600:
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for path, priority, freq in SITEMAP_PAGES:
            out.append(f"<url><loc>{SiteURL}{path}</loc><changefreq>{freq}</changefreq><priority>{priority}</priority></url>")
        from moderation import takedowns
        sets = (takedowns.visible(Beatmap.objects.all()).values("beatmapsetid").annotate(updated=Max("created"))
                .order_by("-updated")[:SITEMAP_MAX_SETS])
        for row in sets:
            lastmod = f"<lastmod>{row['updated']:%Y-%m-%d}</lastmod>" if row["updated"] else ""
            out.append(f"<url><loc>{SiteURL}/beatmapset/{row['beatmapsetid']}</loc>{lastmod}<priority>0.6</priority></url>")
        players = (User.objects.filter(restricted=False, ranked_points__gt=0).exclude(username=None)
                   .order_by("-ranked_points").values_list("id", flat=True)[:SITEMAP_MAX_PLAYERS])
        for uid in players:
            out.append(f"<url><loc>{SiteURL}/user/{uid}</loc><priority>0.4</priority></url>")
        out.append("</urlset>")
        _sitemap_cache.update(at=now, xml="\n".join(out))
    return HttpResponse(_sitemap_cache["xml"], content_type="application/xml")
def robots_txt(request):
    content = """
# As a condition of accessing this website, you agree to abide by the following
# content signals:

# (a)  If a content-signal = yes, you may collect content for the corresponding
#      use.
# (b)  If a content-signal = no, you may not collect content for the
#      corresponding use.
# (c)  If the website operator does not include a content signal for a
#      corresponding use, the website operator neither grants nor restricts
#      permission via content signal with respect to the corresponding use.

# The content signals and their meanings are:

# search:   building a search index and providing search results (e.g., returning
#           hyperlinks and short excerpts from your website's contents). Search does not
#           include providing AI-generated search summaries.
# ai-input: inputting content into one or more AI models (e.g., retrieval
#           augmented generation, grounding, or other real-time taking of content for
#           generative AI search answers).
# ai-train: training or fine-tuning AI models.

# ANY RESTRICTIONS EXPRESSED VIA CONTENT SIGNALS ARE EXPRESS RESERVATIONS OF
# RIGHTS UNDER ARTICLE 4 OF THE EUROPEAN UNION DIRECTIVE 2019/790 ON COPYRIGHT
# AND RELATED RIGHTS IN THE DIGITAL SINGLE MARKET.

# BEGIN Cloudflare Managed content

User-Agent: *
Content-signal: search=yes,ai-train=no
Allow: /
Disallow: /settings
Disallow: /friends
Disallow: /admin
Disallow: /apiv2/

User-agent: Amazonbot
Disallow: /

User-agent: Applebot-Extended
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: GPTBot
Disallow: /

User-agent: meta-externalagent
Disallow: /

# END Cloudflare Managed Content

Sitemap: {site}/sitemap.xml
"""
    return HttpResponse(content.replace("{site}", SiteURL), content_type="text/plain")



def getdifficulties(id): # Difficulty processing
    x=[]
    from moderation import takedowns
    if id!=0 and takedowns.is_down(id):
        return x  # taken down (moderation/takedowns.py): looks like a set with no difficulties
    if id!=0:
        beatmaps = Beatmap.objects.values().filter(beatmapsetid=id)
    else:
        return {"error",1,"msg","Beatmap set not found"}
    for a in beatmaps:
        x.append(a)
    return x
def get_leaderboard(id): # Leaderboard processing
        x=[]
        e=0
        pointtest = 0
        for a in getscores(beatmapid=id):
            points = a['points']
            if pointtest < points:
                pointtest = pointtest
            maxpoints = a['maxpoints']
            data = {
    "username": a['username'],
    "points": points,
    "score": stored_score(a),
    "combo": a['combo'],
    "MAX": a['max'],
    "GOOD": a['great'],
    "MEH": a['meh'],
    "BAD": a['bad'],
    "mods":a['mods'].replace('AT',''),
    "speed_multi":a['speed_multi'],
    "time": int(a['created'].timestamp()),
    "id": a['id'],
    "replay": bool(a.get('replay_path')),
            }
            x.append(data)
            e+=1
        if x:
            pfps = dict(User.objects.filter(username__in={r["username"] for r in x}).values_list("username", "pfppath"))
            for r in x:
                r["pfp"] = _pfp_url(pfps.get(r["username"]))
        spp=0
        if spp:
            for a in range(1,250):
                if e>49:
                    break
                else:
                    mult=1.2
                    pp=randint(1,int(pointtest*mult))
                    data = {
            "username": str(a),
            "points": pp,
            "score": getsimscore(pp,pointtest,mult,type=int),
            "combo": randint(1,int(pointtest//perfbom)),
            "MAX": randint(1,int(pointtest//perfbom)),
            "GOOD": randint(1,int(pointtest//perfbom)),
            "MEH": randint(1,int(pointtest//perfbom)),
            "BAD": randint(1,int(pointtest//perfbom)),
            "time": int(timezone.now().timestamp()-(e*16000))
                    }
                    x.append(data)
                e+=1
        x=sorted(x, key=lambda x: (-x['score'], x.get('time', 0)))

        return x


def getstat(command, useris, raw=False, page=1):  # Added leveltemp parameter with default value
    if command == 'score':
        user = User.objects.get(username=useris)
        t = user.ranked_score if user and user.ranked_score is not None else 0
    elif command == 'level':
        user = User.objects.get(username=useris)
        ranked_score = user.ranked_score if user and user.ranked_score is not None else 0
        t = player_levels.level(int(ranked_score))
    
    elif command == 'rank':
        user = User.objects.get(username=useris)
        t = user.ranking if user else None
    
    elif command == 'pfp_path':
        user = User.objects.get(username=useris)
        t = user.pfppath if user else NoProfilePictureURL
        if t == None:
            t = NoProfilePictureURL
        elif not t.startswith("http"):
            t = DataURL + t
        t = {"url" : str(t)}
    elif command == 'cardborder':
        user = User.objects.get(username=useris)
        t = moderation.border_shown(user.username, user.cardborder) if user else None
        if user.restricted:
            t = CheaterCardBorder
        elif t == None:
            t = None
        elif not t.startswith("http"):
            t = DataURL + t
        t = {"url" : t}
    elif command == 'ranking':
        tols = 0
        users = []
        
        # Get users from DB ordered by ranked_points
        db_users = User.objects.all().filter(restricted = False).order_by('-ranked_points')[50*(page-1):50*page]
        
        for a in db_users:
            try:
                if a.ranked_points:
                    tols += 1
                    users.append(a)
            except AttributeError:
                pass
        
        if tols == 50:
            limit = -1
        else:
            limit = 50 - tols
        return users, tols
    
    elif command in ['accuracy', 'max', 'great', 'meh', 'bad', 'max_combo']:
        user = User.objects.get(username=useris)
        t = getattr(user, command) if user else None
    elif command == 'restricted':
        return User.objects.values().filter(username = useris).first()["restricted"]
    elif command == 'full':
        data = {
            "rank": getstat('rank', useris),
            "points": getstat('points', useris),
            "score": getstat('score', useris),
            "accuracy": getstat('accuracy', useris) * 0.01,
            "max_combo": getstat('max_combo', useris),
            "level": getstat('level', useris),
            "pfp_path": getstat('pfp_path', useris)["url"],
            "cardborder": getstat('cardborder', useris)["url"],
            "donator": moderation.is_supporter(useris),
            "restricted": getstat('restricted', useris),
        }
        
        if not raw:
            import json
            t = json.dumps(data)
        else:
            t = data
    
    elif command == 'points':
        user = User.objects.filter(username=useris).first()
        t = user.ranked_points if user else None
    
    if t is None:
        t = 0
        
    return t# Add multiplier of a mod to the performance

def getmult(multiplier,submit=False, speed = 1):
    try:
        multiplier=float(multiplier)
        #multiplier=1
        newmodsys=0
    except Exception:
        fulltmp=multiplier
        multiplier=1
        newmodsys=1
    if newmodsys:
        # Same multiplier the client uses (ModsOperator.ProcessMultiplierByModList).
        multiplier = ppv2calc.get_multiplier(str(fulltmp), speed if speed is not None else 1)
    return multiplier

def getpulses(pp):
    pulses = pp
    pulses **= pulseinflation
    return pulses

def getpoint(perfect,good,meh,bad,multiplier,combo=1,type=int): # Points System 2024/06/15 Now Obsolete
    ppvalue = 0
    ppvalue = perfect * perfbom
    ppvalue -= perfbom/2 * good
    ppvalue -= perfbom/3 * meh
    ppvalue -= perfbom * bad
    ppvalue += combo * perfbom
    ppvalue *= multiplier
    if type == int:
        return ppvalue
    else:
        return str(ppvalue)
    
def getmedals(user):
    medco=0
    donator=0
    rank=int(getstat('rank',user))
    points=int(getstat('points',user))
    score=int(getstat('score',user))
    level=player_levels.level(score)
    accuracy=getstat('accuracy',user)
    max=getstat('max',user)
    great=getstat('great',user)
    meh=getstat('meh',user)
    bad=getstat('bad',user)
    max_combo=getstat('max_combo',user)
    soon = _former_coming_soon(user)
    # Earned once = kept forever (online.MedalUnlock), except the medals about where you are right now.
    from online.models import MedalUnlock
    kept = set(MedalUnlock.objects.filter(username=user).values_list("medal", flat=True))
    for title,desc in medals:
        show=0
        if medco==0 and rank==1:
            show=1
        elif medco==1 and points>1:
            show=1
        elif medco in (3, 4, 8, 9) and soon.get(medco):
            show=1
        elif medco==2 and max_combo>1000:
            show=1
        elif medco==5 and bad>1000:
            show=1
        elif medco==6 and max>1000:
            show=1
        elif medco==7 and moderation.is_supporter(user):
            show=1
        elif medco==13 and rank and rank<=1000:
            show=1
        elif medco==10 and rank and rank<=100:
            show=1
        elif medco==11 and rank and rank<=50:
            show=1
        elif medco==12 and rank and rank<=10:
            show=1
        elif medco==TEAM_MEDAL and moderation.is_staff(user):
            show=1
        elif medco==MOD_MEDAL and getattr(moderation.staff_of(user), "role", "") == "mod":
            show=1
        if not show and medco in kept and title not in LIVE_MEDALS:
            show=1
        medco+=1
        yield (title,desc,show)
    earned = _extra_medal_checks(user)
    for i, (title, desc, _hint, key) in enumerate(EXTRA_MEDALS):
        yield (title, desc, 1 if earned.get(key) or (len(medals) + i) in kept else 0)


# Medals that follow where a player is right now: they can be lost again. Every other medal, once recorded as
# earned (online.MedalUnlock), stays earned forever even if the play or stat behind it changes later.
LIVE_MEDALS = {"The End", "Top 1,000", "Top 100", "Top 50", "Top 10", "Supporter", "Making the game better",
               "Team Moderator"}

# When the Lv 1-9 pass / full combo medals were added: only plays set from then on earn them.
STARTER_MEDALS_SINCE = datetime.datetime(2026, 11, 16, 21, 29, 52)

WELCOME_BACK_DAYS = 30


def welcome_back(username, last_seen):
    """Called when the game reports a player's status (setstatus): back after WELCOME_BACK_DAYS+ away earns
    "Welcome back Veteran". It's recorded as an unlock right away (the game pops it up on its next medal check)."""
    if not last_seen or timezone.now().timestamp() - last_seen < WELCOME_BACK_DAYS * 86400:
        return
    from online.models import MedalUnlock
    MedalUnlock.objects.get_or_create(username=username, medal=4,
                                      defaults={"title": medals[4][0], "achieved": timezone.now()})


def _former_coming_soon(user):
    """{medal index: earned} for the original medals that used to say "coming soon": Psycho (3),
    Welcome back Veteran (4), Sniper (8) and BreakThrough (9). Rules in MEDAL_HINTS / MEDALS.md."""
    from django.db.models import Min
    from online.models import MedalUnlock
    out = {}
    u = User.objects.filter(username=user).first()
    if u is None:
        return out
    try:
        ranked_plays = Score.objects.filter(username=user, ranked=1)
        clears = _medal_clears(ranked_plays)
        lv = dict(Beatmap.objects.filter(ranked=1, beatmapid__in={c.beatmap_id for c in clears}).values_list("beatmapid", "Level"))
        # Psycho: Random + DT at 1.5x+ on a Lv 30+ map
        out[3] = any("RND" in (c.mods or "").upper() and "DT" in (c.mods or "").upper() and (c.speed_multi or 1) >= 1.5
                     and (lv.get(c.beatmap_id) or 0) >= 30 for c in clears)
        # Welcome back Veteran: recorded live by welcome_back(); or a 30+ day gap between their plays
        if MedalUnlock.objects.filter(username=user, medal=4).exists():
            out[4] = True
        else:
            times = sorted(Score.objects.filter(username=user).values_list("created", flat=True))
            out[4] = any((b - a).days >= WELCOME_BACK_DAYS for a, b in zip(times, times[1:]))
        # Sniper: first clear on a map that 2+ other players cleared later
        clear_ids = {c.id for c in clears}
        mine = {bid: when for sid, bid, when in ranked_plays.values_list("id", "beatmap_id", "created") if sid in clear_ids}
        if mine:
            others = (Score.objects.filter(beatmap_id__in=list(mine), ranked=1).exclude(username=user)
                      .values("beatmap_id", "username").annotate(first=Min("created")))
            first_other, later = {}, {}
            for row in others:
                bid = row["beatmap_id"]
                first_other[bid] = min(first_other.get(bid, row["first"]), row["first"])
                if mine[bid] and row["first"] > mine[bid]:
                    later[bid] = later.get(bid, 0) + 1
            out[8] = any(later.get(bid, 0) >= 2 and first_other[bid] > when for bid, when in mine.items() if when)
        else:
            out[8] = False
        # BreakThrough: +100 pp within 7 days (daily history, Chikara/stathistory.py)
        from dbview.models import StatHistory
        hist = list(StatHistory.objects.filter(user_id=u.id).order_by("date").values_list("date", "points"))
        first_play = ranked_plays.order_by("created").values_list("created", flat=True).first()
        if hist and first_play and first_play.date() >= hist[0][0] - datetime.timedelta(days=1):
            hist.insert(0, (first_play.date() - datetime.timedelta(days=1), 0))  # they had no pp before their first play
        best = False
        for i, (d1, p1) in enumerate(hist):
            for d2, p2 in hist[i + 1:]:
                if (d2 - d1).days > 7:
                    break
                if p2 - p1 >= 100:
                    best = True
                    break
            if best:
                break
        out[9] = best
    except Exception:
        sentry_sdk.capture_exception()
    return out


MEDAL_BANNED_MODS = ("HT", "NF", "AT")  # slowed down, can't fail, autoplay: not a real clear
MEDAL_MIN_ACCURACY = 70                  # C grade or better (the site's grades: C is above 69%)


def _medal_clears(plays):
    """The plays that count as clearing a map for the skill medals: no HT / NF / AT, speed 1.0x or faster,
    and MEDAL_MIN_ACCURACY+. The server can't tell a failed run from a pass, so the accuracy floor stands in."""
    out = []
    for sc in plays.only("beatmap_id", "max", "great", "meh", "bad", "mods", "speed_multi"):
        mods = (sc.mods or "").upper()
        if any(m in mods for m in MEDAL_BANNED_MODS) or (sc.speed_multi or 1) < 1:
            continue
        mx, great, meh, bad = sc.max or 0, sc.great or 0, sc.meh or 0, sc.bad or 0
        total = mx + great + meh + bad
        if total and (mx + great / 2 + meh / 3) / total * 100 >= MEDAL_MIN_ACCURACY:
            out.append(sc)
    return out


def _accuracy(sc):
    """The site's accuracy of one play, in percent."""
    mx, great, meh, bad = sc.max or 0, sc.great or 0, sc.meh or 0, sc.bad or 0
    total = mx + great + meh + bad
    return (mx + great / 2 + meh / 3) / total * 100 if total else 0


def _extra_medal_checks(user):
    """Which EXTRA_MEDALS `user` has earned, {rule key: bool}. Plays = submitted scores. The skill medals (ss, fc30,
    lv50, lv70) only count clean clears, _medal_clears(): ranked maps, normal speed or faster, no NF / AT, 70%+."""
    from django.db.models import Count
    from online.models import BeatmapComment, FavoriteBeatmap, Friend
    from submissions.models import Submission
    u = User.objects.filter(username=user).first()
    if u is None:
        return {}
    plays = Score.objects.filter(username=user)
    ranked_plays = plays.filter(ranked=1)
    play_count = plays.count()
    pp = u.ranked_points or 0
    level = player_levels.level(u.ranked_score or 0)
    clears = _medal_clears(ranked_plays)
    levels = dict(Beatmap.objects.filter(ranked=1, beatmapid__in={c.beatmap_id for c in clears})
                  .values_list("beatmapid", "Level"))
    passed_lv = lambda lv: any((levels.get(c.beatmap_id) or 0) >= lv for c in clears)
    owned = Submission.objects.filter(owner=user).values("beatmapsetid")
    following = Friend.objects.filter(username=user).values("friend")
    checks = {
        "plays50": lambda: play_count >= 50,
        "plays1000": lambda: play_count >= 1000,
        "pp100": lambda: pp >= 100,
        "pp1000": lambda: pp >= 1000,
        "level50": lambda: level >= 50,
        "level100": lambda: level >= 100,
        "ss": lambda: any(c.max and not (c.great or c.meh or c.bad) for c in clears),
        "fc30": lambda: any(c.max and not c.bad and (levels.get(c.beatmap_id) or 0) >= 30 for c in clears),
        "acc98": lambda: play_count >= 50 and (u.accuracy or 0) >= 98,
        "combo3000": lambda: (u.max_combo or 0) >= 3000,
        "lv50": lambda: passed_lv(50),
        "lv70": lambda: passed_lv(70),
        "playtime24": lambda: (u.playtime or 0) >= 24 * 3600,
        "mapper": lambda: Submission.objects.filter(owner=user).exists(),
        "rankedmapper": lambda: Beatmap.objects.filter(beatmapsetid__in=owned, ranked=1).exists(),
        "fav10": lambda: FavoriteBeatmap.objects.filter(username=user).count() >= 10,
        "friends5": lambda: Friend.objects.filter(username__in=following, friend=user).count() >= 5,
        "comments10": lambda: BeatmapComment.objects.filter(username=user).count() >= 10,
        "allmiss": lambda: plays.filter(bad__gt=0, max=0, great=0, meh=0).exists(),
        "onemiss": lambda: any(c.bad == 1 and _accuracy(c) >= 95 for c in clears),
        "speed15": lambda: any("DT" in (c.mods or "").upper() and (c.speed_multi or 1) >= 1.5
                               and (levels.get(c.beatmap_id) or 0) >= 20 for c in clears),
        "slow": lambda: plays.filter(speed_multi__lte=0.75).exists(),
        "pp500": lambda: pp >= 500,
        "ss10": lambda: len({c.beatmap_id for c in clears if c.max and not (c.great or c.meh or c.bad)}) >= 10,
        "plays5000": lambda: play_count >= 5000,
    }
    for lv in (10, 20, 30, 40, 60, 80, 90, 100):
        checks[f"pass{lv}"] = (lambda lv=lv: passed_lv(lv))
    for lv in (10, 20, 40, 50, 60, 70, 80, 90, 100):
        checks[f"fc{lv}"] = (lambda lv=lv: any(c.max and not c.bad and (levels.get(c.beatmap_id) or 0) >= lv for c in clears))
    # Lv 1-9 medals only count plays set after they were added (STARTER_MEDALS_SINCE): nobody gets them for old plays
    new_ids = set(ranked_plays.filter(created__gte=STARTER_MEDALS_SINCE).values_list("id", flat=True))
    fresh = [c for c in clears if c.id in new_ids]
    for lv in range(1, 10):
        checks[f"pass{lv}"] = (lambda lv=lv: any((levels.get(c.beatmap_id) or 0) >= lv for c in fresh))
        checks[f"fc{lv}"] = (lambda lv=lv: any(c.max and not c.bad and (levels.get(c.beatmap_id) or 0) >= lv for c in fresh))
    # mod introductions: any ranked play with the mod and 70%+ (HT / NF allowed here, it's their medal)
    mod_rows = list(ranked_plays.exclude(mods=None).exclude(mods="").only("mods", "max", "great", "meh", "bad"))
    for mod in ("DT", "HT", "RND", "SL", "BT", "NF"):
        checks["mod:" + mod] = (lambda mod=mod: any(mod in (sc.mods or "").upper() and "AT" not in (sc.mods or "").upper()
                                                   and _accuracy(sc) >= MEDAL_MIN_ACCURACY for sc in mod_rows))
    from online.models import MedalUnlock
    claimed = set(MedalUnlock.objects.filter(username=user, medal__in=CLIENT_MEDALS.values()).values_list("medal", flat=True))
    for name, index in CLIENT_MEDALS.items():
        checks["client:" + name] = (lambda i=index: i in claimed)
    out = {}
    for key, check in checks.items():
        try:
            out[key] = bool(check())
        except Exception:  # one broken rule shouldn't take the profile down
            out[key] = False
    return out

# Querying scores

def getscores(user='',beatmapid=0,orderbybiggest=False,limit=30,ranked = 1):
    tols=0
    if orderbybiggest:
        strip='points'
    else:
        strip='created'
    if user=='':
        if beatmapid!=0:
            # Map leaderboards rank by score; ties go to whoever set it first.
            score = Score.objects.values().filter(beatmap_id=beatmapid).filter(ranked=ranked).order_by("-score", "created")[:limit]
        else:
            score = Score.objects.values().order_by(f"-{str(strip)}").filter(ranked=ranked)[:limit]
    elif user != '' and ranked != -1:
        score = Score.objects.filter(username=user).values().order_by(f"-{str(strip)}").filter(ranked=ranked)[:limit]
    elif user != '' and ranked == -1:
        score = Score.objects.filter(username=user).values().order_by(f"-{str(strip)}")[:limit]
    per=1
    for a in score:
        mods=a['mods']
        a['multiplier']=getmult(mods, speed=a.get('speed_multi') or 1)
        a['weighted_pp']=(a['points'] or 0)*per
        a['weight']=per

        if user in a['username'] or beatmapid in a['beatmap_id']:
            yield a
        tols+=1
        per*=PP_WEIGHT
    if not tols:
        return 0

def timeform(t): # Parses time and date to a human readable format
    #t-= 3600 * 4
    if t < 0:
        t = -t
    if t==None:
        return 'Never Played'
    if t>=31536000:
        x=int(t//31536000)
        fix='Year'
    elif t>=2630000:
        fix='Month'
        x=int(t//2630000)
    elif t>=86400:
        x=int(t//86400)
        fix='Day'
    elif t>=3600:
        x=int(t//3600)
        fix='Hour'
    elif t>=60:
        x=int(t//60)
        fix='Minute'
    elif t<60:
        x=int(t)
        fix='Second'        
    if x>1:
        fix+='s'
    return str(x)+' '+str(fix)+' Ago'
# Beatmap Leaderboard
def beatmap(request, command):
    arg = [a for a in command.split("/") if a]
    try:
        setid = int(arg[0])
        diffid = int(arg[1]) if len(arg) > 1 else 0
    except (ValueError, IndexError):
        setid, diffid = 0, 0
    diffs = list(Beatmap.objects.filter(beatmapsetid=setid).order_by("Level", "notecount")) if setid else []
    head = '<link rel="stylesheet" href="/static/css/beatmap.css?v=11">'
    from moderation.models import TakenDown
    down = TakenDown.objects.filter(beatmapsetid=setid).first() if setid and diffs else None
    if down is not None:  # moderation/takedowns.py
        viewer = moderation.request_user(request)
        team = viewer is not None and moderation.is_staff(viewer.username)
        html = header(request, customhead=head, title="Qlute - beatmap unavailable", robots=NOINDEX)
        html += ('<div class="infoboxcontainer"><div class="infobox column verticalpadding spacetop spacebottom">'
                 '<h2>This beatmap set isn\'t available</h2><p>It was taken down by the Qlute team '
                 '(see <a href="/rules#beatmaps">the beatmap rules</a> and <a href="/dmca">copyright claims</a>).</p>')
        if team:
            html += (f'<p class="catalog-hint">Team only: {escape(down.title)} &middot; {escape(down.reason)} &middot; '
                     f'by {escape(down.by)}. <a href="/admin#takedowns">Restore it in the admin panel</a>.</p>')
        html += '</div></div>' + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
        return HttpResponse(html, status=410)
    if not diffs:
        html = header(request, customhead=head, title="Qlute - beatmap not found", robots=NOINDEX)
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/beatmap.html").read() \
            .replace("{setid}", str(setid)).replace("{diffid}", str(diffid)).replace("{dataurl}", escape(DataURL))
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
        return HttpResponse(html, status=404)
    first = diffs[0]
    name = f"{first.artist} - {first.title}"
    url = f"{SiteURL}/beatmapset/{setid}"  # every difficulty's address shows the same set: one canonical page
    cover = DataURL + first.backgroundpath if first.backgroundpath else None
    levels = sorted({d.Level for d in diffs})
    length = max(d.Length for d in diffs)
    lv = f"Lv {levels[0]}" if len(levels) == 1 else f"Lv {levels[0]}-{levels[-1]}"
    description = (f"{name}, a Qlute beatmap set mapped by {first.mapper}: {len(diffs)} "
                   f"difficult{'y' if len(diffs) == 1 else 'ies'} ({lv}), {first.BPM} BPM, {length // 60}:{length % 60:02}. "
                   f"Preview it, see the leaderboard, and download it free for Qlute.")
    structured = json_ld([{
        "@context": "https://schema.org",
        "@type": "MusicRecording",
        "name": first.title,
        "byArtist": {"@type": "MusicGroup", "name": first.artist},
        "duration": f"PT{length // 60}M{length % 60}S",
        "url": url,
        **({"image": cover} if cover else {}),
        **({"keywords": first.tags} if first.tags else {}),
    }, {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Beatmaps", "item": SiteURL + "/beatmaps"},
            {"@type": "ListItem", "position": 2, "name": name, "item": url},
        ],
    }])
    html = header(request, customhead=head, title="Qlute - " + escape(name), description=description,
                  image=cover, canonical=url, jsonld=structured, ogtype="music.song")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/beatmap.html").read() \
        .replace("{setid}", str(setid)).replace("{diffid}", str(diffid)).replace("{dataurl}", escape(DataURL))
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def _grade(mx, great, meh, bad):
    total = mx + great + meh + bad
    if not total:
        return "?", 0.0
    acc = (mx + great / 2 + meh / 3) / total * 100
    if acc >= 100: g = "SS"
    elif acc > 95 and not bad: g = "S"
    elif acc > 90: g = "A"
    elif acc > 85: g = "B"
    elif acc > 69: g = "C"
    elif acc < 1: g = "?"
    else: g = "D"
    return g, acc


def score_page(request, score_id):
    sc = Score.objects.filter(id=score_id).first()
    player = User.objects.filter(username=sc.username).first() if sc else None
    if not sc or (player and player.restricted):
        html = header(request, title="Qlute - score not found", robots=NOINDEX)
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read().replace('{sitetitle}', "404 not found o-o")
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
        return HttpResponse(html, status=404)
    bm = Beatmap.objects.filter(beatmapid=sc.beatmap_id).first()
    mx, great, meh, bad = sc.max or 0, sc.great or 0, sc.meh or 0, sc.bad or 0
    g, acc = _grade(mx, great, meh, bad)
    total = mx + great + meh + bad
    row = {"max": mx, "great": great, "meh": meh, "bad": bad, "mods": sc.mods or "", "speed_multi": sc.speed_multi or 1, "score": sc.score}
    comp_score = stored_score(row)
    name = escape(urllib.parse.unquote(sc.username or ""))
    title = escape(bm.title if bm else (sc.beatmapname or "Unknown beatmap"))
    artist = escape(bm.artist if bm else (sc.artist or ""))
    diff = escape(bm.difficulty if bm else (sc.beatmapdiff or ""))
    map_url = f"/beatmapset/{sc.beatmapset_id}/{sc.beatmap_id}"
    cover = DataURL + "/".join(urllib.parse.quote(p) for p in bm.backgroundpath.split("/")) if bm and bm.backgroundpath else ""

    # placement on this map's leaderboard (best score per player, like the beatmap page)
    placement = None
    if sc.ranked == 1 and comp_score:
        best = {}
        rows = list(Score.objects.filter(beatmap_id=sc.beatmap_id, ranked=1).values("username", "score", "max", "great", "meh", "bad", "mods", "speed_multi", "points", "id"))
        r_points = {r["id"]: r["points"] or 0 for r in rows}
        for r in rows:
            v = (r_points.get(r["id"], 0), stored_score(r))  # same order as the beatmap page: pp, then score
            k = (r["username"] or "").lower()
            if k not in best or v > best[k][0]:
                best[k] = (v, r["id"])
        if best.get((sc.username or "").lower(), (None, None))[1] == sc.id:
            mine = best[(sc.username or "").lower()][0]
            placement = 1 + sum(1 for v, _ in best.values() if v > mine)

    mods = [m for m in modsaliasab if m != "AT" and m in (sc.mods or "")]
    if sc.speed_multi and sc.speed_multi != 1:
        mods.append(f"{sc.speed_multi:g}x")
    when = sc.created
    has_replay = bool(sc.replay_path)
    status = {1: ("Ranked", "s1"), 0: ("Unranked", "s0")}.get(sc.ranked, ("Special", "s2"))

    page_title = f"{urllib.parse.unquote(sc.username or '')} on {bm.title if bm else sc.beatmapname} [{bm.difficulty if bm else sc.beatmapdiff}] - Qlute"
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/score.css?v=3">', title=escape(page_title),
                  description=f"{urllib.parse.unquote(sc.username or '')} got {g} rank, {acc:.2f}% accuracy and {int(sc.points or 0)}pp "
                              f"on {bm.artist + ' - ' + bm.title if bm else sc.beatmapname} in Qlute.",
                  image=cover or None, canonical=f"{SiteURL}/score/{sc.id}", robots=None if sc.ranked == 1 else NOINDEX)
    h = '<div class="infoboxcontainer" id="score-page">'
    h += '<div class="infoboxtitle"><p>score</p></div>'

    # beatmap banner
    h += f'<a class="infobox sc-map" href="{map_url}" style="--cover:url(\'{escape(cover)}\')">'
    h += '<span class="sc-map-bg"></span><span class="sc-map-text">'
    h += f'<span class="sc-status {status[1]}">{status[0]}</span>'
    h += f'<span class="sc-map-title">{title}</span><span class="sc-map-artist">{artist}</span>'
    h += f'<span class="sc-map-diff">{diff}{(" &middot; Lv " + str(bm.Level)) if bm else ""}{(" &middot; mapped by " + escape(bm.mapper)) if bm else ""}</span>'
    h += '</span><span class="sc-map-go">View beatmap &rsaquo;</span></a>'

    # main result card
    h += '<section class="infobox sc-main">'
    h += f'<div class="sc-grade-wrap"><span class="sc-grade g-{escape(g)}">{escape(g)}</span>'
    if placement:
        h += f'<span class="sc-place">#{placement} on this map</span>'
    h += '</div><div class="sc-body">'
    pfp = escape(_pfp_url(player.pfppath if player else None))
    h += (f'<a class="sc-player" href="/user/{escape(sc.username or "")}"><img src="{pfp}" alt="" width="52" height="52">'
          f'<span><b>{name}</b><small title="{escape(when.strftime("%d %B %Y, %H:%M") if when else "")}">'
          f'played {timeform(timezone.now().timestamp() - when.timestamp()).lower() if when else "a while ago"}</small></span></a>')
    h += f'<div class="sc-score">{comp_score:,}</div>'
    h += '<div class="sc-tiles">'
    h += f'<div class="sc-tile sc-tile-pp"><span>Performance</span><b>{int(round(sc.points or 0)):,}pp</b></div>'
    h += f'<div class="sc-tile"><span>Accuracy</span><b>{acc:.2f}%</b></div>'
    combo_max = f'<small> / {bm.notecount:,}x</small>' if bm and bm.notecount else ''
    h += f'<div class="sc-tile"><span>Max combo</span><b>{sc.combo or 0:,}x{combo_max}</b></div>'
    h += f'<div class="sc-tile"><span>Mods</span><b>{"".join(f"<i class=sc-mod>{m}</i>" for m in mods) if mods else "None"}</b></div>'
    h += '</div></div></section>'

    # actions
    h += '<section class="infobox sc-actions">'
    if has_replay:
        h += f'<a class="sc-btn sc-btn-main" href="/apiv2/getreplay/{sc.id}" download>&#8595; Download replay</a>'
    h += f'<a class="sc-btn" href="{map_url}">Beatmap leaderboard</a>'
    h += f'<a class="sc-btn" href="/user/{escape(sc.username or "")}">{name}\'s profile</a>'
    viewer = request.COOKIES.get('username')
    viewer_login = checklogin(viewer, request.COOKIES.get('password', None)) if viewer else (False, False)
    staff_view = bool(viewer_login[0] and not viewer_login[1] and moderation.is_staff(viewer))
    if staff_view:
        h += f'<button type="button" class="sc-btn sc-btn-danger" id="sc-delete" data-id="{sc.id}">Delete score</button>'
    h += f'<span class="sc-dim sc-id">Score #{sc.id}{" &middot; " + escape(when.strftime("%d %b %Y")) if when else ""}</span>'
    h += '</section>'
    if staff_view:
        h += SCORE_DELETE_SCRIPT.replace("{back}", escape(map_url))
        h += score_review_html(sc)

    # judgements
    h += '<section class="infobox column sc-section spacebottom"><div class="sc-sec-head"><span class="title">Judgements</span>'
    h += f'<span class="sc-dim">{total:,} notes</span></div><div class="sc-judges">'
    for label, n, cls in (("Perfect", mx, "perfect"), ("Great", great, "great"), ("Meh", meh, "meh"), ("Miss", bad, "miss")):
        pct = n / total * 100 if total else 0
        h += (f'<div class="sc-judge j-{cls}"><span class="sc-judge-label">{label}</span><b>{n:,}</b>'
              f'<span class="sc-judge-bar"><span style="width:{pct:.2f}%"></span></span><small>{pct:.1f}%</small></div>')
    h += '</div></section></div>'
    html += h + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def score_review_html(sc):
    """Team-only anti-cheat panel on the score page: bot likelihood (private module) and every check."""
    try:
        from Chikara import anticheat
    except ImportError:
        from Chikara import anticheat_basic as anticheat
    try:
        rv = anticheat.score_review(sc)
    except Exception:
        sentry_sdk.capture_exception()
        rv = {"error": "The anti-cheat couldn't check this score."}
    h = '<section class="infobox column sc-section sc-ac"><div class="sc-sec-head"><span class="title">Anti-cheat</span>'
    h += '<span class="sc-dim">only the team sees this</span></div>'
    if rv.get("error"):
        return h + f'<p class="sc-dim">{escape(rv["error"])}</p></section>'
    pct = rv.get("percent")
    if pct is not None:
        band, word = ("high", "Likely botted") if pct >= 60 else ("mid", "Unclear") if pct >= 20 else ("low", "Looks human")
        h += (f'<div class="sc-ac-head ac-{band}"><div class="sc-ac-pct"><b>{pct:g}%</b><span>bot likelihood</span></div>'
              f'<div class="sc-ac-meter"><span class="sc-ac-word">{word}</span>'
              f'<span class="sc-ac-bar"><span style="width:{max(2, pct):.1f}%"></span></span>'
              '<small>An estimate from hit timing, not proof. Real plays here score under 15%; test bots 70-99%.</small></div></div>')
        h += '<table class="sc-ac-table"><thead><tr><th>Sign</th><th>This play</th><th>Real players</th><th>Bot-like</th></tr></thead><tbody>'
        for f in rv.get("factors", []):
            w = f["weight"]
            h += (f'<tr><td>{escape(f["name"])}</td><td>{escape(f["value"])}</td><td class="sc-dim">{escape(f["typical"])}</td>'
                  f'<td><span class="sc-ac-w" style="--w:{w * 100:.0f}%" title="{w * 100:.0f}%"></span></td></tr>')
        h += '</tbody></table>'
    h += '<details class="sc-ac-checks"' + ('' if pct is not None else ' open') + '><summary>All checks</summary>'
    h += '<table class="sc-ac-table"><thead><tr><th>Check</th><th>Result</th><th>Measured</th><th>Expected</th></tr></thead><tbody>'
    for c in rv.get("checks", []):
        st = c["status"]
        h += (f'<tr class="ac-st-{escape(st)}"><td>{escape(c["check"])}</td>'
              f'<td><span class="sc-ac-status">{"sign" if st == "warn" else escape(st)}</span></td>'
              f'<td>{escape(c["value"])}</td><td class="sc-dim">{escape(c["limit"])}</td></tr>')
    return h + '</tbody></table></details></section>'


# Delete button on the score page (team only). Uses the moderation API; the server re-checks staff.
SCORE_DELETE_SCRIPT = """<script>
(function () {
    const b = document.getElementById("sc-delete");
    if (!b) return;
    b.onclick = async () => {
        if (!confirm("Delete this score? The player's pp, accuracy and rank will be recalculated. This can't be undone.")) return;
        b.disabled = true; b.textContent = "Deleting...";
        try {
            const res = await fetch("/apiv2/mod/scores/" + b.dataset.id + "/delete",
                { method: "POST", headers: { "Content-Type": "application/json", "X-Chikara": "1" }, body: "{}" });
            const json = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(json.error || "The server said " + res.status);
            location.href = "{back}";
        } catch (err) {
            alert("Couldn't delete the score: " + err.message);
            b.disabled = false; b.textContent = "Delete score";
        }
    };
})();
</script>"""


# User score Front UX parser
def get_userscore(user='',recent=True,mini=False,limit=50):
    tols=0
    pek=1
    peak = ''
    timeest = ''
    if recent:
        scorecard = open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/scorecardtemplate.html").read()
    else:
        scorecard = open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/scoreweightedcard.html").read()
    for tmp in getscores(user=user,orderbybiggest=not recent,limit=limit):
        tols+=1
        acc=round(((tmp['max']+(tmp['great']/2)+(tmp['meh']/3))/(tmp['max']+tmp['great']+tmp['meh']+tmp['bad']))*100,2)
        if acc>=100:
            gradet='SS'
        elif acc>95 and not tmp['bad']:
            gradet='S'
        elif acc>90:
            gradet='A'
        elif acc>85:
            gradet='B'
        elif acc>69:
            gradet='C'
        elif acc<1:
            gradet='?'
        else:
            gradet='D'
        try:
            timeest = timeform(timezone.now().timestamp()-float(tmp['created'].timestamp()))
        except Exception as error:
            timeest = 'Error Processing Time:' + str(error) + ' ' + str(tmp['created'])
        weighted = str(int(tmp['weighted_pp']))
        weightedp = str(int(pek*100))
        modse=''
        for a in modsaliasab:
            if a in tmp['mods']:
                modse += f'<span class="mod">{a}</span>'
        peak += scorecard.replace("{date}",timeest).replace("{title}",str(tmp['beatmapname'])).replace("{artist}",str(tmp['artist'])).replace("{rank}",gradet).replace("{difficulty}",str(tmp['beatmapdiff'])).replace("{points}",str(int(tmp['points']))).replace("{weighted_points}",weighted).replace("{weighted_percentage}",weightedp).replace("{mods}",str(modse)).replace("{area}","/score/"+str(tmp["id"]))
        pek*=PP_WEIGHT
    if tols==0:
        peak +='<h3 class="bar">No Recent Plays -n-</h3>'
    return peak

# Score Processor

def stored_score(a):
    """Competitive score of a score row (dict). Rows from before pp v3 fall back to the old accuracy-only score."""
    if a.get('score') is not None:
        return int(a['score'])
    return process_score(a["max"], a["great"], a["meh"], getmult(a["mods"], speed=a["speed_multi"]),
                         a["max"] + a["great"] + a["meh"] + a["bad"])


def process_score(maxc=0, great=0, meh=0, multiplier=1.0, notecount=1):
    ratio = int(maxc)
    ratio += int(great) // 2
    ratio += int(meh) // 3

    note_count = float(max(notecount, 1))  # force float like C#
    accuracy = ratio / note_count

    scorelocal = accuracy * 1_000_000 * float(multiplier)
    scorelocal = max(0.0, scorelocal)

    return int(round(scorelocal))

# Playtime parse

def playtime(t):
    if t==None:
        return 'Never Played'
    t=int(t)
    if t==0:
        return '0h 0m'
    hour=t//3600
    t-=3600*hour
    min=t//60
    t-=60*min
    sec=t
    return str(hour)+'h '+str(min)+'m '+str(sec)+'s'

# Checking Login

def checklogin(usr,pwd="",signup=False,id=0):
    if usr in ('None','Guest'):
        return (0,0)
    try:
        id=int(id)
        id=0
    except Exception:
        id=0
    restricted = False
    if signup:
        result = User.objects.filter(
            Q(username=usr) | Q(id=id)
        ).first()
    else:
        result = passwords.user_for(usr, pwd)
    if result!=None and not signup:
        restricted = result.restricted
        if restricted:
            moderation.active_ban(usr)  # ends expired timed bans
            restricted = User.objects.filter(id=result.id).values_list("restricted", flat=True).first()
        result = 1
    elif result != None and signup:
        result = 1
    else:
        result=0
    if result:
        return (1,restricted)
    else:
        return (0,restricted)

        
def getsimscore(achieved,max,mult,type=str):
    mult=getmult(mult)
    mult=1000000*mult
    try:
        tmp=int((float(achieved)/float(max))*mult)
    except Exception:
        pass
    if max==0 and type==int:
        return 0
    elif max==0 and type!=int:
        return str(0)
    elif type==int:
        return tmp
    else:
        return format(tmp,',')


# ---------------------------------------------------------------- online players / public profiles
# Every logged-in game client posts apiv2/setstatus every few seconds, which stamps User.stattime.
ONLINE_SECONDS = 60


def online_players(limit=200, viewer=None):
    """Players online now that `viewer` may see (Chikara/privacy.py)."""
    from Chikara import privacy
    since = int(timezone.now().timestamp()) - ONLINE_SECONDS
    return (User.objects.filter(stattime__gte=since, restricted=False).exclude(username=None)
            .filter(privacy.visible_q(viewer)).order_by('ranking', 'username')[:limit])


def registered_count():
    """Number of accounts, cached for a minute so busy home pages don't run COUNT(*) on every request."""
    from django.core.cache import cache
    n = cache.get("registered_count")
    if n is None:
        n = User.objects.count()
        cache.set("registered_count", n, 60)
    return n


def online_count():
    since = int(timezone.now().timestamp()) - ONLINE_SECONDS
    return User.objects.filter(stattime__gte=since, restricted=False, appear_offline=False).count()


def _pfp_url(path):
    if not path:
        return NoProfilePictureURL
    return path if path.startswith("http") else DataURL + path


def _banner_url(path):
    """A player's profile banner (users.bannerpath, set at apiv2/banner), or "" for none."""
    if not path:
        return ""
    return path if path.startswith("http") else DataURL + path


def shown_banner(u):
    """The banner to show for player `u`: banners are a supporter perk (the Qlute team gets it too), and hidden
    while restricted. The file is kept either way, so it comes back when they support again."""
    if u is None or u.restricted or not u.bannerpath or not moderation.has_supporter_perks(u.username):
        return ""
    return _banner_url(u.bannerpath)


def banner_style(url):
    """class + style attribute text for a card that shows a banner behind it (CSS: .has-banner, --banner)."""
    return f' style="--banner:url(&quot;{escape(url)}&quot;)"' if url else ""


def _player_json(u, viewer=None):
    """A player for the game / website APIs. Presence is what `viewer` may see (Chikara/privacy.py): a hidden
    player looks offline (online false, status "", last_seen 0), same fields and types either way."""
    from Chikara import privacy
    online, status, last_seen = privacy.presence(u, viewer, int(timezone.now().timestamp()), ONLINE_SECONDS)
    return {
        "id": u.id,
        "username": u.username,
        "online": online,
        "status": status,
        "last_seen": last_seen,
        "rank": u.ranking or 0,
        "points": u.ranked_points or 0,
        "pfp": _pfp_url(u.pfppath),
        "banner": shown_banner(u),
        "supporter": moderation.is_supporter(u.username),
    }


def _score_json(sc):
    return {
        "id": sc.id,
        "beatmap": sc.beatmapname or "",
        "artist": sc.artist or "",
        "difficulty": sc.beatmapdiff or "",
        "beatmap_id": sc.beatmap_id or 0,
        "beatmapset_id": sc.beatmapset_id or 0,
        "points": round(sc.points or 0, 2),
        "score": sc.score if sc.score is not None else 0,
        "combo": sc.combo or 0,
        "max": sc.max or 0, "great": sc.great or 0, "meh": sc.meh or 0, "bad": sc.bad or 0,
        "mods": sc.mods or "",
        "speed": sc.speed_multi,
        "created": int(sc.created.timestamp()) if sc.created else 0,
    }


def public_profile(name, viewer=None):
    u = User.objects.filter(username=name).first()
    if u is None:  # an old name (Chikara/accounts.py)
        from Chikara import accounts
        old_id = accounts.resolve_old(name)
        u = User.objects.filter(id=old_id).first() if old_id else None
    if u is None:
        return None
    data = _player_json(u, viewer)
    if u.restricted:
        data.update({"restricted": True, "status": "", "online": False})
        return data
    score = u.ranked_score or 0
    lvl = player_levels.progress(score)
    extra_hints = {t: h for t, _, h, _ in EXTRA_MEDALS}
    from online.medals import unlock_times  # when each medal was first earned (online.medals)
    unlocked = unlock_times(u.username)
    # uploaded / claimed sets per status tab, same counts as the website profile (user())
    from submissions.models import Submission
    owned = Beatmap.objects.filter(beatmapsetid__in=Submission.objects.filter(owner=u.username).values("beatmapsetid"))
    map_counts = {sid: rows.values("beatmapsetid").distinct().count() for sid, rows in
                  (("1", owned.filter(ranked=1)), ("4", owned.filter(ranked__in=(2, 4))), ("0", owned.filter(ranked__lte=0)))}
    from Chikara import accounts
    data.update({
        "restricted": False,
        "previous_usernames": accounts.previous_names(u.id),
        "team_role": getattr(moderation.staff_of(u.username), "role", ""),
        "score": score,
        "level": lvl["level"],
        "level_pct": lvl["pct"],
        "level_next_score": lvl["next"],
        "beatmap_counts": map_counts,
        "accuracy": round(u.accuracy or 0, 2),
        "max_combo": u.max_combo or 0,
        "playtime": u.playtime or 0,
        "playtime_text": playtime(u.playtime),
        "judgements": {"max": u.max or 0, "great": u.great or 0, "meh": u.meh or 0, "bad": u.bad or 0},
        "joined": int(u.created.timestamp()) if u.created else 0,
        "bio": u.bio or "",
        "cardborder": CheaterCardBorder if u.restricted else (
            _pfp_url(moderation.border_shown(u.username, u.cardborder)) if moderation.border_shown(u.username, u.cardborder) else None),
        "medals": [{"title": t, "desc": d, "achieved": bool(g), "hint": MEDAL_HINTS.get(t) or extra_hints.get(t) or d,
                    "category": medal_category(t)[0],
                    "achieved_at": int(unlocked[i].timestamp()) if g and i in unlocked else 0}
                   for i, (t, d, g) in enumerate(getmedals(u.username))],
        "best": [_score_json(sc) for sc in Score.objects.filter(username=u.username, ranked=1).order_by('-points')[:10]],
        "recent": [_score_json(sc) for sc in Score.objects.filter(username=u.username).order_by('-created')[:10]],
    })
    return data

def update_pfp(request, command):
    return None


# ---------------------------------------------------------------- site search (users / online players / scores)
SEARCH_PAGE_SIZE = 50


def _search_args(request):
    query = (request.GET.get("query") or "").strip()[:64]
    try:
        page = max(0, int(request.GET.get("page") or 0))
    except ValueError:
        page = 0
    return query, page * SEARCH_PAGE_SIZE


def search_players(request, online_only=False):
    from Chikara import privacy
    query, start = _search_args(request)
    viewer = privacy.Viewer(request)
    users = User.objects.filter(restricted=False).exclude(username=None).exclude(username="")
    if online_only:
        users = users.filter(stattime__gte=int(timezone.now().timestamp()) - ONLINE_SECONDS).filter(privacy.visible_q(viewer))
    if query:
        users = users.filter(username__icontains=query)
    # Ranked players first (best rank on top), then everyone without a rank yet.
    users = users.order_by(F("ranking").asc(nulls_last=True), "username")
    rows = []
    for u in users[start:start + SEARCH_PAGE_SIZE]:
        data = _player_json(u, viewer)
        data["accuracy"] = round(u.accuracy or 0, 2)
        data["rank"] = u.ranking if u.ranking and u.ranking > 0 else 0
        rows.append(data)
    return JsonResponse({"results": rows, "page_size": SEARCH_PAGE_SIZE})


def search_scores(request):
    query, start = _search_args(request)
    sort = request.GET.get("sort") or "best"
    scores = Score.objects.exclude(username=None)
    restricted = User.objects.filter(restricted=True).values_list("username", flat=True)
    scores = scores.exclude(username__in=list(restricted))
    if request.GET.get("ranked", "1") == "1":
        scores = scores.filter(ranked=1)
    if query:
        scores = scores.filter(
            Q(username__icontains=query) |
            Q(beatmapname__icontains=query) |
            Q(artist__icontains=query) |
            Q(beatmapdiff__icontains=query)
        )
    scores = scores.order_by("-created" if sort == "recent" else "-points")
    rows = []
    for sc in scores[start:start + SEARCH_PAGE_SIZE]:
        data = _score_json(sc)
        data["username"] = sc.username
        data["ranked"] = sc.ranked
        rows.append(data)
    return JsonResponse({"results": rows, "page_size": SEARCH_PAGE_SIZE})


def admin_page(request):
    username = request.COOKIES.get('username')
    login = checklogin(username, request.COOKIES.get('password', None))
    if not (login[0] and not login[1] and moderation.is_staff(username)):
        html = header(request, title="Qlute - the black hole of death.", robots=NOINDEX) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read().replace('{sitetitle}', "404 not found o-o")
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
        return HttpResponse(html, status=404)
    head = '<link rel="stylesheet" href="/static/css/catalog.css"><link rel="stylesheet" href="/static/css/admin.css?v=7">'
    html = header(request, customhead=head, title="Qlute - admin panel", robots=NOINDEX)
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/admin.html").read()
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def chat_page(request):
    """Chat rooms on the website: the game's channels, private rooms and DMs (static/script/chat.js)."""
    username = request.COOKIES.get('username')
    login = checklogin(username, request.COOKIES.get('password', None))
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/chat.css?v=4">', title="Qlute - chat", robots=NOINDEX)
    if not login[0]:
        html += ('<div class="infoboxcontainer"><div class="infoboxtitle ct-titlebar"><h1>chat</h1></div>'
                 '<div class="infobox verticalpadding ct-login"><p>Log in to chat with other players.</p></div></div>')
    elif login[1]:
        html += ('<div class="infoboxcontainer"><div class="infoboxtitle ct-titlebar"><h1>chat</h1></div>'
                 '<div class="infobox verticalpadding ct-login"><p>Restricted accounts can\'t use chat.</p></div></div>')
    else:
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/chat.html").read().replace("{usertag}", escape(username))
        html += '<script src="/static/script/chat.js?v=2" defer></script>'
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def friends_page(request):
    """Your friends list: online first, with their status. Add people from their profile page."""
    from online.friends import friends_json
    username = request.COOKIES.get('username')
    login = checklogin(username, request.COOKIES.get('password', None))
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/friends.css?v=2">', title="Qlute - friends", robots=NOINDEX)
    html += '<div class="infoboxcontainer"><div class="infobox column spacetop spacebottom friends-page">'
    if not login[0]:
        html += '<div class="title">Friends</div><p class="friends-empty">Log in to see your friends.</p>'
    else:
        rows = friends_json(username)
        online = sum(1 for f in rows if f["online"])
        html += f'<div class="title">Friends <span class="friends-count">{online} online · {len(rows)} total</span></div>'
        if not rows:
            html += '<p class="friends-empty">No friends yet -n- Open someone\'s profile and press "Add friend".</p>'
        html += '<div class="friends-list">'
        for f in rows:
            name = escape(f["username"])
            if f["online"]:
                status = escape(f["status"]) or "Online"
            elif f["last_seen"]:
                status = "Last seen " + timeform(timezone.now().timestamp() - f["last_seen"])
            else:
                status = "Offline"
            mutual = ' <span class="friend-mutual">mutual</span>' if f["mutual"] else ""
            rank = f'#{f["rank"]:,}' if f["rank"] else "#?"
            html += (f'<div class="friend-row{" has-banner" if f.get("banner") else ""}" data-name="{name}"{banner_style(f.get("banner"))}>'
                     f'<a class="friend-main" href="/user/{urllib.parse.quote(f["username"])}">'
                     f'<img class="friend-pfp" src="{escape(f["pfp"])}" alt="">'
                     f'<span class="friend-info"><span class="friend-name">{name}{moderation.supporter_heart(f["username"])}{mutual}</span>'
                     f'<span class="friend-status"><i class="dot{" on" if f["online"] else ""}"></i>{status}</span></span></a>'
                     f'<span class="friend-rank">{rank}</span>'
                     f'<button class="profile-action friend-remove" data-target="{name}" title="Remove from your friends">Remove</button></div>')
        html += '</div><script src="/static/script/friends.js?v=1"></script>'
    html += '</div></div>'
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def search_page(request):
    head = '<link rel="stylesheet" href="/static/css/catalog.css?v=17"><link rel="stylesheet" href="/static/css/search.css?v=4">'
    html = header(request, customhead=head, title="Qlute - search players and scores",
                  description="Search Qlute players, see who's online right now, and look up the best and most recent scores.")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/search.html").read()
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)

# API

def api(request,command,value=None):
    command=command.split('/')
    if command[0] != "" and request.method == "POST":
        if command[0]=='signup' and len(command) >1:
            try:
                username = request.META.get('HTTP_USERNAME', '')
                password = request.META.get('HTTP_PASSWORD', '')
                from Chikara import accounts  # a name someone just changed away from stays theirs for a while
                accept=bool(password) and not checklogin(username, '',signup=True)[0] and not accounts.taken(username)
                
                # Process the credentials (authentication logic here)
                if accept:  
                    User.objects.create(
                    username=username,
                    password=passwords.make(password)  # the game sends SHA-256(password); stored salted
                    )
                    response = JsonResponse({"success": True}, status=200)
                else:
                    response =  JsonResponse({"success": False}, status=401)
            except json.JSONDecodeError:
                response = JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)
            return response
        elif command[0]=='login':
            try:
                username = request.POST.get("username")
                password = request.POST.get("password")
                password = passwords.prehash(password)
                accept=checklogin(username, password)[0]
                
                # Process the credentials (authentication logic here)
                if accept:  # Example check
                    stored = User.objects.filter(username=username).values_list("password", flat=True).first()
                    # Still on the old unsalted SHA-256: the website sends them to /changepassword.
                    response = JsonResponse({"success": True, "change_password": passwords.is_legacy(stored)}, status=200)
                    response.set_cookie("username", username, max_age=31536000)
                    response.set_cookie("password", password, max_age=31536000)
                else:
                    response =  JsonResponse({"success": False}, status=401)
            except json.JSONDecodeError:
                response = JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)
        elif command[0] == "ss":
            try:
                replay_data = request.body.decode("utf-8")

                accept=0
                user = request.META.get("HTTP_USERNAME","")
                game = checkgamehash(request)
                test=checklogin(user,request.META.get("HTTP_PASSWORD",""))
                if "AT" in request.META.get("HTTP_MODS",""):
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "Don't try to cheat with Auto dude. :/","error": 1})
                elif len(replay_data) < 64:
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "Replay data is empty.","error": 1})
                elif not test[0]:
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "Incorrect Credentials.","error": 1})
                elif test[1]:
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "You can't submit scores because your restricted.","error": 1})
                elif not allowsubmissions:
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "Submissions are disabled.","error": 1})
                elif not game[1] and not user in ("Kupachan" , "aquapoki"):
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": f"Please update to the latest version to submit scores.\nThis score will not be submitted :<","error": 1})
                else:
                    accept = 1
                if accept and allowsubmissions:
                   # ORDER BY points DESC 
                   try:
                       taken=int(float(request.META.get("HTTP_TAKEN","")))
                   except Exception as error:
                       print(str(error))
                       taken=0
                   mods = request.META.get("HTTP_MODS","")
                   combo = int(request.META.get("HTTP_COMBO",""))
                   smax = int(request.META.get("HTTP_MAX",""))
                   sgreat = int(request.META.get("HTTP_GREAT",""))
                   smeh = int(request.META.get("HTTP_MEH",""))
                   sbad = int(request.META.get("HTTP_BAD",""))
                   beatmap_id = int(request.META.get("HTTP_BEATMAPID",""))
                   beatmapset_id = int(request.META.get("HTTP_BEATMAPSETID",""))
                   speed_multi = float(request.META.get("HTTP_MULTIPLIER",""))
                   mult = getmult(mods,speed=speed_multi)
                   info = Beatmap.objects.filter(beatmapid = beatmap_id, beatmapsetid = beatmapset_id).first()
                   
                   from moderation import takedowns
                   if info is not None and takedowns.is_down(beatmapset_id):
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "This beatmap was taken down, so scores on it can't be submitted.","error": 1})
                   if info == None:
                    return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": "There is no beatmaps that I recognize with this one :/","error": 1})
                   else:
                        ranked = info.ranked
                        difficulty = info.difficulty
                        bpm = info.BPM
                   # every accepted play counts towards the catalog's "Plays" sort
                   from django.db.models import F
                   Beatmap.objects.filter(id=info.id).update(playcount=F("playcount") + 1)
                   replay_name = f"{REPLAYS}/{timezone.now().timestamp()}-{beatmapset_id}-{beatmap_id}-{user}-{mods}.qrf"
                   replayfile = open(replay_name, "w")
                   replayfile.write(replay_data)
                   replayfile.close()
                   # The server re-plays the replay with the client's exact judging: counts, combo,
                   # pp and score of every submission come from here, not from the client (pp v3).
                   try:
                       pointsdata = ppv2calc.calculate_ppv2(replay_name, storage_root + info.chartfile, mods=mods, speed=speed_multi)
                   except Exception:
                       if info.ranked != 0:
                           raise
                       pointsdata = None  # unranked map whose chart can't be read: keep the client's numbers
                   if pointsdata is not None:
                       client_points = re.search(r"^#Points: *([-+0-9.eE]+)", replay_data, re.M)
                       if (smax, sgreat, smeh, sbad) != (pointsdata.perfect, pointsdata.great, pointsdata.meh, pointsdata.bad) or \
                               (client_points and abs(float(client_points.group(1)) - pointsdata.points) > 0.001):
                           print(f"[pp] mismatch {user} map {beatmap_id}: client {client_points.group(1) if client_points else '?'}pp "
                                 f"P{smax} G{sgreat} M{smeh} B{sbad} / server {pointsdata.points}pp "
                                 f"P{pointsdata.perfect} G{pointsdata.great} M{pointsdata.meh} B{pointsdata.bad}")
                       smax, sgreat, smeh, sbad = pointsdata.perfect, pointsdata.great, pointsdata.meh, pointsdata.bad
                       combo = pointsdata.max_combo
                       finalscore = pointsdata.score
                   else:
                       finalscore = process_score(smax, sgreat, smeh, mult, info.notecount)
                   # Anti-cheat: cheating is refused and banned, suspicious plays are kept and reported (admin panel).
                   # Chikara/anticheat.py is private (git-ignored); without it the public Chikara/anticheat_basic.py runs.
                   try:
                       from Chikara import anticheat
                   except ImportError:
                       from Chikara import anticheat_basic as anticheat
                   if anticheat:
                       ac_header, ac_presses = anticheat.parse(replay_data)
                       ac_pp = User.objects.filter(username=user).values_list("ranked_points", flat=True).first() or 0
                       verdict = anticheat.check(user, ac_header, ac_presses, pointsdata, beatmap_id, beatmapset_id, mods, speed_multi,
                                                 anticheat.stored_replays(beatmap_id, exclude_path=replay_name),
                                                 ranked=info.ranked, pp_limit=max(ac_pp * PP_JUMP_RATIO, PP_JUMP_FLOOR),
                                                 history=anticheat.player_urs(user, exclude_path=replay_name),
                                                 levels=anticheat.player_levels(user, exclude_path=replay_name))
                       ban_msg = anticheat.act(user, verdict, beatmap_id, info.title, replay_name,
                                               pp=pointsdata.points if pointsdata else None,
                                               acc=pointsdata.accuracy if pointsdata else None)
                       if verdict.reject:
                           if verdict.duplicate:
                               os.remove(replay_name)
                           print(f"[anticheat] refused {user} map {beatmap_id}: {verdict.ban_reason or verdict.reject}")
                           return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,
                                                "msg": ban_msg or verdict.reject,"error": 1})
                       anticheat.accepted(user, pointsdata)
                   if info.ranked != 0:
                       points = pointsdata.points
                       maxpoints = pointsdata.max_points
                   else:
                       points = 0.000000001
                       maxpoints = 0.01
                   usr = User.objects.get(username = user)
                   current_pp = usr.ranked_points or 0
                   threshold = max(current_pp * PP_JUMP_RATIO, PP_JUMP_FLOOR)
                   # One row per player per map: the best by score (ties keep the older play).
                   previous = list(Score.objects.filter(beatmap_id = beatmap_id, username = user))
                   if previous:
                       best_old = max(stored_score({"score": t.score, "max": t.max or 0, "great": t.great or 0, "meh": t.meh or 0,
                                                    "bad": t.bad or 0, "mods": t.mods or "", "speed_multi": t.speed_multi})
                                      for t in previous)
                       submit = finalscore > best_old or all(t.replay_path is None for t in previous)
                   else:
                       submit = True
                   def save_score():
                       for t in previous:
                           t.delete()
                       Score.objects.create(
                           username = user,
                           beatmapname = info.title,
                           artist = info.artist,
                           points = points,
                           combo = combo,
                           beatmap_id = beatmap_id,
                           beatmapset_id = beatmapset_id,
                           max = smax,
                           great = sgreat,
                           meh = smeh,
                           bad = sbad,
                           beatmapdiff = difficulty,
                           ranked = info.ranked,
                           mods = mods,
                           maxpoints = maxpoints,
                           score = finalscore,
                           replay_path = replay_name.removeprefix(storage_root),
                           version = ppv2calc.PP_VERSION,
                           speed_multi = speed_multi
                       )
                   if accept and ranked > 0 and float(points) <= threshold:
                        if submit:
                            save_score()
                        # ACC and pp: the same 0.95^n weighting over the best PP_TOP_SCORES plays
                        best = list(getscores(user=user,orderbybiggest=True,limit=PP_TOP_SCORES))
                        weight_sum = sum(a['weight'] for a in best)
                        acc_sum = 0.0
                        for a in best:
                            p_, g_, m_, b_ = a['max'] or 0, a['great'] or 0, a['meh'] or 0, a['bad'] or 0
                            total = p_ + g_ + m_ + b_
                            if total:
                                acc_sum += (p_ + g_ / 2 + m_ / 3) / total * a['weight']
                        t = round(acc_sum / weight_sum * 100, 2) if weight_sum else 0
                        usr.accuracy = t
                        if usr.max != None:
                            usr.max += smax
                        else:
                            usr.max = smax
                        if usr.great != None:
                            usr.great += sgreat
                        else:
                            usr.great = sgreat
                        if usr.meh != None:
                            usr.meh += smeh
                        else:
                            usr.meh = smeh
                        if usr.bad != None:
                            usr.bad += sbad
                        else:
                            usr.bad = sbad
                        # Combo

                        max_combo = Score.objects.filter(username = user).order_by("-combo").first().combo
                        usr.max_combo = max_combo

                        # Points
                        rankedpoints = int(round(sum(a['weighted_pp'] for a in best)))
                        if usr.money is None:
                            usr.money = getpulses(rankedpoints)
                        else:
                            usr.money += getpulses(points)
                        rankedscore=usr.ranked_score
                        if rankedscore:
                            t+=(int(rankedscore)+int(finalscore))*dedipoints
                        users=[]
                        for a in User.objects.order_by("-ranked_points"):
                            name=a.username
                            pp=a.ranked_points
                            if not pp:
                                pp=0
                            users.append((name,pp))
                        if allowspoof:
                            for name,pp in getspp():
                                users.append((name,pp))
                            users=sorted(users, key=lambda x: x[1],reverse=True)
                        rankb=1
#                        if user != "aquapoki":
                        for a in users:
                            if a[0]==user:
                                break
                            rankb+=1
#                        else:
#                            rankb=(simulatedrank - ((rankedpoints/simulatedpp) * simulatedrank)) + 1
                        ranking=rankb
                        usr.ranked_points = rankedpoints
                        usr.ranking = ranking
                        if usr.playtime == None:
                            usr.playtime = int(taken)
                        else:
                            usr.playtime += int(taken)
                        if usr.ranked_score == None:
                            usr.ranked_score = finalscore
                            level = 1
                            rankedscore = finalscore
                        else:
                            usr.ranked_score += finalscore
                            level=player_levels.level(usr.ranked_score)
                        if usr.max_combo != None:
                            maxcombo = int(usr.max_combo)
                        else:
                            maxcombo = 0
                        if usr.accuracy != None:
                            accuracy = float(usr.accuracy) * 0.01
                        else:
                            accuracy = 0
                        if level<1:
                            level=1
                        usr.save()
                        try:  # today's point on everyone's profile graph (ranks shift for others too)
                            from Chikara import stathistory
                            stathistory.snapshot()
                        except Exception:
                            sentry_sdk.capture_exception()
                        from online import medals as medal_unlocks  # medals this play unlocked: the game pops them up
                        return JsonResponse({"rank": usr.ranking,"points": usr.ranked_points,"level": level,"score": usr.ranked_score,"accuracy": accuracy,"max_combo": maxcombo,"rankedmap": ranked,"msg": "", "error": 0,
                                             "medals": medal_unlocks.take_unseen_safe(user)})
                   elif accept and ranked == 0:
                        if submit:
                            save_score()
                        from online import medals as medal_unlocks
                        return JsonResponse({"rank": usr.ranking,"points": usr.ranked_points,"level": 0,"score": usr.ranked_score,"accuracy": usr.accuracy,"max_combo": usr.max_combo,"rankedmap": 0,"msg": "", "error": 0,
                                             "medals": medal_unlocks.take_unseen_safe(user)})
                   elif accept and ranked > 0:
                        usr.restricted = True
                        usr.save()
                        return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": ranked,"msg": restrictionnotice,"error": 1})
                   else:
                       return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": ranked,"msg": "Forbidden Score.","error": 1})
            except Exception as err:
                return JsonResponse({"rank": 0,"points": 0,"level": 0,"score":0,"accuracy": 0,"maxcombo": 0,"rankedmap": 0,"msg": str(traceback.format_exc()),"error": 1})
        return response
    elif command[0] != "" and request.method == "GET":
        if command[0]=='listmedal':
            username=command[1]
            data=[]
            try:
                for title,desc,gotit in getmedals(username):
                    data.append({'title':title,'desc':desc,'achieved':gotit})
                return HttpResponse(json.dumps(data))
            except Exception as err:
                return HttpResponse(err)
        elif command[0]=='getonline':
            from Chikara import privacy
            viewer = privacy.Viewer(request)
            players = [_player_json(u, viewer) for u in online_players(viewer=viewer)]
            return JsonResponse({"count": online_count(), "players": players})
        elif command[0]=='getuser' and len(command) > 1 and command[1] != "":
            try:
                from Chikara import privacy
                data = public_profile(urllib.parse.unquote(command[1]), privacy.Viewer(request))
            except Exception as err:
                return JsonResponse({"error": 1, "reason": str(err)}, status=500)
            if data is None:
                return JsonResponse({"error": 1, "reason": "No such player."}, status=404)
            return JsonResponse(data)
        elif command[0]=='getnotice':
            # Home-screen banners, managed in the admin panel (moderation.Notice).
            from moderation import content
            return JsonResponse(content.game_notices(), safe=False)
        elif command[0]=='cardborders':
            # Borders anyone can pick in their settings.
            from moderation import content
            from moderation.models import CardBorder
            return JsonResponse({"results": [content.border_json(b) for b in CardBorder.objects.filter(active=True).order_by("name")]})
        elif command[0]=='pfps':
            # Profile pictures for up to 50 usernames: ?names=a,b,c -> {"a": url, ...}. Unknown names are left out.
            names = [n for n in (request.GET.get("names") or "").split(",") if n][:50]
            rows = User.objects.filter(username__in=names).values_list("username", "pfppath", "restricted")
            return JsonResponse({name: (NoProfilePictureURL if restricted else _pfp_url(path)) for name, path, restricted in rows})

        elif command[0]=='getdifficulties' and not request.META.get('HTTP_BEATMAPSETID', '') == "":
            try:
                return JsonResponse(getdifficulties(request.META.get('HTTP_BEATMAPSETID', '')),safe=False)
            except Exception as error:
                return JsonResponse({"error" : 1,"reason": str(error)})
        elif command[0]=='getleaderboard' and not request.META.get('HTTP_BEATMAPID', '') == "":
            try:
                return JsonResponse(get_leaderboard(request.META.get('HTTP_BEATMAPID', '')),safe=False)
            except Exception as error:
                return JsonResponse({"error" : 1,"reason": str(error)})
        elif command[0]=='getleaderboard':
            return JsonResponse({"error" : 0,"reason": "No BeatmapID"})
        elif command[0]=='getreplay' and len(command) > 1 and command[1].isdigit():
            # Download the replay (.qrf) of a leaderboard score by its id.
            sc = Score.objects.filter(id=int(command[1])).values("username", "replay_path").first()
            if not sc or not sc["replay_path"]:
                return JsonResponse({"error": 1, "reason": "No replay for this score."}, status=404)
            if User.objects.filter(username=sc["username"], restricted=True).exists():
                return JsonResponse({"error": 1, "reason": "No replay for this score."}, status=404)
            path = os.path.realpath(os.path.join(storage_root, sc["replay_path"].lstrip("/")))
            if not path.startswith(os.path.realpath(REPLAYS) + os.sep) or not os.path.isfile(path):
                return JsonResponse({"error": 1, "reason": "Replay file is missing."}, status=404)
            with open(path, encoding="utf-8", errors="replace") as f:
                resp = HttpResponse(f.read(), content_type="text/plain; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{int(command[1])}.qrf"'
            return resp
        elif command[0]=='createroom' and 0 != 0:
            login=command[1:]
            currently=urllib.parse.unquote(login[5])
            beatmapid=login[4]
            beatmapsetid=login[3]
            roomname=urllib.parse.unquote(login[2])
            password=login[1]
            username=login[0]
            if checklogin(username,password):
                print(login)
                #mycursor.execute("INSERT INTO multiplayer (room_name,currently_playing,player_list,host,state) VALUES (%s,%s,%s,%s,%s)",(roomname,currently,username+';',username,1))
                #mydb.commit()
        elif command[0]=='getmultilist' and 0 != 0:
            try:
                #mycursor.execute("SELECT id,room_name,currently_playing,player_list,host,state FROM multiplayer ORDER BY created DESC LIMIT 5")
                #multilist=mycursor.fetchall()
                #print(multilist)
                #print({'name':'Lv. 15-629 Maps ONLY','current_players':36,'currently_playing':'DJ Dril4 - Nut Mommy'},{'name':'Lv. 3-10 Maps ONLY','current_players':653,'player_limit':9999,'currently_playing':'DJ Dril4 - Nut Mommy [CREEPER]'},)
                #multilist=()
                print(json.dumps(multilist))
            except Exception as err:
                print(err)
        elif command[0]=='s' and len(command) == 2:
            beatmap = Beatmap.objects.values_list('ranked', flat=True).filter(beatmapid=command[1]).first()
            if beatmap != None:
                return JsonResponse({"error" : 0, "RankedStatus" : beatmap})
            else:
                return JsonResponse({"error": 1, "msg": "BeatmapSet not found", "RankedStatus" : -1})

        elif command[0]=='s' and len(command) != 2:
            return JsonResponse({"error": 1, "msg": "Missing Beatmapset ID", "RankedStatus" : -1})
        elif command[0]=='rankstatus':
            # Batch rank status for a game client's local library: ?ids=1,2,3 (max 500)
            # -> {"statuses": {"1": 1, "2": 0, "3": -1}}; -1 = not on this server.
            ids = []
            for part in request.GET.get("ids", "").split(",")[:500]:
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
            found = dict(Beatmap.objects.filter(beatmapid__in=ids).values_list("beatmapid", "ranked"))
            return JsonResponse({"error": 0, "statuses": {str(i): found.get(i, -1) for i in ids}})
        elif command[0]=='search':
            # Filters, sorting and paging: Chikara/catalog.py
            from Chikara import catalog
            return catalog.search(request)
        elif command[0]=='beatmapfilters':
            from Chikara import catalog
            return catalog.filters(request)
        elif command[0]=='recommendation':
            # The logged-in player's comfortable level and recommended pp range (Chikara/recommend.py),
            # for the "Recommended Difficulty (Lv. X)" button. Anonymous: the new-player range.
            from Chikara import recommend
            me = moderation.request_user(request)
            data = recommend.profile(me.username if me else None)
            data["username"] = me.username if me else None
            return JsonResponse(data)
        elif command[0]=='searchusers':
            return search_players(request)
        elif command[0]=='searchplayers':
            return search_players(request, online_only=True)
        elif command[0]=='searchscores':
            return search_scores(request)
        elif command[0]=='menunotice':
            f=open('motd').read().rstrip('\n').split('\n')
            r=randint(1,len(f))
            return HttpResponse(f[r-1])
        elif command[0]=='setstatus':
            username = request.META.get('HTTP_USERNAME', '')
            password = request.META.get('HTTP_PASSWORD', '')
            text = request.META.get('HTTP_NOWPLAYING', '')
            login = checklogin(username, password)
            accept = login[0] and not login[1]
            if accept and len(text) >0:
                usr = User.objects.get(username = username)
                try:
                    welcome_back(usr.username, usr.stattime)  # 30+ days away -> "Welcome back Veteran"
                except Exception:
                    sentry_sdk.capture_exception()
                usr.stattime = int(timezone.now().timestamp())
                usr.status = text
                usr.save()
                return JsonResponse({"success": True})
            return JsonResponse({"success": False}, status=401)
        elif command[0]=='chkprofile':
            sentry_sdk.capture_message("You caught me!")
            msg=''
            usrpwd=request.META.get('HTTP_USERNAME', ''),request.META.get('HTTP_PASSWORD', '')
            prof = checklogin(usrpwd[0],usrpwd[1])
            game = checkgamehash(request)
            if prof[0]:
                ac=1
            else:
                ac=0
            if prof[1]:
                msg = moderation.ban_message(moderation.active_ban(usrpwd[0]))
            elif not game[1]:
                msg = f"This version of {game[0]} is not supported.\nPlease update to the latest version to continue."
            # Still on the old unsalted SHA-256: the game asks the player to change it on the website.
            legacy = bool(ac) and passwords.is_legacy(
                User.objects.filter(username=usrpwd[0]).values_list("password", flat=True).first())
            prompt={'success':ac,'notification':msg,'change_password':legacy}
            return JsonResponse(prompt)


        elif command[0]=='getstat':
            #print(login)
            accept=0
            t=0
            user = request.META.get('HTTP_USERNAME', '')
            if checklogin(user,'x',signup=True)[0]:
                accept=1
            if accept:
                if command[1] in ("pfp_path", "full"):
                    raw=True
                else:
                    raw=False
                t=getstat(command[1],user,raw=raw)
                return JsonResponse(t)
            else:
                return JsonResponse({"error":1})
        else:
            return HttpResponse('Unknown Command ' + str(command))
    else:
        return HttpResponse('(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧ Welcome to Chikara!')


# User Page

SITE_DESCRIPTION = ("Qlute is a free mania-style rhythm game inspired by osu!mania, with community beatmaps, "
                    "online rankings and leaderboards. Download it free for Windows, macOS and Linux.")
SITE_IMAGE = SiteURL + "/static/img/gamescreens/1.png"
NOINDEX = "noindex, follow"


def json_ld(data):
    """A <script type="application/ld+json"> block (structured data for search engines)."""
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{text}</script>'


ADMIN_MENU_ITEM = ('<a class="am-item" href="/admin"><svg viewBox="0 0 24 24" aria-hidden="true">'
                   '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/></svg>Admin panel</a>')


HEADER_BUTTONS = """<link rel="stylesheet" href="/static/css/headerbuttons.css?v=2">
<script src="/static/script/notifications.js?v=4" defer></script>
<div class="hb">
    <a class="hb-btn" href="/chat" aria-label="Chat rooms" title="Chat rooms">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12Z"/></svg>
    </a>
    <div class="hb-notif">
        <button type="button" class="hb-btn" id="notif-button" aria-label="Notifications" title="Notifications" aria-expanded="false" aria-controls="notif-panel">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/></svg>
            <span class="hb-badge" id="notif-badge"{badge_hidden}>{unread}</span>
        </button>
        <div class="hb-panel" id="notif-panel" hidden>
            <div class="hb-panel-head">
                <strong>Notifications</strong>
                <span class="hb-panel-actions">
                    <button type="button" id="notif-readall">Mark all read</button>
                    <button type="button" id="notif-clear">Clear</button>
                </span>
            </div>
            <ul class="hb-list" id="notif-list"><li class="hb-empty">Loading…</li></ul>
        </div>
    </div>
</div>"""


def header_buttons(username):
    """Chat + notifications buttons beside the account card (logged-in, unrestricted players only)."""
    from online.notifications import unread_count
    unread = unread_count(username)
    return (HEADER_BUTTONS.replace("{unread}", "99+" if unread > 99 else str(unread))
            .replace("{badge_hidden}", "" if unread else " hidden"))


def header(request, customhead="", title="{sitetitle}", description=None, image=None, robots=None,
           canonical=None, jsonld="", ogtype="website"):
    """The page head + site header. description / image / canonical feed the search + social preview tags;
    robots=NOINDEX keeps private or empty pages out of search results."""
    head = open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/header.html").read()
    username = request.COOKIES.get('username')
    password = request.COOKIES.get('password', None)
    proc = checklogin(username, password)
    accept=proc[0]
    if accept:
        head = head.replace("{usertag}", escape(username)).replace("{pfppath}", getstat("pfp_path",username)["url"])
    else:
        head = head.replace("{usertag}", "Guest").replace("{pfppath}", NoProfilePictureURL)
    if accept and not proc[1] and request.path != "/changepassword" and passwords.is_legacy(
            User.objects.filter(username=username).values_list("password", flat=True).first()):
        head += ('<div class="warning-box"><p>We\'ve upgraded how passwords are stored. '
                 '<a href="/changepassword" style="color: inherit; text-decoration: underline;">Please change your password.</a></p></div>')
    if proc[1]:
        notice = moderation.ban_message(moderation.active_ban(username)).split("\n", 1)[-1]
        head += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/restricted.html").read().replace("{details}", escape(notice).replace("\n", "<br>"))
    # Your profile banner behind the account card + the top of its menu (hidden while restricted, like the profile).
    banner = shown_banner(User.objects.filter(username=username).only("username", "bannerpath", "restricted").first()) \
        if accept and not proc[1] else ""
    head = head.replace("{cardbanner}", (" data-banner" + banner_style(banner)) if banner else "")
    staff = moderation.staff_of(username) if accept and not proc[1] else None
    head = head.replace("{headerbuttons}", header_buttons(username) if accept and not proc[1] else "")
    head = head.replace("{adminbutton}", ADMIN_MENU_ITEM if staff else "")
    head = head.replace("{description}", escape(description or SITE_DESCRIPTION))
    head = head.replace("{canonical}", escape(canonical or SiteURL + urllib.parse.quote(request.path)))
    head = head.replace("{ogimage}", escape(image or SITE_IMAGE))
    head = head.replace("{ogtype}", ogtype)
    head = head.replace("{robots}", robots or "index, follow, max-image-preview:large")
    head = head.replace("{jsonld}", jsonld)
    head = head.replace("{head}", customhead)
    head = head.replace("{sitetitle}", title)
    return head

def _clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0].rstrip(",.;:-") + "…"


def profile_seo(usr):
    """header() arguments for a public profile: a search/preview description with rank, pp and bio,
    the avatar as the preview image, and ProfilePage structured data."""
    if usr is None:
        return {}
    url = f"{SiteURL}/user/{usr.id}"
    rank = f"#{usr.ranking:,}" if usr.ranking and usr.ranking > 0 else "unranked"
    stats = f"{usr.username} on Qlute: {rank} global rank, {usr.ranked_points or 0:,}pp, {round(usr.accuracy or 0, 2)}% accuracy."
    from Chikara.bbcode import to_plain
    about = to_plain(usr.bio)
    description = stats + (" " + _clip(about, 300 - len(stats)) if about else
                           " See their best scores, medals and favourite beatmaps.")
    picture = getstat("pfp_path", usr.username)["url"]
    person = {"@type": "Person", "name": usr.username, "url": url, "image": picture}
    if about:
        person["description"] = _clip(about, 500)
    structured = json_ld({
        "@context": "https://schema.org",
        "@type": "ProfilePage",
        **({"dateCreated": usr.created.strftime("%Y-%m-%d")} if usr.created else {}),
        "mainEntity": person,
    })
    return {"description": description, "image": picture, "canonical": url, "jsonld": structured, "ogtype": "profile"}


TEAM_TITLES = {"mod": "Team Moderator", "admin": "Dev"}


def team_badge(username):
    """Badges beside a player's name: their Qlute team role, and the supporter heart."""
    staff = moderation.staff_of(username)
    html = f'<span class="team-badge {escape(staff.role)}">{TEAM_TITLES.get(staff.role, "Qlute Team")}</span>' if staff else ""
    if moderation.is_supporter(username):
        html += '<span class="team-badge supporter" title="Supports Qlute <3">&#9829; Supporter</span>'
    return html


def user_classic(request, user):
    """The profile page before the 2026-11-13 redesign (kept as a fallback: /user/<name>?classic=1)."""
    tickle= timezone.now().timestamp()
    usertest = checklogin(user,'x',signup=True,id=user)
    public = usertest[0] and not usertest[1]
    seo = profile_seo(User.objects.filter(username=user).first()) if public else {}
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=17"><link rel="stylesheet" href="/static/css/favorites.css?v=2">',
                  robots=None if public else NOINDEX, **seo)
    status = 200 if usertest[0] else 404
    if usertest[0]:
        if user=='aquapoki':
            emblem='Dev',
            donator=1
        else:
            emblem=''
            donator=0
        if not usertest[1]:
            html = html.replace('{sitetitle}',f"{escape(user)}'s Profile - Qlute")
            usr = User.objects.get(username = user)
            try:
                rank=usr.ranking
                points=usr.ranked_points
                score=usr.ranked_score
                level=player_levels.level(score)
                accuracy=usr.accuracy
                max=usr.max
                great=usr.great
                meh=usr.meh
                bad=usr.bad
            except Exception as err:
                rank = 0
                points = 0
                score = 0
                level = 1
                accuracy = 0
                max = 0
                great = 0
                meh = 0
                bad = 0
            minnum=0
            for a in getscores(user=user,orderbybiggest=True,limit=50):
                minnum+=1
            if rank<1:
                rank=None
            max_combo=usr.max_combo
            if rank:
                finalrank=format(rank,',')
            else:
                finalrank='?'
            html += '<div class="infoboxcontainer">'
            html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/usernamecard.html").read().replace('{username}',usr.username).replace('{pfppath}',getstat("pfp_path", user)["url"]).replace('{badges}', team_badge(usr.username)) # User name card

            html += '<div class="infobox infoboxtile column spacetop spacebottom" style="flex-direction:row;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;">'
            html += '<span>'
            try:
                from Chikara import privacy  # hidden by their privacy settings -> nothing shown
                on, st, seen = privacy.presence(usr, privacy.Viewer(request), timezone.now().timestamp(), 300)
                if on:
                    html += escape(st or "Online")
                elif seen:
                    html += 'Last Seen '+str( timeform(timezone.now().timestamp()-seen))
                elif usr.stattime is None:
                    html += 'New player <3'
            except Exception as err:
                html += 'New player <3'
            html += '</span>'
            if usr.created:
                joined = usr.created
                html += f'<span style="opacity:60%;" title="{timeform(timezone.now().timestamp()-usr.created.timestamp())}">Joined {joined.day} {joined.strftime("%B %Y")}</span>'
            html += '</div>' # Status Card
            viewer = request.COOKIES.get('username')
            viewerlogin = checklogin(viewer, request.COOKIES.get('password', None))
            actions = ''
            if viewerlogin[0] and not viewerlogin[1] and viewer != usr.username:
                from online.friends import is_friend
                added, mutual = is_friend(viewer, usr.username), is_friend(usr.username, viewer)
                label = ("Mutual friends ✓" if mutual else "Friend ✓") if added else "Add friend"
                actions += (f'<button class="profile-action friend-toggle{" on" if added else ""}" data-target="{escape(usr.username)}" '
                            f'title="{"Remove from your friends" if added else "Add to your friends list"}">{label}</button>')
                actions += f'<button class="profile-action report-open" data-target="{escape(usr.username)}" title="Report this player to the Qlute team">Report</button>'
            if moderation.is_staff(viewer) and viewerlogin[0]:
                actions += f'<a class="profile-action" href="/admin#user={urllib.parse.quote(usr.username)}" title="Open this player in the admin panel">Moderate</a>'
            if actions:
                html += f'<div class="infobox profile-actions">{actions}</div>' # Report / Moderate
            html += '<script src="/static/script/friends.js?v=1"></script>'
            html += '<div class="infobox column spacetop spacebottom">'
            html += '<div class="title">Stats</div>'
            html += '<div class="statblock">'
            html += '<span class="importantinfo"><p>Global Rank</p><h1 style="margin-top:0px;margin-bottom:35px;flex: 1;" class="box">#'+str(finalrank)+'</h1></span>'
            if level>0:
                html += '<span class="importantinfo"><p>Level</p><h1 style="margin-top:0px;margin-bottom:35px;flex: 1;" class="box">'+str(format(level,','))+'</h1></span>'
            html += '<div class="statinfo">'

            html += '<span class="bar">Ranked Points: '
            html += str(format(points,','))+'pp</span>'
            html += '<span class="bar">Total Play Time: '
            html += str(playtime(usr.playtime))+'</span>'
            if score>0:
                html += '<span class="bar">'
                html += 'Ranked Score: '
                html += str(format(score,','))+'</span>'
            html += '<span class="bar">'
            html += 'Accuracy: '
            html += str(round(accuracy,2))+'%</span>'
            html += '<span class="bar">'
            html += 'Total Perfect: '
            html += str(max)+'</span>'
            html += '<span class="bar">'
            html += 'Total Great: '
            html += str(great)+'</span>'
            html += '<span class="bar">'
            html += 'Total Meh: '
            html += str(meh)+'</span>'
            html += '<span class="bar">'
            html += 'Total Bad: '
            html += str(bad)+'</span>'
            html += '<span class="bar">'
            html += 'Max Combo: '
            html += str(max_combo)+'x</span>'
            if usr.username=='aquapoki':
                html += '<span class="bar">'
                html += 'Virgin Meter: '
                html += '69.420%</span>'
            html += "</div>"
            if issignin and username=='aquapoki':
                html += '<a href="/recentplay"><button class="minibutton">Recent Plays</button></a></span>'
            html += '</br></div></div>' # Ends Stats Section
            # "About me": osu!-style BBCode, centred. The owner edits it right here (bioeditor.js).
            owner = viewerlogin[0] and not viewerlogin[1] and viewer == usr.username
            if usr.bio or owner:
                from Chikara.bbcode import to_html
                BIO_MAX = moderation.limit_for(usr.username, "bio")
                shown = to_html(usr.bio) if usr.bio else '<p class="profile-bio-empty">You haven\'t written anything about yourself yet.</p>'
                html += '<div class="infobox column spacetop spacebottom profile-bio" id="profile-bio">'
                html += '<div class="profile-bio-head"><div class="title">About me</div>'
                if owner:
                    html += '<button type="button" class="profile-action" id="bio-edit">Edit</button>'
                html += f'</div><div class="profile-bio-text bb" id="bio-view">{shown}</div>'
                if owner:
                    html += (f'<textarea id="bio-raw" hidden data-max="{BIO_MAX}">{escape(usr.bio or "")}</textarea>'
                             '<script src="/static/script/bioeditor.js?v=3" defer></script>')
                html += '</div>'
            html += '<div style="display:flex;flex-wrap: wrap;flex-direction: row;align-content: center;justify-content: space-evenly;" class="infobox column spacetop spacebottom">'
            medco=0
            for title,desc,show in getmedals(user):
                if show:
                    suf=''
                else:
                    suf='opacity:20%;'
                html += '<div style="margin-top:10px;width:auto;'+suf+'" class="medalbox"><h3>'+str(title)+'</h3><p>'+str(desc)+'</p></div>'
            html += '</div>'
            html += '<div class="infobox column spacetop spacebottom">'
            html += '<div class="title">Best Scores</div>'
            html += get_userscore(user=user,recent=False,mini=True,limit=10)
            html += '</div>'


            html += '<div class="infobox column spacetop">'
            html += '<div class="title">Last Played</div>'
            html += get_userscore(user=user,recent=True,mini=True,limit=10)
            html += '</div>'

            # Favourite beatmaps: cards like the /beatmaps listing, filled by profilefavorites.js
            html += f'<div class="infobox column spacetop spacebottom" id="profile-favorites" data-user="{escape(usr.username)}">'
            html += '<div class="title">Favourite Beatmaps <span class="pf-count" id="pf-count"></span></div>'
            html += '<div class="catalog-grid" id="pf-grid"></div>'
            html += '<p class="catalog-hint" id="pf-hint">Loading favourites...</p>'
            html += '<button type="button" class="pf-more" id="pf-more" hidden>Show more</button>'
            html += '</div>'
            html += '<script src="/static/script/beatmapcard.js?v=1"></script><script src="/static/script/profilefavorites.js?v=10"></script>'
        elif usertest[1]:
            html += '<div class="info"><span class="center"><h1>o-o</h1><h3>This profile has been privated QnQ</h3></span></div>'
    else:
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read()
        html = html.replace('{sitetitle}',"404 not found o-o")
    html = html.replace('{sitetitle}', f"{escape(user)}'s Profile - Qlute")  # the restricted-profile page
#    tickle = round((timezone.now().timestamp() - tickle) / 0.001,2)
    html += "</div>"
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/report.html").read()
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html, status=status)

PROFILE_CLASSIC = False  # True = every profile uses the old layout (user_classic) again


def user(request, user):
    # Profiles live at /user/<id>. /user/<name> still works and redirects there; a numeric path is read as an id first.
    from django.http import HttpResponseRedirect
    target = user.strip("/")
    found = User.objects.filter(id=int(target)).first() if target.isdigit() else None
    if found:
        user = found.username or user
    else:
        found = User.objects.filter(username=target).first()
        if found is None:  # an old name (Chikara/accounts.py) still leads to the profile, like osu!
            from Chikara import accounts
            old_id = accounts.resolve_old(target)
            found = User.objects.filter(id=old_id).first() if old_id else None
        if found:
            qs = request.META.get("QUERY_STRING", "")
            return HttpResponseRedirect(f"/user/{found.id}" + (f"?{qs}" if qs else ""))
    if PROFILE_CLASSIC or request.GET.get("classic"):
        return user_classic(request, user)
    usertest = checklogin(user, 'x', signup=True, id=user)
    public = usertest[0] and not usertest[1]
    seo = profile_seo(User.objects.filter(username=user).first()) if public else {}
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=17"><link rel="stylesheet" href="/static/css/favorites.css?v=2">'
                                      '<link rel="stylesheet" href="/static/css/profile.css?v=14">',
                  robots=None if public else NOINDEX, **seo)
    status = 200 if usertest[0] else 404
    footer = (open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/report.html").read()
              + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read())
    if not usertest[0]:
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read()
        html = html.replace('{sitetitle}', "404 not found o-o")
        return HttpResponse(html + "</div>" + footer, status=status)
    html = html.replace('{sitetitle}', f"{escape(user)}'s Profile - Qlute")
    if usertest[1]:
        html += '<div class="info"><span class="center"><h1>o-o</h1><h3>This profile has been privated QnQ</h3></span></div>'
        return HttpResponse(html + "</div>" + footer, status=status)

    usr = User.objects.get(username=user)
    now = timezone.now().timestamp()
    rank = usr.ranking if usr.ranking and usr.ranking > 0 else None
    points = usr.ranked_points or 0
    score = usr.ranked_score or 0
    lvl = player_levels.progress(score)
    level, level_pct = lvl["level"], lvl["pct"]
    accuracy = round(usr.accuracy or 0, 2)
    hits = [("Perfect", usr.max or 0, "perfect"), ("Great", usr.great or 0, "great"),
            ("Meh", usr.meh or 0, "meh"), ("Miss", usr.bad or 0, "miss")]
    total_hits = sum(h[1] for h in hits)
    name = escape(urllib.parse.unquote(usr.username))

    from Chikara import privacy
    online, shown_status, last_seen = privacy.presence(usr, privacy.Viewer(request), now, 300)
    if online:
        status_text = escape(shown_status) if shown_status else "Online"
        presence = f'<span class="pf-presence on" title="{status_text}"><span class="pf-dot"></span><span class="pf-presence-text">{status_text}</span></span>'
    elif last_seen:
        presence = f'<span class="pf-presence">Last seen {timeform(now - last_seen).lower()}</span>'
    elif usr.stattime:
        presence = ""  # hidden by their privacy settings: show nothing rather than a made-up "new player"
    else:
        presence = '<span class="pf-presence">New player &lt;3</span>'
    joined = ""
    if usr.created:
        joined = (f'<span class="pf-joined" title="Joined {usr.created.day} {usr.created.strftime("%B %Y")} '
                  f'({timeform(now - usr.created.timestamp()).lower()})">Joined {usr.created.day} {usr.created.strftime("%B %Y")}</span>')

    viewer = request.COOKIES.get('username')
    viewerlogin = checklogin(viewer, request.COOKIES.get('password', None))
    actions = ''
    if viewerlogin[0] and not viewerlogin[1] and viewer != usr.username:
        from online.friends import is_friend
        added, mutual = is_friend(viewer, usr.username), is_friend(usr.username, viewer)
        label = ("Mutual friends ✓" if mutual else "Friend ✓") if added else "Add friend"
        actions += (f'<button class="profile-action pf-btn friend-toggle{" on" if added else ""}" data-target="{escape(usr.username)}" '
                    f'title="{"Remove from your friends" if added else "Add to your friends list"}">{label}</button>')
        actions += f'<button class="profile-action pf-btn pf-btn-quiet report-open" data-target="{escape(usr.username)}" title="Report this player to the Qlute team">Report</button>'
    if moderation.is_staff(viewer) and viewerlogin[0]:
        actions += f'<a class="profile-action pf-btn pf-btn-quiet" href="/admin#user={urllib.parse.quote(usr.username)}" title="Open this player in the admin panel">Moderate</a>'
    owner = viewerlogin[0] and not viewerlogin[1] and viewer == usr.username
    if owner:
        actions += '<a class="profile-action pf-btn pf-btn-quiet" href="/settings">Edit profile</a>'

    html += '<div class="infoboxcontainer" id="profile-page">'
    html += '<div class="infoboxtitle"><p>user page</p></div>'

    # ---- hero
    pfp = escape(getstat("pfp_path", user)["url"])
    hero_banner = shown_banner(usr)
    html += f'<section class="infobox pf-hero{" has-banner" if hero_banner else ""}"{banner_style(hero_banner)}>'
    html += (f'<div class="pf-avatar"><img src="{pfp}" id="userpfp" alt="{name}\'s avatar" width="120" height="120">'
             f'{"<span class=pf-avatar-dot title=online></span>" if online else ""}</div>')
    html += f'<div class="pf-ident"><div class="pf-name-row"><h1 class="pf-name">{name}</h1>{team_badge(usr.username)}</div>'
    from Chikara import countries
    where = (f'<a class="pf-country" href="/ranking?country={usr.country}">{countries.flag(usr.country)}{escape(countries.name(usr.country))}</a>'
             if countries.name(usr.country) and not usr.hide_country else "")
    # line 1: country · joined; line 2: what they're doing (its own line, so long song names don't crowd the rest)
    from Chikara import accounts
    old_names = accounts.previous_names(usr.id)
    aka = (f'<span class="pf-aka" title="Previously known as {escape(", ".join(old_names))}">Previously known as '
           f'{escape(", ".join(old_names[:3]))}{f" +{len(old_names) - 3}" if len(old_names) > 3 else ""}</span>') if old_names else ""
    html += f'<div class="pf-meta">{where}{joined}{aka}</div><div class="pf-status-row">{presence}</div></div>'
    html += f'<div class="pf-rank-block"><span class="pf-rank-label">Global rank</span><span class="pf-rank">#{format(rank, ",") if rank else "?"}</span>'
    html += f'<span class="pf-pp">{points:,} pp</span></div>'
    if actions:
        html += f'<div class="pf-actions">{actions}</div>'
    html += '</section>'
    html += '<script src="/static/script/friends.js?v=1"></script>'

    # ---- stats (beside the history graph when there is one: history 70%, stats 30%)
    stats = '<section class="infobox column pf-section pf-stats">'
    stats += '<div class="pf-tiles">'
    stats += (f'<div class="pf-tile pf-tile-level"><span class="pf-tile-label">Level</span><span class="pf-tile-value">{level:,}</span>'
             f'<span class="pf-level-bar" title="{lvl["into"]:,} / {lvl["needed"]:,} score into level {level} ({level_pct}%)">'
             f'<span style="width:{level_pct}%"></span></span>'
             f'<span class="pf-tile-sub">{_short_num(lvl["next"] - score)} score to level {level + 1}</span></div>')
    play_count = Score.objects.filter(username=usr.username).count()
    tiles = [("Accuracy", f"{accuracy}%"), ("Ranked score", f"{score:,}"), ("Play count", f"{play_count:,}"), ("Play time", playtime(usr.playtime)),
             ("Max combo", f"{usr.max_combo or 0:,}x")]
    if usr.username == 'aquapoki':
        tiles.append(("Virgin Meter", "69.420%"))  # easter egg, carried over from the classic profile
    for label, value in tiles:
        wide = " pf-tile-wide" if label == "Ranked score" else ""  # long number: a full row in the narrow column
        stats += f'<div class="pf-tile{wide}"><span class="pf-tile-label">{label}</span><span class="pf-tile-value">{value}</span></div>'
    stats += '</div>'
    # hit distribution
    stats += '<div class="pf-hits"><div class="pf-hits-head"><span class="pf-sec-title">Hit distribution</span>'
    stats += f'<span class="pf-dim">{total_hits:,} notes hit</span></div>'
    stats += '<div class="pf-hitbar" role="img" aria-label="' + ", ".join(f"{h[0]} {h[1]:,}" for h in hits) + '">'
    if total_hits:
        for label, n, cls in hits:
            if n:
                stats += f'<span class="pf-hit-{cls}" style="flex:{n}" title="{label}: {n:,}"></span>'
    stats += '</div><div class="pf-hit-legend">'
    for label, n, cls in hits:
        pct = f"{n / total_hits * 100:.1f}%" if total_hits else "0%"
        stats += f'<span><i class="pf-hit-{cls}"></i>{label} <b>{n:,}</b> <small>{pct}</small></span>'
    stats += '</div></div></section>'

    # ---- 90-day rank / pp / ranked score graph (Chikara/stathistory.py, drawn by profilehistory.js)
    from Chikara import stathistory
    stathistory.ensure_today()
    hist = stathistory.history(usr.id)
    graph = ''
    if len(hist) >= 2:
        graph = '<section class="infobox column pf-section" id="profile-history">'
        graph += ('<div class="pf-sec-head"><span class="title">History</span>'
                 '<div class="pf-hist-tabs" role="tablist">'
                 '<button type="button" class="pf-hist-tab" data-key="rank">Rank</button>'
                 '<button type="button" class="pf-hist-tab" data-key="pp">Performance</button>'
                 '<button type="button" class="pf-hist-tab" data-key="score">Ranked score</button></div></div>')
        graph += '<div class="pf-hist-summary"><span class="pf-hist-now"></span><span class="pf-hist-delta"></span><span class="pf-dim">last 90 days</span></div>'
        graph += '<div class="pf-hist-chart"></div>'
        graph += f'<script type="application/json" id="pf-history-data">{json.dumps(hist)}</script>'  # dates and numbers only
        graph += '</section><script src="/static/script/profilehistory.js?v=3"></script>'

    if graph:
        html += '<div class="pf-stat-cols">' + graph + stats + '</div>'
    else:
        html += stats

    # ---- about me (ids kept for bioeditor.js)
    if usr.bio or owner:
        from Chikara.bbcode import to_html
        BIO_MAX = moderation.limit_for(usr.username, "bio")
        shown = to_html(usr.bio) if usr.bio else '<p class="profile-bio-empty">You haven\'t written anything about yourself yet.</p>'
        html += '<section class="infobox column pf-section profile-bio" id="profile-bio">'
        html += '<div class="profile-bio-head"><div class="title">About me</div>'
        if owner:
            html += '<button type="button" class="profile-action" id="bio-edit">Edit</button>'
        html += f'</div><div class="profile-bio-text bb" id="bio-view">{shown}</div>'
        if owner:
            html += (f'<textarea id="bio-raw" hidden data-max="{BIO_MAX}">{escape(usr.bio or "")}</textarea>'
                     '<script src="/static/script/bioeditor.js?v=3" defer></script>')
        html += '</section>'

    # ---- medals
    medal_list = list(getmedals(user))
    earned = sum(1 for m in medal_list if m[2])
    html += '<section class="infobox column pf-section" id="medals">'
    html += f'<div class="pf-sec-head"><span class="title">Medals</span><span class="pf-dim">{earned} / {len(medal_list)} earned</span></div>'
    extra_hints = {t: h for t, _, h, _ in EXTRA_MEDALS}
    from online.medals import unlock_times
    unlocked = unlock_times(user)
    groups = {}
    for index, (title, desc, show) in enumerate(medal_list):
        cat, key = medal_category(title)
        groups.setdefault(cat, []).append((key, index, title, desc, show))
    for cat, items in sorted(groups.items(), key=lambda g: min(i[0] for i in g[1])):
        items.sort()
        got_n = sum(1 for i in items if i[4])
        html += (f'<div class="pf-medal-group"><div class="pf-medal-group-head"><span>{escape(cat)}</span>'
                 f'<span class="pf-dim">{got_n} / {len(items)}</span></div><div class="pf-medals">')
        for _key, index, title, desc, show in items:
            how = MEDAL_HINTS.get(title) or extra_hints.get(title) or desc
            when = unlocked.get(index) if show else None
            got = (f"Got it on {when.strftime('%-d %b %Y')}!" if when else "Got it!") if show else ""
            hint = escape(how)
            got_attr = f' data-got="{escape(got)}"' if got else ""  # shown under the hint (profile.css)
            html += (f'<div class="pf-medal{"" if show else " locked"}" tabindex="0" data-hint="{hint}"{got_attr} '
                     f'aria-label="{escape(title)}. {hint}{(" " + escape(got)) if got else ""}">'
                     f'<span class="pf-medal-icon">{"★" if show else "?"}</span>'
                     f'<span><b>{title}</b><small>{desc}</small></span></div>')
        html += '</div></div>'
    html += '</section>'

    # ---- scores
    html += '<div class="pf-score-cols">'
    html += '<section class="infobox column pf-section pf-scores"><div class="title">Best scores</div>'
    html += get_userscore(user=user, recent=False, mini=True, limit=10) + '</section>'
    html += '<section class="infobox column pf-section pf-scores"><div class="title">Last played</div>'
    html += get_userscore(user=user, recent=True, mini=True, limit=10) + '</section>'
    html += '</div>'

    html += '<script src="/static/script/beatmapcard.js?v=1"></script>'
    # ---- beatmaps they uploaded or claimed, Ranked / Special / Unranked tabs (filled by profilebeatmaps.js; hidden when there are none)
    from submissions.models import Submission
    owned = Beatmap.objects.filter(beatmapsetid__in=Submission.objects.filter(owner=usr.username).values("beatmapsetid"))
    map_tabs = [("1", "Ranked", owned.filter(ranked=1)), ("4", "Special", owned.filter(ranked__in=(2, 4))),
                ("0", "Unranked", owned.filter(ranked__lte=0))]
    map_tabs = [(sid, label, rows.values("beatmapsetid").distinct().count()) for sid, label, rows in map_tabs]
    if any(n for _, _, n in map_tabs):
        html += f'<section class="infobox column pf-section" id="profile-beatmaps" data-user="{escape(usr.username)}">'
        html += '<div class="title">Beatmaps</div><div class="pb-tabs" role="tablist">'
        for sid, label, n in map_tabs:
            html += (f'<button type="button" class="pb-tab" role="tab" data-status="{sid}" data-count="{n}"'
                     f'{" disabled" if not n else ""}>{label} <span class="pf-count">{n:,}</span></button>')
        html += '</div><div class="catalog-grid" id="pb-grid"></div>'
        html += '<p class="catalog-hint" id="pb-hint" hidden></p>'
        html += '<button type="button" class="pf-more" id="pb-more" hidden>Show more</button>'
        html += '</section>'
        html += '<script src="/static/script/profilebeatmaps.js?v=2"></script>'

    # ---- favourites (filled by profilefavorites.js)
    html += f'<section class="infobox column pf-section" id="profile-favorites" data-user="{escape(usr.username)}">'
    html += '<div class="title">Favourite Beatmaps <span class="pf-count" id="pf-count"></span></div>'
    html += '<div class="catalog-grid" id="pf-grid"></div>'
    html += '<p class="catalog-hint" id="pf-hint">Loading favourites...</p>'
    html += '<button type="button" class="pf-more" id="pf-more" hidden>Show more</button>'
    html += '</section>'
    html += '<script src="/static/script/profilefavorites.js?v=10"></script>'
    html += '</div>'  # #profile-page
    return HttpResponse(html + footer, status=status)


def _rank_name(u):
    return escape(urllib.parse.unquote(u.username or "")) + moderation.supporter_heart(u.username)


def ranking_tabs(active, country=""):
    """Performance / Ranked score / Countries tabs at the top of /ranking (the country filter is kept)."""
    keep = f"country={country}" if country else ""
    tabs = (("pp", "Performance", "/ranking" + ("?" + keep if keep else "")),
            ("score", "Ranked score", "/ranking?type=score" + ("&" + keep if keep else "")),
            ("countries", "Countries", "/ranking?type=countries"))
    return ("<div class='rk-head'><nav class='rk-tabs' aria-label='Ranking type'>"
            + "".join(f"<a class='rk-tab{' active' if k == active else ''}' href='{escape(u)}'{' aria-current=page' if k == active else ''}>{t}</a>"
                      for k, t, u in tabs) + "</nav></div>")


def country_ranking(request):
    """/ranking?type=countries: countries by their ranked players' total pp."""
    from Chikara import countries
    from django.db.models import Avg, Count, Sum
    rows = list(User.objects.filter(restricted=False, ranked_points__gt=0, hide_country=False).exclude(country=None).values("country")
                .annotate(pp=Sum("ranked_points"), players=Count("id"), acc=Avg("accuracy"), score=Sum("ranked_score"))
                .order_by("-pp"))
    rows = [r for r in rows if countries.name(r["country"])]
    top = {}
    for u in User.objects.filter(restricted=False, ranked_points__gt=0, hide_country=False).exclude(country=None).order_by("-ranked_points", "username"):
        top.setdefault(u.country, u)
    unknown = User.objects.filter(restricted=False, ranked_points__gt=0, country=None, hide_country=False).count()
    htmltemp = header(request, customhead='<link rel="stylesheet" href="/static/css/ranking.css?v=4">',
                      title="Qlute - country ranking", canonical=SiteURL + "/ranking?type=countries",
                      description="Qlute countries ranked by their players' total performance points.") \
        + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/ranking.html").read()
    html = ranking_tabs("countries")
    html += (f"<p class='rk-sub'>{len(rows):,} {'country' if len(rows) == 1 else 'countries'} &middot; ranked by their players' total performance points"
             + (f" &middot; {unknown:,} players don't have a country yet" if unknown else "") + "</p>")
    if not rows:
        html += "<div class='rk-empty'><h3>No countries yet: players get theirs the next time they log in.</h3></div>"
    else:
        html += ("<div class='table-scroll'><table class='rk-table rk-countries'><thead><tr>"
                 "<th class='rk-c-rank'>Rank</th><th class='rk-c-player'>Country</th><th>Total pp</th><th>Players</th>"
                 "<th class='rk-hide-sm'>Avg. accuracy</th><th class='rk-hide-sm'>Ranked score</th>"
                 "<th class='rk-hide-sm rk-c-top'>Top player</th></tr></thead><tbody>")
        for i, r in enumerate(rows, 1):
            code = r["country"]
            best = top.get(code)
            acc = round(r["acc"] or 0, 2)
            html += (f"<tr><td class='rk-c-rank'>#{i}</td>"
                     f"<td class='rk-c-player'><a href='/ranking?country={code}'>{countries.flag(code, 'lg')}"
                     f"<span class='rk-name'>{escape(countries.name(code))}</span></a></td>"
                     f"<td class='rk-pp'>{r['pp'] or 0:,}</td><td>{r['players']:,}</td>"
                     f"<td class='rk-hide-sm'><span class='rk-acc'><span class='rk-acc-bar'><span style='width:{max(0, min(100, acc))}%'></span></span>{acc}%</span></td>"
                     f"<td class='rk-hide-sm'>{r['score'] or 0:,}</td>"
                     f"<td class='rk-hide-sm rk-c-top'>"
                     + (f"<a href='/user/{escape(best.username or '')}'>{_rank_name(best)}</a>" if best else "")
                     + "</td></tr>")
        html += "</tbody></table></div>"
    html += "</div></div>"
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(htmltemp.replace('{entry}', html))


def ranking(request, command=""):
    try:
        page_no = max(1, int(command.strip("/") or 1))
    except ValueError:
        page_no = 1
    per_page = 50
    # ?type=score ranks by ranked score instead of performance points, ?type=countries ranks countries,
    # ?country=XX shows only that country's players
    from Chikara import countries
    kind = request.GET.get("type")
    if kind == "countries":
        return country_ranking(request)
    by_score = kind == "score"
    field = "ranked_score" if by_score else "ranked_points"
    country = (request.GET.get("country") or "").upper()
    country = country if countries.name(country) else ""
    params = {k: v for k, v in (("type", "score" if by_score else ""), ("country", country)) if v}
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    ranked = User.objects.filter(restricted=False, **{field + "__gt": 0})
    present = sorted({c for c in ranked.filter(hide_country=False).exclude(country=None).values_list("country", flat=True) if countries.name(c)},
                     key=countries.name)
    if country:
        ranked = ranked.filter(country=country, hide_country=False)
    total = ranked.count()
    pages = max(1, -(-total // per_page))
    where = f" in {countries.name(country)}" if country else ""
    title = (f"Qlute - ranked score ranking{where}" if by_score else f"Qlute - player ranking{where}" if country
             else "Qlute - global player ranking") + (f" (page {page_no})" if page_no > 1 else "")
    htmltemp = header(request, customhead='<link rel="stylesheet" href="/static/css/ranking.css?v=4">', title=title,
                      canonical=SiteURL + "/ranking" + (f"/{page_no}" if page_no > 1 else "") + qs,
                      description="The global Qlute leaderboard: the top rhythm game players ranked by performance points, "
                                  "with score, accuracy and hit counts.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/ranking.html").read()
    users = list(ranked.order_by("-" + field, "username")[per_page * (page_no - 1):per_page * page_no])
    tols = len(users)
    now = int(timezone.now().timestamp())
    me = request.COOKIES.get('username', None)
    from Chikara import privacy
    viewer = privacy.Viewer(request)

    def stats(u):
        return {"points": u.ranked_points or 0, "score": u.ranked_score or 0, "acc": round(u.accuracy or 0, 2),
                "perfect": u.max or 0, "great": u.great or 0, "meh": u.meh or 0, "miss": u.bad or 0,
                "online": privacy.presence(u, viewer, now, ONLINE_SECONDS)[0],
                "pfp": escape(_pfp_url(u.pfppath)), "href": "/user/" + escape(u.username or ""),
                "banner": shown_banner(u),
                "me": me is not None and urllib.parse.unquote(me) == urllib.parse.unquote(u.username or "")}

    html = ranking_tabs("score" if by_score else "pp", country)
    # country filter: only countries that have ranked players
    opts = "".join(f"<option value='{c}'{' selected' if c == country else ''}>{escape(countries.name(c))}</option>" for c in present)
    html += ("<form class='rk-filter' method='get' action='/ranking'>"
             + (f"<input type='hidden' name='type' value='score'>" if by_score else "")
             + f"{countries.flag(country, 'lg') if country else ''}"
             f"<select name='country' aria-label='Country' onchange='this.form.submit()'><option value=''>All countries</option>{opts}</select>"
             "<noscript><button type='submit'>Show</button></noscript>"
             f"<p class='rk-sub'>{total:,} ranked players{escape(where)} &middot; ranked by {'ranked score' if by_score else 'performance points'}</p></form>")
    if not tols:
        html += "<div class='rk-empty'><h3>Someone needs to play more! (｡•̀ᴖ•́｡)</h3></div>"
    rank = per_page * (page_no - 1)
    rows = list(users)
    if page_no == 1 and rows:
        podium = rows[:3]
        html += "<div class='rk-podium'>"
        for i, u in enumerate(podium):
            st = stats(u)
            place = i + 1
            dot = "<span class='rk-dot' title='online'></span>" if st["online"] else ""
            html += (f"<a class='rk-pod rk-pod-{place}{' rk-me' if st['me'] else ''}{' has-banner' if st['banner'] else ''}' href='{st['href']}'{banner_style(st['banner'])}>"
                     f"<span class='rk-medal'>#{place}</span>"
                     f"<span class='rk-pod-avatar'><img src='{st['pfp']}' alt='' loading='lazy' width='88' height='88'>{dot}</span>"
                     f"<span class='rk-pod-name'>{'' if u.hide_country else countries.flag(u.country)}{_rank_name(u)}</span>"
                     + (f"<span class='rk-pod-pp'>{st['score']:,}<small> score</small></span>"
                        f"<span class='rk-pod-meta'>{st['acc']}% acc &middot; {st['points']:,} pp</span></a>" if by_score else
                        f"<span class='rk-pod-pp'>{st['points']:,}<small> pp</small></span>"
                        f"<span class='rk-pod-meta'>{st['acc']}% acc &middot; {st['score']:,} score</span></a>"))
        html += "</div>"
    if rows:
        html += ("<div class='table-scroll'><table class='rk-table'><thead><tr>"
                 "<th class='rk-c-rank'>Rank</th><th class='rk-c-player'>Player</th>"
                 + ("<th>Score</th><th>Accuracy</th><th class='rk-hide-sm'>Points</th>" if by_score else
                    "<th>Points</th><th>Accuracy</th><th class='rk-hide-sm'>Score</th>") +
                 "<th class='rk-hide-sm rk-hit'>Perfect</th><th class='rk-hide-sm rk-hit'>Great</th>"
                 "<th class='rk-hide-sm rk-hit'>Meh</th><th class='rk-hide-sm rk-hit'>Miss</th></tr></thead><tbody>")
        for u in rows:
            rank += 1
            st = stats(u)
            dot = "<span class='rk-dot' title='online'></span>" if st["online"] else ""
            acc_w = max(0, min(100, st["acc"]))
            html += (f"<tr class='{'rk-me' if st['me'] else ''}'><td class='rk-c-rank'>#{rank}</td>"
                     f"<td class='rk-c-player'><a href='{st['href']}'><span class='rk-avatar'><img src='{st['pfp']}' alt='' loading='lazy' width='34' height='34'>{dot}</span>"
                     f"{'' if u.hide_country else countries.flag(u.country)}<span class='rk-name'>{_rank_name(u)}</span></a></td>"
                     f"<td class='rk-pp'>{st['score' if by_score else 'points']:,}</td>"
                     f"<td><span class='rk-acc'><span class='rk-acc-bar'><span style='width:{acc_w}%'></span></span>{st['acc']}%</span></td>"
                     f"<td class='rk-hide-sm'>{st['points' if by_score else 'score']:,}</td>"
                     f"<td class='rk-hide-sm rk-hit'>{st['perfect']:,}</td><td class='rk-hide-sm rk-hit'>{st['great']:,}</td>"
                     f"<td class='rk-hide-sm rk-hit'>{st['meh']:,}</td><td class='rk-hide-sm rk-hit rk-miss'>{st['miss']:,}</td></tr>")
        html += "</tbody></table></div>"

    # pagination: first, prev, a window around the current page, next, last
    def pg(n, label=None, cls=""):
        if n == page_no and label is None:
            return f"<span class='rk-page rk-page-cur' aria-current='page'>{n}</span>"
        return f"<a class='rk-page {cls}' href='/ranking/{n}{escape(qs)}'>{label or n}</a>"
    nav = []
    if page_no > 1:
        nav.append(pg(page_no - 1, "&lsaquo; prev", "rk-page-step"))
    window = sorted({1, pages, *range(max(1, page_no - 2), min(pages, page_no + 2) + 1)})
    last = 0
    for n in window:
        if n - last > 1:
            nav.append("<span class='rk-gap'>&hellip;</span>")
        nav.append(pg(n))
        last = n
    if page_no < pages:
        nav.append(pg(page_no + 1, "next &rsaquo;", "rk-page-step"))
    html += "<nav class='rk-pages' aria-label='Ranking pages'>" + "".join(nav) + "</nav>"
    html += "</div></div>"
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    htmltemp = htmltemp.replace('{entry}', html)
    return HttpResponse(htmltemp)


QLUTE_REPO = "Jinkku/Qlute"
DL_PLATFORMS = (("windows", "Windows.zip"), ("mac", "MacOS.zip"), ("linux", "Linux.zip"))
_release_cache = {"at": 0, "data": None}


def latest_release():
    """Latest Qlute GitHub release: version, date and a direct zip url + size per platform (cached for an hour)."""
    now = time.time()
    if _release_cache["data"] and now - _release_cache["at"] < 3600:
        return _release_cache["data"]
    data = {"version": "", "date": "",
            "assets": {os_: {"url": f"https://github.com/{QLUTE_REPO}/releases/latest/download/{name}", "file": name, "size": ""}
                       for os_, name in DL_PLATFORMS}}
    try:
        import urllib.request
        req = urllib.request.Request(f"https://api.github.com/repos/{QLUTE_REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "qlute-site"})
        with urllib.request.urlopen(req, timeout=5) as r:
            rel = json.load(r)
        data["version"] = rel.get("name") or rel.get("tag_name") or ""
        data["date"] = (rel.get("published_at") or "")[:10]
        by_name = {a["name"]: a for a in rel.get("assets", [])}
        for os_, name in DL_PLATFORMS:
            a = by_name.get(name)
            if a:
                data["assets"][os_] = {"url": a["browser_download_url"], "file": name,
                                       "size": f"{a['size'] / 1048576:.0f} MB"}
        _release_cache.update(at=now, data=data)
    except Exception:
        _release_cache.update(at=now - 3300, data=data)  # GitHub unreachable: retry in ~5 minutes
    return data


def download_html():
    rel = latest_release()
    html = open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/download.html").read()
    html = html.replace("{dl_version}", escape(rel["version"])).replace("{dl_date}", escape(rel["date"]))
    for os_, a in rel["assets"].items():
        html = (html.replace("{dl_%s_url}" % os_, escape(a["url"])).replace("{dl_%s_file}" % os_, escape(a["file"]))
                .replace("{dl_%s_size}" % os_, escape(a["size"])))
    return html


def base(request, uri,command=""):
    status = 200
    logged_in = uri == "" and checklogin(request.COOKIES.get('username', None), request.COOKIES.get('password', None))[0]
    if uri == "" and not logged_in:
        structured = json_ld([{
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Qlute",
            "url": SiteURL + "/",
        }, {
            "@context": "https://schema.org",
            "@type": "VideoGame",
            "name": "Qlute",
            "url": SiteURL + "/",
            "description": SITE_DESCRIPTION,
            "image": SITE_IMAGE,
            "genre": ["Rhythm game", "Music game"],
            "gamePlatform": ["Windows", "macOS", "Linux"],
            "operatingSystem": "Windows 10+, macOS, Linux",
            "applicationCategory": "GameApplication",
            "playMode": ["SinglePlayer", "MultiPlayer"],
            "author": {"@type": "Organization", "name": "Jinkku Productions"},
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "sameAs": ["https://github.com/Jinkku/Qlute", "https://jinkku.itch.io/qlute", "https://www.youtube.com/@qlutegame"],
        }])
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/home.css?v=2">', title="Qlute - A free rhythm game inspired by osu!mania", canonical=SiteURL + "/", jsonld=structured) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/home.html").read().replace("{usercount}",format(registered_count(),",")).replace("{active}",format(online_count(),","))
    elif uri == "":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/news.css?v=1">', title="Qlute - home page", canonical=SiteURL + "/") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/homes.html").read().replace("{news}", __import__("moderation.news", fromlist=["x"]).latest_html()).replace("{usertag}",escape(request.COOKIES.get('username', None))).replace("{usercount}",format(registered_count(),",")).replace("{active}",format(online_count(),","))
    elif uri.strip("/") == "beatmaps":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=18">', title="Qlute - beatmap listing",
                      canonical=SiteURL + "/beatmaps",
                      description="Browse every Qlute beatmap: search by title, artist or mapper, filter by status, genre and language, "
                                  "preview songs and download them free.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/beatmaps.html").read()
    elif uri.strip("/") == "download":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/download.css?v=2">', title="Download Qlute - free rhythm game for Windows, macOS and Linux", canonical=SiteURL + "/download",
                      description="Download Qlute free for Windows 10+, macOS and Linux, or grab the source code on GitHub. "
                                  "A mania-style rhythm game inspired by osu!mania.") + download_html()
    elif uri.strip("/") == "rules":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/rules.css?v=2">', title="Qlute - rules",
                      canonical=SiteURL + "/rules",
                      description="The Qlute community rules: accounts, fair play, chat conduct, multiplayer, "
                                  "profiles, beatmap submissions and how rules are enforced.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/rules.html").read()
    elif uri.strip("/") == "dmca":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/rules.css?v=2">', title="Qlute - DMCA & copyright",
                      canonical=SiteURL + "/dmca",
                      description="How copyright holders can ask for content on Qlute to be taken down, "
                                  "and how uploaders can file a counter-notice.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/dmca.html").read()
    else:
        status = 404
        html = header(request, title="Qlute - the black hole of death.", robots=NOINDEX) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read().replace('{sitetitle}',"404 not found o-o")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html, status=status)
