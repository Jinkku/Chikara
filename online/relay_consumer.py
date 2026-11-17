"""Online multiplayer relay for the game: ws/v1/multiplayer/  (protocol: online/PROTOCOL.md)

The room runs on the host's game (same code as LAN rooms). This server only:
  - lists rooms (MultiplayerRoom rows, refreshed by the host's "update" heartbeats),
  - hands out peer ids (host = 1, players = 2, 3, ...),
  - forwards binary game packets between the host and its players. Players can only talk to the host.
  - when the host leaves (or drops), moves the room to one of its players (if the host's game supports it):
    that player becomes peer 1 and runs the room from its own copy of the room state; everyone else keeps
    their peer id and is pointed at the new host.

All per-room routing lives in the host's consumer (peer id -> channel name), so it works with
several server processes as long as they share the channel layer (Redis).
"""
import asyncio
import json
import struct
import time
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from .auth import authenticate, clean
from .models import MultiplayerRoom

PROTOCOL = 1
MAX_FRAME = 512 * 1024            # one game packet (beatmap chunks are ~60 KB)
MAX_BYTES_PER_SEC = 4 * 1024 * 1024
MAX_FRAMES_PER_SEC = 400
# A host speaks for the whole room (state, chat, everyone's scores, replies to each player), so it gets more.
HOST_BYTES_PER_SEC = 16 * 1024 * 1024
HOST_FRAMES_PER_SEC = 4000
ROOM_TTL = timedelta(seconds=45)   # hosts send "update" at least every 15 s
JOIN_TIMEOUT = 8.0
MAX_PEERS = getattr(settings, "ONLINE_ROOM_MAX_PEERS", 256)
HEADER = struct.Struct("<iBB")     # target/from peer id, channel, transfer mode


@database_sync_to_async
def list_rooms():
    fresh = timezone.now() - ROOM_TTL
    MultiplayerRoom.objects.filter(updated__lt=fresh - timedelta(minutes=5)).delete()
    return [{"id": r.id, "name": r.name, "host": r.host, "players": r.players, "phase": r.phase,
             "map": r.beatmap, "proto": r.proto, "ver": r.game_version}
            for r in MultiplayerRoom.objects.filter(updated__gte=fresh).order_by("-players", "name")[:200]]


@database_sync_to_async
def create_room(host, channel_name, name, proto, ver):
    MultiplayerRoom.objects.filter(host_channel=channel_name).delete()
    return MultiplayerRoom.objects.create(host=host, host_channel=channel_name, name=name, proto=proto,
                                          game_version=ver, updated=timezone.now()).id


@database_sync_to_async
def update_room(room_id, fields):
    fields["updated"] = timezone.now()
    MultiplayerRoom.objects.filter(id=room_id).update(**fields)


@database_sync_to_async
def move_room(room_id, host, channel_name, players):
    MultiplayerRoom.objects.filter(id=room_id).update(host=host, host_channel=channel_name, players=players,
                                                       updated=timezone.now())


@database_sync_to_async
def delete_room(room_id):
    MultiplayerRoom.objects.filter(id=room_id).delete()


@database_sync_to_async
def find_room(room_id):
    return MultiplayerRoom.objects.filter(id=room_id, updated__gte=timezone.now() - ROOM_TTL).first()


def room_players_group(room_id):
    """Every player (not the host) of a room: what the host sends to everyone goes out with one group_send."""
    return f"relay.room.{room_id}"


def as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def relay_user_group(user_id):
    """Every multiplayer socket of one account; moderation.service.kick_online drops them when it's banned."""
    return f"relay.user.{user_id}"


@database_sync_to_async
def user_id_of(username):
    from dbview.models import User
    return User.objects.filter(username=username).values_list("id", flat=True).first()


