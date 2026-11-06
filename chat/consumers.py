import json
from channels.generic.websocket import JsonWebsocketConsumer
from asgiref.sync import async_to_sync
from .models import Message

class ChatConsumer(JsonWebsocketConsumer):

    def connect(self):
        self.room_name  = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group  = f"chat_{self.room_name}"

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group, self.channel_name
        )
        self.accept()

        # Send last 20 messages on connect
        history = Message.objects.filter(room=self.room_name).order_by("-created_at")[:20]
        for msg in reversed(history):
            self.send_json({"type": "chat_message",
                            "author": msg.author,
                            "body":   msg.body})

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group, self.channel_name
        )

    def receive_json(self, content):
        author = content.get("author", "anonymous")
        body   = content.get("body", "")

        # Persist
        Message.objects.create(room=self.room_name, author=author, body=body)

        # Broadcast to group
        async_to_sync(self.channel_layer.group_send)(
            self.room_group,
            {"type": "chat_message", "author": author, "body": body},
        )

    # Called by group_send
    def chat_message(self, event):
        self.send_json({"type": "chat_message",
                        "author": event["author"],
                        "body":   event["body"]})