// The supporter page (/support): buy a supporter tag through Xsolla (moderation/payments.py).
(function () {
    const $ = id => document.getElementById(id);

    // ---------------------------------------------------------------- back from Xsolla: /support?order=ID
    const orderId = new URLSearchParams(location.search).get("order");
    if (orderId && /^\d+$/.test(orderId)) {
        const box = $("sp-done"), title = $("sp-done-title"), text = $("sp-done-text");
        box.hidden = false;
        box.scrollIntoView({ block: "center" });
        let tries = 0;
        const check = async () => {
            tries++;
            try {
                const res = await fetch("/apiv2/support/order/" + orderId);
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
                    text.textContent = "No supporter time was added. If you were charged, it will be refunded by Xsolla.";
                    return;
                }
            } catch (e) {
                title.textContent = "Couldn't check your order";
                text.textContent = e.message;
                return;
            }
            if (tries < 40) setTimeout(check, tries < 10 ? 3000 : 10000);
            else text.textContent = "Still waiting on Xsolla. If you completed the payment, your supporter time will show up shortly; you'll get a notification.";
        };
        check();
    }

    function esc(s) {
        return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    // ---------------------------------------------------------------- buying
    const buy = $("sp-buy");
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
        try {
            const res = await fetch("/apiv2/support/checkout", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Chikara": "1" },
                body: JSON.stringify({ sku: plan.value, gift: to }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.url) throw new Error(data.error || "Something went wrong. Try again?");
            location.href = data.url;
        } catch (e) {
            msg.className = "sp-msg bad";
            msg.textContent = e.message;
            buy.disabled = false;
        }
    });
})();
