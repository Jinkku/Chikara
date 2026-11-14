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
medals=("The End","You've made it"),("Baby Steps","Welcome to the Game"),(">~<","Impressive"),('Psycho','Dang you can read that?!'),('Welcome back Veteran','Glad to see you back'),('D-Ranker','Unrhythmic'),('S-Ranker','Like to show off. huh?'),('Donator','Thanks for Supporting the Game!'),('Sniper','First Comes, First Serve!'),('BreakThrough','Unstoppable'),('Top 100','You are the chosen one'),('Top 50','Almost There'),('Top 10','Grab some Popcorn 🍿'),('Top 1,000','Still a Virgin at this game are you?'),("Making the game better", "You are making the community better!"),("Team Moderator", "Keeping Qlute fun and fair for everyone") # Medals
# How to earn each original medal: the profile's hover hint (their descriptions are flavour text). Keep in step with
# getmedals() and MEDALS.md.
MEDAL_HINTS = {
    "The End": "Climb all the way to global rank #1. Nobody above you. Nobody.",
    "Baby Steps": "Earn your very first pp (more than 1). Everyone starts somewhere!",
    ">~<": "Chain a combo of over 1,000 without dropping it",
    "Psycho": "Coming soon\u2122. Even the devs don't know how yet \U0001F440",
    "Welcome back Veteran": "Coming soon\u2122. Pack your bags, veteran",
    "D-Ranker": "Miss over 1,000 notes in total. A badge of honour, honestly",
    "S-Ranker": "Land over 1,000 Perfect hits in total",
    "Donator": "Coming soon\u2122. Thank-you gifts are on their way",
    "Sniper": "Coming soon\u2122. Keep your sights steady",
    "BreakThrough": "Coming soon\u2122. The wall hasn't been built yet",
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
)
leveltemp=0.0000005 # Level multiplier
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
                 ("/rules", "0.4", "monthly"))
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
        sets = (Beatmap.objects.values("beatmapsetid").annotate(updated=Max("created"))
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
        t = int(int(ranked_score) * leveltemp)
    
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
        t = user.cardborder if user else None
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
            "donator": False,
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
    level=int(score*leveltemp)
    if level<1:
        level=1
    accuracy=getstat('accuracy',user)
    max=getstat('max',user)
    great=getstat('great',user)
    meh=getstat('meh',user)
    bad=getstat('bad',user)
    max_combo=getstat('max_combo',user)
    for title,desc in medals:
        show=0
        if medco==0 and rank==1:
            show=1
        elif medco==1 and points>1:
            show=1
        elif medco==3 and points>1000:
            show=0
        elif medco==2 and max_combo>1000:
            show=1
        elif medco==5 and bad>1000:
            show=1
        elif medco==6 and max>1000:
            show=1
        elif medco==7 and donator:
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
        medco+=1
        yield (title,desc,show)
    earned = _extra_medal_checks(user)
    for title, desc, _hint, key in EXTRA_MEDALS:
        yield (title, desc, 1 if earned.get(key) else 0)


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
    level = int((u.ranked_score or 0) * leveltemp)
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
    }
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
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/score.css?v=1">', title=escape(page_title),
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
    h += f'<span class="sc-dim sc-id">Score #{sc.id}{" &middot; " + escape(when.strftime("%d %b %Y")) if when else ""}</span>'
    h += '</section>'

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


def online_players(limit=200):
    since = int(timezone.now().timestamp()) - ONLINE_SECONDS
    return User.objects.filter(stattime__gte=since, restricted=False).exclude(username=None).order_by('ranking', 'username')[:limit]


def online_count():
    since = int(timezone.now().timestamp()) - ONLINE_SECONDS
    return User.objects.filter(stattime__gte=since, restricted=False).count()


def _pfp_url(path):
    if not path:
        return NoProfilePictureURL
    return path if path.startswith("http") else DataURL + path


def _banner_url(path):
    """A player's profile banner (users.bannerpath, set at apiv2/banner), or "" for none."""
    if not path:
        return ""
    return path if path.startswith("http") else DataURL + path


def banner_style(url):
    """class + style attribute text for a card that shows a banner behind it (CSS: .has-banner, --banner)."""
    return f' style="--banner:url(&quot;{escape(url)}&quot;)"' if url else ""


