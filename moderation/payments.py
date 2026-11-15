"""Supporter tags bought through Xsolla (like osu!'s supporter tags).

Flow:
  1. /support: the player picks a plan (settings.SUPPORTER_PLANS), optionally as a gift, and presses Buy.
  2. POST apiv2/support/checkout {plan (months), gift}: we save a SupportOrder, ask Xsolla's Catalog API for a
     payment token for `months` x the supporter item (settings.SUPPORTER_ITEM_SKU, one item = one month; the buyer
     is user.id = their Qlute user id) and answer with the Pay Station URL.
  3. The player pays on Xsolla's page and comes back to /support?order=ID, which polls
     GET apiv2/support/order/ID until the order is paid.
  4. Xsolla calls POST apiv2/xsolla (the webhook URL set in Publisher Account), signed with
     "Authorization: Signature sha1(raw body + webhook secret)":
       user_validation  -> 204 if the Qlute account exists and isn't restricted, else 400 INVALID_USER
       order_paid       -> grant the months (once per Xsolla order id), 204
       order_canceled   -> take the months back, 204
     Anything else (payment / refund on older projects) gets 204 and is ignored: order_* carry the items.

Keys live in config/config.conf (not in git): xsolla_project_id, xsolla_api_key, xsolla_webhook_secret,
xsolla_sandbox. In sandbox mode Pay Station takes test cards only; orders Xsolla marks as sandbox are
ignored once sandbox mode is off, so test payments can never grant real supporter time.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
from datetime import timedelta

import requests
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt

from Chikara import settings as S
from dbview.models import User
from . import service
from .models import SupportOrder, Supporter

log = logging.getLogger(__name__)

TOKEN_URL = "https://store.xsolla.com/api/v3/project/{project}/admin/payment/token"
PAYSTATION = "https://secure.xsolla.com/paystation4/?token={token}"
PAYSTATION_SANDBOX = "https://sandbox-secure.xsolla.com/paystation4/?token={token}"
ORDERS_PER_HOUR = 10


def configured():
    return bool(S.XSOLLA_PROJECT_ID and S.XSOLLA_API_KEY and S.XSOLLA_WEBHOOK_SECRET)


def plans():
    """{"4": {"months": 4, "price": "$10"}, ...}: the lengths offered on /support."""
    return {str(m): {"months": m, "price": price_label(m)} for m in S.SUPPORTER_PLANS}


def price_label(months):
    total = S.SUPPORTER_MONTH_PRICE * months
    return f"${total:.0f}" if total == int(total) else f"${total:.2f}"


def _fail(text, status=400):
    return JsonResponse({"error": text}, status=status)


def _client_ip(request):
    """The buyer's IPv4 (Xsolla picks the currency from it; it doesn't take IPv6)."""
    # Cloudflare sits in front of the site: nginx's X-Real-IP is Cloudflare's address, CF-Connecting-IP the buyer's.
    ip = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or ""
    try:
        return ip if ipaddress.ip_address(ip).version == 4 else ""
    except ValueError:
        return ""


# ---------------------------------------------------------------- website API: apiv2/support/...

@csrf_exempt
def api(request, action=""):
    parts = [p for p in action.strip("/").split("/") if p]
    write = request.method == "POST"
    me = service.request_user(request, write=write)
    if me is None:
        return _fail("Log in first.", 401)
    if write and parts == ["checkout"]:
        return checkout(request, me)
    if not write and len(parts) == 2 and parts[0] == "order" and parts[1].isdigit():
        order = SupportOrder.objects.filter(id=int(parts[1]), buyer=me.username).first()
        if order is None:
            return _fail("That order doesn't exist.", 404)
        if order.status == SupportOrder.STATUS_PENDING:
            sync_orders([order])
            order.refresh_from_db()
        return JsonResponse(order_json(order))
    return _fail("Unknown request.", 404)


def order_json(o):
    return {"id": o.id, "status": o.status, "months": o.months, "recipient": o.recipient,
            "gift": o.recipient != o.buyer, "sandbox": o.sandbox}


def checkout(request, me):
    if not configured():
        return _fail("Supporter tags can't be bought just yet. Check back soon <3", 503)
    if me.restricted:
        return _fail("Restricted accounts can't buy supporter tags.", 403)
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    plan = plans().get(str(data.get("plan") or ""))
    if plan is None:
        return _fail("Pick one of the plans.")
    recipient = me
    gift = str(data.get("gift") or "").strip()[:256]
    if gift and gift != me.username:
        recipient = User.objects.filter(username=gift).first()
        if recipient is None:
            return _fail(f"There's no player called {gift}.", 404)
        if recipient.restricted:
            return _fail(f"{recipient.username} can't receive gifts right now.")
    recent = SupportOrder.objects.filter(buyer=me.username, created__gt=timezone.now() - timedelta(hours=1)).count()
    if recent >= ORDERS_PER_HOUR:
        return _fail("That's a lot of checkouts. Try again in a bit.", 429)

    order = SupportOrder.objects.create(buyer=me.username, recipient=recipient.username, sku=S.SUPPORTER_ITEM_SKU,
                                        months=plan["months"], sandbox=S.XSOLLA_SANDBOX)
    body = {
        "sandbox": S.XSOLLA_SANDBOX,
        "user": {"id": {"value": str(me.id)}, "name": {"value": me.username}},
        "purchase": {"items": [{"sku": S.SUPPORTER_ITEM_SKU, "quantity": plan["months"]}]},  # 1 item = 1 month
        # No settings.external_id: Xsolla answers "[0401-2000] Exception with PayStation service" when it's set
        # (orders are matched by Xsolla's order id; custom_parameters keeps ours for their dashboard).
        "settings": {
            "return_url": f"{S.SiteURL}/support?order={order.id}",
            "language": "en",
        },
        "custom_parameters": {"qlute_order": order.id, "recipient": recipient.username},
    }
    headers = {"Content-Type": "application/json"}
    # Xsolla needs the buyer's IP or country (it picks the currency from it) or it refuses the checkout.
    ip = _client_ip(request)
    country = (request.META.get("HTTP_CF_IPCOUNTRY") or "").upper()
    if ip:
        headers["X-User-Ip"] = ip
    elif len(country) == 2 and country.isalpha() and country not in ("XX", "T1"):
        body["user"]["country"] = {"value": country}
    else:
        body["user"]["country"] = {"value": "US"}
    auth = base64.b64encode(f"{S.XSOLLA_PROJECT_ID}:{S.XSOLLA_API_KEY}".encode()).decode()
    headers["Authorization"] = "Basic " + auth
    try:
        res = requests.post(TOKEN_URL.format(project=S.XSOLLA_PROJECT_ID), json=body, headers=headers, timeout=15)
        reply = res.json()
    except (requests.RequestException, ValueError) as e:
        log.error("xsolla token request failed: %s", e)
        order.delete()
        return _fail("Couldn't reach the payment provider. Try again in a minute.", 424)
    if res.status_code not in (200, 201) or not reply.get("token"):
        log.error("xsolla token refused (%s): %s", res.status_code, reply)
        order.delete()
        return _fail("The payment provider refused the checkout. Try again later.", 424)  # not 502: Cloudflare would hide this
    if reply.get("order_id"):
        SupportOrder.objects.filter(id=order.id).update(xsolla_order_id=int(reply["order_id"]))
    page = PAYSTATION_SANDBOX if S.XSOLLA_SANDBOX else PAYSTATION
    return JsonResponse({"ok": True, "order": order.id, "url": page.format(token=reply["token"]), "sandbox": S.XSOLLA_SANDBOX})


# ---------------------------------------------------------------- Xsolla webhook: POST apiv2/xsolla

def _xsolla_error(code, message, status=400):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def signature_ok(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Signature ") or not S.XSOLLA_WEBHOOK_SECRET:
        return False
    expected = hashlib.sha1(request.body + S.XSOLLA_WEBHOOK_SECRET.encode()).hexdigest()
    return hmac.compare_digest(header[len("Signature "):].strip().lower(), expected)


def _months_in(items):
    """Supporter months in an order's items: one supporter item is one month (other SKUs: ignored)."""
    total = 0
    for item in items or []:
        if str(item.get("sku") or "").lower() == S.SUPPORTER_ITEM_SKU.lower():
            try:
                total += max(1, int(item.get("quantity") or 1))
            except (TypeError, ValueError):
                total += 1
    return total


