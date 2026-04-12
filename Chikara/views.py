from django.utils import timezone
from django.shortcuts import render, HttpResponse
import sentry_sdk
import traceback
from django.http import JsonResponse
from Chikara.settings import BASE_DIR, STATIC_ROOT, REPLAYS,storage_root,client_id,client_secret, DataURL, AssetPath, SongFilePath, CheaterCardBorder
from django.db.models import Q
from random import randint
import json,hashlib
import urllib.parse
import sys,time,datetime,os
from ossapi import Ossapi
from dbview.models import *
import json
import Chikara.ppv2calc as ppv2calc
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
medals=("The End","You've made it"),("Baby Steps","Welcome to the Game"),(">~<","Impressive"),('Psycho','Dang you can read that?!'),('Welcome back Veteran','Glad to see you back'),('D-Ranker','Unrhythmic'),('S-Ranker','Like to show off. huh?'),('Donator','Thanks for Supporting the Game!'),('Sniper','First Comes, First Serve!'),('BreakThrough','Unstoppable'),('Top 100','You are the chosen one'),('Top 50','Almost There'),('Top 10','Grab some Popcorn 🍿'),('Top 1,000','Still a Virgin at this game are you?'),("Making the game better", "You are making the community better!") # Medals
leveltemp=0.0000005 # Level multiplier
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



def sitemap(request):
    return HttpResponse(open( "/qlute-devdj/static/sitemap.xml").read(), content_type="application/xml")
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

