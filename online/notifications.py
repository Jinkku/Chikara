"""Website notifications (the bell in the header): apiv2/notifications...

  GET  apiv2/notifications            -> {"unread": N, "notifications": [notification]}  (newest first, last 30)
  GET  apiv2/notifications/count      -> {"unread": N}
  POST apiv2/notifications/read       -> {"ok": true}   marks everything read
  POST apiv2/notifications/read/ID    -> {"ok": true}   marks one read
  POST apiv2/notifications/read/dm/NAME -> {"ok": true} marks NAME's messages read (the chat page does this when you open the DM)
  POST apiv2/notifications/clear      -> {"ok": true}   deletes them all

Open pages hear about changes right away over ws/v1/notify/ (online/notify_consumer.py).

A notification: {"id", "kind" (friend / invite / dm / comment), "actor", "text", "link", "count", "read", "created" (unix)}.
Same auth as apiv2/friends (game headers, or website cookies + "X-Chikara: 1" for POSTs).
Nothing here may fail the action that caused it, so push() swallows its own errors.
"""
import urllib.parse
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from moderation.service import request_user
from .models import Notification

LIST_SIZE = 30
KEEP = timedelta(days=60)
STACKING = {"dm"}   # unread ones from the same person merge into one row


def push(username, kind, actor, text, link=""):
    """Adds a notification for `username` (never for yourself) and tells their open pages."""
    try:
        if not username or username == actor:
            return
        now = timezone.now()
        row = None
        if kind in STACKING:
            row = Notification.objects.filter(username=username, kind=kind, actor=actor, read=False).first()
            if row is not None:
                row.count += 1
                row.text, row.link, row.created = text, link, now
                row.save(update_fields=["count", "text", "link", "created"])
        if row is None:
            row = Notification.objects.create(username=username, kind=kind, actor=actor, text=text[:300], link=link[:300], created=now)
        _send(username, {"type": "notify.new", "unread": unread_count(username), "notification": _json(row)})
    except Exception as e:
        print(f"[notifications] couldn't notify {username}: {e}")


def _send(username, event):
    """Live update to the player's open pages. Never fails the caller over it."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from .notify_consumer import notify_group
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(notify_group(username), event)
    except Exception as e:
        print(f"[notifications] couldn't reach {username}'s pages: {e}")


def _count_changed(username):
    n = unread_count(username)
    _send(username, {"type": "notify.unread", "unread": n})
    return n


def unread_count(username):
    return Notification.objects.filter(username=username, read=False).count()


def _json(n):
    return {"id": n.id, "kind": n.kind, "actor": n.actor, "text": n.text, "link": n.link,
            "count": n.count, "read": n.read, "created": int(n.created.timestamp())}


@csrf_exempt
def api(request, action=""):
    parts = [urllib.parse.unquote(p) for p in action.strip("/").split("/") if p]
    write = request.method == "POST"
    me = request_user(request, write=write)
    if me is None:
        return JsonResponse({"error": 1, "reason": "Log in first."}, status=401)
    mine = Notification.objects.filter(username=me.username)
    if not write and not parts:
        mine.filter(created__lt=timezone.now() - KEEP).delete()
        rows = list(mine.order_by("-created")[:LIST_SIZE])
        return JsonResponse({"unread": unread_count(me.username), "notifications": [_json(n) for n in rows]})
    if not write and parts == ["count"]:
        return JsonResponse({"unread": unread_count(me.username)})
    if write and parts and parts[0] == "read":
        if len(parts) == 1:
            mine.filter(read=False).update(read=True)
        elif len(parts) == 2 and parts[1].isdigit():
            mine.filter(id=int(parts[1])).update(read=True)
        elif len(parts) == 3 and parts[1] == "dm":
            mine.filter(kind="dm", actor=parts[2], read=False).update(read=True)
        else:
            return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
        return JsonResponse({"ok": True, "unread": _count_changed(me.username)})
    if write and parts == ["clear"]:
        mine.delete()
        return JsonResponse({"ok": True, "unread": _count_changed(me.username)})
    return JsonResponse({"error": 1, "reason": "Unknown request."}, status=404)