def _user_by_id(value):
    try:
        return User.objects.filter(id=int(value)).first()
    except (TypeError, ValueError):
        return None


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    if not signature_ok(request):
        return _xsolla_error("INVALID_SIGNATURE", "Signature mismatch.")
    try:
        data = json.loads(request.body)
    except ValueError:
        return _xsolla_error("INVALID_PARAMETER", "Body isn't JSON.")
    kind = data.get("notification_type")

    if kind == "user_validation":
        u = _user_by_id((data.get("user") or {}).get("id"))
        if u is None or u.restricted:
            return _xsolla_error("INVALID_USER", "User not found.")
        return HttpResponse(status=204)

    if kind == "order_paid":
        return _order_paid(data)
    if kind == "order_canceled":
        return _order_canceled(data)
    return HttpResponse(status=204)  # payment / refund / others: nothing to do (order_* carry the items)


def _order_paid(data):
    order_info = data.get("order") or {}
    sandbox = order_info.get("mode") == "sandbox" or bool((data.get("billing") or {}).get("transaction", {}).get("dry_run"))
    mark_paid(order_info.get("id"), data.get("items"), sandbox,
              f'{order_info.get("amount", "")} {order_info.get("currency", "")}'.strip(),
              (data.get("user") or {}).get("external_id"))
    return HttpResponse(status=204)


