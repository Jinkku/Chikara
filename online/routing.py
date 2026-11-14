from django.urls import re_path

from .chat_consumer import OnlineChatConsumer
from .relay_consumer import RelayConsumer

# Versioned paths: a future incompatible protocol gets /ws/v2/... next to these, never in place of them.
websocket_urlpatterns = [
    re_path(r"^ws/v1/chat/$", OnlineChatConsumer.as_asgi()),
    re_path(r"^ws/v1/multiplayer/$", RelayConsumer.as_asgi()),
]
