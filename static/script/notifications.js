// The bell in the header: unread badge + dropdown list. Uses apiv2/notifications..., and listens on
// ws/v1/notify/ so new notifications show up (badge + a short toast) without reloading or clicking.
(function () {
    if (window.qluteNotificationsLoaded) return;
    window.qluteNotificationsLoaded = true;

    const POLL_MS = 60000;
    const ICONS = {
        friend: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM19 8v6M22 11h-6"/>',
        invite: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12ZM12 9v6M9 12h6"/>',
        dm: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12Z"/>',
        comment: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2ZM8 9h8M8 13h5"/>',
        supporter: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 12 5.6 5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
        moderation: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10ZM12 8v4M12 16h.01"/>',
        medal: '<circle cx="12" cy="15" r="6"/><path d="M8.5 10.2 5 2h4l3 6M15.5 10.2 19 2h-4l-1.6 3.3M12 12.5l.8 1.6 1.7.2-1.2 1.2.3 1.7-1.6-.8-1.6.8.3-1.7-1.2-1.2 1.7-.2Z"/>',
    };

    async function call(path, post) {
        const res = await fetch("/apiv2/notifications" + path, post ? { method: "POST", headers: { "X-Chikara": "1" } } : {});
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.error) throw new Error(data.reason || "Couldn't load notifications.");
        return data;
    }

    function ago(unix) {
        const s = Math.max(0, Date.now() / 1000 - unix);
        if (s < 60) return "just now";
        const units = [[31536000, "year"], [2592000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"]];
        for (const [n, name] of units) {
            if (s >= n) { const v = Math.floor(s / n); return `${v} ${name}${v === 1 ? "" : "s"} ago`; }
        }
    }

    function ready(fn) {
        if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn);
    }

    ready(() => {
        const button = document.getElementById("notif-button");
        const panel = document.getElementById("notif-panel");
        const badge = document.getElementById("notif-badge");
        const list = document.getElementById("notif-list");
        if (!button || !panel) return;

        function setBadge(n) {
            badge.textContent = n > 99 ? "99+" : String(n);
            badge.hidden = !n;
            button.setAttribute("aria-label", n ? `Notifications (${n} unread)` : "Notifications");
        }
        window.qluteSetUnread = setBadge;  // the chat page updates it after reading DMs

        function iconSvg(kind) {
            return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[kind] || ICONS.comment}</svg>`;
        }

        function label(n) {
            return n.count > 1 && n.kind === "dm" ? `${n.actor} sent you ${n.count} messages` : n.text;
        }

        function render(items) {
            list.textContent = "";
            if (!items.length) {
                list.innerHTML = '<li class="hb-empty">You\'re all caught up &lt;3</li>';
                return;
            }
            for (const n of items) {
                const li = document.createElement("li");
                li.className = "hb-item" + (n.read ? "" : " unread");
                const a = document.createElement("a");
                a.href = n.link || "#";
                a.innerHTML = `<span class="hb-ico">${iconSvg(n.kind)}</span>`;
                const body = document.createElement("span");
                body.className = "hb-body";
                body.textContent = label(n);
                const time = document.createElement("span");
                time.className = "hb-time";
                time.textContent = ago(n.created);
                body.appendChild(time);
                a.appendChild(body);
                if (!n.read) {
                    const dot = document.createElement("span");
                    dot.className = "hb-dot";
                    dot.setAttribute("aria-label", "unread");
                    a.appendChild(dot);
                }
                a.addEventListener("click", ev => {
                    if (n.read) return;
                    ev.preventDefault();
                    call("/read/" + n.id, true).catch(() => {}).finally(() => { location.href = a.href; });
                });
                li.appendChild(a);
                list.appendChild(li);
            }
        }

        async function load() {
            try {
                const data = await call("", false);
                setBadge(data.unread);
                render(data.notifications);
            } catch (e) {
                list.innerHTML = "";
                const li = document.createElement("li");
                li.className = "hb-empty";
                li.textContent = e.message;
                list.appendChild(li);
            }
        }

        function setOpen(open) {
            panel.hidden = !open;
            button.setAttribute("aria-expanded", open ? "true" : "false");
            if (open) load();
        }

        button.addEventListener("click", e => { e.stopPropagation(); setOpen(panel.hidden); });
        panel.addEventListener("click", e => e.stopPropagation());
        document.addEventListener("click", () => { if (!panel.hidden) setOpen(false); });
        document.addEventListener("keydown", e => {
            if (e.key === "Escape" && !panel.hidden) { setOpen(false); button.focus(); }
        });

        document.getElementById("notif-readall").addEventListener("click", async () => {
            await call("/read", true).catch(() => {});
            load();
        });
        document.getElementById("notif-clear").addEventListener("click", async () => {
            await call("/clear", true).catch(() => {});
            load();
        });

        // ---------------------------------------------------------------- toast

        const toasts = document.createElement("div");
        toasts.className = "hb-toasts";
        toasts.setAttribute("aria-live", "polite");
        document.body.appendChild(toasts);

        function toast(n) {
            // The chat page already shows the DM you're looking at.
            if (n.kind === "dm" && location.pathname === "/chat" && document.hasFocus() &&
                decodeURIComponent(location.hash) === "#dm=" + n.actor) return;
            const old = [...toasts.children].find(t => t.dataset.id === String(n.id));
            if (old) old.remove();
            const a = document.createElement("a");
            a.className = "hb-toast";
            a.dataset.id = n.id;
            a.dataset.kind = n.kind;
            a.href = n.link || "#";
            a.innerHTML = `<span class="hb-ico">${iconSvg(n.kind)}</span>`;
            const body = document.createElement("span");
            body.className = "hb-body";
            body.textContent = label(n);
            a.appendChild(body);
            a.addEventListener("click", ev => {
                ev.preventDefault();
                call("/read/" + n.id, true).catch(() => {}).finally(() => { location.href = a.href; });
            });
            toasts.prepend(a);
            while (toasts.children.length > 3) toasts.lastChild.remove();
            setTimeout(() => { a.classList.add("out"); setTimeout(() => a.remove(), 300); }, 7000);
        }

        // ---------------------------------------------------------------- live updates

        let ws = null, retry = 0, pingTimer = null, pollTimer = null;

        async function poll() {
            if (document.hidden || !panel.hidden) return;
            try { setBadge((await call("/count", false)).unread); } catch (e) { /* offline: try again later */ }
        }

        function startPolling() {
            if (!pollTimer) pollTimer = setInterval(poll, POLL_MS);
        }

        function stopPolling() {
            clearInterval(pollTimer);
            pollTimer = null;
        }

        function listen() {
            if (!("WebSocket" in window)) { startPolling(); return; }
            ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/v1/notify/");
            ws.onopen = () => {
                retry = 0;
                stopPolling();
                clearInterval(pingTimer);
                pingTimer = setInterval(() => { if (ws.readyState === 1) ws.send('{"op":"ping"}'); }, 25000);
            };
            ws.onmessage = ev => {
                let d;
                try { d = JSON.parse(ev.data); } catch (e) { return; }
                if (typeof d.unread === "number") setBadge(d.unread);
                if (d.op === "notification") {
                    toast(d.notification);
                    if (!panel.hidden) load();
                } else if (d.op === "unread" && !panel.hidden) {
                    load();
                }
            };
            ws.onclose = ev => {
                clearInterval(pingTimer);
                startPolling();             // keep the badge roughly right while we're disconnected
                if (ev.code === 4001) return; // logged out / not allowed: don't hammer the server
                setTimeout(listen, Math.min(60000, 2000 * 2 ** retry++));
            };
        }

        listen();
        document.addEventListener("visibilitychange", () => { if (!document.hidden && pollTimer) poll(); });
    });
})();
