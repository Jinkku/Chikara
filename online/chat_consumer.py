"""Online chat for the game: ws/v1/chat/  (protocol: online/PROTOCOL.md)

Public channels come from settings.ONLINE_CHAT_CHANNELS and everyone is in all of them.
Private rooms are made by players, who invite others by username.
Direct messages ("d<low id>-<high id>") are one-to-one conversations (clients that send "Features: dm").
Clients that send "Features: ban" stay connected while their account is restricted, so they hear about a ban
and its end right away (old clients are just refused / dropped, as before).
"""
import asyncio
import re
import time
from collections import deque
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from chat.models import Message
from dbview.models import User
from .auth import authenticate, clean, features, restricted_login
from .models import DirectChat, OnlineSession, PrivateChatInvite, PrivateChatMember, PrivateChatRoom

PROTOCOL = 1
MAX_TEXT = 500
MAX_TITLE = 40
HISTORY = 50
ONLINE_WINDOW = timedelta(seconds=90)   # clients ping every 30 s
RATE_COUNT, RATE_WINDOW = 8, 5.0         # at most 8 actions per 5 s
MAX_PRIVATE_ROOMS = 20
MAX_DMS_LISTED = 30
PRESENCE_GROUP = "chat.presence"
RECONNECT_CODE = 4002   # "your account changed (banned / unbanned): connect again"


def public_channels():
    return list(getattr(settings, "ONLINE_CHAT_CHANNELS", ["#general"]))


def channel_group(channel):
    return "chat.pub." + re.sub(r"[^A-Za-z0-9_.-]", "_", channel.lstrip("#"))[:80]


def room_group(room_id):
    return f"chat.priv.{room_id}"


def user_group(user_id):
    return f"chat.user.{user_id}"


def ts(dt):
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------- DB helpers

@database_sync_to_async
def user_id_of(username):
    return User.objects.filter(username=username).values_list("id", flat=True).first()


@database_sync_to_async
def history(room_key):
    rows = list(Message.objects.filter(room=room_key).order_by("-created_at")[:HISTORY])
    return [{"author": m.author, "text": m.body, "ts": ts(m.created_at)} for m in reversed(rows)]


@database_sync_to_async
def save_message(room_key, author, text):
    return ts(Message.objects.create(room=room_key, author=author, body=text).created_at)


def _room_json(room):
    return {"id": room.key, "title": room.title, "owner": room.owner,
            "members": sorted(room.members.values_list("username", flat=True))}


@database_sync_to_async
def my_private_rooms(username):
    rooms = PrivateChatRoom.objects.filter(members__username=username).distinct()
    return [(r.id, _room_json(r)) for r in rooms]


@database_sync_to_async
def my_invites(username):
    return [{"room": i.room.key, "title": i.room.title, "from": i.inviter}
            for i in PrivateChatInvite.objects.filter(username=username).select_related("room")]


@database_sync_to_async
def room_json(room_id):
    room = PrivateChatRoom.objects.filter(id=room_id).first()
    return _room_json(room) if room else None


@database_sync_to_async
def is_member(room_id, username):
    return PrivateChatMember.objects.filter(room_id=room_id, username=username).exists()


@database_sync_to_async
def create_room(owner, title):
    if PrivateChatMember.objects.filter(username=owner).count() >= MAX_PRIVATE_ROOMS:
        return None
    with transaction.atomic():
        room = PrivateChatRoom.objects.create(owner=owner, title=title)
        PrivateChatMember.objects.create(room=room, username=owner)
    return room.id


@database_sync_to_async
def add_invite(room_id, username, inviter):
    room = PrivateChatRoom.objects.filter(id=room_id).first()
    if room is None:
        return None, "That room doesn't exist."
    if not User.objects.filter(username=username).exists():
        return None, f"There's no player called {username}."
    if PrivateChatMember.objects.filter(room=room, username=username).exists():
        return None, f"{username} is already in this room."
    try:
        PrivateChatInvite.objects.create(room=room, username=username, inviter=inviter)
    except IntegrityError:
        pass  # already invited: just notify again
    return {"room": room.key, "title": room.title, "from": inviter}, None


@database_sync_to_async
def accept_invite(room_id, username):
    with transaction.atomic():
        deleted, _ = PrivateChatInvite.objects.filter(room_id=room_id, username=username).delete()
        if not deleted:
            return False
        PrivateChatMember.objects.get_or_create(room_id=room_id, username=username)
    return True


