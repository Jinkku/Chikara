import json
import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer

# Initialize a global async Redis connection pool
# (Ensure your Redis server is running on localhost:6379)
redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)

class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        # Reject unauthenticated connections immediately
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = "global_presence_lobby"

        # 1. Join the broadcast channel group
        await self.channel_layer.group_add(
            self.room_group_name, 
            self.channel_name
        )
        await self.accept()

        # 2. Add user to the Redis Set tracking online users
        await redis_client.sadd("online_users", self.user.id)

        # 3. Broadcast to everyone else that this user came online
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "presence_broadcast",
                "user_id": self.user.id,
                "username": self.user.username,
                "status": "online",
            }
        )

        # 4. Send the current full online user list directly to the newly connected client
        online_user_ids = await redis_client.smembers("online_users")
        await self.send(text_data=json.dumps({
            "action": "current_online_list",
            "online_users": list(online_user_ids)
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # 1. Remove user from the Redis Set
            await redis_client.srem("online_users", self.user.id)

            # 2. Broadcast to everyone else that this user went offline
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "presence_broadcast",
                    "user_id": self.user.id,
                    "username": self.user.username,
                    "status": "offline",
                }
            )

        # Leave the channel group
        await self.channel_layer.group_discard(
            self.room_group_name, 
            self.channel_name
        )

    # Receives event from channel_layer.group_send and pushes it down the WebSocket
    async def presence_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "action": "presence_update",
            "user_id": event["user_id"],
            "username": event["username"],
            "status": event["status"],
        }))

    async def get_online_count():
        # SCARD returns the total number of unique elements in the set
        count = await redis_client.scard("online_users")
        return count