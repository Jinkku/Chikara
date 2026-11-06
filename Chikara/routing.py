# routing.py (inside your app folder)
from django.urls import re_path
from Chikara.consumers import PresenceConsumer

websocket_urlpatterns = [
    re_path(r"ws/game/$", PresenceConsumer.as_asgi()),
]