Sitemap: https://qlute.jinkku.moe/sitemap.xml
"""
    return HttpResponse(content, content_type="text/plain")



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
    "score": process_score(a["max"], a["great"], a["meh"], getmult(a["mods"],speed=a["speed_multi"]),a["max"] + a["great"] + a["meh"] + a["bad"]),
    "combo": a['combo'],
    "MAX": a['max'],
    "GOOD": a['great'],
    "MEH": a['meh'],
    "BAD": a['bad'],
    "mods":a['mods'].replace('AT',''),
    "speed_multi":a['speed_multi'],
    "time": int(a['created'].timestamp())
            }
            x.append(data)
            e+=1
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
        x=sorted(x, key=lambda x: x['points'],reverse=True)

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
        for a in modsaliasab:
            if a in str(fulltmp):
                if a == 'BT':
                    multiplier *= 1.15
                elif a == 'DT':
                    multiplier *= 1.15 * (speed / 1.25)
                elif a == 'HT':
                    multiplier *= 0.3 * (speed / 0.5)
                elif a == 'NF':
                    multiplier *= 0.5
                elif a not in ('AT', 'RND'):
                    multiplier *= 1.05
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
        medco+=1
        yield (title,desc,show)

# Querying scores

def getscores(user='',beatmapid=0,orderbybiggest=False,limit=30,ranked = 1):
    tols=0
    if orderbybiggest:
        strip='points'
    else:
        strip='created'
    if user=='':
        if beatmapid!=0:
            score = Score.objects.values().filter(beatmap_id=beatmapid).filter(ranked=ranked)[:limit]
        else:
            score = Score.objects.values().order_by(f"-{str(strip)}").filter(ranked=ranked)[:limit]
    elif user != '' and ranked != -1:
        score = Score.objects.filter(username=user).values().order_by(f"-{str(strip)}").filter(ranked=ranked)[:limit]
    elif user != '' and ranked == -1:
        score = Score.objects.filter(username=user).values().order_by(f"-{str(strip)}")[:limit]
    per=1
    for a in score:
        mods=a['mods']
        a['multiplier']=getmult(mods)
        #a['points']=getpoint(a['max'],a['great'],a['meh'],a['bad'],a['multiplier'], a['combo'])
        a['weighted_pp']=a['points']*per#*(tmp[15]*2)
        
        if user in a['username'] or beatmapid in a['beatmap_id']:
            yield a
        tols+=1
        per-=0.02
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
    arg = command.split("/")
    head = """
    <script src="/static/script/beatmapquery.js"></script>
    <script src="/static/script/difficultyloading.js"></script>"""
    if len(arg) > 1:
        id = int(arg[1])
        object = Beatmap.objects.filter(beatmapsetid=int(arg[0]), beatmapid=id).first()
    else:
        object = Beatmap.objects.filter(beatmapsetid=int(arg[0])).first()
        id = -1
    html = header(request, customhead=head, title="Qlute - " + str(object.title)) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/beatmap.html").read()
    if object != None:
        html = html.replace("{Title}",object.title).replace("{Artist}",object.artist).replace("{Mapper}",object.mapper)
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
        peak += scorecard.replace("{date}",timeest).replace("{sitetitle}",str(tmp['beatmapname'])).replace("{artist}",str(tmp['artist'])).replace("{rank}",gradet).replace("{difficulty}",str(tmp['beatmapdiff'])).replace("{points}",str(int(tmp['points']))).replace("{weighted_points}",weighted).replace("{weighted_percentage}",weightedp).replace("{mods}",str(modse)).replace("{area}","/beatmapset/"+str(tmp["beatmapset_id"])+"/"+str(tmp["beatmap_id"]))
        pek-=0.02
    if tols==0:
        peak +='<h3 class="bar">No Recent Plays -n-</h3>'
    return peak

# Score Processor

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
        result = User.objects.filter(
            username=usr,
            password=pwd
        ).first()
    if result!=None and not signup:
        restricted = result.restricted
        p=str(result.password)
        result = (pwd == p)
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

def update_pfp(request, command):
    return None

# API

def api(request,command,value=None):
    command=command.split('/')
    if command[0] != "" and request.method == "POST":
        if command[0]=='signup' and len(command) >1:
            try:
                username = request.META.get('HTTP_USERNAME', '')
                password = request.META.get('HTTP_PASSWORD', '')
                accept=not checklogin(username, '',signup=True)[0]
                
                # Process the credentials (authentication logic here)
                if accept:  
                    User.objects.create(
                    username=username,
                    password=password
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
                password = hashlib.sha256(bytes(password,'utf-8')).hexdigest()
                accept=checklogin(username, password)[0]
                
                # Process the credentials (authentication logic here)
                if accept:  # Example check
                    response = JsonResponse({"success": True}, status=200)
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
                elif not game[1]:
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
                   replay_name = f"{REPLAYS}/{timezone.now().timestamp()}-{beatmapset_id}-{beatmap_id}-{user}-{mods}.qrf"
                   replayfile = open(replay_name, "w")
                   replayfile.write(replay_data)
                   replayfile.close()
                   if info.ranked != 0:
                       pointsdata = ppv2calc.calculate_ppv2(replay_name, storage_root + info.chartfile)
                       points = pointsdata.pp * mult
                       maxpoints=pointsdata.max_pp * mult
                   else:
                       points = 0.000000001
                       maxpoints = 0.01
                   finalscore=process_score(smax, sgreat, smeh, mult, info.notecount)
                   usr = User.objects.get(username = user)
                   if not float(points)>usr.ranked_points / 4 and accept and ranked > 0:
                        tmp = Score.objects.filter(beatmap_id = beatmap_id, username = user).first()
                        if not tmp==None:
                            oldmult=getmult(tmp.mods)
                            
                            if tmp.replay_path == None or pointsdata.pp:
                                tmp.delete()
                                submit=True
                            else:
                                submit=False
                        else:
                            submit=True
                        if submit:
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
                                replay_path = replay_name.removeprefix(storage_root),
                                version = 2,
                                speed_multi = speed_multi
                            )
                        # ACC

                        hits=[0,0,0,0]
                        b=1
                        for a in getscores(user=user,orderbybiggest=True,limit=50):
                            hits[0]+=a['max']
                            hits[1]+=a['great']
                            hits[2]+=a['meh']
                            hits[3]+=a['bad']
                        t=round(((hits[0]+(hits[1]/2)+(hits[2]/3))/(hits[0]+hits[1]+hits[2]+hits[3]))*100,2)
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
                        rankedpoints=0
                        x=0
                        for a in getscores(user=user,orderbybiggest=True,limit=50):
                            try:
                                al=int(a['weighted_pp'])
                                x+=1
                                rankedpoints+=int(al)
                            except Exception as err:
                                sys.stdout.write(str(err))
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
                   elif accept and ranked == 0 and submit:
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
                                replay_path = replay_name.removeprefix(storage_root),
                                version = 2,
                                speed_multi = speed_multi
                        )
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
        elif command[0]=='getnotice':
            f=os.listdir(storage_root + "events")
            data = []
            for a in f:
                data.append({"url" : DataURL + "/events/" + a, "text" : a,"redirect": ""})
            return JsonResponse(data,safe=False)

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
        elif command[0]=='search':
            t = time.time()
            searchentry = request.GET.get("query")
            if searchentry == None:
                searchentry = ""
            status = request.GET.get("status")
            if status == None:
                status = 1
            else:
                status = int(status)
            page = request.GET.get("page")
            if page == None:
                page = 0
            else:
                page = int(page)
            page *= 100
            if searchentry == "":
                cache = Beatmap.objects.values().filter(ranked = status).order_by("-created")[page: page + 100]
            else:
                cache = Beatmap.objects.values().filter(
                    Q(title__icontains=searchentry) |
                    Q(title_unicode__icontains=searchentry) |
                    Q(artist__icontains=searchentry) |
                    Q(beatmapid__icontains=searchentry) |
                    Q(beatmapsetid__icontains=searchentry)
                ).filter(ranked = status).order_by("-created")[page: page + 100]
            lis = []
            js = {}
            beatmaps = []
            if len(cache) != 0:
                oldbid = 0
                for a in cache:
                    if oldbid != a["beatmapsetid"]:
                        if js != {}:
                            lis.append(js)
                        js = {}
                        beatmaps = []
                        js["id"] = a["beatmapsetid"]
                        js["bpm"] = a["BPM"]
                        js["title"] = a["title"]
                        js["artist"] = a["artist"]
                        js["creator"] = a["mapper"]
                        js["preview_url"] = DataURL + a["previewpath"]
                        js["download_url"] = DataURL + a["beatmapfile"]
                        js["covers"] = {
                            "cover" : DataURL + a["backgroundpath"],
                            "card" : DataURL + a["backgroundpath"],
                            "list" : DataURL + a["backgroundpath"],
                            "slimcover" : DataURL + a["backgroundpath"],
                        }
                        js["source"] = ""
                        js["last_updated"] = int(a["created"].timestamp())
                        js["beatmaps"] = beatmaps
                        oldbid = a["beatmapsetid"]
                    beatmaps.append({
                        "id" : a["beatmapid"],
                        "level" : a["Level"],
                        "count_circles" : a["notecount"],
                        "count_sliders" : 0,
                        "max_combo" : a["notecount"],
                        "ranked" : a["ranked"],
                        "total_length" : a["Length"],
                        "version" : a["difficulty"],
                        "bpm" : a["BPM"],
                        "pp" : a["pp"],
                        
                        
                        })    
                if js != {} and not js in lis:
                    lis.append(js)
            t = time.time() - t
            return JsonResponse(lis, safe= False)
        elif command[0]=='menunotice':
            f=open('motd').read().rstrip('\n').split('\n')
            r=randint(1,len(f))
            return HttpResponse(f[r-1])
        elif command[0]=='setstatus':
            username = request.META.get('HTTP_USERNAME', '')
            password = request.META.get('HTTP_PASSWORD', '')
            text = request.META.get('HTTP_NOWPLAYING', '')
            accept=checklogin(username, '',signup=True)[0]
            if checklogin(username,password,signup=True)[0]:
                accept=1
            if accept and len(text) >0:
                usr = User.objects.get(username = username)
                usr.stattime = int(timezone.now().timestamp())
                usr.status = text
                usr.save()
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
                msg = restrictionnotice
            elif not game[1]:
                msg = f"This version of {game[0]} is not supported.\nPlease update to the latest version to continue."
            prompt={'success':ac,'notification':msg}
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

def header(request, customhead="", title="{sitetitle}"):
    head = open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/header.html").read()
    username = request.COOKIES.get('username')
    password = request.COOKIES.get('password', None)
    proc = checklogin(username, password)
    accept=proc[0]
    if accept:
        head = head.replace("{usertag}", username).replace("{pfppath}", getstat("pfp_path",username)["url"])
    else:
        head = head.replace("{usertag}", "Guest").replace("{pfppath}", NoProfilePictureURL)
    if proc[1]:
        head += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/restricted.html").read()
    head = head.replace("{head}", customhead)
    head = head.replace("{sitetitle}", title)
    return head

def user(request, user):
    tickle= timezone.now().timestamp()
    html = header(request)
    usertest = checklogin(user,'x',signup=True,id=user)
    if usertest[0]:
        if user=='aquapoki':
            emblem='Dev',
            donator=1
        else:
            emblem=''
            donator=0
        if not usertest[1]:
            html = html.replace('{sitetitle}',f"{user}'s Profile")
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
            html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/usernamecard.html").read().replace('{username}',usr.username).replace('{pfppath}',getstat("pfp_path", user)["url"]) # User name card

            html += '<div class="infobox infoboxtile column spacetop spacebottom">'
            html += '<span>'
            try:
                if (usr.stattime,usr.status)!=(None,None) and not timezone.now().timestamp()-usr.stattime>300:
                    html += usr.status
                else:
                    html += 'Last Seen '+str( timeform(timezone.now().timestamp()-usr.stattime))
            except Exception as err:
                html += 'New player <3'
            html += '</span></div>' # Status Card
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
        elif usertest[1]:
            html += '<div class="info"><span class="center"><h1>o-o</h1><h3>This profile has been privated QnQ</h3></span></div>'
    else:
        html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read()
        html = html.replace('{sitetitle}',"404 not found o-o")
#    tickle = round((timezone.now().timestamp() - tickle) / 0.001,2)
    html += "</div>"
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)

def ranking(request, command=""):
    htmltemp = header(request, title="Qlute - Ranking Page") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/ranking.html").read()
    html = ''
    users, tols = getstat('ranking', None, page=1)        
    if not tols:
        html += "<h3 class='bar'>Someone needs to play more! (｡•̀ᴖ•́｡)</h3>"
    else:
        html += "<table class='tablebar'><tr><th>Rank</th><th>Username</th><th>Points</th><th>Score</th><th>Accuracy</th><th>Perfect</th><th>Great</th><th>Meh</th><th>Miss</th></tr>"
        rank = 0
    if command != "":
        html = str(command)
    for user in users:
        rank += 1
        points = user.ranked_points if user.ranked_points is not None else 0
        score = user.ranked_score if user.ranked_score is not None else 0
        acc = user.accuracy if user.accuracy is not None else 0
        max_hit = user.max if user.max is not None else 0
        great = user.great if user.great is not None else 0
        meh = user.meh if user.meh is not None else 0
        bad = user.bad if user.bad is not None else 0
        html += f"<tr><td class='lbar'>#{rank}</td>"
        html += f"<td class='cbar'><a href='/user/{user.username}'>{urllib.parse.unquote(user.username)}</a></td>"
        html += f"<td class='cbar'>{points:,}</td>"
        html += f"<td class='cbar'>{score:,}</td>"
        html += f"<td class='cbar'>{acc}%</td>"
        html += f"<td class='cbar'>{max_hit:,}</td>"
        html += f"<td class='cbar'>{great:,}</td>"
        html += f"<td class='cbar'>{meh:,}</td>"
        html += f"<td class='ebar'>{bad:,}</td></tr>"
    html += "</table>"
    html += "<center>"
    for a in range(1, 11):
        html += f"<a href='../ranking/{a}'><button class='minibutton'>{a}</button></a> "        
    html += "</center></div></div><br>"
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    htmltemp = htmltemp.replace('{entry}',html)
    return HttpResponse(htmltemp)

def base(request, uri,command=""):
    if uri == "" and not checklogin(request.COOKIES.get('username', None), request.COOKIES.get('password', None))[0]:
        html = header(request, title="Qlute - A free rhythm game inspired by osu!mania") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/home.html").read()
    elif uri == "" and checklogin(request.COOKIES.get('username', None), request.COOKIES.get('password', None))[0]:
        html = header(request, title="Qlute - home page") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/homes.html").read().replace("{usertag}",request.COOKIES.get('username', None)).replace("{usercount}",str(format(User.objects.last().id,","))).replace("{active}","0")
    elif uri == "download":
        html = header(request, title="Qlute - download page") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/download.html").read().replace("{sitetitle}","Download")
    else:
        html = header(request, title="Qlute - the black hole of death.") + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/404.html").read().replace('{sitetitle}',"404 not found o-o")
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)
