"""Live notifications for the website header: ws/v1/notify/

Every logged-in page opens one of these (static/script/notifications.js). It's listen-only: the server sends
  {"op": "notification", "unread": N, "notification": {...}}   something new happened (same shape as apiv2/notifications)
  {"op": "unread", "unread": N}                                 the count changed (read / cleared, maybe in another tab)
and answers {"op": "ping"} with {"op": "pong"}. Login is the site's cookies, from the site's own origin only
(online/auth.py). Unlike the chat socket it doesn't mark you online or send any history.
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .auth import authenticate, is_web


def notify_group(username):
    return "notify." + "".join(c if c.isalnum() or c in "-_." else "_" for c in username.lower())[:90]


@database_sync_to_async
def unread(username):
    from .notifications import unread_count
    return unread_count(username)


class NotifyConsumer(AsyncJsonWebsocketConsumer):
    group = None

    async def connect(self):
        if not is_web(self.scope):
            await self.close(code=4001)
            return
        username, error = await authenticate(self.scope)
        if error:
            await self.close(code=4001)
            return
        self.group = notify_group(username)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"op": "unread", "unread": await unread(username)})

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("op") == "ping":
            await self.send_json({"op": "pong"})

    async def notify_new(self, e):
        await self.send_json({"op": "notification", "unread": e["unread"], "notification": e["notification"]})

    async def notify_unread(self, e):
        await self.send_json({"op": "unread", "unread": e["unread"]})
