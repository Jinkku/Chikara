"""apiv2/mod/... : reports, bans and the team. Used by the website (/admin, report button) and the game.

Auth: the game's Username + Password headers, or the website's login cookies (+ "X-Chikara: 1" on POSTs).
Every POST takes a JSON body. Every reply is JSON; failures are {"error": "..."} with a 4xx status.
"""
import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone

from Chikara.settings import SUPPORT_URL
from dbview.models import Score, User
from submissions import claims
from . import content, news, service
from .models import Ban, CardBorder, Notice, Report, StaffMember, SupportOrder, Supporter

PAGE = 50
MAX_REASON = 500
MAX_DETAILS = 2000


def fail(text, status=400):
    return JsonResponse({"error": text}, status=status)


def body(request):
    try:
        data = json.loads(request.body or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def text(data, key, limit):
    v = data.get(key)
    if not isinstance(v, str):
        return ""
    return "".join(c for c in v if c.isprintable() or c == "\n").strip()[:limit]


def page_of(request):
    try:
        return max(0, int(request.GET.get("page") or 0))
    except ValueError:
        return 0


def ts(dt):
    return int(dt.timestamp()) if dt else 0


def report_json(r):
    return {
        "id": r.id, "reporter": r.reporter, "target": r.target,
        "category": r.category, "category_text": dict(Report.CATEGORIES).get(r.category, r.category),
        "details": r.details, "context": r.context, "source": r.source, "status": r.status,
        "created": ts(r.created), "handled_by": r.handled_by, "handled_at": ts(r.handled_at), "note": r.note,
        "evidence": r.evidence or [],
    }


def ban_json(b):
    now = timezone.now()
    active = b.enforced and (b.expires is None or b.expires > now)
    return {
        "id": b.id, "username": b.username, "reason": b.reason, "issued_by": b.issued_by,
        "created": ts(b.created), "expires": ts(b.expires), "permanent": b.expires is None,
        "active": active, "time_left": service.time_left(b.expires) if active and b.expires else "",
        "lifted_by": b.lifted_by, "lifted_at": ts(b.lifted_at), "lift_note": b.lift_note,
        "report": b.report_id or 0,
    }


def user_row(u, staff_roles):
    return {
        "id": u.id, "username": u.username, "restricted": bool(u.restricted),
        "rank": u.ranking or 0, "points": u.ranked_points or 0,
        "joined": ts(u.created), "last_seen": u.stattime or 0,
        "staff": staff_roles.get(u.username, ""),
    }


# ---------------------------------------------------------------- entry point

def api(request, action):
    parts = [p for p in action.split("/") if p]
    if not parts:
        return fail("Unknown action.", 404)
    name, args = parts[0], parts[1:]
    write = request.method == "POST"
    me = service.request_user(request, write=write)
    if me is None:
        return fail("Log in first." if not write else "Log in first (or your login has expired).", 401)

    if name == "me" and not write:
        return me_view(me)
    if name == "report" and write and not args:
        return report_view(request, me)

    # Everything else is the admin panel.
    staff = service.staff_of(me.username)
    if staff is None or me.restricted:
        return fail("Only the Qlute team can do that.", 403)
    service.expire_all()
    handlers = {
        ("reports", False): reports_view,
        ("report", True): report_close_view,
        ("users", False): users_view,
        ("user", False): user_view,
        ("ban", True): ban_view,
        ("unban", True): unban_view,
        ("bans", False): bans_view,
        ("staff", False): staff_view,
        ("staff", True): staff_edit_view,
        ("notices", False): notices_view,
        ("notices", True): notices_edit_view,
        ("supporters", False): supporters_view,
        ("supporters", True): supporters_edit_view,
        ("borders", False): borders_view,
        ("borders", True): borders_edit_view,
        ("claims", False): claims.claims_view,
        ("claims", True): claims.claims_edit_view,
        ("news", False): news.news_view,
        ("news", True): news.news_edit_view,
        ("scores", True): scores_edit_view,
        ("country", True): country_edit_view,
    }
    handler = handlers.get((name, write))
    if handler is None:
        return fail("Unknown action.", 404)
    return handler(request, me, staff, args)


# ---------------------------------------------------------------- everyone

def me_view(me):
    staff = service.staff_of(me.username)
    ban = service.active_ban(me.username) if me.restricted else None
    data = {
        "username": me.username,
        "staff": staff is not None,
        "admin": staff is not None and staff.role == StaffMember.ROLE_ADMIN,
        "role": staff.role if staff else "",
        "restricted": bool(User.objects.filter(id=me.id).values_list("restricted", flat=True).first()),
        "ban": ban_json(ban) if ban else None,
        "categories": [{"id": k, "text": v} for k, v in Report.CATEGORIES],
    }
    if staff is not None:
        data["open_reports"] = Report.objects.filter(status=Report.STATUS_OPEN).count()
        data["pending_claims"] = claims.BeatmapClaim.objects.filter(status=claims.BeatmapClaim.PENDING).count()
    return JsonResponse(data)


def report_view(request, me):
    if me.restricted:
        return fail("Restricted accounts can't send reports.", 403)
    data = body(request)
    target = text(data, "target", 256)
    if not target:
        return fail("Who are you reporting?")
    if target == me.username:
        return fail("You can't report yourself.")
    if not User.objects.filter(username=target).exists():
        return fail(f"There's no player called {target}.", 404)
    details = text(data, "details", MAX_DETAILS)
    if len(details) < 5:
        return fail("Please say what happened (at least a few words).")
    if not service.can_report(me.username):
        return fail("You've sent a lot of reports recently. Please wait a while.", 429)
    source = "game" if request.META.get("HTTP_USERNAME") else "web"
    report, created = service.file_report(me.username, target, text(data, "category", 16), details,
                                          text(data, "context", 512), source)
    return JsonResponse({"ok": True, "id": report.id, "merged": not created,
                         "message": "Thanks! The Qlute team will look into it."})


# ---------------------------------------------------------------- team: reports

def reports_view(request, me, staff, args):
    status = request.GET.get("status") or "open"
    reports = Report.objects.all()
    if status == "open":
        reports = reports.filter(status=Report.STATUS_OPEN).order_by("created")  # oldest first: work the queue
    else:
        if status == "closed":
            reports = reports.exclude(status=Report.STATUS_OPEN)
        reports = reports.order_by("-created")
    who = (request.GET.get("user") or "").strip()
    if who:
        reports = reports.filter(Q(target=who) | Q(reporter=who))
    start = page_of(request) * PAGE
    rows = list(reports[start:start + PAGE])
    # How many open reports each target has, so the panel can show "3 reports".
    targets = {r.target for r in rows}
    counts = dict(Report.objects.filter(target__in=targets, status=Report.STATUS_OPEN)
                  .values_list("target").annotate(n=Count("id")).values_list("target", "n"))
    restricted = set(User.objects.filter(username__in=targets, restricted=True).values_list("username", flat=True))
    out = []
    for r in rows:
        j = report_json(r)
        j["target_open_reports"] = counts.get(r.target, 0)
        j["target_restricted"] = r.target in restricted
        out.append(j)
    return JsonResponse({"results": out, "page_size": PAGE,
                         "open": Report.objects.filter(status=Report.STATUS_OPEN).count()})


def report_close_view(request, me, staff, args):
    # POST mod/report/<id>/close {status: resolved|dismissed, note}   or   mod/report/<id>/reopen
    if len(args) != 2 or not args[0].isdigit() or args[1] not in ("close", "reopen"):
        return fail("Unknown action.", 404)
    report = Report.objects.filter(id=int(args[0])).first()
    if report is None:
        return fail("That report doesn't exist.", 404)
    data = body(request)
    if args[1] == "reopen":
        report.status, report.handled_by, report.handled_at = Report.STATUS_OPEN, "", None
    else:
        status = data.get("status")
        if status not in (Report.STATUS_RESOLVED, Report.STATUS_DISMISSED):
            return fail("status must be resolved or dismissed.")
        report.status = status
        report.handled_by = me.username
        report.handled_at = timezone.now()
        report.note = text(data, "note", MAX_REASON)
    report.save()
    return JsonResponse({"ok": True, "report": report_json(report)})


# ---------------------------------------------------------------- team: players

def users_view(request, me, staff, args):
    query = (request.GET.get("query") or "").strip()[:64]
    users = User.objects.exclude(username=None).exclude(username="")
    if request.GET.get("restricted") == "1":
        users = users.filter(restricted=True)
    if query:
        users = users.filter(username__icontains=query)
    start = page_of(request) * PAGE
    rows = list(users.order_by("username")[start:start + PAGE])
    roles = dict(StaffMember.objects.filter(username__in=[u.username for u in rows]).values_list("username", "role"))
    return JsonResponse({"results": [user_row(u, roles) for u in rows], "page_size": PAGE})


def user_view(request, me, staff, args):
    name = "/".join(args)
    u = User.objects.filter(username=name).first()
    if u is None:
        return fail(f"There's no player called {name}.", 404)
    roles = dict(StaffMember.objects.filter(username=u.username).values_list("username", "role"))
    data = user_row(u, roles)
    data.update({
        "status": u.status or "",
        "accuracy": round(u.accuracy or 0, 2),
        "scores": Score.objects.filter(username=u.username).count(),
        "bans": [ban_json(b) for b in Ban.objects.filter(username=u.username).order_by("-created")[:50]],
        "reports_against": [report_json(r) for r in Report.objects.filter(target=u.username).order_by("-created")[:50]],
        "reports_sent": Report.objects.filter(reporter=u.username).count(),
        "can_ban": can_ban(me, staff, u.username) is None,
        "supporter": supporter_json(Supporter.objects.filter(username=u.username).first()),
        "can_grant_support": staff.role == StaffMember.ROLE_ADMIN,
    })
    from Chikara import countries
    hist = countries.history(u.id)
    data.update({
        "country": u.country or "", "country_name": countries.name(u.country), "country_set": ts(u.country_set),
        "countries_seen": [{"code": c, "name": countries.name(c), "days": h["days"], "first": h["first"].isoformat(),
                            "last": h["last"].isoformat()} for c, h in sorted(hist.items(), key=lambda x: -x[1]["days"])],
        "all_countries": sorted(([c, n] for c, n in countries.NAMES.items()), key=lambda x: x[1]),
    })
    return JsonResponse(data)


def country_edit_view(request, me, staff, args):
    """POST apiv2/mod/country {"username", "country"}: the team sets anyone's country ("" clears it), no waiting period."""
    from Chikara import countries
    data = body(request)
    u = User.objects.filter(username=str(data.get("username") or "")).first()
    if u is None:
        return fail("There's no player called that.", 404)
    code = str(data.get("country") or "").upper()
    if code and not countries.name(code):
        return fail("Pick a country from the list.")
    countries.set_country(u.id, code)
    return JsonResponse({"ok": True, "country": code, "name": countries.name(code)})


def can_ban(me, staff, target):
    """None if allowed, else why not."""
    if target == me.username:
        return "You can't ban yourself."
    other = service.staff_of(target)
    if other is not None and (staff.role != StaffMember.ROLE_ADMIN or other.role == StaffMember.ROLE_ADMIN):
        return "Team members can only be banned by an admin, and admins can't be banned here."
    return None


def ban_view(request, me, staff, args):
    data = body(request)
    target = text(data, "username", 256)
    u = User.objects.filter(username=target).first() if target else None
    if u is None:
        return fail(f"There's no player called {target}.", 404)
    why_not = can_ban(me, staff, u.username)
    if why_not:
        return fail(why_not, 403)
    reason = text(data, "reason", MAX_REASON)
    if len(reason) < 3:
        return fail("Give a reason; the player will see it.")
    try:
        hours = float(data.get("hours") or 0)
    except (TypeError, ValueError):
        return fail("hours must be a number (0 = permanent).")
    if hours < 0 or hours > service.MAX_BAN_HOURS:
        return fail("That ban length isn't allowed.")
    report = None
    if str(data.get("report") or "").isdigit():
        report = Report.objects.filter(id=int(data["report"])).first()
    b = service.ban(u.username, reason, hours or None, me.username, report)
    deleted = 0
    if data.get("delete_scores") is True:
        deleted, _ = service.delete_scores(Score.objects.filter(username=u.username))
        print(f"[moderation] {me.username} banned {u.username} and deleted all {deleted} of their scores")
    if data.get("close_reports", True):
        Report.objects.filter(target=u.username, status=Report.STATUS_OPEN).update(
            status=Report.STATUS_RESOLVED, handled_by=me.username, handled_at=timezone.now(),
            note=f"Banned: {reason}"[:MAX_REASON])
    return JsonResponse({"ok": True, "ban": ban_json(b), "deleted_scores": deleted})


def unban_view(request, me, staff, args):
    data = body(request)
    target = text(data, "username", 256)
    u = User.objects.filter(username=target).first() if target else None
    if u is None:
        return fail(f"There's no player called {target}.", 404)
    lifted = service.unban(u.username, me.username, text(data, "note", MAX_REASON))
    return JsonResponse({"ok": True, "lifted": lifted})


def bans_view(request, me, staff, args):
    bans = Ban.objects.all()
    if (request.GET.get("status") or "active") == "active":
        bans = bans.filter(enforced=True)
    query = (request.GET.get("query") or "").strip()[:64]
    if query:
        bans = bans.filter(username__icontains=query)
    start = page_of(request) * PAGE
    return JsonResponse({"results": [ban_json(b) for b in bans.order_by("-created")[start:start + PAGE]],
                         "page_size": PAGE})


# ---------------------------------------------------------------- team: members

def staff_view(request, me, staff, args):
    rows = StaffMember.objects.order_by("role", "username")
    return JsonResponse({"results": [{"username": s.username, "role": s.role, "added_by": s.added_by,
                                      "added": ts(s.added)} for s in rows],
                         "can_edit": staff.role == StaffMember.ROLE_ADMIN})


def staff_edit_view(request, me, staff, args):
    # POST mod/staff/add {username, role}   or   mod/staff/remove {username}
    if staff.role != StaffMember.ROLE_ADMIN:
        return fail("Only admins can change the team.", 403)
    if len(args) != 1 or args[0] not in ("add", "remove"):
        return fail("Unknown action.", 404)
    data = body(request)
    target = text(data, "username", 256)
    if target == me.username:
        return fail("You can't change your own team role.")
    u = User.objects.filter(username=target).first() if target else None
    if u is None:
        return fail(f"There's no player called {target}.", 404)
    if args[0] == "remove":
        StaffMember.objects.filter(username=u.username).delete()
        return JsonResponse({"ok": True})
    role = data.get("role") if data.get("role") in dict(StaffMember.ROLES) else StaffMember.ROLE_MOD
    StaffMember.objects.update_or_create(username=u.username, defaults={"role": role, "added_by": me.username})
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- team: deleting scores

def scores_edit_view(request, me, staff, args):
    # POST mod/scores/<id>/delete
    # POST mod/scores/purge {hours, username (optional), confirm}: without confirm=true it only counts what would go.
    #      hours = 0 means all time, which needs a username.
    data = body(request)
    if len(args) == 2 and args[0].isdigit() and args[1] == "delete":
        scores = Score.objects.filter(id=int(args[0]))
        if not scores.exists():
            return fail("That score doesn't exist.", 404)
        deleted, players = service.delete_scores(scores)
        print(f"[moderation] {me.username} deleted score #{args[0]} by {', '.join(players)}")
        return JsonResponse({"ok": True, "deleted": deleted, "players": players})
    if args != ["purge"]:
        return fail("Unknown action.", 404)
    try:
        hours = float(data.get("hours") or 0)
    except (TypeError, ValueError):
        return fail("hours must be a number.")
    who = text(data, "username", 256)
    if hours == 0 and not who:
        return fail("Deleting scores from all time needs a player name.")
    if not 0 <= hours <= service.MAX_PURGE_HOURS:
        return fail(f"Pick between a few minutes and {service.MAX_PURGE_HOURS // 24} days.")
    scores = Score.objects.all()
    if hours:
        scores = scores.filter(created__gte=timezone.now() - timezone.timedelta(hours=hours))
    if who:
        if not User.objects.filter(username=who).exists():
            return fail(f"There's no player called {who}.", 404)
        scores = scores.filter(username=who)
    if data.get("confirm") is not True:
        players = list(scores.values("username").annotate(n=Count("id")).order_by("-n").values_list("username", "n"))
        return JsonResponse({"ok": True, "preview": True, "count": sum(n for _, n in players),
                             "players": [{"username": u or "", "scores": n} for u, n in players[:100]]})
    deleted, players = service.delete_scores(scores)
    print(f"[moderation] {me.username} deleted {deleted} scores from {'all time' if not hours else f'the last {hours:g}h'}"
          f"{' by ' + who if who else ''} ({len(players)} players)")
    return JsonResponse({"ok": True, "deleted": deleted, "players": players})


# ---------------------------------------------------------------- supporters (admins grant time, e.g. after a donation)

def supporter_json(s):
    if s is None:
        return None
    return {"username": s.username, "active": s.active(), "forever": s.expires is None, "expires": ts(s.expires),
            "time_left": service.time_left(s.expires) if s.expires and s.active() else "",
            "granted_by": s.granted_by, "granted": ts(s.granted), "updated": ts(s.updated), "note": s.note}


def supporters_view(request, me, staff, args):
    rows = list(Supporter.objects.order_by("-updated")[:500])
    rows.sort(key=lambda s: (not s.active(), s.username.lower()))
    from . import payments
    # Settle recent checkouts whose webhook never came (paid or canceled on Xsolla's side).
    payments.sync_orders(SupportOrder.objects.filter(status=SupportOrder.STATUS_PENDING,
                                                     created__gt=timezone.now() - timezone.timedelta(days=2))[:50])
    orders = [{"id": o.id, "buyer": o.buyer, "recipient": o.recipient, "months": o.months, "status": o.status,
               "amount": o.amount, "sandbox": o.sandbox, "xsolla_order": o.xsolla_order_id or 0,
               "created": ts(o.created), "paid_at": ts(o.paid_at)}
              for o in SupportOrder.objects.exclude(status=SupportOrder.STATUS_PENDING, created__lt=timezone.now() - timezone.timedelta(days=2))
                                           .order_by("-created")[:50]]
    return JsonResponse({"results": [supporter_json(s) for s in rows], "support_url": SUPPORT_URL,
                         "can_edit": staff.role == StaffMember.ROLE_ADMIN, "orders": orders,
                         "payments_ready": payments.configured()})


def supporters_edit_view(request, me, staff, args):
    # POST mod/supporters/grant {username, months (0 = forever), note}   or   mod/supporters/revoke {username}
    if staff.role != StaffMember.ROLE_ADMIN:
        return fail("Only admins can grant or remove supporter time.", 403)
    if len(args) != 1 or args[0] not in ("grant", "revoke"):
        return fail("Unknown action.", 404)
    data = body(request)
    target = text(data, "username", 256)
    u = User.objects.filter(username=target).first() if target else None
    if u is None:
        return fail(f"There's no player called {target}.", 404)
    if args[0] == "revoke":
        service.revoke_support(u.username)
        return JsonResponse({"ok": True})
    try:
        months = int(data.get("months") or 0)
    except (TypeError, ValueError):
        return fail("months must be a whole number (0 = forever).")
    if months < 0 or months > service.MAX_SUPPORT_MONTHS:
        return fail("That length isn't allowed.")
    row = service.grant_support(u.username, months or None, me.username, text(data, "note", 300))
    return JsonResponse({"ok": True, "supporter": supporter_json(row)})


# ---------------------------------------------------------------- admins: notices + card borders

def form(request):
    """Fields from a multipart upload or a JSON body."""
    if request.content_type and request.content_type.startswith("multipart/"):
        return request.POST
    return body(request)


def admin_only(staff):
    return None if staff.role == StaffMember.ROLE_ADMIN else fail("Only admins can change site content.", 403)


def notices_view(request, me, staff, args):
    rows = Notice.objects.order_by("position", "id")
    return JsonResponse({"results": [content.notice_json(n) for n in rows],
                         "can_edit": staff.role == StaffMember.ROLE_ADMIN})


def notices_edit_view(request, me, staff, args):
    # POST notices/add (multipart: image, text, redirect) | notices/<id>/edit | notices/<id>/move {dir} | notices/<id>/delete
    denied = admin_only(staff)
    if denied:
        return denied
    data = form(request)
    if args == ["add"]:
        txt = text(data, "text", 200)
        try:
            image = content.save_notice_image(request.FILES.get("image"), txt)
        except content.BadImage as e:
            return fail(str(e))
        last = Notice.objects.order_by("-position").values_list("position", flat=True).first()
        n = Notice.objects.create(image=image, text=txt, redirect=clean_link(data), created_by=me.username,
                                  position=(last if last is not None else -1) + 1)
        return JsonResponse({"ok": True, "notice": content.notice_json(n)})
    if len(args) != 2 or not args[0].isdigit():
        return fail("Unknown action.", 404)
    n = Notice.objects.filter(id=int(args[0])).first()
    if n is None:
        return fail("That notice doesn't exist.", 404)
    action = args[1]
    if action == "delete":
        content.delete_notice(n)
        return JsonResponse({"ok": True})
    if action == "move":
        rows = list(Notice.objects.order_by("position", "id"))
        i = rows.index(n)
        j = i + (1 if str(data.get("dir")) == "1" else -1)
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            for pos, row in enumerate(rows):
                if row.position != pos:
                    Notice.objects.filter(id=row.id).update(position=pos)
        return JsonResponse({"ok": True})
    if action != "edit":
        return fail("Unknown action.", 404)
    if "text" in data:
        n.text = text(data, "text", 200)
    if "redirect" in data:
        n.redirect = clean_link(data)
    if "active" in data:
        n.active = str(data.get("active")).lower() in ("1", "true")
    if request.FILES.get("image"):
        try:
            new_image = content.save_notice_image(request.FILES["image"], n.text)
        except content.BadImage as e:
            return fail(str(e))
        content._remove(n.image, "events")
        n.image = new_image
    n.save()
    return JsonResponse({"ok": True, "notice": content.notice_json(n)})


def clean_link(data):
    link = text(data, "redirect", 500)
    if link and not link.startswith(("https://", "http://")):
        link = "https://" + link
    return link


def borders_view(request, me, staff, args):
    rows = CardBorder.objects.order_by("-active", "name")
    return JsonResponse({"results": [content.border_json(b, content.border_users(b)) for b in rows],
                         "size": list(content.BORDER_SIZE), "can_edit": staff.role == StaffMember.ROLE_ADMIN})


def borders_edit_view(request, me, staff, args):
    # POST borders/add (multipart: image, name) | borders/<id>/edit {name, active} | borders/<id>/delete
    denied = admin_only(staff)
    if denied:
        return denied
    data = form(request)
    if args == ["add"]:
        name = text(data, "name", 64)
        if not name:
            return fail("Give the border a name.")
        try:
            image = content.save_border_image(request.FILES.get("image"), name)
        except content.BadImage as e:
            return fail(str(e))
        b = CardBorder.objects.create(name=name, image=image, created_by=me.username)
        return JsonResponse({"ok": True, "border": content.border_json(b, 0)})
    if len(args) != 2 or not args[0].isdigit():
        return fail("Unknown action.", 404)
    b = CardBorder.objects.filter(id=int(args[0])).first()
    if b is None:
        return fail("That card border doesn't exist.", 404)
    if args[1] == "delete":
        content.delete_border(b)
        return JsonResponse({"ok": True})
    if args[1] != "edit":
        return fail("Unknown action.", 404)
    if "name" in data:
        name = text(data, "name", 64)
        if not name:
            return fail("Give the border a name.")
        b.name = name
    if "active" in data:
        b.active = str(data.get("active")).lower() in ("1", "true")
    if "supporter_only" in data:
        b.supporter_only = str(data.get("supporter_only")).lower() in ("1", "true")
    b.save()
    service.borders_changed()
    return JsonResponse({"ok": True, "border": content.border_json(b, content.border_users(b))})
