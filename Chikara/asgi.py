import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Chikara.settings')

# Set Django up before importing consumers (they import models).
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

import Chikara.routing  # noqa: E402
import chat.routing  # noqa: E402
import online.routing  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            online.routing.websocket_urlpatterns
            + Chikara.routing.websocket_urlpatterns
            + chat.routing.websocket_urlpatterns
        )
    ),
})