def _player_json(u):
    now = int(timezone.now().timestamp())
    online = u.stattime is not None and now - u.stattime <= ONLINE_SECONDS
    return {
        "id": u.id,
        "username": u.username,
        "online": online,
        "status": (u.status or "") if online else "",
        "last_seen": u.stattime or 0,
        "rank": u.ranking or 0,
        "points": u.ranked_points or 0,
        "pfp": _pfp_url(u.pfppath),
        "banner": "" if u.restricted else _banner_url(u.bannerpath),
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


def public_profile(name):
    u = User.objects.filter(username=name).first()
    if u is None:
        return None
    data = _player_json(u)
    if u.restricted:
        data.update({"restricted": True, "status": "", "online": False})
        return data
    score = u.ranked_score or 0
    level_raw = score * leveltemp
    extra_hints = {t: h for t, _, h, _ in EXTRA_MEDALS}
    # uploaded / claimed sets per status tab, same counts as the website profile (user())
    from submissions.models import Submission
    owned = Beatmap.objects.filter(beatmapsetid__in=Submission.objects.filter(owner=u.username).values("beatmapsetid"))
    map_counts = {sid: rows.values("beatmapsetid").distinct().count() for sid, rows in
                  (("1", owned.filter(ranked=1)), ("4", owned.filter(ranked__in=(2, 4))), ("0", owned.filter(ranked__lte=0)))}
    data.update({
        "restricted": False,
        "team_role": getattr(moderation.staff_of(u.username), "role", ""),
        "score": score,
        "level": max(1, int(level_raw)),
        "level_pct": int((level_raw - int(level_raw)) * 100) if level_raw >= 1 else int(level_raw * 100),
        "beatmap_counts": map_counts,
        "accuracy": round(u.accuracy or 0, 2),
        "max_combo": u.max_combo or 0,
        "playtime": u.playtime or 0,
        "playtime_text": playtime(u.playtime),
        "judgements": {"max": u.max or 0, "great": u.great or 0, "meh": u.meh or 0, "bad": u.bad or 0},
        "joined": int(u.created.timestamp()) if u.created else 0,
        "bio": u.bio or "",
        "cardborder": CheaterCardBorder if u.restricted else (_pfp_url(u.cardborder) if u.cardborder else None),
        "medals": [{"title": t, "desc": d, "achieved": bool(g), "hint": MEDAL_HINTS.get(t) or extra_hints.get(t) or d}
                   for t, d, g in getmedals(u.username)],
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
    query, start = _search_args(request)
    users = User.objects.filter(restricted=False).exclude(username=None).exclude(username="")
    if online_only:
        users = users.filter(stattime__gte=int(timezone.now().timestamp()) - ONLINE_SECONDS)
    if query:
        users = users.filter(username__icontains=query)
    # Ranked players first (best rank on top), then everyone without a rank yet.
    users = users.order_by(F("ranking").asc(nulls_last=True), "username")
    rows = []
    for u in users[start:start + SEARCH_PAGE_SIZE]:
        data = _player_json(u)
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
    head = '<link rel="stylesheet" href="/static/css/catalog.css"><link rel="stylesheet" href="/static/css/admin.css?v=3">'
    html = header(request, customhead=head, title="Qlute - admin panel", robots=NOINDEX)
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/admin.html").read()
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
                     f'<span class="friend-info"><span class="friend-name">{name}{mutual}</span>'
                     f'<span class="friend-status"><i class="dot{" on" if f["online"] else ""}"></i>{status}</span></span></a>'
                     f'<span class="friend-rank">{rank}</span>'
                     f'<button class="profile-action friend-remove" data-target="{name}" title="Remove from your friends">Remove</button></div>')
        html += '</div><script src="/static/script/friends.js?v=1"></script>'
    html += '</div></div>'
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)


def search_page(request):
    head = '<link rel="stylesheet" href="/static/css/catalog.css?v=17"><link rel="stylesheet" href="/static/css/search.css?v=2">'
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
                accept=bool(password) and not checklogin(username, '',signup=True)[0]
                
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
                            level=int(usr.ranked_score*leveltemp)
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
                        return JsonResponse({"rank": usr.ranking,"points": usr.ranked_points,"level": level,"score": usr.ranked_score,"accuracy": accuracy,"max_combo": maxcombo,"rankedmap": ranked,"msg": "", "error": 0})
                   elif accept and ranked == 0:
                        if submit:
                            save_score()
                        return JsonResponse({"rank": usr.ranking,"points": usr.ranked_points,"level": 0,"score": usr.ranked_score,"accuracy": usr.accuracy,"max_combo": usr.max_combo,"rankedmap": 0,"msg": "", "error": 0})
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
            players = [_player_json(u) for u in online_players()]
            return JsonResponse({"count": online_count(), "players": players})
        elif command[0]=='getuser' and len(command) > 1 and command[1] != "":
            try:
                data = public_profile(urllib.parse.unquote(command[1]))
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
    staff = moderation.staff_of(username) if accept and not proc[1] else None
    head = head.replace("{adminbutton}", '<a href="/admin"><button class="login-btn">Admin Panel</button></a>' if staff else "")
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
    staff = moderation.staff_of(username)
    if staff is None:
        return ""
    return f'<span class="team-badge {escape(staff.role)}">{TEAM_TITLES.get(staff.role, "Qlute Team")}</span>'


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
                level=int(score*leveltemp)
                if level<1:
                    level=1
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
                if (usr.stattime,usr.status)!=(None,None) and not timezone.now().timestamp()-usr.stattime>300:
                    html += usr.status
                else:
                    html += 'Last Seen '+str( timeform(timezone.now().timestamp()-usr.stattime))
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
                from Chikara.usersettings import BIO_MAX
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
        if found:
            qs = request.META.get("QUERY_STRING", "")
            return HttpResponseRedirect(f"/user/{found.id}" + (f"?{qs}" if qs else ""))
    if PROFILE_CLASSIC or request.GET.get("classic"):
        return user_classic(request, user)
    usertest = checklogin(user, 'x', signup=True, id=user)
    public = usertest[0] and not usertest[1]
    seo = profile_seo(User.objects.filter(username=user).first()) if public else {}
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=17"><link rel="stylesheet" href="/static/css/favorites.css?v=2">'
                                      '<link rel="stylesheet" href="/static/css/profile.css?v=4">',
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
    level_raw = score * leveltemp
    level = max(1, int(level_raw))
    level_pct = int((level_raw - int(level_raw)) * 100) if level_raw >= 1 else int(level_raw * 100)
    accuracy = round(usr.accuracy or 0, 2)
    hits = [("Perfect", usr.max or 0, "perfect"), ("Great", usr.great or 0, "great"),
            ("Meh", usr.meh or 0, "meh"), ("Miss", usr.bad or 0, "miss")]
    total_hits = sum(h[1] for h in hits)
    name = escape(urllib.parse.unquote(usr.username))

    online = usr.stattime is not None and now - usr.stattime <= 300
    if online:
        presence = f'<span class="pf-presence on"><span class="pf-dot"></span>{escape(usr.status) if usr.status else "Online"}</span>'
    elif usr.stattime:
        presence = f'<span class="pf-presence">Last seen {timeform(now - usr.stattime).lower()}</span>'
    else:
        presence = '<span class="pf-presence">New player &lt;3</span>'
    joined = ""
    if usr.created:
        joined = (f'<span class="pf-joined" title="{timeform(now - usr.created.timestamp())}">'
                  f'Joined {usr.created.day} {usr.created.strftime("%B %Y")}</span>')

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
    hero_banner = "" if usr.restricted else _banner_url(usr.bannerpath)
    html += f'<section class="infobox pf-hero{" has-banner" if hero_banner else ""}"{banner_style(hero_banner)}>'
    html += (f'<div class="pf-avatar"><img src="{pfp}" id="userpfp" alt="{name}\'s avatar" width="120" height="120">'
             f'{"<span class=pf-avatar-dot title=online></span>" if online else ""}</div>')
    html += f'<div class="pf-ident"><div class="pf-name-row"><h1 class="pf-name">{name}</h1>{team_badge(usr.username)}</div>'
    html += f'<div class="pf-meta">{presence}{joined}</div></div>'
    html += f'<div class="pf-rank-block"><span class="pf-rank-label">Global rank</span><span class="pf-rank">#{format(rank, ",") if rank else "?"}</span>'
    html += f'<span class="pf-pp">{points:,} pp</span></div>'
    if actions:
        html += f'<div class="pf-actions">{actions}</div>'
    html += '</section>'
    html += '<script src="/static/script/friends.js?v=1"></script>'

    # ---- stats
    html += '<section class="infobox column pf-section">'
    html += '<div class="pf-tiles">'
    html += (f'<div class="pf-tile pf-tile-level"><span class="pf-tile-label">Level</span><span class="pf-tile-value">{level:,}</span>'
             f'<span class="pf-level-bar" title="{level_pct}% to level {level + 1}"><span style="width:{level_pct}%"></span></span>'
             f'<span class="pf-tile-sub">{level_pct}% to next</span></div>')
    tiles = [("Accuracy", f"{accuracy}%"), ("Ranked score", f"{score:,}"), ("Play time", playtime(usr.playtime)),
             ("Max combo", f"{usr.max_combo or 0:,}x")]
    if usr.username == 'aquapoki':
        tiles.append(("Virgin Meter", "69.420%"))  # easter egg, carried over from the classic profile
    for label, value in tiles:
        html += f'<div class="pf-tile"><span class="pf-tile-label">{label}</span><span class="pf-tile-value">{value}</span></div>'
    html += '</div>'
    # hit distribution
    html += '<div class="pf-hits"><div class="pf-hits-head"><span class="pf-sec-title">Hit distribution</span>'
    html += f'<span class="pf-dim">{total_hits:,} notes hit</span></div>'
    html += '<div class="pf-hitbar" role="img" aria-label="' + ", ".join(f"{h[0]} {h[1]:,}" for h in hits) + '">'
    if total_hits:
        for label, n, cls in hits:
            if n:
                html += f'<span class="pf-hit-{cls}" style="flex:{n}" title="{label}: {n:,}"></span>'
    html += '</div><div class="pf-hit-legend">'
    for label, n, cls in hits:
        pct = f"{n / total_hits * 100:.1f}%" if total_hits else "0%"
        html += f'<span><i class="pf-hit-{cls}"></i>{label} <b>{n:,}</b> <small>{pct}</small></span>'
    html += '</div></div></section>'

    # ---- about me (ids kept for bioeditor.js)
    if usr.bio or owner:
        from Chikara.bbcode import to_html
        from Chikara.usersettings import BIO_MAX
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
    html += '<section class="infobox column pf-section">'
    html += f'<div class="pf-sec-head"><span class="title">Medals</span><span class="pf-dim">{earned} / {len(medal_list)} earned</span></div>'
    html += '<div class="pf-medals">'
    extra_hints = {t: h for t, _, h, _ in EXTRA_MEDALS}
    for title, desc, show in sorted(medal_list, key=lambda m: not m[2]):
        how = MEDAL_HINTS.get(title) or extra_hints.get(title) or desc
        hint = escape(("Got it! " if show else "") + how)
        html += (f'<div class="pf-medal{"" if show else " locked"}" tabindex="0" data-hint="{hint}" aria-label="{escape(title)}. {hint}">'
                 f'<span class="pf-medal-icon">{"★" if show else "?"}</span>'
                 f'<span><b>{title}</b><small>{desc}</small></span></div>')
    html += '</div></section>'

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
    return escape(urllib.parse.unquote(u.username or ""))


def ranking(request, command=""):
    try:
        page_no = max(1, int(command.strip("/") or 1))
    except ValueError:
        page_no = 1
    per_page = 50
    total = User.objects.filter(restricted=False, ranked_points__gt=0).count()
    pages = max(1, -(-total // per_page))
    title = "Qlute - global player ranking" + (f" (page {page_no})" if page_no > 1 else "")
    htmltemp = header(request, customhead='<link rel="stylesheet" href="/static/css/ranking.css?v=2">', title=title,
                      canonical=SiteURL + "/ranking" + (f"/{page_no}" if page_no > 1 else ""),
                      description="The global Qlute leaderboard: the top rhythm game players ranked by performance points, "
                                  "with score, accuracy and hit counts.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/ranking.html").read()
    users, tols = getstat('ranking', None, page=page_no)
    now = int(timezone.now().timestamp())
    me = request.COOKIES.get('username', None)

    def stats(u):
        return {"points": u.ranked_points or 0, "score": u.ranked_score or 0, "acc": round(u.accuracy or 0, 2),
                "perfect": u.max or 0, "great": u.great or 0, "meh": u.meh or 0, "miss": u.bad or 0,
                "online": u.stattime is not None and now - u.stattime <= ONLINE_SECONDS,
                "pfp": escape(_pfp_url(u.pfppath)), "href": "/user/" + escape(u.username or ""),
                "banner": "" if u.restricted else _banner_url(u.bannerpath),
                "me": me is not None and urllib.parse.unquote(me) == urllib.parse.unquote(u.username or "")}

    html = f"<p class='rk-sub'>{total:,} ranked players &middot; ranked by performance points</p>"
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
                     f"<span class='rk-pod-name'>{_rank_name(u)}</span>"
                     f"<span class='rk-pod-pp'>{st['points']:,}<small> pp</small></span>"
                     f"<span class='rk-pod-meta'>{st['acc']}% acc &middot; {st['score']:,} score</span></a>")
        html += "</div>"
    if rows:
        html += ("<div class='table-scroll'><table class='rk-table'><thead><tr>"
                 "<th class='rk-c-rank'>Rank</th><th class='rk-c-player'>Player</th><th>Points</th><th>Accuracy</th>"
                 "<th class='rk-hide-sm'>Score</th><th class='rk-hide-sm rk-hit'>Perfect</th><th class='rk-hide-sm rk-hit'>Great</th>"
                 "<th class='rk-hide-sm rk-hit'>Meh</th><th class='rk-hide-sm rk-hit'>Miss</th></tr></thead><tbody>")
        for u in rows:
            rank += 1
            st = stats(u)
            dot = "<span class='rk-dot' title='online'></span>" if st["online"] else ""
            acc_w = max(0, min(100, st["acc"]))
            html += (f"<tr class='{'rk-me' if st['me'] else ''}'><td class='rk-c-rank'>#{rank}</td>"
                     f"<td class='rk-c-player'><a href='{st['href']}'><span class='rk-avatar'><img src='{st['pfp']}' alt='' loading='lazy' width='34' height='34'>{dot}</span>"
                     f"<span class='rk-name'>{_rank_name(u)}</span></a></td>"
                     f"<td class='rk-pp'>{st['points']:,}</td>"
                     f"<td><span class='rk-acc'><span class='rk-acc-bar'><span style='width:{acc_w}%'></span></span>{st['acc']}%</span></td>"
                     f"<td class='rk-hide-sm'>{st['score']:,}</td>"
                     f"<td class='rk-hide-sm rk-hit'>{st['perfect']:,}</td><td class='rk-hide-sm rk-hit'>{st['great']:,}</td>"
                     f"<td class='rk-hide-sm rk-hit'>{st['meh']:,}</td><td class='rk-hide-sm rk-hit rk-miss'>{st['miss']:,}</td></tr>")
        html += "</tbody></table></div>"

    # pagination: first, prev, a window around the current page, next, last
    def pg(n, label=None, cls=""):
        if n == page_no and label is None:
            return f"<span class='rk-page rk-page-cur' aria-current='page'>{n}</span>"
        return f"<a class='rk-page {cls}' href='/ranking/{n}'>{label or n}</a>"
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
        html = header(request, title="Qlute - A free rhythm game inspired by osu!mania", canonical=SiteURL + "/", jsonld=structured) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/home.html").read()
    elif uri == "":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/news.css?v=1">', title="Qlute - home page", canonical=SiteURL + "/") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/homes.html").read().replace("{news}", __import__("moderation.news", fromlist=["x"]).latest_html()).replace("{usertag}",escape(request.COOKIES.get('username', None))).replace("{usercount}",str(format(User.objects.last().id,","))).replace("{active}",format(online_count(),","))
    elif uri.strip("/") == "beatmaps":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=17">', title="Qlute - beatmap listing",
                      canonical=SiteURL + "/beatmaps",
                      description="Browse every Qlute beatmap: search by title, artist or mapper, filter by status, genre and language, "
                                  "preview songs and download them free.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/beatmaps.html").read()
    elif uri.strip("/") == "download":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/download.css?v=2">', title="Download Qlute - free rhythm game for Windows, macOS and Linux", canonical=SiteURL + "/download",
                      description="Download Qlute free for Windows 10+, macOS and Linux, or grab the source code on GitHub. "
                                  "A mania-style rhythm game inspired by osu!mania.") + download_html()
    elif uri.strip("/") == "rules":
        html = header(request, customhead='<link rel="stylesheet" href="/static/css/rules.css?v=1">', title="Qlute - rules",
                      canonical=SiteURL + "/rules",
                      description="The Qlute community rules: accounts, fair play, chat conduct, multiplayer, "
                                  "profiles, beatmap submissions and how rules are enforced.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/rules.html").read()
    else:
        status = 404
        html = header(request, title="Qlute - the black hole of death.", robots=NOINDEX) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read().replace('{sitetitle}',"404 not found o-o")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html, status=status)
