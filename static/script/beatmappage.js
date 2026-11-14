// Beatmap info page: /beatmapset/SET or /beatmapset/SET/DIFF
// Data: /apiv2/getdifficulties (BEATMAPSETID header) and /apiv2/getleaderboard (BEATMAPID header).
(function () {
    const page = document.getElementById("beatmap-page");
    const setId = page.dataset.set;
    const dataUrl = page.dataset.dataurl || "";
    const $ = id => document.getElementById(id);
    const statusNames = { 1: "Ranked", 2: "Special", 4: "Special", 0: "Unranked" };
    const mods = ["AT", "DT", "HT", "SL", "BT", "RND", "NF"];
    const me = decodeURIComponent((document.cookie.match(/(?:^|; )username=([^;]*)/) || [])[1] || "");

    let diffs = [];
    let current = null;
    let boardRequest = 0;
    let audio = null;

    function esc(s) {
        return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }
    // File names can contain spaces, "&" or "#": encode each path segment.
    const asset = path => !path ? "" : /^https?:/.test(path) ? path : dataUrl + path.split("/").map(encodeURIComponent).join("/");
    const num = n => Number(n || 0).toLocaleString("en-US");
    function length(sec) {
        sec = Math.round(sec || 0);
        return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
    }
    function ago(unix) {
        let t = Math.max(0, Date.now() / 1000 - unix);
        const units = [[31536000, "year"], [2630000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"], [1, "second"]];
        for (const [size, name] of units) {
            if (t >= size || size === 1) {
                const x = Math.floor(t / size);
                return `${x} ${name}${x === 1 ? "" : "s"} ago`;
            }
        }
    }
    function grade(s) {
        const total = s.MAX + s.GOOD + s.MEH + s.BAD;
        if (!total) return ["?", 0];
        const acc = (s.MAX + s.GOOD / 2 + s.MEH / 3) / total * 100;
        let g = "D";
        if (acc >= 100) g = "SS";
        else if (acc > 95 && !s.BAD) g = "S";
        else if (acc > 90) g = "A";
        else if (acc > 85) g = "B";
        else if (acc > 69) g = "C";
        else if (acc < 1) g = "?";
        return [g, acc];
    }

    // ------------------------------------------------------------ load

    async function load() {
        if (!setId || setId === "0") return missing();
        try {
            const res = await fetch("/apiv2/getdifficulties", { headers: { BEATMAPSETID: setId } });
            const data = await res.json();
            diffs = Array.isArray(data) ? data : [];
        } catch (e) {
            $("bm-title").textContent = "Couldn't load this beatmap. Try refreshing.";
            return;
        }
        if (!diffs.length) return missing();
        diffs.sort((a, b) => (a.Level - b.Level) || (a.notecount - b.notecount));
        renderSet(diffs[0]);
        renderTabs();
        const wanted = Number(page.dataset.diff);
        select(diffs.find(d => d.beatmapid === wanted) || diffs[0], false);
    }

    function missing() {
        $("bm-hero").hidden = true;
        $("bm-missing").hidden = false;
        document.title = "Qlute - beatmap not found";
    }

    function renderSet(m) {
        $("bm-hero-bg").style.backgroundImage = `url("${asset(m.backgroundpath).replace(/"/g, "%22")}")`;
        $("bm-title").textContent = m.title;
        $("bm-title-unicode").textContent = m.title_unicode && m.title_unicode !== m.title ? m.title_unicode : "";
        $("bm-artist").textContent = m.artist + (m.artist_unicode && m.artist_unicode !== m.artist ? `  (${m.artist_unicode})` : "");
        $("bm-mapper").innerHTML = `mapped by <b>${esc(m.mapper)}</b>` + (m.created ? ` &middot; uploaded ${esc(new Date(m.created).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }))}` : "");
        const status = $("bm-status");
        status.textContent = statusNames[m.ranked] ?? "Unknown";
        status.className = "bm-status s" + m.ranked;
        const plays = diffs.reduce((n, d) => n + (d.playcount || 0), 0);
        const longest = Math.max(...diffs.map(d => d.Length || 0));
        const lvs = diffs.map(d => d.Level);
        const lvText = Math.min(...lvs) === Math.max(...lvs) ? `Lv ${lvs[0]}` : `Lv ${Math.min(...lvs)}-${Math.max(...lvs)}`;
        $("bm-hero-stats").innerHTML = [
            ["&#9201;", length(longest)], ["&#9835;", `${esc(m.BPM)} BPM`],
            ["&#9776;", `${diffs.length} difficult${diffs.length === 1 ? "y" : "ies"}`], ["&#9733;", lvText],
            ["&#9654;", `${num(plays)} plays`],
        ].map(([i, t]) => `<span class="bm-chip"><i aria-hidden="true">${i}</i>${t}</span>`).join("");
        $("bm-download").href = asset(m.beatmapfile);
        $("bm-actions").hidden = false;
        if (!m.previewpath) $("bm-preview").hidden = true;
        renderMeta(m);
    }

    // Genre / language names, for the Details box.
    const filterLists = fetch("/apiv2/beatmapfilters").then(r => r.json()).catch(() => ({ genres: [], languages: [] }));

    // Details box. beatmapedit.js adds "Submitted by" for submitted sets (#bm-meta-owner).
    async function renderMeta(m) {
        const lists = await filterLists;
        const nameOf = (list, id) => (list || []).find(x => x.id === (id || 1))?.name || "Unspecified";
        const searchStatus = m.ranked === 2 ? 4 : m.ranked; // the catalog's Special tab is status 4
        const find = q => `/beatmaps?q=${encodeURIComponent(q)}${searchStatus === 1 ? "" : "&status=" + searchStatus}`;
        const rows = [];
        if (m.source) rows.push(["Source", `<a href="${find(m.source)}" title="Find more from ${esc(m.source)}">${esc(m.source)}</a>`]);
        rows.push(["Mapper", `<a href="${find(m.mapper)}" title="More maps by ${esc(m.mapper)}">${esc(m.mapper)}</a>`]);
        rows.push(["Status", esc(statusNames[m.ranked] ?? "Unknown")]);
        const facet = (key, id, name) => id && id !== 1
            ? `<a href="/beatmaps?${key}=${id}${searchStatus === 1 ? "" : "&status=" + searchStatus}">${esc(name)}</a>` : esc(name);
        rows.push(["Genre", facet("genre", m.genre, nameOf(lists.genres, m.genre))]);
        rows.push(["Language", facet("language", m.language, nameOf(lists.languages, m.language))]);
        const SHOW_VIDEO_SB = false; // video / storyboard: off until they're supported in game (also in beatmapcatalog.js)
        const extras = [m.nsfw ? '<span class="bm-flag explicit">Explicit</span>' : "", SHOW_VIDEO_SB && m.video ? '<span class="bm-flag">Video</span>' : "",
            SHOW_VIDEO_SB && m.storyboard ? '<span class="bm-flag">Storyboard</span>' : ""].filter(Boolean);
        rows.push(["Content", extras.length ? extras.join(" ") : '<span class="bm-dim">No extras</span>']);
        const plays = diffs.reduce((n, d) => n + (d.playcount || 0), 0);
        rows.push(["Plays", num(plays)]);
        if (m.title_unicode && m.title_unicode !== m.title) rows.push(["Title (original)", esc(m.title_unicode)]);
        if (m.artist_unicode && m.artist_unicode !== m.artist) rows.push(["Artist (original)", esc(m.artist_unicode)]);
        if (m.created) rows.push(["Added", esc(new Date(m.created).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }))]);
        rows.push(["Beatmap set ID", esc(m.beatmapsetid)]);
        rows.push(["Beatmap ID", `<span id="bm-meta-diffid">${esc((current || m).beatmapid)}</span>`]); // renderMeta waits for the lists, select() may already have run
        $("bm-meta").innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("");
        const tags = [...new Set(String(m.tags || "").split(/\s+/).filter(Boolean))];
        $("bm-tags").innerHTML = tags.map(t => `<a href="${find(t)}">${esc(t)}</a>`).join("");
        $("bm-tags-wrap").hidden = !tags.length;
        $("bm-meta-section").hidden = false;
        document.dispatchEvent(new Event("bm-meta-ready"));
    }

    function renderTabs() {
        const box = $("bm-diffs");
        box.innerHTML = "";
        diffs.forEach(d => {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "bm-diff";
            b.setAttribute("role", "tab");
            b.dataset.id = d.beatmapid;
            b.title = d.difficulty;
            b.innerHTML = `<span class="bm-diff-lv">Lv ${esc(d.Level)}</span><span class="bm-diff-nm">${esc(d.difficulty || "")}</span>`;
            // same scale as the beatmap cards (beatmapcatalog.js): blue -> red -> magenta, black from Lv 70
            const lv = d.Level || 0;
            b.style.setProperty("--lv-hue", String(Math.round(lv <= 55 ? 200 - lv * 200 / 55 : 360 - (Math.min(lv, 70) - 55) * 4)));
            b.classList.toggle("lv-black", lv >= 70);
            b.addEventListener("click", () => select(d, true));
            box.appendChild(b);
        });
        $("bm-diff-section").hidden = false;
    }

    function select(d, push) {
        current = d;
        document.querySelectorAll(".bm-diff").forEach(b => {
            const on = Number(b.dataset.id) === d.beatmapid;
            b.classList.toggle("active", on);
            b.setAttribute("aria-selected", on);
        });
        $("bm-diff-name").textContent = d.difficulty || "Difficulty";
        if ($("bm-meta-diffid")) $("bm-meta-diffid").textContent = d.beatmapid;
        const stats = [
            ["Level", d.Level],
            ["Length", length(d.Length)],
            ["BPM", d.BPM],
            ["Notes", num(d.notecount)],
            ["Overall Difficulty", d.Accuracy],
        ];
        if (d.pp) stats.push(["Max Performance", `${Math.round(d.pp)}pp`]);
        if (d.playcount) stats.push(["Plays", num(d.playcount)]);
        $("bm-stats").innerHTML = stats.map(([k, v]) => `<div class="bm-stat"><p>${esc(k)}</p><b>${esc(v)}</b></div>`).join("");
        const url = `/beatmapset/${setId}/${d.beatmapid}`;
        if (push && location.pathname !== url) history.pushState({ diff: d.beatmapid }, "", url);
        else if (!push) history.replaceState({ diff: d.beatmapid }, "", url);
        loadBoard(d);
    }

    window.addEventListener("popstate", e => {
        const d = diffs.find(x => x.beatmapid === e.state?.diff);
        if (d) select(d, false);
    });

    // ------------------------------------------------------------ leaderboard

    async function loadBoard(d) {
        const mine = ++boardRequest;
        $("bm-board-section").hidden = false;
        $("bm-board-title").textContent = `Leaderboard · ${d.difficulty}`;
        const box = $("bm-board");
        box.innerHTML = '<p class="bm-empty">Loading scores...</p>';
        let rows;
        try {
            const res = await fetch("/apiv2/getleaderboard", { headers: { BEATMAPID: String(d.beatmapid) } });
            rows = await res.json();
        } catch (e) {
            if (mine === boardRequest) box.innerHTML = '<p class="bm-empty">Couldn\'t load the leaderboard. Try again in a bit.</p>';
            return;
        }
        if (mine !== boardRequest) return;
        if (!Array.isArray(rows)) rows = [];
        // Best score per player, highest pp first.
        const best = new Map();
        rows.forEach(r => {
            const k = (r.username || "").toLowerCase();
            if (!best.has(k) || r.points > best.get(k).points) best.set(k, r);
        });
        rows = [...best.values()].sort((a, b) => b.points - a.points || b.score - a.score);
        if (!rows.length) {
            box.innerHTML = d.ranked === 0
                ? '<p class="bm-empty">Unranked maps don\'t have a leaderboard.</p>'
                : '<p class="bm-empty">No scores yet. Be the first to set one!</p>';
            return;
        }
        box.innerHTML = `<div class="bm-table-wrap"><table class="bm-table">
            <thead><tr><th>#</th><th></th><th>Player</th><th class="num">Score</th><th class="num">Accuracy</th><th class="num">Combo</th>
            <th class="num">Perfect</th><th class="num">Great</th><th class="num">Meh</th><th class="num">Miss</th><th class="num">pp</th><th>Mods</th><th>Set</th><th></th></tr></thead>
            <tbody>${rows.map(row).join("")}</tbody></table></div>`;
        box.querySelectorAll("tr[data-href]").forEach(tr => tr.addEventListener("click", e => {
            if (e.target.closest("a")) return;
            location.href = tr.dataset.href;
        }));
    }

    function row(r, i) {
        const [g, acc] = grade(r);
        const modTags = mods.filter(m => m !== "AT" && (r.mods || "").includes(m)).map(m => `<span class="mod">${m}</span>`).join("");
        const speed = r.speed_multi && r.speed_multi !== 1 ? `<span class="mod">${r.speed_multi}x</span>` : "";
        const when = r.time ? new Date(r.time * 1000) : null;
        const cls = [i < 3 ? "top" + (i + 1) : "", me && r.username === me ? "me" : "", r.id ? "click" : ""].join(" ").trim();
        const href = r.id ? `/score/${encodeURIComponent(r.id)}` : "";
        const pfp = r.pfp ? `<img class="bm-pfp" src="${esc(r.pfp)}" alt="" loading="lazy" width="28" height="28">` : "";
        return `<tr class="${cls}"${href ? ` data-href="${href}" title="View this score"` : ""}>
            <td class="rank">#${i + 1}</td>
            <td><span class="bm-grade ${esc(g)}">${esc(g)}</span></td>
            <td><a class="bm-player" href="/user/${encodeURIComponent(r.username)}">${pfp}<span>${esc(r.username)}</span></a></td>
            <td class="num">${num(r.score)}</td>
            <td class="num">${acc.toFixed(2)}%</td>
            <td class="num">${num(r.combo)}x</td>
            <td class="num">${num(r.MAX)}</td>
            <td class="num">${num(r.GOOD)}</td>
            <td class="num">${num(r.MEH)}</td>
            <td class="num">${num(r.BAD)}</td>
            <td class="num"><b>${Math.round(r.points || 0)}pp</b></td>
            <td>${modTags || speed ? modTags + speed : '<span class="bm-dim">-</span>'}</td>
            <td class="bm-dim" title="${when ? esc(when.toLocaleString()) : ""}">${when ? ago(r.time) : "-"}</td>
            <td>${href ? `<a class="bm-view" href="${href}" aria-label="View score #${i + 1}">&rsaquo;</a>` : ""}</td>
        </tr>`;
    }

    // ------------------------------------------------------------ buttons

    function stopPreview() {
        if (audio) { audio.pause(); audio = null; }
        $("bm-preview-icon").innerHTML = "&#9654;";
        $("bm-preview-bar").classList.remove("playing");
        $("bm-preview-fill").style.width = "0";
    }

    $("bm-preview").addEventListener("click", () => {
        if (audio) return stopPreview();
        const m = current || diffs[0];
        if (!m || !m.previewpath) return;
        audio = new Audio(asset(m.previewpath));
        audio.volume = 0.5;
        audio.addEventListener("timeupdate", () => {
            if (audio && audio.duration) $("bm-preview-fill").style.width = (audio.currentTime / audio.duration * 100) + "%";
        });
        audio.addEventListener("ended", stopPreview);
        audio.play().then(() => {
            $("bm-preview-icon").innerHTML = "&#10074;&#10074;";
            $("bm-preview-bar").classList.add("playing");
        }).catch(stopPreview);
    });

    $("bm-copy").addEventListener("click", async () => {
        const btn = $("bm-copy");
        try {
            await navigator.clipboard.writeText(location.href);
            btn.textContent = "Copied!";
        } catch (e) {
            btn.textContent = "Couldn't copy";
        }
        setTimeout(() => { btn.innerHTML = "&#128279; Copy link"; }, 1500);
    });

    load();
})();