def _order_canceled(data):
    mark_canceled((data.get("order") or {}).get("id"))
    return HttpResponse(status=204)


def mark_paid(xid, items, sandbox, amount, buyer_id):
    """An Xsolla order was paid (webhook or our own check): grant the time, once per order."""
    if sandbox and not S.XSOLLA_SANDBOX:
        log.warning("ignoring sandbox order %s while sandbox mode is off", xid)
        return
    months = _months_in(items)
    if not months or not xid:
        return  # not a supporter tag
    with transaction.atomic():
        order = SupportOrder.objects.select_for_update().filter(xsolla_order_id=xid).first()
        if order is None:
            # Bought outside our checkout (e.g. an Xsolla web shop): it's for the paying account.
            buyer = _user_by_id(buyer_id)
            if buyer is None:
                log.error("paid order %s for unknown user %s", xid, buyer_id)
                return
            order = SupportOrder.objects.create(buyer=buyer.username, recipient=buyer.username, sku=S.SUPPORTER_ITEM_SKU,
                                                months=months, xsolla_order_id=xid, sandbox=sandbox)
        if order.status != SupportOrder.STATUS_PENDING:
            return  # already handled (webhook retry, or the webhook and our check both saw it)
        order.status, order.paid_at, order.months, order.amount = SupportOrder.STATUS_PAID, timezone.now(), months, amount
        order.save(update_fields=["status", "paid_at", "months", "amount"])
        plural = "month" if months == 1 else "months"
        if order.recipient != order.buyer:
            message = f"{order.buyer} gifted you {months} {plural} of Qlute supporter! <3 You can upload a profile banner in your settings."
        else:
            message = f"Thank you for supporting Qlute! <3 You got {months} {plural} of supporter. You can upload a profile banner in your settings."
        service.grant_support(order.recipient, months, "xsolla", note=f"Xsolla order {xid}"[:300], message=message)


def mark_canceled(xid):
    """An Xsolla order was canceled / refunded: take the time back if it was granted."""
    if not xid:
        return
    with transaction.atomic():
        order = SupportOrder.objects.select_for_update().filter(xsolla_order_id=xid).first()
        if order is None or order.status == SupportOrder.STATUS_CANCELED:
            return
        was_paid = order.status == SupportOrder.STATUS_PAID
        order.status, order.canceled_at = SupportOrder.STATUS_CANCELED, timezone.now()
        order.save(update_fields=["status", "canceled_at"])
        if was_paid:
            service.take_support(order.recipient, order.months)


# ---------------------------------------------------------------- asking Xsolla directly (when no webhook came)

SEARCH_URL = "https://store.xsolla.com/api/v3/project/{project}/admin/order/search"
SYNC_EVERY = 5         # seconds between checks of the same order
SEARCH_LIMIT = 100     # recent orders fetched per check