@database_sync_to_async
def decline_invite(room_id, username):
    deleted, _ = PrivateChatInvite.objects.filter(room_id=room_id, username=username).delete()
    return deleted > 0


@database_sync_to_async
def leave_room(room_id, username):
    PrivateChatMember.objects.filter(room_id=room_id, username=username).delete()
    if not PrivateChatMember.objects.filter(room_id=room_id).exists():
        PrivateChatRoom.objects.filter(id=room_id).delete()
        Message.objects.filter(room=f"p{room_id}").delete()
        return True
    return False


@database_sync_to_async
def touch_session(username, channel_name):
    now = timezone.now()
    OnlineSession.objects.update_or_create(channel_name=channel_name, defaults={"username": username, "last_seen": now})
    OnlineSession.objects.filter(last_seen__lt=now - timedelta(minutes=10)).delete()


@database_sync_to_async
def drop_session(username, channel_name):
    OnlineSession.objects.filter(channel_name=channel_name).delete()
    return not OnlineSession.objects.filter(username=username, last_seen__gte=timezone.now() - ONLINE_WINDOW).exists()


@database_sync_to_async
def online_users():
    since = timezone.now() - ONLINE_WINDOW
    return sorted(set(OnlineSession.objects.filter(last_seen__gte=since).values_list("username", flat=True)))[:500]


