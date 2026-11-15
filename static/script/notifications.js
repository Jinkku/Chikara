// The bell in the header: unread badge + dropdown list. Uses apiv2/notifications...
(function () {
    if (window.qluteNotificationsLoaded) return;
    window.qluteNotificationsLoaded = true;

    const POLL_MS = 60000;
    const ICONS = {
        friend: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM19 8v6M22 11h-6"/>',
        invite: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12ZM12 9v6M9 12h6"/>',
        dm: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12Z"/>',
        comment: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2ZM8 9h8M8 13h5"/>',
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
                a.innerHTML = `<span class="hb-ico"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[n.kind] || ICONS.comment}</svg></span>`;
                const body = document.createElement("span");
                body.className = "hb-body";
                body.textContent = n.count > 1 && n.kind === "dm" ? `${n.actor} sent you ${n.count} messages` : n.text;
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

        async function poll() {
            if (document.hidden || !panel.hidden) return;
            try { setBadge((await call("/count", false)).unread); } catch (e) { /* offline: try again later */ }
        }
        setInterval(poll, POLL_MS);
        document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
    });
})();
