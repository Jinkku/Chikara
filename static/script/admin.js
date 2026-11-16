// Admin panel (/admin). Talks to /apiv2/mod/... with the login cookies; POSTs carry "X-Chikara: 1".
// Views live in the URL hash: #reports, #reports=closed, #players, #user=NAME, #bans, #bans=all, #team.
(function () {
    const view = document.getElementById("admin-view");
    const hint = document.getElementById("admin-hint");
    const tabs = document.querySelectorAll("#admin-tabs .catalog-tab");
    const openCount = document.getElementById("open-count");
    let me = null;
    let render = 0; // bumps on every navigation so late replies don't draw over a newer view

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const userLink = n => `<a href="#user=${encodeURIComponent(n)}">${esc(n)}</a>`;
    function when(ts) {
        if (!ts) return "never";
        const d = new Date(ts * 1000);
        let t = Math.round((Date.now() - d) / 1000);
        const future = t < 0; t = Math.abs(t);
        const units = [[86400, "day"], [3600, "hour"], [60, "minute"], [1, "second"]];
        let txt = "just now";
        for (const [n, u] of units) if (t >= n) { const x = Math.floor(t / n); txt = `${x} ${u}${x === 1 ? "" : "s"}`; break; }
        if (txt !== "just now") txt = future ? "in " + txt : txt + " ago";
        return `<span title="${esc(d.toLocaleString())}">${txt}</span>`;
    }

    async function api(path, data) {
        const opts = data === undefined ? {} : {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Chikara": "1" },
            body: JSON.stringify(data),
        };
        const res = await fetch("/apiv2/mod/" + path, opts);
        let json = {};
        try { json = await res.json(); } catch (e) { }
        if (!res.ok) throw new Error(json.error || "The server said " + res.status);
        return json;
    }

    // Multipart POST (file uploads).
    async function upload(path, fields) {
        const form = new FormData();
        for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) form.append(k, v);
        const res = await fetch("/apiv2/mod/" + path, { method: "POST", headers: { "X-Chikara": "1" }, body: form });
        let json = {};
        try { json = await res.json(); } catch (e) { }
        if (!res.ok) throw new Error(json.error || (res.status === 413 ? "That file is too big for the server." : "The server said " + res.status));
        return json;
    }

    function imageSize(file) {
        return new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file isn't an image we can read.")); };
            img.src = url;
        });
    }

    // Notice images: keep the upload under the web server's 1 MB limit (shrink to 2048px, re-encode as WebP).
    async function fitNotice(file) {
        const img = await imageSize(file);
        const scale = Math.min(1, 2048 / Math.max(img.naturalWidth, img.naturalHeight));
        if (file.size < 900 * 1024 && scale === 1) return file;
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        for (const q of [0.92, 0.8, 0.65]) {
            const blob = await new Promise(r => canvas.toBlob(r, "image/webp", q));
            if (blob && blob.size < 950 * 1024) return new File([blob], "notice.webp", { type: "image/webp" });
        }
        throw new Error("That image is too big even after shrinking it. Try a smaller one.");
    }

    function route() {
        const [tab, arg] = decodeURIComponent(location.hash.slice(1) || "reports").split(/=(.*)/s);
        const mine = ++render;
        tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === (tab === "user" ? "players" : tab)));
        view.innerHTML = "";
        hint.style.display = "";
        hint.textContent = "Loading...";
        const views = { scores: showScores, supporters: showSupporters, news: showNews, claims: showClaims, reports: showReports, players: showPlayers, user: showUser, bans: showBans, team: showTeam, notices: showNotices, borders: showBorders };
        (views[tab] || showReports)(arg || "", mine).catch(err => {
            if (mine === render) hint.textContent = err.message;
        });
    }
    const current = mine => mine === render;
    function done(text) { hint.textContent = text || ""; hint.style.display = text ? "" : "none"; }

    async function refreshMe() {
        me = await api("me");
        openCount.textContent = me.open_reports ? me.open_reports : "";
        document.getElementById("claim-count").textContent = me.pending_claims ? me.pending_claims : "";
        document.querySelectorAll(".admin-only").forEach(t => t.hidden = !me.admin);
    }

    // ---------------------------------------------------------------- reports
    async function showReports(status, mine) {
        status = status || "open";
        let page = 0;
        view.innerHTML = `
            <div class="adm-bar">
                <div class="catalog-tabs">
                    <button class="catalog-tab ${status === "open" ? "active" : ""}" data-s="open">Open</button>
                    <button class="catalog-tab ${status === "closed" ? "active" : ""}" data-s="closed">Closed</button>
                </div>
            </div>
            <div class="adm-list" id="list"></div>
            <div class="adm-more" id="more"></div>`;
        view.querySelectorAll("[data-s]").forEach(b => b.onclick = () => location.hash = "reports=" + b.dataset.s);
        const list = view.querySelector("#list"), more = view.querySelector("#more");
        async function load() {
            const data = await api(`reports?status=${status}&page=${page}`);
            if (!current(mine)) return;
            openCount.textContent = data.open || "";
            data.results.forEach(r => list.appendChild(reportCard(r, () => { refreshMe(); route(); })));
            page++;
            more.innerHTML = data.results.length === data.page_size ? `<button class="adm-btn">Load more</button>` : "";
            if (more.firstChild) more.firstChild.onclick = load;
            done(list.children.length ? "" : status === "open" ? "No open reports. Nice and quiet ^-^" : "No closed reports yet.");
        }
        await load();
    }

    function reportCard(r, changed) {
        const card = document.createElement("div");
        card.className = "adm-card" + (r.status === "open" ? "" : " closed");
        const statusPill = r.status === "open" ? `<span class="adm-pill yellow">open</span>`
            : `<span class="adm-pill ${r.status === "resolved" ? "green" : ""}">${esc(r.status)}</span>`;
        card.innerHTML = `
            <div class="adm-head">
                <span class="who">${userLink(r.target)} ${r.target_restricted ? `<span class="adm-pill red">restricted</span>` : ""}
                    ${r.target_open_reports > 1 ? `<span class="adm-pill purple">${r.target_open_reports} open reports</span>` : ""}</span>
                <span>${statusPill} <span class="adm-pill">${esc(r.category_text)}</span></span>
            </div>
            <div class="adm-meta">#${r.id} reported by ${userLink(r.reporter)} ${when(r.created)} from the ${r.source === "game" ? "game" : "website"}</div>
            <p class="adm-text">${esc(r.details)}</p>
            ${r.context ? `<div class="adm-meta">Context: ${esc(r.context)}</div>` : ""}
            ${r.status !== "open" ? `<div class="adm-meta">${esc(r.status)} by ${esc(r.handled_by)} ${when(r.handled_at)}${r.note ? ": " + esc(r.note) : ""}</div>` : ""}
            <div class="adm-actions"></div>
            <p class="adm-msg"></p>`;
        const actions = card.querySelector(".adm-actions"), msg = card.querySelector(".adm-msg");
        function button(text, cls, fn) {
            const b = document.createElement("button");
            b.className = "adm-btn " + cls;
            b.textContent = text;
            b.onclick = async () => {
                b.disabled = true;
                try { await fn(); } catch (err) { msg.textContent = err.message; b.disabled = false; }
            };
            actions.appendChild(b);
        }
        button("Open player", "", async () => location.hash = "user=" + encodeURIComponent(r.target));
        if (r.status === "open") {
            button("Ban...", "danger", async () => location.hash = `user=${encodeURIComponent(r.target)}&report=${r.id}`);
            button("Resolve", "good", async () => {
                const note = prompt("What was done? (optional)", "");
                if (note === null) throw new Error("");
                await api(`report/${r.id}/close`, { status: "resolved", note });
                changed();
            });
            button("Dismiss", "", async () => {
                const note = prompt("Why dismiss it? (optional)", "");
                if (note === null) throw new Error("");
                await api(`report/${r.id}/close`, { status: "dismissed", note });
                changed();
            });
        } else {
            button("Reopen", "", async () => { await api(`report/${r.id}/reopen`, {}); changed(); });
        }
        return card;
    }

    // ---------------------------------------------------------------- news (mods and admins)
    async function showNews(arg, mine) {
        const data = await api("news");
        if (!current(mine)) return;
        if (arg) return newsEditor(arg === "new" ? null : data.results.find(p => String(p.id) === arg), mine);
        view.innerHTML = `
            <div class="adm-bar"><button class="adm-btn good" id="new-post">+ Write a post</button>
                <a class="adm-btn" href="/news" target="_blank">Open the news page</a></div>
            <div class="adm-list" id="list"></div>`;
        view.querySelector("#new-post").onclick = () => location.hash = "news=new";
        const list = view.querySelector("#list");
        data.results.forEach(p => {
            const card = document.createElement("div");
            card.className = "adm-card" + (p.published ? "" : " closed");
            card.innerHTML = `
                <div class="adm-head"><span class="who">${esc(p.title)}</span>
                    <span>${p.pinned ? `<span class="adm-pill purple">pinned</span>` : ""}
                    ${p.published ? `<span class="adm-pill green">published</span>` : `<span class="adm-pill yellow">draft</span>`}</span></div>
                <div class="adm-meta">#${p.id} by ${userLink(p.author)} ${when(p.created)}${p.edited_by ? ` &middot; last edited by ${esc(p.edited_by)} ${when(p.updated)}` : ""}</div>
                <div class="adm-actions"><a class="adm-btn" href="#news=${p.id}">Edit</a><a class="adm-btn" href="/news/${p.id}" target="_blank">View</a></div>`;
            list.appendChild(card);
        });
        done(data.results.length ? "" : "No posts yet. Write the first one!");
    }

    function newsEditor(p, mine) {
        if (p === undefined) { done("That post doesn't exist."); return; }
        p = p || { title: "", summary: "", body: "", image: "", published: true, pinned: false };
        view.innerHTML = `
            <div class="adm-bar"><a class="adm-btn" href="#news">&lsaquo; All posts</a>
                ${p.id ? `<a class="adm-btn" href="/news/${p.id}" target="_blank">View post</a>` : ""}</div>
            <div class="adm-form nw-editor">
                <label for="nw-title">Title</label><input type="text" id="nw-title" maxlength="200" value="${esc(p.title)}">
                <label for="nw-summary">Summary <span class="adm-meta">(optional, one line shown on the news list; otherwise the start of the post)</span></label>
                <input type="text" id="nw-summary" maxlength="300" value="${esc(p.summary)}">
                <label for="nw-image">Cover image link <span class="adm-meta">(optional, https://...)</span></label>
                <input type="text" id="nw-image" maxlength="500" value="${esc(p.image)}" placeholder="https://">
                <label for="nw-body">Post <span class="adm-meta">(BBCode, like profile bios)</span></label>
                <div class="adm-row nw-tools">
                    ${[["b", "<b>B</b>"], ["i", "<i>I</i>"], ["u", "<u>U</u>"], ["heading", "Heading"], ["url", "Link"], ["img", "Image"],
                       ["list", "List"], ["quote", "Quote"], ["notice", "Notice"], ["centre", "Centre"]]
                        .map(([t, l]) => `<button type="button" class="adm-btn" data-tag="${t}">${l}</button>`).join("")}
                </div>
                <textarea id="nw-body" rows="16" maxlength="20000">${esc(p.body)}</textarea>
                <div class="adm-row">
                    <label><input type="checkbox" id="nw-published" ${p.published ? "checked" : ""}> Published (untick to keep it as a draft)</label>
                    <label><input type="checkbox" id="nw-pinned" ${p.pinned ? "checked" : ""}> Pinned to the top</label>
                </div>
                <div class="adm-row">
                    <button type="button" class="adm-btn good" id="nw-save">${p.id ? "Save changes" : "Post it"}</button>
                    <button type="button" class="adm-btn" id="nw-preview">Preview</button>
                    ${p.id ? `<button type="button" class="adm-btn danger" id="nw-delete">Delete</button>` : ""}
                </div>
                <p class="adm-msg" id="nw-msg"></p>
            </div>
            <div class="adm-section" id="nw-preview-title" hidden>Preview</div>
            <div class="adm-card bb nw-preview" id="nw-preview-box" hidden></div>`;
        const $ = id => view.querySelector("#" + id);
        const body = $("nw-body"), msg = $("nw-msg");
        view.querySelectorAll("[data-tag]").forEach(b => b.onclick = () => {
            const t = b.dataset.tag, s = body.selectionStart, e = body.selectionEnd, sel = body.value.slice(s, e);
            const inner = t === "list" ? (sel ? sel.split("\n").map(l => "[*]" + l).join("\n") : "[*]") : sel;
            const open = t === "url" ? "[url=https://]" : `[${t}]`, close = `[/${t}]`;
            body.setRangeText(open + (t === "list" ? "\n" : "") + inner + (t === "list" ? "\n" : "") + close, s, e, "end");
            body.focus();
        });
        const values = () => ({ id: p.id, title: $("nw-title").value, summary: $("nw-summary").value, image: $("nw-image").value,
            body: body.value, published: $("nw-published").checked, pinned: $("nw-pinned").checked });
        $("nw-preview").onclick = async () => {
            try {
                const r = await api("news/preview", { body: body.value });
                $("nw-preview-box").innerHTML = `<h2>${esc($("nw-title").value)}</h2>` + r.html;
                $("nw-preview-box").hidden = $("nw-preview-title").hidden = false;
            } catch (err) { msg.textContent = err.message; }
        };
        $("nw-save").onclick = async e => {
            e.target.disabled = true; msg.textContent = "Saving...";
            try {
                const r = await api("news/save", values());
                msg.textContent = "Saved!";
                p = r.post;
                if (location.hash !== "#news=" + p.id) location.hash = "news=" + p.id; else e.target.disabled = false;
            } catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
        if ($("nw-delete")) $("nw-delete").onclick = async e => {
            if (!confirm(`Delete "${p.title}"? This can't be undone.`)) return;
            e.target.disabled = true;
            try { await api("news/delete", { id: p.id }); location.hash = "news"; }
            catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
        done("");
    }

    // ---------------------------------------------------------------- beatmap claims (osu! creators asking to own their set)
    async function showClaims(status, mine) {
        status = status || "pending";
        let page = 0;
        view.innerHTML = `
            <div class="adm-bar">
                <div class="catalog-tabs">
                    <button class="catalog-tab ${status === "pending" ? "active" : ""}" data-s="pending">Waiting</button>
                    <button class="catalog-tab ${status === "closed" ? "active" : ""}" data-s="closed">Handled</button>
                </div>
            </div>
            <p class="adm-meta">Every claim here was checked with osu!: the player logged into the osu! account that created the set.
                Accepting makes them the set's owner on Qlute (they can edit it and upload updates while it's unranked).</p>
            <div class="adm-list" id="list"></div>
            <div class="adm-more" id="more"></div>`;
        view.querySelectorAll("[data-s]").forEach(b => b.onclick = () => location.hash = "claims=" + b.dataset.s);
        const list = view.querySelector("#list"), more = view.querySelector("#more");
        async function load() {
            const data = await api(`claims?status=${status}&page=${page}`);
            if (!current(mine)) return;
            document.getElementById("claim-count").textContent = data.pending || "";
            data.results.forEach(c => list.appendChild(claimCard(c, () => { refreshMe(); route(); })));
            page++;
            more.innerHTML = data.results.length === data.page_size ? `<button class="adm-btn">Load more</button>` : "";
            if (more.firstChild) more.firstChild.onclick = load;
            done(list.children.length ? "" : status === "pending" ? "No claims waiting." : "No handled claims yet.");
        }
        await load();
    }

    function claimCard(c, changed) {
        const card = document.createElement("div");
        card.className = "adm-card" + (c.status === "pending" ? "" : " closed");
        const pill = c.status === "pending" ? `<span class="adm-pill yellow">waiting</span>`
            : `<span class="adm-pill ${c.status === "accepted" ? "green" : "red"}">${esc(c.status)}</span>`;
        const osuLink = `<a href="https://osu.ppy.sh/users/${encodeURIComponent(c.osu_user_id)}" target="_blank" rel="noopener">${esc(c.osu_username)}</a>`;
        card.innerHTML = `
            <div class="adm-head">
                <span class="who"><a href="/beatmapset/${encodeURIComponent(c.setid)}" target="_blank">${esc(c.title)}</a></span>
                <span>${pill} <span class="adm-pill green">osu! verified</span></span>
            </div>
            <div class="adm-meta">Qlute player ${userLink(c.username)} &middot; osu! account ${osuLink} (#${esc(c.osu_user_id)})
                &middot; set creator on osu!: <b>${esc(c.set_creator)}</b> &middot;
                <a href="https://osu.ppy.sh/beatmapsets/${encodeURIComponent(c.setid)}" target="_blank" rel="noopener">set on osu!</a></div>
            <div class="adm-meta">#${c.id} claimed ${when(c.created)}${c.owner ? ` &middot; current owner: ${userLink(c.owner)}` : ""}</div>
            ${c.status !== "pending" ? `<div class="adm-meta">${esc(c.status)} by ${esc(c.handled_by)} ${when(c.handled_at)}${c.note ? ": " + esc(c.note) : ""}</div>` : ""}
            <div class="adm-actions"></div>
            <p class="adm-msg"></p>`;
        const actions = card.querySelector(".adm-actions"), msg = card.querySelector(".adm-msg");
        function button(text, cls, fn) {
            const b = document.createElement("button");
            b.className = "adm-btn " + cls;
            b.textContent = text;
            b.onclick = async () => {
                b.disabled = true;
                try { await fn(); } catch (err) { msg.textContent = err.message; b.disabled = false; }
            };
            actions.appendChild(b);
        }
        if (c.status === "pending") {
            button("Accept", "good", async () => {
                const note = prompt("Accept this claim? A note for the player (optional):", "");
                if (note === null) throw new Error("");
                await api(`claims/${c.id}/accept`, { note });
                changed();
            });
            button("Decline", "danger", async () => {
                const note = prompt("Why decline it? The player sees this.", "");
                if (note === null) throw new Error("");
                await api(`claims/${c.id}/decline`, { note });
                changed();
            });
        }
        return card;
    }

    // ---------------------------------------------------------------- players
    async function showPlayers(query, mine) {
        view.innerHTML = `
            <div class="adm-bar">
                <input class="catalog-search" type="search" id="q" placeholder="Find a player by name..." value="${esc(query)}" autocomplete="off">
                <label class="adm-row"><input type="checkbox" id="r"> Restricted only</label>
            </div>
            <div class="adm-grid" id="list"></div>`;
        const q = view.querySelector("#q"), r = view.querySelector("#r"), list = view.querySelector("#list");
        let req = 0;
        async function load() {
            const mineReq = ++req;
            const data = await api(`users?query=${encodeURIComponent(q.value.trim())}&restricted=${r.checked ? 1 : 0}`);
            if (!current(mine) || mineReq !== req) return;
            list.innerHTML = data.results.map(u => `
                <a href="#user=${encodeURIComponent(u.username)}" class="adm-card">
                    <span class="who"><b>${esc(u.username)}</b>
                        ${u.restricted ? `<span class="adm-pill red">restricted</span>` : ""}
                        ${u.staff ? `<span class="adm-pill purple">${esc(u.staff)}</span>` : ""}</span>
                    <span class="adm-meta">${u.rank ? "#" + u.rank.toLocaleString() : "Unranked"} &middot; joined ${when(u.joined)}</span>
                </a>`).join("");
            done(data.results.length ? "" : "No players match.");
        }
        let typing;
        q.oninput = () => { clearTimeout(typing); typing = setTimeout(() => load().catch(e => done(e.message)), 300); };
        r.onchange = () => load().catch(e => done(e.message));
        q.focus();
        await load();
    }

    async function showUser(arg, mine) {
        const [name, reportPart] = arg.split("&report=");
        const u = await api("user/" + encodeURIComponent(name));
        if (!current(mine)) return;
        const active = u.bans.filter(b => b.active);
        view.innerHTML = `
            <div class="adm-head">
                <span class="who" style="font-size:24px">${esc(u.username)}
                    ${u.restricted ? `<span class="adm-pill red">restricted</span>` : `<span class="adm-pill green">in good standing</span>`}
                    ${u.staff ? `<span class="adm-pill purple">${esc(u.staff)}</span>` : ""}</span>
                <a href="/user/${encodeURIComponent(u.username)}"><button class="adm-btn">View profile</button></a>
            </div>
            <div class="adm-stats" style="margin:8px 0 4px">
                <span>Rank: ${u.rank ? "#" + u.rank.toLocaleString() : "unranked"}</span>
                <span>${(u.points || 0).toLocaleString()}pp</span>
                <span>${u.accuracy}% acc</span>
                <span>${u.scores.toLocaleString()} scores</span>
                <span>Joined ${when(u.joined)}</span>
                <span>Last seen ${when(u.last_seen)}</span>
                <span>Sent ${u.reports_sent} report${u.reports_sent === 1 ? "" : "s"}</span>
            </div>
            <div id="action"></div>
            ${u.scores ? `<div class="adm-row" style="margin-top:8px"><button class="adm-btn danger" id="wipe-all">Delete all ${u.scores.toLocaleString()} scores</button>
                <a href="#scores=${encodeURIComponent(u.username)}"><button class="adm-btn">Delete recent scores...</button></a></div>
                <p class="adm-msg" id="wmsg"></p>` : ""}
            <div class="adm-section">Supporter</div>
            <div id="support"></div>
            <div class="adm-section">Bans (${u.bans.length})</div>
            <div class="adm-list" id="bans"></div>
            <div class="adm-section">Reports about them (${u.reports_against.length})</div>
            <div class="adm-list" id="reports"></div>`;
        supportBox(view.querySelector("#support"), u.username, u.supporter, u.can_grant_support, () => route());
        const wipeAll = view.querySelector("#wipe-all");
        if (wipeAll) wipeAll.onclick = async () => {
            if (!confirm(`Delete ALL ${u.scores} of ${u.username}'s scores? Their pp, accuracy and rank go back to what's left (nothing). This can't be undone.`)) return;
            wipeAll.disabled = true;
            try { await api("scores/purge", { hours: 0, username: u.username, confirm: true }); route(); }
            catch (err) { view.querySelector("#wmsg").textContent = err.message; wipeAll.disabled = false; }
        };
        const action = view.querySelector("#action");
        if (u.restricted) {
            const b = active[0];
            action.innerHTML = `
                <div class="adm-form">
                    <b>${b ? (b.permanent ? "Banned permanently" : "Banned, ends " + when(b.expires)) : "Restricted by hand (no ban record)"}</b>
                    ${b ? `<span class="adm-meta">Reason: ${esc(b.reason)} &middot; by ${esc(b.issued_by)} ${when(b.created)}</span>` : ""}
                    <label for="unote">Note (optional)</label>
                    <input id="unote" type="text" maxlength="500" placeholder="Why lift it?">
                    <div class="adm-row"><button class="adm-btn good" id="unban">Lift ban / unrestrict</button></div>
                    <p class="adm-msg" id="umsg"></p>
                </div>`;
            action.querySelector("#unban").onclick = async e => {
                if (!confirm(`Unrestrict ${u.username}?`)) return;
                e.target.disabled = true;
                try {
                    await api("unban", { username: u.username, note: action.querySelector("#unote").value });
                    route();
                } catch (err) { action.querySelector("#umsg").textContent = err.message; e.target.disabled = false; }
            };
        } else if (u.can_ban) {
            action.innerHTML = `
                <div class="adm-form">
                    <b>Ban ${esc(u.username)}${reportPart ? ` (from report #${esc(reportPart)})` : ""}</b>
                    <label for="reason">Reason (the player sees this)</label>
                    <textarea id="reason" rows="2" maxlength="500" placeholder="e.g. Using an auto-player on ranked maps"></textarea>
                    <label for="length">Length</label>
                    <div class="adm-row">
                        <select id="length">
                            <option value="1">1 hour</option>
                            <option value="24">1 day</option>
                            <option value="72">3 days</option>
                            <option value="168" selected>1 week</option>
                            <option value="720">30 days</option>
                            <option value="2160">90 days</option>
                            <option value="custom">Custom...</option>
                            <option value="0">Permanent</option>
                        </select>
                        <span id="custom" hidden>
                            <input type="number" id="amount" min="1" value="2">
                            <select id="unit"><option value="1">hours</option><option value="24" selected>days</option><option value="168">weeks</option></select>
                        </span>
                    </div>
                    <label class="adm-row"><input type="checkbox" id="close" checked> Mark their open reports as resolved</label>
                    <label class="adm-row"><input type="checkbox" id="wipe"> Also delete all their scores (${u.scores.toLocaleString()}); can't be undone</label>
                    <div class="adm-row"><button class="adm-btn danger" id="ban">Ban</button></div>
                    <p class="adm-msg" id="bmsg"></p>
                </div>`;
            const length = action.querySelector("#length"), custom = action.querySelector("#custom");
            length.onchange = () => custom.hidden = length.value !== "custom";
            action.querySelector("#ban").onclick = async e => {
                const reason = action.querySelector("#reason").value.trim();
                const hours = length.value === "custom"
                    ? Number(action.querySelector("#amount").value) * Number(action.querySelector("#unit").value)
                    : Number(length.value);
                const msg = action.querySelector("#bmsg");
                if (reason.length < 3) { msg.textContent = "Give a reason; the player will see it."; return; }
                if (!(hours >= 0)) { msg.textContent = "Pick a length."; return; }
                const lengthText = hours === 0 ? "permanently" : length.value === "custom" ? `for ${hours} hours` : "for " + length.selectedOptions[0].text;
                const wipe = action.querySelector("#wipe").checked;
                if (!confirm(`Ban ${u.username} ${lengthText}?\n\nReason: ${reason}` +
                             (wipe ? `\n\nThis also DELETES ALL ${u.scores} of their scores, even if the ban is lifted later.` : ""))) return;
                e.target.disabled = true;
                try {
                    await api("ban", { username: u.username, reason, hours, report: reportPart || null,
                                       close_reports: action.querySelector("#close").checked, delete_scores: wipe });
                    refreshMe();
                    location.hash = "user=" + encodeURIComponent(u.username);
                    route();
                } catch (err) { msg.textContent = err.message; e.target.disabled = false; }
            };
        } else {
            action.innerHTML = `<p class="adm-meta">You can't ban this account (yourself, or a team member you don't outrank).</p>`;
        }
        const bans = view.querySelector("#bans");
        bans.innerHTML = u.bans.map(banCard).join("") || `<p class="adm-meta">No bans.</p>`;
        const reports = view.querySelector("#reports");
        u.reports_against.forEach(r => reports.appendChild(reportCard(r, route)));
        if (!u.reports_against.length) reports.innerHTML = `<p class="adm-meta">No reports.</p>`;
        done("");
    }

    function banCard(b) {
        const state = b.active ? `<span class="adm-pill red">${b.permanent ? "permanent" : "active, " + esc(b.time_left) + " left"}</span>`
            : b.lifted_by ? `<span class="adm-pill green">lifted</span>` : `<span class="adm-pill">expired</span>`;
        return `
            <div class="adm-card${b.active ? "" : " closed"}">
                <div class="adm-head"><span class="who">${userLink(b.username)}</span><span>${state}</span></div>
                <p class="adm-text">${esc(b.reason)}</p>
                <div class="adm-meta">By ${esc(b.issued_by)} ${when(b.created)} &middot; ${b.permanent ? "no end date" : b.active ? "ends " + when(b.expires) : "was set to end " + esc(new Date(b.expires * 1000).toLocaleString())}${b.report ? ` &middot; report #${b.report}` : ""}</div>
                ${b.lifted_by ? `<div class="adm-meta">Lifted by ${esc(b.lifted_by)} ${when(b.lifted_at)}${b.lift_note ? ": " + esc(b.lift_note) : ""}</div>` : ""}
            </div>`;
    }

    // ---------------------------------------------------------------- bans
    async function showBans(status, mine) {
        status = status || "active";
        let page = 0;
        view.innerHTML = `
            <div class="adm-bar">
                <div class="catalog-tabs">
                    <button class="catalog-tab ${status === "active" ? "active" : ""}" data-s="active">Active</button>
                    <button class="catalog-tab ${status === "all" ? "active" : ""}" data-s="all">History</button>
                </div>
            </div>
            <div class="adm-list" id="list"></div>
            <div class="adm-more" id="more"></div>`;
        view.querySelectorAll("[data-s]").forEach(b => b.onclick = () => location.hash = "bans=" + b.dataset.s);
        const list = view.querySelector("#list"), more = view.querySelector("#more");
        async function load() {
            const data = await api(`bans?status=${status}&page=${page}`);
            if (!current(mine)) return;
            list.insertAdjacentHTML("beforeend", data.results.map(banCard).join(""));
            page++;
            more.innerHTML = data.results.length === data.page_size ? `<button class="adm-btn">Load more</button>` : "";
            if (more.firstChild) more.firstChild.onclick = load;
            done(list.children.length ? "" : status === "active" ? "Nobody is banned right now." : "No bans yet.");
        }
        await load();
    }

    // ---------------------------------------------------------------- scores (bulk delete, e.g. after a broken submit or a cheater's spree)
    async function showScores(prefill, mine) {
        view.innerHTML = `
            <p class="adm-meta" style="margin-top:0">Delete every score set in a time window, optionally only one player's.
                Players' pp, accuracy and rank are recalculated. To delete a single score, open it and use "Delete score".</p>
            <div class="adm-form">
                <div class="adm-row">
                    <label for="hours">Scores from the last</label>
                    <select id="hours">
                        <option value="0.25">15 minutes</option>
                        <option value="1" selected>1 hour</option>
                        <option value="3">3 hours</option>
                        <option value="6">6 hours</option>
                        <option value="12">12 hours</option>
                        <option value="24">24 hours</option>
                        <option value="72">3 days</option>
                        <option value="168">7 days</option>
                        <option value="720">30 days</option>
                        <option value="0">All time (needs a player)</option>
                    </select>
                </div>
                <input type="text" id="name" placeholder="Only this player (leave empty for everyone)" maxlength="256" value="${esc(prefill)}">
                <div class="adm-row"><button class="adm-btn" id="check">Check what would be deleted</button></div>
                <div id="preview"></div>
                <p class="adm-msg"></p>
            </div>`;
        const form = view.querySelector(".adm-form"), msg = form.querySelector(".adm-msg"), preview = form.querySelector("#preview");
        const hours = form.querySelector("#hours"), name = form.querySelector("#name");
        const ask = () => ({ hours: Number(hours.value), username: name.value.trim() });
        hours.onchange = name.oninput = () => { preview.innerHTML = ""; msg.textContent = ""; };
        form.querySelector("#check").onclick = async () => {
            msg.textContent = ""; preview.innerHTML = "";
            const q = ask();
            try {
                const data = await api("scores/purge", q);
                if (!data.count) { msg.textContent = "No scores in that window."; return; }
                const label = hours.options[hours.selectedIndex].text;
                preview.innerHTML = `
                    <div class="adm-meta"><b>${data.count}</b> score${data.count === 1 ? "" : "s"} from ${q.hours ? "the last " + esc(label) : "all time"} by ${data.players.length} player${data.players.length === 1 ? "" : "s"}:</div>
                    <div class="adm-meta">${data.players.map(p => `${userLink(p.username)} (${p.scores})`).join(", ")}</div>
                    <div class="adm-row"><button class="adm-btn danger" id="go">Delete ${data.count} score${data.count === 1 ? "" : "s"}</button></div>`;
                preview.querySelector("#go").onclick = async () => {
                    if (!confirm(`Delete ${data.count} scores from ${q.hours ? "the last " + label : "all time"}${q.username ? " by " + q.username : ""}? This can't be undone.`)) return;
                    try {
                        const res = await api("scores/purge", { ...q, confirm: true });
                        preview.innerHTML = "";
                        msg.textContent = `Deleted ${res.deleted} score${res.deleted === 1 ? "" : "s"} (${res.players.length} player${res.players.length === 1 ? "" : "s"} recalculated).`;
                    } catch (err) { msg.textContent = err.message; }
                };
            } catch (err) { msg.textContent = err.message; }
        };
        done("");
    }

    // ---------------------------------------------------------------- team
    async function showTeam(_, mine) {
        const data = await api("staff");
        if (!current(mine)) return;
        view.innerHTML = `
            <p class="adm-meta" style="margin-top:0">Team members get the "Making the game better" medal (moderators also get "Team Moderator") and can open this panel (here and in the game).
                Moderators handle reports and bans; admins can also ban moderators and change the team.</p>
            <div class="adm-list" id="list"></div>
            <div id="add"></div>`;
        const list = view.querySelector("#list");
        data.results.forEach(s => {
            const card = document.createElement("div");
            card.className = "adm-card";
            card.innerHTML = `
                <div class="adm-head">
                    <span class="who">${userLink(s.username)} <span class="adm-pill purple">${esc(s.role)}</span></span>
                    <span class="adm-meta">added ${when(s.added)}${s.added_by ? " by " + esc(s.added_by) : ""}</span>
                </div>
                <div class="adm-actions"></div><p class="adm-msg"></p>`;
            if (data.can_edit && s.username !== me.username) {
                const actions = card.querySelector(".adm-actions");
                const other = s.role === "admin" ? "mod" : "admin";
                actions.innerHTML = `<button class="adm-btn">Make ${other}</button><button class="adm-btn danger">Remove from team</button>`;
                actions.children[0].onclick = () => teamEdit("add", { username: s.username, role: other }, card);
                actions.children[1].onclick = () => { if (confirm(`Remove ${s.username} from the team?`)) teamEdit("remove", { username: s.username }, card); };
            }
            list.appendChild(card);
        });
        if (data.can_edit) {
            const add = view.querySelector("#add");
            add.innerHTML = `
                <div class="adm-section">Add a team member</div>
                <div class="adm-form">
                    <div class="adm-row">
                        <input type="text" id="name" placeholder="Username" maxlength="256">
                        <select id="role"><option value="mod">Moderator</option><option value="admin">Admin</option></select>
                        <button class="adm-btn good" id="go">Add</button>
                    </div>
                    <p class="adm-msg"></p>
                </div>`;
            add.querySelector("#go").onclick = () => teamEdit("add", { username: add.querySelector("#name").value.trim(), role: add.querySelector("#role").value }, add);
        }
        done("");
    }

    async function teamEdit(action, data, card) {
        try { await api("staff/" + action, data); route(); }
        catch (err) { card.querySelector(".adm-msg").textContent = err.message; }
    }

    // ---------------------------------------------------------------- supporters (perks: profile banner + badge)
    function supportStatus(s) {
        if (!s) return `<span class="adm-pill">not a supporter</span>`;
        if (!s.active) return `<span class="adm-pill red">ended</span> <span class="adm-meta">${when(s.expires)}</span>`;
        return `<span class="adm-pill purple">&#9829; supporter</span> <span class="adm-meta">${s.forever ? "forever" : "ends " + when(s.expires) + " (" + esc(s.time_left) + " left)"}</span>`;
    }

    // Status + grant / extend / remove for one player. Admins only can change it.
    function supportBox(box, username, s, canEdit, changed) {
        box.innerHTML = `
            <div class="adm-card">
                <div class="adm-head"><span class="who">${userLink(username)} ${supportStatus(s)}</span>
                    ${s ? `<span class="adm-meta">last changed ${when(s.updated)}${s.granted_by ? " by " + esc(s.granted_by) : ""}</span>` : ""}</div>
                ${s && s.note ? `<div class="adm-meta">Note: ${esc(s.note)}</div>` : ""}
                ${canEdit ? `
                <div class="adm-form">
                    <label>${s && s.active ? "Add more time" : "Make them a supporter"} (time stacks on what they have left)</label>
                    <div class="adm-row">
                        <select class="sp-months">
                            <option value="1">1 month</option><option value="3">3 months</option><option value="6">6 months</option>
                            <option value="12">1 year</option><option value="0">Forever</option>
                        </select>
                        <input type="text" class="sp-note" maxlength="300" placeholder="Note, e.g. BMC donation 14 Nov ($5)">
                        <button class="adm-btn good sp-grant">${s && s.active ? "Extend" : "Grant"}</button>
                        ${s ? `<button class="adm-btn danger sp-revoke">Remove</button>` : ""}
                    </div>
                    <p class="adm-msg"></p>
                </div>` : `<p class="adm-meta">Only admins can grant supporter time.</p>`}
            </div>`;
        if (!canEdit) return;
        const msg = box.querySelector(".adm-msg");
        box.querySelector(".sp-grant").onclick = async e => {
            e.target.disabled = true; msg.textContent = "Saving...";
            try {
                await api("supporters/grant", { username, months: Number(box.querySelector(".sp-months").value), note: box.querySelector(".sp-note").value });
                changed();
            } catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
        const revoke = box.querySelector(".sp-revoke");
        if (revoke) revoke.onclick = async e => {
            if (!confirm(`Remove ${username}'s supporter status? Their banner will be hidden (the image is kept).`)) return;
            e.target.disabled = true;
            try { await api("supporters/revoke", { username }); changed(); }
            catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
    }

    async function showSupporters(_, mine) {
        const data = await api("supporters");
        if (!current(mine)) return;
        const active = data.results.filter(s => s.active).length;
        view.innerHTML = `
            <p class="adm-meta" style="margin-top:0">Supporters get a profile banner and a &#9829; Supporter badge (the team gets banners too).
                Players buy supporter tags on <a href="${esc(data.support_url)}" target="_blank" rel="noopener">the supporter page</a> through Xsolla,
                which grants the time on its own${data.payments_ready ? "" : " (<b>payments aren't set up yet: add the Xsolla keys to config/config.conf</b>)"}.
                You can also grant time by hand here. ${active} active supporter${active === 1 ? "" : "s"}.</p>
            <div id="add"></div>
            <div class="adm-list" id="list"></div>
            <div class="adm-section">Recent purchases</div>
            <div class="adm-list" id="orders"></div>`;
        const orders = view.querySelector("#orders");
        if (!data.orders.length) orders.innerHTML = `<p class="adm-meta">No purchases yet.</p>`;
        data.orders.forEach(o => {
            const card = document.createElement("div");
            card.className = "adm-card" + (o.status === "paid" ? "" : " closed");
            const pill = { paid: "green", canceled: "red", pending: "yellow" }[o.status] || "";
            card.innerHTML = `
                <div class="adm-head">
                    <span class="who">#${o.id} ${userLink(o.buyer)}${o.recipient !== o.buyer ? ` &rarr; ${userLink(o.recipient)} (gift)` : ""}
                        <span class="adm-pill ${pill}">${esc(o.status)}</span>${o.sandbox ? ` <span class="adm-pill">test</span>` : ""}</span>
                    <span class="adm-meta">${o.months} month${o.months === 1 ? "" : "s"}${o.amount ? " &middot; " + esc(o.amount) : ""}</span>
                </div>
                <div class="adm-meta">started ${when(o.created)}${o.paid_at ? " &middot; paid " + when(o.paid_at) : ""}${o.xsolla_order ? " &middot; Xsolla order " + o.xsolla_order : ""}</div>`;
            orders.appendChild(card);
        });
        if (data.can_edit) {
            const add = view.querySelector("#add");
            add.innerHTML = `
                <div class="adm-form">
                    <b>Add a supporter</b>
                    <div class="adm-row">
                        <input type="text" id="sp-name" placeholder="Username" maxlength="256">
                        <button class="adm-btn good" id="sp-find">Open</button>
                    </div>
                    <p class="adm-meta">Opens their player page, where you pick how long.</p>
                </div>`;
            const go = () => { const n = add.querySelector("#sp-name").value.trim(); if (n) location.hash = "user=" + encodeURIComponent(n); };
            add.querySelector("#sp-find").onclick = go;
            add.querySelector("#sp-name").onkeydown = e => { if (e.key === "Enter") go(); };
        }
        const list = view.querySelector("#list");
        data.results.forEach(s => {
            const card = document.createElement("div");
            supportBox(card, s.username, s, data.can_edit, () => route());
            list.appendChild(card.firstElementChild);
        });
        done(data.results.length ? "" : "No supporters yet.");
    }

    // ---------------------------------------------------------------- notices (game home screen banners)
    async function showNotices(_, mine) {
        const data = await api("notices");
        if (!current(mine)) return;
        view.innerHTML = `
            <p class="adm-meta" style="margin-top:0">These banners rotate on the game's home screen, top to bottom. Clicking one opens its link.</p>
            <div class="adm-list" id="list"></div>
            <div class="adm-section">Add a notice</div>
            <div class="adm-form" id="add">
                <label>Image</label>
                <input type="file" id="img" accept="image/png,image/jpeg,image/webp">
                <label for="ntext">Title (shown to the team, and as the banner's name)</label>
                <input type="text" id="ntext" maxlength="200" placeholder="e.g. Halloween event">
                <label for="nlink">Link when clicked (optional)</label>
                <input type="text" id="nlink" maxlength="500" placeholder="https://...">
                <div class="adm-row"><button class="adm-btn good" id="go">Add notice</button></div>
                <p class="adm-msg"></p>
            </div>`;
        const list = view.querySelector("#list");
        data.results.forEach((n, i) => list.appendChild(noticeCard(n, i, data.results.length)));
        if (!data.results.length) list.innerHTML = `<p class="adm-meta">No notices yet. The home screen shows no banners.</p>`;
        const add = view.querySelector("#add"), msg = add.querySelector(".adm-msg");
        add.querySelector("#go").onclick = async e => {
            const file = add.querySelector("#img").files[0];
            if (!file) { msg.textContent = "Pick an image."; return; }
            e.target.disabled = true;
            msg.textContent = "Uploading...";
            try {
                await upload("notices/add", { image: await fitNotice(file), text: add.querySelector("#ntext").value.trim(), redirect: add.querySelector("#nlink").value.trim() });
                route();
            } catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
        done("");
    }

    function noticeCard(n, i, count) {
        const card = document.createElement("div");
        card.className = "adm-card" + (n.active ? "" : " closed");
        card.innerHTML = `
            <div class="adm-notice">
                <img src="${esc(n.image)}" alt="" loading="lazy">
                <div class="adm-list" style="flex:1;min-width:0">
                    <div class="adm-head"><span class="who">${esc(n.text || "(untitled)")}</span>
                        <span>${n.active ? `<span class="adm-pill green">shown</span>` : `<span class="adm-pill">hidden</span>`}</span></div>
                    <label class="adm-meta">Title</label>
                    <input type="text" class="t" maxlength="200" value="${esc(n.text)}">
                    <label class="adm-meta">Link when clicked</label>
                    <input type="text" class="l" maxlength="500" value="${esc(n.redirect)}" placeholder="(none)">
                    <label class="adm-meta">Replace image (optional)</label>
                    <input type="file" class="f" accept="image/png,image/jpeg,image/webp">
                    <div class="adm-actions">
                        <button class="adm-btn good" data-a="save">Save</button>
                        <button class="adm-btn" data-a="toggle">${n.active ? "Hide" : "Show"}</button>
                        <button class="adm-btn" data-a="up" ${i === 0 ? "disabled" : ""}>Move up</button>
                        <button class="adm-btn" data-a="down" ${i === count - 1 ? "disabled" : ""}>Move down</button>
                        <button class="adm-btn danger" data-a="delete">Delete</button>
                    </div>
                    <p class="adm-msg"></p>
                </div>
            </div>`;
        const msg = card.querySelector(".adm-msg");
        const run = async (fn, b) => {
            b.disabled = true;
            msg.textContent = "Working...";
            try { await fn(); route(); } catch (err) { msg.textContent = err.message; b.disabled = false; }
        };
        card.querySelectorAll("[data-a]").forEach(b => b.onclick = () => {
            const a = b.dataset.a;
            if (a === "save") run(async () => {
                const file = card.querySelector(".f").files[0];
                await upload(`notices/${n.id}/edit`, { text: card.querySelector(".t").value.trim(), redirect: card.querySelector(".l").value.trim(), image: file ? await fitNotice(file) : null });
            }, b);
            else if (a === "toggle") run(() => api(`notices/${n.id}/edit`, { active: !n.active }), b);
            else if (a === "up" || a === "down") run(() => api(`notices/${n.id}/move`, { dir: a === "down" ? 1 : -1 }), b);
            else if (a === "delete" && confirm(`Delete the notice "${n.text || "(untitled)"}"? Its image is deleted too.`)) run(() => api(`notices/${n.id}/delete`, {}), b);
        });
        return card;
    }

    // ---------------------------------------------------------------- card borders
    async function showBorders(_, mine) {
        const data = await api("borders");
        if (!current(mine)) return;
        const [W, H] = data.size;
        view.innerHTML = `
            <p class="adm-meta" style="margin-top:0">Players pick these in their settings. Every border must be exactly ${W}&times;${H} pixels (PNG with transparency works best).</p>
            <div class="adm-grid" id="list"></div>
            <div class="adm-section">Add a card border</div>
            <div class="adm-form" id="add">
                <label>Image (${W}&times;${H})</label>
                <input type="file" id="img" accept="image/png,image/jpeg,image/webp">
                <img id="prev" class="adm-border" alt="" hidden>
                <label for="bname">Name</label>
                <input type="text" id="bname" maxlength="64" placeholder="e.g. Sakura">
                <div class="adm-row"><button class="adm-btn good" id="go">Add card border</button></div>
                <p class="adm-msg"></p>
            </div>`;
        const list = view.querySelector("#list");
        data.results.forEach(b => {
            const card = document.createElement("div");
            card.className = "adm-card" + (b.active ? "" : " closed");
            card.innerHTML = `
                <img class="adm-border" src="${esc(b.url)}" alt="">
                <input type="text" class="n" maxlength="64" value="${esc(b.name)}">
                <span class="adm-meta">${b.supporter_only ? `<span class="adm-pill purple">&#9829; supporter-only</span> ` : ""}${b.active ? "Offered in settings" : "Hidden from settings"} &middot; used by ${b.users} player${b.users === 1 ? "" : "s"}</span>
                <div class="adm-actions">
                    <button class="adm-btn good" data-a="save">Save name</button>
                    <button class="adm-btn" data-a="toggle">${b.active ? "Hide" : "Offer"}</button>
                    <button class="adm-btn" data-a="supporter">${b.supporter_only ? "Make it free for everyone" : "Make it supporter-only"}</button>
                    <button class="adm-btn danger" data-a="delete">Delete</button>
                </div>
                <p class="adm-msg"></p>`;
            const msg = card.querySelector(".adm-msg");
            card.querySelectorAll("[data-a]").forEach(btn => btn.onclick = async () => {
                const a = btn.dataset.a;
                if (a === "delete" && !confirm(`Delete "${b.name}"? ${b.users} player(s) using it go back to no border.`)) return;
                btn.disabled = true;
                try {
                    if (a === "save") await api(`borders/${b.id}/edit`, { name: card.querySelector(".n").value.trim() });
                    else if (a === "toggle") await api(`borders/${b.id}/edit`, { active: !b.active });
                    else if (a === "supporter") await api(`borders/${b.id}/edit`, { supporter_only: !b.supporter_only });
                    else await api(`borders/${b.id}/delete`, {});
                    route();
                } catch (err) { msg.textContent = err.message; btn.disabled = false; }
            });
            list.appendChild(card);
        });
        if (!data.results.length) list.innerHTML = `<p class="adm-meta">No card borders yet.</p>`;

        const add = view.querySelector("#add"), msg = add.querySelector(".adm-msg"), file = add.querySelector("#img"), prev = add.querySelector("#prev");
        let ok = false;
        file.onchange = async () => {
            ok = false;
            prev.hidden = true;
            msg.textContent = "";
            const f = file.files[0];
            if (!f) return;
            try {
                const img = await imageSize(f);
                if (img.naturalWidth !== W || img.naturalHeight !== H) {
                    msg.textContent = `That image is ${img.naturalWidth}x${img.naturalHeight}. Card borders must be exactly ${W}x${H}.`;
                    return;
                }
                prev.src = img.src = URL.createObjectURL(f);
                prev.hidden = false;
                ok = true;
                const name = add.querySelector("#bname");
                if (!name.value) name.value = f.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").slice(0, 64);
            } catch (err) { msg.textContent = err.message; }
        };
        add.querySelector("#go").onclick = async e => {
            if (!file.files[0]) { msg.textContent = "Pick an image."; return; }
            if (!ok) return;
            const name = add.querySelector("#bname").value.trim();
            if (!name) { msg.textContent = "Give the border a name."; return; }
            e.target.disabled = true;
            msg.textContent = "Uploading...";
            try { await upload("borders/add", { image: file.files[0], name }); route(); }
            catch (err) { msg.textContent = err.message; e.target.disabled = false; }
        };
        done("");
    }

    tabs.forEach(t => t.onclick = () => location.hash = t.dataset.tab);
    window.addEventListener("hashchange", route);
    refreshMe().then(route).catch(err => { hint.textContent = err.message; });
})();