def parse_dm(key):
    """'d3-17' -> (3, 17), anything else -> None."""
    m = re.fullmatch(r"d(\d{1,18})-(\d{1,18})", key) if isinstance(key, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def _dm_json(dm, my_id):
    other = dm.other(my_id)
    me = dm.low_name if my_id == dm.low_id else dm.high_name
    return {"id": dm.key, "title": other, "owner": "", "members": sorted([me, other]), "dm": True, "with": other}


@database_sync_to_async
def my_dms(user_id):
    rows = (DirectChat.objects.filter(low_id=user_id, hidden_low=False) | DirectChat.objects.filter(high_id=user_id, hidden_high=False))
    return [_dm_json(d, user_id) for d in rows.order_by("-updated")[:MAX_DMS_LISTED]]


@database_sync_to_async
def open_dm(me_id, me_name, other_name):
    """Finds or starts the conversation and shows it in my list. Returns (room json, error)."""
    other = User.objects.filter(username=other_name).values("id", "username", "restricted").first()
    if other is None:
        return None, f"There's no player called {other_name}."
    if other["id"] == me_id:
        return None, "You can't message yourself."
    if other["restricted"]:
        return None, f"{other['username']} can't get messages right now."
    low, high = sorted([(me_id, me_name), (other["id"], other["username"])])
    dm, _ = DirectChat.objects.get_or_create(low_id=low[0], high_id=high[0], defaults={
        "low_name": low[1], "high_name": high[1], "updated": timezone.now()})
    DirectChat.objects.filter(id=dm.id).update(**{"hidden_low" if me_id == low[0] else "hidden_high": False})
    return _dm_json(dm, me_id), None


@database_sync_to_async
def dm_for(key, user_id):
    """The conversation if this user is in it, else None."""
    ids = parse_dm(key)
    if ids is None or user_id not in ids:
        return None
    return DirectChat.objects.filter(low_id=ids[0], high_id=ids[1]).first()


@database_sync_to_async
def dm_send_check(dm, user_id):
    """Why this message can't go out (the other side got restricted), or None."""
    other = dm.high_id if user_id == dm.low_id else dm.low_id
    if User.objects.filter(id=other, restricted=True).exists():
        return f"{dm.other(user_id)} can't get messages right now."
    DirectChat.objects.filter(id=dm.id).update(updated=timezone.now(), hidden_low=False, hidden_high=False)
    return None


@database_sync_to_async
def hide_dm(dm, user_id):
    DirectChat.objects.filter(id=dm.id).update(**{"hidden_low" if user_id == dm.low_id else "hidden_high": True})


@database_sync_to_async
def dm_json(key, user_id):
    ids = parse_dm(key)
    dm = DirectChat.objects.filter(low_id=ids[0], high_id=ids[1]).first() if ids else None
    return _dm_json(dm, user_id) if dm else None


@database_sync_to_async
def notify(username, kind, actor, text, link="/chat"):
    from .notifications import push
    push(username, kind, actor, text, link)


@database_sync_to_async
def still_restricted(username):
    """Ends the ban if it ran out. Returns (restricted, ban message, expiry ms or None)."""
    from moderation.service import active_ban, ban_message
    ban = active_ban(username)
    restricted = User.objects.filter(username=username, restricted=True).exists()
    return restricted, ban_message(ban), (int(ban.expires.timestamp() * 1000) if ban and ban.expires else None)


def parse_room(key):
    """'p12' -> 12, anything else -> None."""
    if isinstance(key, str) and re.fullmatch(r"p\d{1,18}", key):
        return int(key[1:])
    return None


# ---------------------------------------------------------------- consumer

class OnlineChatConsumer(AsyncJsonWebsocketConsumer):
    username = None

    restricted = False
    expiry_task = None
    _lifted = False

    async def dispatch(self, message):
        # A restricted connection only hears about its own ban / unban.
        if self.restricted and message.get("type", "").startswith("chat.") and message["type"] not in ("chat.kick", "chat.unrestricted"):
            return
        await super().dispatch(message)

    async def connect(self):
        self.features = features(self.scope)
        self.username, error = await authenticate(self.scope)
        await self.accept()
        if error:
            limited = await restricted_login(self.scope) if "ban" in self.features else None
            if limited:
                await self.enter_restricted(*limited)
                return
            await self.send_json({"op": "error", "fatal": True, "text": error})
            await self.close(code=4001)
            return
        self.user_id = await user_id_of(self.username)
        self.actions = deque()
        self.rooms = set()
        self.dms = set()

        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)
        await self.channel_layer.group_add(user_group(self.user_id), self.channel_name)
        for ch in public_channels():
            await self.channel_layer.group_add(channel_group(ch), self.channel_name)
        private = await my_private_rooms(self.username)
        for room_id, _ in private:
            self.rooms.add(room_id)
            await self.channel_layer.group_add(room_group(room_id), self.channel_name)
        dms = await my_dms(self.user_id) if "dm" in self.features else []
        self.dms = {d["id"] for d in dms}
        await touch_session(self.username, self.channel_name)

        await self.send_json({
            "op": "welcome", "v": PROTOCOL, "user": self.username,
            "channels": [{"id": c, "title": c} for c in public_channels()],
            "rooms": [r for _, r in private] + dms,
            "invites": await my_invites(self.username),
            "online": await online_users(),
        })
        for ch in public_channels():
            await self.send_json({"op": "history", "channel": ch, "lines": await history(ch)})
        for room_id, r in private:
            await self.send_json({"op": "history", "channel": r["id"], "lines": await history(r["id"])})
        for d in dms:
            await self.send_json({"op": "history", "channel": d["id"], "lines": await history(d["id"])})
        await self.channel_layer.group_send(PRESENCE_GROUP, {"type": "chat.presence", "user": self.username, "online": True})

    async def disconnect(self, code):
        if not self.username:
            return
        if self.restricted:
            if self.expiry_task:
                self.expiry_task.cancel()
            await self.channel_layer.group_discard(user_group(self.user_id), self.channel_name)
            return
        went_offline = await drop_session(self.username, self.channel_name)
        await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)
        await self.channel_layer.group_discard(user_group(self.user_id), self.channel_name)
        for ch in public_channels():
            await self.channel_layer.group_discard(channel_group(ch), self.channel_name)
        for room_id in self.rooms:
            await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
        if went_offline:
            await self.channel_layer.group_send(PRESENCE_GROUP, {"type": "chat.presence", "user": self.username, "online": False})

    def rate_limited(self):
        now = time.monotonic()
        while self.actions and now - self.actions[0] > RATE_WINDOW:
            self.actions.popleft()
        if len(self.actions) >= RATE_COUNT:
            return True
        self.actions.append(now)
        return False

    async def error(self, text):
        await self.send_json({"op": "error", "text": text})

    async def receive_json(self, content, **kwargs):
        if not self.username or not isinstance(content, dict):
            return
        op = content.get("op")
        if self.restricted:
            if op == "ping":
                await self.send_json({"op": "pong"})
            return  # a restricted account only listens
        if op == "ping":
            await touch_session(self.username, self.channel_name)
            await self.send_json({"op": "pong"})
            return
        if op == "online":
            await self.send_json({"op": "online_list", "online": await online_users()})
            return
        handler = {
            "msg": self.op_msg, "create": self.op_create, "invite": self.op_invite,
            "accept": self.op_accept, "decline": self.op_decline, "leave": self.op_leave,
            "dm_open": self.op_dm_open,
        }.get(op)
        if handler is None:
            return  # unknown op from a newer client: ignore
        if self.rate_limited():
            await self.error("You're doing that too fast.")
            return
        await handler(content)

    async def op_msg(self, c):
        channel = c.get("channel")
        text = clean(c.get("text"), MAX_TEXT)
        if not text:
            return
        if channel in public_channels():
            group = channel_group(channel)
        elif parse_dm(channel):
            dm = await dm_for(channel, self.user_id)
            if dm is None:
                await self.error("That conversation doesn't exist.")
                return
            why_not = await dm_send_check(dm, self.user_id)
            if why_not:
                await self.error(why_not)
                return
            when = await save_message(channel, self.username, text)
            event = {"type": "chat.dm", "channel": channel, "author": self.username, "text": text, "ts": when}
            for uid in (dm.low_id, dm.high_id):
                await self.channel_layer.group_send(user_group(uid), event)
            await notify(dm.other(self.user_id), "dm", self.username, f"{self.username} sent you a message",
                         "/chat#dm=" + self.username)
            return
        else:
            room_id = parse_room(channel)
            if room_id is None or room_id not in self.rooms or not await is_member(room_id, self.username):
                await self.error("You're not in that room.")
                return
            group = room_group(room_id)
        when = await save_message(channel, self.username, text)
        await self.channel_layer.group_send(group, {"type": "chat.msg", "channel": channel,
                                                    "author": self.username, "text": text, "ts": when})

    async def op_create(self, c):
        title = clean(c.get("title"), MAX_TITLE, f"{self.username}'s room")
        room_id = await create_room(self.username, title)
        if room_id is None:
            await self.error(f"You can be in at most {MAX_PRIVATE_ROOMS} private rooms.")
            return
        await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.joined", "room": room_id})

    async def op_invite(self, c):
        room_id = parse_room(c.get("room"))
        target = clean(c.get("user"), 256)
        if room_id is None or not target or not await is_member(room_id, self.username):
            await self.error("You're not in that room.")
            return
        invite, err = await add_invite(room_id, target, self.username)
        if err:
            await self.error(err)
            return
        target_id = await user_id_of(target)
        await self.channel_layer.group_send(user_group(target_id), {"type": "chat.invite", **invite})
        await notify(target, "invite", self.username, f'{self.username} invited you to the chat room "{invite["title"]}"')
        await self.notice(room_id, f"{self.username} invited {target}.")

    async def op_accept(self, c):
        room_id = parse_room(c.get("room"))
        if room_id is None or not await accept_invite(room_id, self.username):
            await self.error("That invite isn't valid anymore.")
            return
        await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.joined", "room": room_id})
        await self.notice(room_id, f"{self.username} joined.")
        await self.room_changed(room_id)

    async def op_decline(self, c):
        room_id = parse_room(c.get("room"))
        if room_id is not None and await decline_invite(room_id, self.username):
            await self.notice(room_id, f"{self.username} declined the invite.")
            await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.invite_gone", "room": f"p{room_id}"})

    async def op_dm_open(self, c):
        if "dm" not in self.features:
            return
        room, err = await open_dm(self.user_id, self.username, clean(c.get("user"), 256, ""))
        if err:
            await self.error(err)
            return
        await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.dm_room", "room": room["id"], "focus": True})

    async def op_leave(self, c):
        if parse_dm(c.get("room")):
            dm = await dm_for(c.get("room"), self.user_id)
            if dm:
                await hide_dm(dm, self.user_id)
                await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.dm_left", "room": dm.key})
            return
        room_id = parse_room(c.get("room"))
        if room_id is None or not await is_member(room_id, self.username):
            return
        deleted = await leave_room(room_id, self.username)
        await self.channel_layer.group_send(user_group(self.user_id), {"type": "chat.left", "room": room_id})
        if not deleted:
            await self.notice(room_id, f"{self.username} left.")
            await self.room_changed(room_id)

    async def notice(self, room_id, text):
        await self.channel_layer.group_send(room_group(room_id), {"type": "chat.notice", "channel": f"p{room_id}", "text": text})

    async def room_changed(self, room_id):
        await self.channel_layer.group_send(room_group(room_id), {"type": "chat.room", "room": room_id})

    # ---------------------------------------------------------------- group events

    async def chat_msg(self, e):
        await self.send_json({"op": "msg", "channel": e["channel"], "author": e["author"], "text": e["text"], "ts": e["ts"]})

    async def chat_notice(self, e):
        await self.send_json({"op": "notice", "channel": e["channel"], "text": e["text"]})

    async def chat_kick(self, e):
        # Sent by moderation.service.kick_online when this account is banned.
        if "ban" in self.features:
            # Show it now; the reconnect lands in restricted mode (with the expiry), still listening for the lift.
            await self.send_json({"op": "restricted", "text": e["text"]})
            await self.close(code=RECONNECT_CODE)
            return
        await self.send_json({"op": "error", "fatal": True, "text": e["text"]})
        await self.close(code=4001)

    async def chat_unrestricted(self, e):
        if self.restricted:
            await self.lifted()

    # ---------------------------------------------------------------- restricted mode

    async def enter_restricted(self, username, text, expires):
        """Restricted account on a client that can show it: no chat, just ban news (and the lift, live)."""
        self.restricted, self.username = True, username
        self.user_id = await user_id_of(username)
        await self.channel_layer.group_add(user_group(self.user_id), self.channel_name)
        await self.send_json({"op": "restricted", "text": text, "expires": expires})
        if expires:
            self.expiry_task = asyncio.ensure_future(self.watch_expiry(expires))

    async def watch_expiry(self, expires):
        """Timed bans end lazily; check when this one should end so the player hears about it on time."""
        while expires:
            wait = expires / 1000 - time.time()
            await asyncio.sleep(min(max(wait, 1) + 1, 3600))
            restricted, _, expires = await still_restricted(self.username)
            if not restricted:
                await self.lifted()
                return

    async def lifted(self):
        if self._lifted:
            return  # the expiry check and the unban notice can both get here
        self._lifted = True
        if self.expiry_task and self.expiry_task is not asyncio.current_task():
            self.expiry_task.cancel()
        self.expiry_task = None
        await self.send_json({"op": "unrestricted", "text": "Your restriction has been lifted. Welcome back!"})
        await self.close(code=RECONNECT_CODE)

    # ---------------------------------------------------------------- DMs + friends

    async def chat_dm(self, e):
        if "dm" not in self.features or self.restricted:
            return
        if e["channel"] not in self.dms:
            # A new conversation for this session: the room (with its history, which has this message) instead.
            await self.show_dm(e["channel"], focus=False)
            return
        await self.send_json({"op": "msg", "channel": e["channel"], "author": e["author"], "text": e["text"], "ts": e["ts"]})

    async def chat_dm_room(self, e):
        if "dm" not in self.features or self.restricted:
            return
        await self.show_dm(e["room"], focus=e.get("focus", False))

    async def show_dm(self, key, focus):
        info = await dm_json(key, self.user_id)
        if not info:
            return
        self.dms.add(key)
        await self.send_json({"op": "room", "room": info, "focus": focus})
        await self.send_json({"op": "history", "channel": key, "lines": await history(key)})

    async def chat_dm_left(self, e):
        if "dm" in self.features and e["room"] in self.dms:
            self.dms.discard(e["room"])
            await self.send_json({"op": "left", "room": e["room"]})

    async def chat_friend(self, e):
        if "friends" in self.features and not self.restricted:
            await self.send_json({"op": "friend", "user": e["user"], "added": e["added"], "mutual": e.get("mutual", False)})

    async def chat_presence(self, e):
        if e["user"] != self.username:
            await self.send_json({"op": "presence", "user": e["user"], "online": e["online"]})

    async def chat_invite(self, e):
        await self.send_json({"op": "invite", "room": e["room"], "title": e["title"], "from": e["from"]})

    async def chat_invite_gone(self, e):
        await self.send_json({"op": "invite_gone", "room": e["room"]})

    async def chat_joined(self, e):
        """This user (any of their sessions) is now in a private room."""
        room_id = e["room"]
        if room_id not in self.rooms:
            self.rooms.add(room_id)
            await self.channel_layer.group_add(room_group(room_id), self.channel_name)
        info = await room_json(room_id)
        if info:
            await self.send_json({"op": "room", "room": info})
            await self.send_json({"op": "history", "channel": info["id"], "lines": await history(info["id"])})
            await self.send_json({"op": "invite_gone", "room": info["id"]})

    async def chat_left(self, e):
        room_id = e["room"]
        self.rooms.discard(room_id)
        await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
        await self.send_json({"op": "left", "room": f"p{room_id}"})

    async def chat_room(self, e):
        info = await room_json(e["room"])
        if info:
            await self.send_json({"op": "room", "room": info})