def sync_orders(orders):
    """Looks our pending orders up in Xsolla's order list and settles the ones that were paid or canceled.
    Webhooks are the main signal; this catches payments whose webhook never arrived (not set up, blocked...)."""
    from django.core.cache import cache
    wanted = {}
    for o in orders:
        if o.status == SupportOrder.STATUS_PENDING and o.xsolla_order_id and cache.add(f"xsolla-sync-{o.id}", 1, SYNC_EVERY):
            wanted[int(o.xsolla_order_id)] = o
    if not wanted or not configured():
        return
    auth = base64.b64encode(f"{S.XSOLLA_PROJECT_ID}:{S.XSOLLA_API_KEY}".encode()).decode()
    try:
        res = requests.post(SEARCH_URL.format(project=S.XSOLLA_PROJECT_ID), json={"limit": SEARCH_LIMIT},
                            headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"}, timeout=10)
        found = res.json().get("orders") or [] if res.ok else []
        if not res.ok:
            log.error("xsolla order search failed (%s): %s", res.status_code, res.text[:300])
    except (requests.RequestException, ValueError) as e:
        log.error("xsolla order search failed: %s", e)
        return
    for x in found:
        xid = x.get("order_id")
        if xid not in wanted:
            continue
        status = x.get("status")
        if status in ("paid", "done"):
            price = (x.get("price") or {})
            mark_paid(xid, x.get("items"), x.get("mode") == "sandbox",
                      f'{price.get("amount", "")} {price.get("currency", "")}'.strip(), (x.get("user") or {}).get("id"))
        elif status in ("canceled", "refunded", "expired"):
            mark_canceled(xid)


# ---------------------------------------------------------------- the /support page

PERKS = [
    ("banner", "Profile banner", "Put any image behind your name on your profile, the friends list, the ranking podium and your header card."),
    ("heart", "Supporter badge", "A pink heart badge next to your name, so everyone knows you keep Qlute going."),
    ("server", "Keep Qlute free", "Every tag pays for servers and development. Qlute stays free and open source for everyone."),
]
ICONS = {
    "banner": '<path d="M3 5h18v14H3zM3 15l5-5 4 4 3-3 6 6"/><circle cx="16" cy="9" r="1.5"/>',
    "heart": '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 12 5.6 5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
    "server": '<path d="M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01"/>',
}


def support_page(request):
    from Chikara.views import BASE_DIR, STATIC_ROOT, header, checklogin
    username = request.COOKIES.get("username")
    login = checklogin(username, request.COOKIES.get("password"))
    me = username if login[0] and not login[1] else None
    html = header(request, customhead='<link rel="stylesheet" href="/static/css/support.css?v=2">',
                  title="Qlute supporter - support Qlute and get a profile banner",
                  description="Become a Qlute supporter: get a profile banner and a supporter badge, and help keep Qlute free.")

    status = ""
    if me:
        row = Supporter.objects.filter(username=me).first()
        if row is not None and row.active():
            until = "forever" if row.expires is None else "until " + row.expires.strftime("%-d %B %Y")
            status = f'<p class="sp-status on">&#9829; You\'re a supporter {until}. Thank you! Buying more adds to your time.</p>'

    perks = "".join(
        f'<li class="sp-perk"><span class="sp-perk-ico"><svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[i]}</svg></span>'
        f'<h3>{escape(t)}</h3><p>{escape(d)}</p></li>' for i, t, d in PERKS)
    cards = "".join(
        f'<label class="sp-plan"><input type="radio" name="sp-plan" value="{p["months"]}"{" checked" if n == 0 else ""}>'
        f'<span class="sp-plan-box"><span class="sp-months">{p["months"]}</span>'
        f'<span class="sp-unit">month{"" if p["months"] == 1 else "s"}</span>'
        f'<span class="sp-price">{escape(p["price"])}</span></span></label>'
        for n, p in enumerate(plans().values()))

    if not configured():
        buy = '<p class="sp-note">Supporter tags aren\'t on sale just yet. Check back soon &lt;3</p>'
    elif not me:
        buy = '<p class="sp-note">Log in (top right) to buy a supporter tag.</p>'
    else:
        buy = ('<div class="sp-gift"><label class="sp-check"><input type="checkbox" id="sp-gift-on"> Gift it to another player</label>'
               '<input type="text" id="sp-gift" maxlength="256" placeholder="Their username" hidden></div>'
               '<button type="button" class="sp-buy" id="sp-buy">Continue to payment</button>'
               '<p class="sp-msg" id="sp-msg" role="status"></p>'
               '<p class="sp-fine">Payments are handled by Xsolla. Supporter time starts right after payment and doesn\'t renew on its own.'
               + (' <strong>Test mode: use Xsolla\'s test cards; no real money is taken.</strong>' if S.XSOLLA_SANDBOX else '') + '</p>')

    html += f'''<div class="infoboxcontainer" id="support-page">
    <div class="infoboxtitle"><h1 class="page-title">supporter</h1></div>
    <section class="infobox sp-hero">
        <div class="sp-hero-text">
            <p class="sp-eyebrow">&#9829; Qlute supporter</p>
            <h2>Support Qlute, get a little something back</h2>
            <p>Qlute is made by one developer and is free for everyone. Supporter tags keep the servers running and
               unlock a few cosmetic perks. They never affect gameplay or rankings.</p>
            {status}
        </div>
    </section>
    <section class="infobox column sp-section sp-done" id="sp-done" hidden>
        <h2 class="sp-h" id="sp-done-title">Waiting for your payment…</h2>
        <p id="sp-done-text">This page updates on its own once Xsolla confirms it. It usually takes a few seconds.</p>
    </section>
    <section class="infobox column sp-section"><ul class="sp-perks">{perks}</ul></section>
    <section class="infobox column sp-section" id="sp-shop">
        <h2 class="sp-h">Pick a length</h2>
        <div class="sp-plans" role="radiogroup" aria-label="Supporter length">{cards}</div>
        {buy}
    </section>
</div>
<script src="/static/script/support.js?v=3" defer></script>'''
    html += open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/footer.html").read()
    return HttpResponse(html)