class RelayConsumer(AsyncWebsocketConsumer):
    username = None

    async def connect(self):
        self.username, error = await authenticate(self.scope)
        await self.accept()
        if error:
            await self.send_op("error", fatal=True, text=error)
            await self.close(code=4001)
            return
        self.role = None          # None | "host" | "joining" | "client"
        self.room_id = None
        self.peer_id = 0
        self.host_channel = None  # client: where packets go
        self.peers = {}           # host: peer id -> channel name
        self.peer_users = {}      # host: peer id -> account name
        self.next_peer = 2
        self.can_migrate = False  # host: its game can take a room over (sent with "host")
        self.successor = 0        # host: who its game wants to take over (sent with "update")
        self.join_task = None
        self.window_start, self.window_bytes, self.window_frames = time.monotonic(), 0, 0
        self.user_id = await user_id_of(self.username)
        if self.user_id is not None:
            await self.channel_layer.group_add(relay_user_group(self.user_id), self.channel_name)

    async def disconnect(self, code):
        if getattr(self, "user_id", None) is not None:
            await self.channel_layer.group_discard(relay_user_group(self.user_id), self.channel_name)
        if self.username:
            await self.leave_session("The host left, so the room closed.")

    async def relay_kick(self, e):
        """This account was just banned: same message and close code as a restricted login (code 4001)."""
        await self.send_op("error", fatal=True, text=e["text"])
        await self.close(code=4001)

    async def send_op(self, op, **fields):
        await self.send(text_data=json.dumps({"op": op, **fields}))

    # ---------------------------------------------------------------- client -> server

    async def receive(self, text_data=None, bytes_data=None):
        if not self.username:
            return
        if bytes_data is not None:
            await self.relay(bytes_data)
            return
        try:
            c = json.loads(text_data)
        except (TypeError, ValueError):
            return
        if not isinstance(c, dict):
            return
        op = c.get("op")
        if op == "ping":
            if self.role == "host":
                await update_room(self.room_id, {})
            await self.send_op("pong")
        elif op == "list":
            await self.send_op("rooms", rooms=await list_rooms())
        elif op == "host":
            await self.op_host(c)
        elif op == "update":
            await self.op_update(c)
        elif op == "join":
            await self.op_join(c)
        elif op == "kick":
            await self.op_kick(c)
        elif op == "leave":
            await self.leave_session("The host closed the room.")
        # unknown ops (newer clients) are ignored

    async def op_host(self, c):
        if self.role is not None:
            await self.send_op("error", text="You're already in a room.")
            return
        name = clean(c.get("name"), 64, f"{self.username}'s room")
        self.room_id = await create_room(self.username, self.channel_name, name,
                                         as_int(c.get("proto")), clean(c.get("ver"), 32, ""))
        self.role, self.peer_id, self.peers, self.peer_users, self.next_peer = "host", 1, {}, {}, 2
        self.can_migrate, self.successor = c.get("migrate") is True, 0
        await self.send_op("hosted", room=self.room_id, peer=1)

    async def op_update(self, c):
        if self.role != "host":
            return
        fields = {}
        if "name" in c:
            fields["name"] = clean(c.get("name"), 64, "Room")
        if "players" in c:
            fields["players"] = max(0, min(as_int(c.get("players"), 1), 10000))
        if "phase" in c:
            fields["phase"] = as_int(c.get("phase"))
        if "map" in c:
            fields["beatmap"] = clean(c.get("map"), 300, "")
        if "next" in c:
            self.successor = as_int(c.get("next"))
        await update_room(self.room_id, fields)

    async def op_join(self, c):
        if self.role is not None:
            await self.send_op("error", text="You're already in a room.")
            return
        room = await find_room(as_int(c.get("room"), -1))
        if room is None:
            await self.send_op("join_failed", text="That room doesn't exist anymore.")
            return
        if room.host == self.username:
            await self.send_op("join_failed", text="You can't join your own room from another game.")
            return
        self.role, self.room_id, self.host_channel = "joining", room.id, room.host_channel
        await self.channel_layer.send(room.host_channel, {
            "type": "relay.join_request", "room": room.id, "channel": self.channel_name, "user": self.username})
        self.join_task = asyncio.ensure_future(self.join_timeout(room.id))

    async def join_timeout(self, room_id):
        await asyncio.sleep(JOIN_TIMEOUT)
        if self.role == "joining" and self.room_id == room_id:
            self.role, self.room_id, self.host_channel = None, None, None
            await self.send_op("join_failed", text="The room didn't answer.")

    async def op_kick(self, c):
        if self.role != "host":
            return
        peer = as_int(c.get("peer"))
        channel = self.peers.pop(peer, None)
        self.peer_users.pop(peer, None)
        if channel:
            await self.channel_layer.group_discard(room_players_group(self.room_id), channel)
            await self.channel_layer.send(channel, {"type": "relay.closed", "room": self.room_id, "reason": "You were removed from the room."})

    async def leave_session(self, reason):
        if self.join_task:
            self.join_task.cancel()
            self.join_task = None
        if self.role == "host":
            if self.can_migrate and self.peers:
                await self.migrate()
            else:
                await close_for(self.channel_layer, self.room_id, self.peers.values(), reason)
                await delete_room(self.room_id)
        elif self.role == "client" and self.host_channel:
            await self.channel_layer.send(self.host_channel, {"type": "relay.peer_left", "room": self.room_id, "peer": self.peer_id})
        if self.role == "client":
            await self.channel_layer.group_discard(room_players_group(self.room_id), self.channel_name)
        self.role, self.room_id, self.peer_id, self.host_channel, self.peers = None, None, 0, None, {}
        self.peer_users = {}

    async def migrate(self):
        """We're the host and we're leaving: hand the room to the player our game picked (or the longest-standing one)."""
        new = self.successor if self.successor in self.peers else min(self.peers)
        channel = self.peers[new]
        others = {pid: ch for pid, ch in self.peers.items() if pid != new}
        await move_room(self.room_id, self.peer_users.get(new, "?"), channel, len(self.peers))
        await self.channel_layer.send(channel, {
            "type": "relay.promote", "room": self.room_id, "old_peer": new, "next_peer": self.next_peer,
            "peers": [[pid, ch, self.peer_users.get(pid, "?")] for pid, ch in others.items()]})
        for ch in others.values():
            await self.channel_layer.send(ch, {"type": "relay.host_moved", "room": self.room_id, "channel": channel, "old_peer": new})

    # ---------------------------------------------------------------- packets

    async def relay(self, data):
        if self.role not in ("host", "client") or len(data) < HEADER.size or len(data) > MAX_FRAME:
            return
        now = time.monotonic()
        if now - self.window_start >= 1.0:
            self.window_start, self.window_bytes, self.window_frames = now, 0, 0
        self.window_bytes += len(data)
        self.window_frames += 1
        host = self.role == "host"
        if self.window_bytes > (HOST_BYTES_PER_SEC if host else MAX_BYTES_PER_SEC) \
                or self.window_frames > (HOST_FRAMES_PER_SEC if host else MAX_FRAMES_PER_SEC):
            return  # over the limit: drop (the game resends what matters on its own)

        target, channel, mode = HEADER.unpack_from(data)
        payload = data[HEADER.size:]
        event = {"type": "relay.data", "room": self.room_id, "from": self.peer_id,
                 "channel": channel, "mode": mode, "data": payload}
        if self.role == "client":
            await self.channel_layer.send(self.host_channel, event)
            return
        if target == 0:
            # One send for the whole room instead of one per player.
            await self.channel_layer.group_send(room_players_group(self.room_id), event)
            return
        elif target < 0:
            targets = [ch for pid, ch in self.peers.items() if pid != -target]
        else:
            targets = [self.peers[target]] if target in self.peers else []
        for ch in targets:
            await self.channel_layer.send(ch, event)

    # ---------------------------------------------------------------- channel layer events

    async def relay_data(self, e):
        if e.get("room") != self.room_id:
            return
        if self.role == "host" and e["from"] not in self.peers:
            return  # a player we already dropped
        if self.role == "client" and e["from"] != 1:
            return
        if self.role not in ("host", "client"):
            return
        await self.send(bytes_data=HEADER.pack(e["from"], e["channel"], e["mode"]) + e["data"])

    async def relay_join_request(self, e):
        reply_to = e["channel"]
        if self.role != "host" or e.get("room") != self.room_id:
            await self.channel_layer.send(reply_to, {"type": "relay.join_reject", "room": e.get("room"), "reason": "That room doesn't exist anymore."})
            return
        if len(self.peers) >= MAX_PEERS:
            await self.channel_layer.send(reply_to, {"type": "relay.join_reject", "room": self.room_id, "reason": "That room is full."})
            return
        peer = self.next_peer
        self.next_peer += 1
        self.peers[peer] = reply_to
        self.peer_users[peer] = e["user"]
        await self.channel_layer.send(reply_to, {"type": "relay.join_accept", "room": self.room_id, "peer": peer})
        await self.send_op("peer_connected", peer=peer, user=e["user"])

    async def relay_join_accept(self, e):
        if self.role == "joining" and e.get("room") == self.room_id:
            if self.join_task:
                self.join_task.cancel()
                self.join_task = None
            self.role, self.peer_id = "client", e["peer"]
            await self.channel_layer.group_add(room_players_group(self.room_id), self.channel_name)
            await self.send_op("joined", room=self.room_id, peer=self.peer_id)
        else:
            # We gave up waiting (or left) in the meantime: tell the host to drop the slot.
            room_host = await find_room(e.get("room") or -1)
            if room_host:
                await self.channel_layer.send(room_host.host_channel, {"type": "relay.peer_left", "room": e.get("room"), "peer": e["peer"]})

    async def relay_join_reject(self, e):
        if self.role == "joining" and e.get("room") == self.room_id:
            if self.join_task:
                self.join_task.cancel()
                self.join_task = None
            self.role, self.room_id, self.host_channel = None, None, None
            await self.send_op("join_failed", text=e.get("reason", "Couldn't join that room."))

    async def relay_peer_left(self, e):
        if self.role == "host" and e.get("room") == self.room_id and self.peers.pop(e["peer"], None):
            self.peer_users.pop(e["peer"], None)
            await self.send_op("peer_disconnected", peer=e["peer"])

    async def relay_closed(self, e):
        if self.role in ("client", "joining") and e.get("room") == self.room_id:
            await self.channel_layer.group_discard(room_players_group(self.room_id), self.channel_name)
            self.role, self.room_id, self.peer_id, self.host_channel = None, None, 0, None
            await self.send_op("closed", reason=e.get("reason", "The room closed."))

    async def relay_promote(self, e):
        """The host left and picked us: we're peer 1 now and our game runs the room."""
        peers = {int(pid): ch for pid, ch, _ in e["peers"]}
        if self.role != "client" or e.get("room") != self.room_id:
            # We're leaving too: nobody can run it, so close it for the rest.
            await close_for(self.channel_layer, e.get("room"), peers.values(), "The host left, so the room closed.")
            await delete_room(e.get("room"))
            return
        self.role, self.peer_id, self.host_channel = "host", 1, None
        await self.channel_layer.group_discard(room_players_group(self.room_id), self.channel_name)  # host now
        self.peers = peers
        self.peer_users = {int(pid): user for pid, _, user in e["peers"]}
        self.next_peer = max(e.get("next_peer", 2), max(peers, default=1) + 1)
        self.can_migrate, self.successor = True, 0
        await self.send_op("promoted", room=self.room_id, old_peer=e["old_peer"],
                           peers=[{"peer": pid, "user": user} for pid, user in self.peer_users.items()])

    async def relay_host_moved(self, e):
        if self.role == "client" and e.get("room") == self.room_id:
            self.host_channel = e["channel"]
            await self.send_op("host_moved", room=self.room_id, old_peer=e["old_peer"])


async def close_for(layer, room_id, channels, reason):
    for channel in channels:
        await layer.send(channel, {"type": "relay.closed", "room": room_id, "reason": reason})
