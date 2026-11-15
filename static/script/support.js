// The supporter page (/support): buy a supporter tag through Xsolla (moderation/payments.py).
// Checkout opens in Xsolla's Pay Station popup (their embed script) over this page; if that script can't load
// we fall back to sending the player to the Pay Station page, which brings them back to /support?order=ID.
(function () {
    const $ = id => document.getElementById(id);
    const WIDGET = "https://cdn.xsolla.net/payments-bucket-prod/embed/1.5.0/widget.min.js";

    function esc(s) {
        return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    // ---------------------------------------------------------------- waiting for the payment to be confirmed
    let watching = null;
    function watch(orderId, opts = {}) {
        const box = $("sp-done"), title = $("sp-done-title"), text = $("sp-done-text");
        const mine = watching = String(orderId);
        box.hidden = false;
        box.classList.remove("ok");
        title.textContent = opts.closed ? "Checking your order…" : "Waiting for your payment…";
        text.textContent = "This updates on its own once Xsolla confirms it. It usually takes a few seconds.";
        box.scrollIntoView({ block: "center", behavior: "smooth" });
        let tries = 0;
        const check = async () => {
            if (watching !== mine) return;
            tries++;
            try {
                const res = await fetch("/apiv2/support/order/" + encodeURIComponent(orderId));
                const o = await res.json();
                if (!res.ok) throw new Error(o.error || "Couldn't find that order.");
                if (o.status === "paid") {
                    box.classList.add("ok");
                    title.textContent = o.gift ? `Gift sent to ${o.recipient}! Thank you <3` : "You're a supporter now! Thank you <3";
                    text.innerHTML = o.gift ? `${esc(o.recipient)} got ${o.months} month${o.months === 1 ? "" : "s"} of supporter.`
                        : `You got ${o.months} month${o.months === 1 ? "" : "s"} of supporter. <a href="/settings">Upload your profile banner</a>.`;
                    return;
                }
                if (o.status === "canceled") {
                    title.textContent = "That order was canceled";
                    text.textContent = "No supporter time was added. If you were charged, Xsolla will refund it.";
                    return;
                }
            } catch (e) {
                title.textContent = "Couldn't check your order";
                text.textContent = e.message;
                return;
            }
            // Closing the popup without paying: stop after a short while instead of waiting forever.
            const limit = opts.closed ? 4 : 40;
            if (tries < limit) setTimeout(check, tries < 10 ? 3000 : 10000);
            else if (opts.closed) box.hidden = true;
            else text.textContent = "Still waiting on Xsolla. If you completed the payment, your supporter time will show up shortly; you'll get a notification.";
        };
        check();
    }

    // Back from the Pay Station page (fallback flow): /support?order=ID
    const back = new URLSearchParams(location.search).get("order");
    if (back && /^\d+$/.test(back)) watch(back);

    // ---------------------------------------------------------------- the popup
    let widgetLoading = null;
    function loadWidget() {
        if (window.XPayStationWidget) return Promise.resolve(window.XPayStationWidget);
        if (!widgetLoading) {
            widgetLoading = new Promise((resolve, reject) => {
                const s = document.createElement("script");
                s.src = WIDGET;
                s.async = true;
                s.onload = () => window.XPayStationWidget ? resolve(window.XPayStationWidget) : reject(new Error("no widget"));
                s.onerror = () => { widgetLoading = null; reject(new Error("widget blocked")); };
                document.head.appendChild(s);
                setTimeout(() => reject(new Error("widget timeout")), 8000);
            });
        }
        return widgetLoading;
    }
    const buy = $("sp-buy");
    if (buy) loadWidget().catch(() => {});  // warm it up so the popup opens instantly

    let current = null, hooked = false;   // the checkout that's open; handlers are added once per page
    function openPopup(W, data) {
        const ev = W.eventTypes || {};
        current = { order: data.order, paid: false };
        // payment_url: we already have the Pay Station 4 link (the script would otherwise build an old paystation2 one).
        W.init({
            payment_url: data.url,
            sandbox: !!data.sandbox,
            lightbox: {
                width: "740px", height: "760px", zIndex: 3000, overlayOpacity: ".75", overlayBackground: "#1a1620",
                contentBackground: "#2a242f", closeByClick: false, spinner: "xsolla",
            },
            childWindow: { target: "_blank" },
        });
        if (!hooked) {
            hooked = true;
            W.on(ev.STATUS_DONE || "status-done", () => { if (current && !current.paid) { current.paid = true; watch(current.order); } });
            W.on(ev.CLOSE || "close", () => {
                buy.disabled = false;
                msg.textContent = "";
                // They may have paid and closed before the status page: check a few times either way.
                if (current && !current.paid) watch(current.order, { closed: true });
            });
        }
        W.open();
    }

    // ---------------------------------------------------------------- buying
    if (!buy) return;
    const giftOn = $("sp-gift-on"), gift = $("sp-gift"), msg = $("sp-msg");
    giftOn.addEventListener("change", () => {
        gift.hidden = !giftOn.checked;
        if (giftOn.checked) gift.focus();
        buy.textContent = giftOn.checked ? "Continue to payment (gift)" : "Continue to payment";
    });
    buy.addEventListener("click", async () => {
        const plan = document.querySelector('input[name="sp-plan"]:checked');
        if (!plan) { msg.textContent = "Pick a length first."; return; }
        const to = giftOn.checked ? gift.value.trim() : "";
        if (giftOn.checked && !to) { msg.textContent = "Type who the gift is for."; gift.focus(); return; }
        buy.disabled = true;
        msg.className = "sp-msg";
        msg.textContent = "Opening checkout…";
        let data;
        try {
            const res = await fetch("/apiv2/support/checkout", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Chikara": "1" },
                body: JSON.stringify({ plan: plan.value, gift: to }),
            });
            data = await res.json().catch(() => ({}));
            if (!res.ok || !data.url) throw new Error(data.error || "Something went wrong. Try again?");
        } catch (e) {
            msg.className = "sp-msg bad";
            msg.textContent = e.message;
            buy.disabled = false;
            return;
        }
        try {
            openPopup(await loadWidget(), data);
            msg.textContent = "Checkout is open. Finish paying in the Xsolla window.";
        } catch (e) {
            location.href = data.url;  // popup script blocked (ad blocker...): full-page checkout instead
        }
    });
})();
