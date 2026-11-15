// The website chat page (/chat). Speaks the game's chat protocol (online/PROTOCOL.md) over ws/v1/chat/,
// logged in with the site's cookies, so it's the same channels, rooms and DMs as in the game.
(function () {
    const app = document.getElementById("chat-app");
    if (!app) return;
    const me = app.dataset.me;
    const $ = id => document.getElementById(id);

    const state = {
        channels: [],          // [{id, title}]
        rooms: new Map(),      // id -> {id, title, owner, members, dm, with}
        lines: new Map(),      // id -> [{author, text, ts} | {notice}]
        unread: new Map(),     // id -> count
        invites: new Map(),    // room id -> {room, title, from}
        online: new Set(),
        active: null,
        pendingDm: null,       // a name from #dm=NAME, opened once we're connected
    };
    let ws = null, pingTimer = null, retry = 0, fatal = false;

    const m = location.hash.match(/^#dm=(.+)$/);
    if (m) state.pendingDm = decodeURIComponent(m[1]);

    // ---------------------------------------------------------------- socket

    function connect() {
        setStatus("Connecting…");
        ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/v1/chat/");
        ws.onopen = () => {
            retry = 0;
            clearInterval(pingTimer);
            pingTimer = setInterval(() => send({ op: "ping" }), 20000);
        };
        ws.onmessage = ev => {
            let data;
            try { data = JSON.parse(ev.data); } catch (e) { return; }
            const handler = handlers[data.op];
            if (handler) handler(data);
        };
        ws.onclose = ev => {
            clearInterval(pingTimer);
            setComposer(false);
            if (fatal || ev.code === 4001) return;
            if (ev.code === 4002) { connect(); return; }
            const wait = Math.min(30000, 1000 * 2 ** retry++);
            setStatus("Disconnected. Reconnecting…", true);
            setTimeout(connect, wait);
        };
    }

    function send(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(obj)); return true; }
        return false;
    }

    const handlers = {
        welcome(d) {
            state.channels = d.channels;
            state.rooms.clear();
            d.rooms.forEach(r => state.rooms.set(r.id, r));
            state.invites.clear();
            d.invites.forEach(i => state.invites.set(i.room, i));
            state.online = new Set(d.online);
            state.online.add(me);
            setStatus("Connected");
            if (!state.active || !(isChannel(state.active) || state.rooms.has(state.active))) state.active = d.channels[0] && d.channels[0].id;
            renderAll();
            setComposer(true);
            if (state.pendingDm) { send({ op: "dm_open", user: state.pendingDm }); state.pendingDm = null; }
        },
        history(d) {
            state.lines.set(d.channel, d.lines.slice());
            if (d.channel === state.active) renderMessages();
        },
        msg(d) {
            push(d.channel, { author: d.author, text: d.text, ts: d.ts, supporter: !!d.supporter });
            if (d.channel !== state.active || document.hidden) {
                if (d.author !== me) state.unread.set(d.channel, (state.unread.get(d.channel) || 0) + 1);
                renderLists();
            } else if (state.rooms.get(d.channel) && state.rooms.get(d.channel).dm && d.author !== me) {
                readDm(state.rooms.get(d.channel));
            }
        },
        notice(d) { push(d.channel, { notice: d.text, ts: Date.now() }); },
        room(d) {
            state.rooms.set(d.room.id, d.room);
            if (d.focus) select(d.room.id);
            else if (d.room.id === state.active) renderHead();
            renderLists();
        },
        left(d) {
            state.rooms.delete(d.room);
            state.lines.delete(d.room);
            state.unread.delete(d.room);
            if (state.active === d.room) select(state.channels[0] && state.channels[0].id);
            renderLists();
        },
        invite(d) { state.invites.set(d.room, d); renderInvites(); },
        invite_gone(d) { state.invites.delete(d.room); renderInvites(); },
        presence(d) {
            if (d.online) state.online.add(d.user); else state.online.delete(d.user);
            renderOnline();
            renderLists();
        },
        online_list(d) { state.online = new Set(d.online); renderOnline(); },
        error(d) {
            if (d.fatal) {
                fatal = true;
                setStatus("Can't connect", true);
                showError(d.text);
                return;
            }
            showError(d.text);
        },
        restricted(d) {
            setStatus("Restricted", true);
            showError(d.text || "Your account is restricted, so you can't chat right now.");
            setComposer(false);
        },
        unrestricted(d) { showError(d.text); },
    };

    // ---------------------------------------------------------------- state helpers

    function isChannel(id) { return state.channels.some(c => c.id === id); }

    function push(channel, line) {
        if (!state.lines.has(channel)) state.lines.set(channel, []);
        const lines = state.lines.get(channel);
        lines.push(line);
        if (lines.length > 300) lines.splice(0, lines.length - 300);
        if (channel === state.active) appendLine(line, true);
    }

    function select(id) {
        if (!id) return;
        state.active = id;
        state.unread.delete(id);
        const room = state.rooms.get(id);
        if (room && room.dm) {
            readDm(room);
            history.replaceState(null, "", "#dm=" + encodeURIComponent(room.with));
        } else if (location.hash) {
            history.replaceState(null, "", location.pathname);
        }
        app.classList.add("ct-show-main");
        renderLists();
        renderHead();
        renderMessages();
        if (window.matchMedia("(min-width: 761px)").matches) $("ct-input").focus();
    }

    function readDm(room) {
        fetch("/apiv2/notifications/read/dm/" + encodeURIComponent(room.with), { method: "POST", headers: { "X-Chikara": "1" } })
            .then(r => r.json()).then(d => { if (window.qluteSetUnread && typeof d.unread === "number") window.qluteSetUnread(d.unread); })
            .catch(() => {});
    }

    // ---------------------------------------------------------------- rendering

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }

    function setStatus(text, bad) {
        const s = $("ct-status");
        s.textContent = text;
        s.classList.toggle("bad", !!bad);
    }

    function setComposer(on) {
        $("ct-input").disabled = !on;
        $("ct-send").disabled = !on;
    }

    let errorTimer = null;
    function showError(text) {
        const e = $("ct-error");
        e.textContent = text;
        e.hidden = false;
        clearTimeout(errorTimer);
        if (!fatal) errorTimer = setTimeout(() => { e.hidden = true; }, 6000);
    }

    function renderAll() { renderLists(); renderInvites(); renderOnline(); renderHead(); renderMessages(); }

    function item(id, label, opts = {}) {
        const li = el("li");
        const b = el("button", "ct-item" + (id === state.active ? " active" : ""));
        b.type = "button";
        if (id === state.active) b.setAttribute("aria-current", "true");
        if (opts.dot !== undefined) b.appendChild(el("span", "ct-presence" + (opts.dot ? " on" : "")));
        else b.appendChild(el("span", "ct-hash", opts.prefix || "#"));
        b.appendChild(el("span", "ct-name", label));
        const n = state.unread.get(id);
        if (n) b.appendChild(el("span", "ct-unread", n > 99 ? "99+" : String(n)));
        b.addEventListener("click", () => select(id));
        li.appendChild(b);
        return li;
    }

    function renderLists() {
        const ch = $("ct-channels"), rooms = $("ct-rooms"), dms = $("ct-dms");
        ch.textContent = rooms.textContent = dms.textContent = "";
        state.channels.forEach(c => ch.appendChild(item(c.id, c.title.replace(/^#/, ""))));
        const all = [...state.rooms.values()];
        all.filter(r => !r.dm).sort((a, b) => a.title.localeCompare(b.title))
            .forEach(r => rooms.appendChild(item(r.id, r.title, { prefix: "🔒" })));
        all.filter(r => r.dm).forEach(r => dms.appendChild(item(r.id, r.with, { dot: state.online.has(r.with) })));
        $("ct-rooms-empty").hidden = rooms.children.length > 0;
        $("ct-dms-empty").hidden = dms.children.length > 0;
        const total = [...state.unread.values()].reduce((a, b) => a + b, 0);
        document.title = (total ? `(${total}) ` : "") + "Qlute - chat";
    }

    function renderInvites() {
        const ul = $("ct-invites");
        ul.textContent = "";
        for (const inv of state.invites.values()) {
            const li = el("li", "ct-invite-card");
            const p = el("p");
            p.append(el("strong", "", inv.from), " invited you to ", el("strong", "", inv.title));
            li.appendChild(p);
            const row = el("div", "ct-invite-row");
            const yes = el("button", "ct-btn primary", "Join");
            const no = el("button", "ct-btn", "Decline");
            yes.type = no.type = "button";
            yes.addEventListener("click", () => send({ op: "accept", room: inv.room }));
            no.addEventListener("click", () => send({ op: "decline", room: inv.room }));
            row.append(yes, no);
            li.appendChild(row);
            ul.appendChild(li);
        }
        $("ct-invites-group").hidden = state.invites.size === 0;
    }

    function renderOnline() {
        const ul = $("ct-online");
        ul.textContent = "";
        const names = [...state.online].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
        $("ct-online-count").textContent = names.length ? String(names.length) : "";
        names.slice(0, 200).forEach(name => {
            const li = el("li");
            const b = el("button", "ct-item");
            b.type = "button";
            b.appendChild(el("span", "ct-presence on"));
            b.appendChild(el("span", "ct-name", name + (name === me ? " (you)" : "")));
            if (name !== me) {
                b.title = "Message " + name;
                b.addEventListener("click", () => send({ op: "dm_open", user: name }));
            } else b.disabled = true;
            li.appendChild(b);
            ul.appendChild(li);
        });
    }

    function renderHead() {
        const id = state.active;
        const room = state.rooms.get(id);
        const title = $("ct-title"), sub = $("ct-subtitle");
        title.textContent = "";
        $("ct-invite").hidden = true;
        $("ct-leave").hidden = true;
        if (!id) { title.innerHTML = "&nbsp;"; sub.textContent = ""; return; }
        if (room && room.dm) {
            const a = el("a", "", room.with);
            a.href = "/user/" + encodeURIComponent(room.with);
            title.appendChild(a);
            sub.textContent = state.online.has(room.with) ? "Online" : "Offline";
            $("ct-leave").hidden = false;
            $("ct-leave").textContent = "Close";
        } else if (room) {
            title.textContent = "🔒 " + room.title;
            sub.textContent = `${room.members.length} member${room.members.length === 1 ? "" : "s"}: ${room.members.join(", ")}`;
            $("ct-invite").hidden = false;
            $("ct-leave").hidden = false;
            $("ct-leave").textContent = "Leave";
        } else {
            title.textContent = id;
            sub.textContent = "Public channel · everyone online can see it";
        }
        $("ct-input").placeholder = room && room.dm ? `Message ${room.with}…` : `Message ${room ? room.title : id}…`;
    }

    function fmtTime(ts) {
        const d = new Date(ts), now = new Date();
        const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return d.toDateString() === now.toDateString() ? time : d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + time;
    }

    let lastAuthor = null, lastTs = 0;

    function appendLine(line, live) {
        const box = $("ct-messages");
        const stick = !live || box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        const empty = box.querySelector(".ct-empty");
        if (empty) empty.remove();
        if (line.notice) {
            box.appendChild(el("div", "ct-notice", line.notice));
            lastAuthor = null;
        } else {
            const grouped = line.author === lastAuthor && line.ts - lastTs < 5 * 60 * 1000;
            const row = el("div", "ct-msg" + (grouped ? " grouped" : "") + (line.author === me ? " mine" : ""));
            if (!grouped) {
                const head = el("div", "ct-msg-head");
                const a = el("a", "ct-author" + (line.supporter ? " sup" : ""), line.author);
                a.href = "/user/" + encodeURIComponent(line.author);
                if (line.supporter) {
                    a.title = "Qlute supporter";
                    a.appendChild(el("span", "ct-sup-heart", "\u2665"));
                }
                const t = el("time", "ct-time", fmtTime(line.ts));
                t.dateTime = new Date(line.ts).toISOString();
                head.append(a, t);
                row.appendChild(head);
            }
            row.appendChild(el("div", "ct-text", line.text));
            box.appendChild(row);
            lastAuthor = line.author;
            lastTs = line.ts;
        }
        if (stick) box.scrollTop = box.scrollHeight;
    }

    function renderMessages() {
        const box = $("ct-messages");
        box.textContent = "";
        lastAuthor = null;
        const lines = state.lines.get(state.active) || [];
        if (!lines.length) box.appendChild(el("p", "ct-empty", "No messages yet. Say hi!"));
        lines.forEach(l => appendLine(l, false));
        box.scrollTop = box.scrollHeight;
    }

    // ---------------------------------------------------------------- controls

    const input = $("ct-input");
    function grow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
    input.addEventListener("input", grow);
    input.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("ct-compose").requestSubmit(); }
    });
    $("ct-compose").addEventListener("submit", e => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || !state.active) return;
        if (send({ op: "msg", channel: state.active, text: text.slice(0, 500) })) { input.value = ""; grow(); }
        else showError("Not connected. Trying again…");
    });

    document.querySelectorAll(".ct-add").forEach(b => b.addEventListener("click", () => {
        const form = $(b.dataset.form);
        form.hidden = !form.hidden;
        if (!form.hidden) form.querySelector("input").focus();
    }));
    function inlineForm(id, fn) {
        const form = $(id);
        form.addEventListener("submit", e => {
            e.preventDefault();
            const field = form.querySelector("input");
            const value = field.value.trim();
            if (!value) return;
            if (fn(value) !== false) { field.value = ""; if (id !== "ct-invite") form.hidden = true; }
        });
    }
    inlineForm("ct-new-room", title => send({ op: "create", title }));
    inlineForm("ct-new-dm", user => send({ op: "dm_open", user }));
    inlineForm("ct-invite", user => send({ op: "invite", room: state.active, user }));
    $("ct-leave").addEventListener("click", () => {
        const room = state.rooms.get(state.active);
        if (!room) return;
        if (!room.dm && !confirm(`Leave "${room.title}"? You'll need a new invite to come back.`)) return;
        send({ op: "leave", room: room.id });
    });
    $("ct-back").addEventListener("click", () => app.classList.remove("ct-show-main"));

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && state.active && state.unread.has(state.active)) {
            state.unread.delete(state.active);
            const room = state.rooms.get(state.active);
            if (room && room.dm) readDm(room);
            renderLists();
        }
    });

    connect();
})();
