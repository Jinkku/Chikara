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

urlpatterns = [
    path('apiv2/<path:command>', views.api),
    path('apiv2/', views.api, {'command': ''}),
    path('user/<path:user>', views.user),
    path('settings', usersettings.usersettings),
    path('ranking', views.ranking),
    path('ranking/<path:command>', views.ranking),
    path('beatmapset/<path:command>', views.beatmap),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap),
    path('<path:uri>', views.base),
    path('', views.base, {'uri': ''}),
]
#path('apiv2/<path:uri>', views.api),
