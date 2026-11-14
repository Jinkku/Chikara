"""
URL configuration for Chikara project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
import Chikara.views as views
import Chikara.usersettings as usersettings
import moderation.views as moderation
import online.friends as friends
import submissions.views as submissions
import online.beatmapsocial as beatmapsocial
import submissions.claims as claims
import moderation.news as news

urlpatterns = [
    path('apiv2/search', views.api, {'command': 'search'}),
    path('apiv2/mod/<path:action>', moderation.api),
    path('apiv2/submit/<path:action>', submissions.api),
    path('apiv2/friends', friends.api),
    path('apiv2/friends/<path:action>', friends.api),
    path('apiv2/favorites', beatmapsocial.api, {'kind': 'favorites'}),
    path('apiv2/favorites/<path:action>', beatmapsocial.api, {'kind': 'favorites'}),
    path('apiv2/comments/<path:action>', beatmapsocial.api, {'kind': 'comments'}),
    path('apiv2/avatar', usersettings.avatar),
    path('apiv2/banner', usersettings.banner),
    path('apiv2/cardborder', usersettings.cardborder),
    path('apiv2/bio', usersettings.bio),
    path('apiv2/bio/<str:action>', usersettings.bio),
    path('apiv2/<path:command>', views.api),
    path('apiv2/', views.api, {'command': ''}),
    path('apiv2', views.api, {'command': ''}),
    path('user/<path:user>', views.user),
    path('settings', usersettings.usersettings),
    path('search', views.search_page),
    path('friends', views.friends_page),
    path('admin', views.admin_page),
    path('ranking', views.ranking),
    path('ranking/<path:command>', views.ranking),
    path('beatmapset/<path:command>', views.beatmap),
    path('score/<int:score_id>', views.score_page),
    path('osu/claim/<int:setid>', claims.start),
    path('osu/callback', claims.callback),
    path('news', news.news_list),
    path('news/page/<int:command>', lambda r, command: news.news_list(r, str(command))),
    path('news/<int:post_id>', news.news_post),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap),
    path('<path:uri>', views.base),
    path('', views.base, {'uri': ''}),
]
#path('apiv2/<path:uri>', views.api),
