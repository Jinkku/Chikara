def user(request, user):
    tickle= timezone.now().timestamp()
    usertest = checklogin(user,'x',signup=True,id=user)
    public = usertest[0] and not usertest[1]
    seo = profile_seo(User.objects.filter(username=user).first()) if public else {}
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/catalog.css?v=7"><link rel="stylesheet" href="/static/css/favorites.css?v=1">',
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
            html += '<script src="/static/script/profilefavorites.js?v=1"></script>'
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

