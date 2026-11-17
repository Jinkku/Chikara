// Site search: users, online players and scores.
//   /apiv2/searchusers?query=&page=
//   /apiv2/searchplayers?query=&page=          (online in the last minute)
//   /apiv2/searchscores?query=&page=&sort=best|recent&ranked=1|0
(function () {
    const results = document.getElementById("search-results");
    const hint = document.getElementById("search-hint");
    const more = document.getElementById("search-more");
    const search = document.getElementById("site-search");
    const tabs = document.querySelectorAll("#search-tabs .sr-tab");
    const scoreOptions = document.getElementById("score-options");
    const sortTabs = scoreOptions.querySelectorAll(".sr-tab");
    const title = document.getElementById("search-title");
    const countEl = document.getElementById("search-count");
    const rankedBox = document.getElementById("score-ranked");
    const kinds = {
        users: { api: "searchusers", label: "users", title: "Users", placeholder: "Search users by name..." },
        players: { api: "searchplayers", label: "online players", title: "Online now", placeholder: "Search online players by name..." },
        scores: { api: "searchscores", label: "scores", title: "Scores", placeholder: "Search scores by player, song, artist or difficulty..." },
    };
    const modAliases = ["AT", "DT", "HT", "SL", "BT", "RND", "NF"];

    const params = new URLSearchParams(location.search);
    let query = params.get("q") || "";
    let kind = kinds[params.get("type")] ? params.get("type") : "users";
    let sort = params.get("sort") === "recent" ? "recent" : "best";
    rankedBox.checked = params.get("ranked") !== "0";
    let page = 0, loading = false, done = false, request = 0, count = 0, list = null;

    search.value = query;

    function esc(s) {
        return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }
    function ago(ts) {
        if (!ts) return "never";
        let t = Math.max(0, Date.now() / 1000 - ts);
        const units = [[31536000, "year"], [2630000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"], [1, "second"]];
        for (const [n, name] of units) {
            if (t >= n || n === 1) {
                const x = Math.floor(t / n);
                return `${x} ${name}${x === 1 ? "" : "s"} ago`;
            }
        }
    }
    function grade(s) {
        const total = s.max + s.great + s.meh + s.bad;
        if (!total) return ["?", 0];
        const acc = (s.max + s.great / 2 + s.meh / 3) / total * 100;
        let g = "D";
        if (acc >= 100) g = "SS";
        else if (acc > 95 && !s.bad) g = "S";
        else if (acc > 90) g = "A";
        else if (acc > 85) g = "B";
        else if (acc > 69) g = "C";
        else if (acc < 1) g = "?";
        return [g, acc];
    }

    function setUrl() {
        const p = new URLSearchParams();
        if (query) p.set("q", query);
        if (kind !== "users") p.set("type", kind);
        if (kind === "scores" && sort !== "best") p.set("sort", sort);
        if (kind === "scores" && !rankedBox.checked) p.set("ranked", "0");
        history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
    }

    function reset() {
        request++;
        loading = false;
        results.innerHTML = "";
        list = document.createElement("div");
        list.className = kind === "scores" ? "search-scores" : "search-users";
        results.appendChild(list);
        page = 0; count = 0; done = false;
        tabs.forEach(t => t.classList.toggle("active", t.dataset.kind === kind));
        sortTabs.forEach(t => t.classList.toggle("active", t.dataset.sort === sort));
        scoreOptions.style.display = kind === "scores" ? "" : "none";
        search.placeholder = kinds[kind].placeholder;
        title.textContent = kind === "scores" ? (sort === "recent" ? "Recent scores" : "Best scores") : kinds[kind].title;
        countEl.textContent = "";
        setUrl();
        load();
    }

    function renderUser(u) {
        const a = document.createElement("a");
        a.className = "sr-user" + (u.banner ? " has-banner" : "");
        a.href = "/user/" + encodeURIComponent(u.username);
        if (u.banner) a.style.setProperty("--banner", `url("${u.banner.replace(/"/g, "%22")}")`); // profile banner behind the card
        const presence = u.online
            ? `<span class="sr-presence on"><span class="sr-live"></span>${esc(u.status || "Online")}</span>`
            : `<span class="sr-presence">Last seen ${esc(ago(u.last_seen))}</span>`;
        const rank = u.rank
            ? `<span class="sr-rank">#${u.rank.toLocaleString()}</span><span class="sr-pp">${(u.points || 0).toLocaleString()} pp</span>`
            : `<span class="sr-rank none">Unranked</span>`;
        a.innerHTML = `
            <span class="sr-avatar"><img src="${esc(u.pfp)}" alt="" loading="lazy">${u.online ? '<span class="sr-avatar-dot" title="online"></span>' : ""}</span>
            <span class="sr-ident">
                <span class="sr-name" title="${esc(u.username)}">${esc(u.username)}</span>
                ${presence}
                <span class="sr-acc">${esc(u.accuracy)}% accuracy</span>
            </span>
            <span class="sr-rank-block">${rank}</span>`;
        return a;
    }

    function renderScore(s) {
        const [g, acc] = grade(s);
        const mods = modAliases.filter(m => (s.mods || "").includes(m)).map(m => `<span class="mod">${m}</span>`).join("");
        const a = document.createElement("a");
        a.href = s.id ? `/score/${encodeURIComponent(s.id)}` : `/beatmapset/${s.beatmapset_id}/${s.beatmap_id}`;
        a.innerHTML = `
            <div class="score-card">
                <div class="score-card-left">
                    <div class="rank ${g}">${g}</div>
                    <div class="info">
                        <span><b>${esc(s.beatmap)}</b> by ${esc(s.artist)}</span>
                        <span class="sr-dim">${esc(s.difficulty)} &middot; ${s.combo}x &middot; ${esc(ago(s.created))}</span>
                        <span class="sr-dim">played by <span class="sr-player">${esc(s.username)}</span></span>
                    </div>
                </div>
                <div class="score-card-right">
                    ${mods}
                    <span class="sr-acc-chip">${acc.toFixed(2)}%</span>
                    <div class="pp">${Math.round(s.points)}pp</div>
                </div>
            </div>`;
        // The player name links to their profile without leaving the score card link.
        a.querySelector(".sr-player").addEventListener("click", e => {
            e.preventDefault();
            location.href = "/user/" + encodeURIComponent(s.username);
        });
        return a;
    }

    async function load() {
        if (loading || done) return;
        loading = true;
        const mine = request;
        hint.style.display = "";
        hint.textContent = `Loading ${kinds[kind].label}...`;
        if (page === 0) {
            for (let i = 0; i < 6; i++) list.insertAdjacentHTML("beforeend", '<div class="sr-skel"></div>');
            hint.style.display = "none";
        }
        let url = `/apiv2/${kinds[kind].api}?query=${encodeURIComponent(query)}&page=${page}`;
        if (kind === "scores") url += `&sort=${sort}&ranked=${rankedBox.checked ? 1 : 0}`;
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            if (mine !== request) return;
            list.querySelectorAll(".sr-skel").forEach(el => el.remove());
            data.results.forEach(r => list.appendChild(kind === "scores" ? renderScore(r) : renderUser(r)));
            count += data.results.length;
            page++;
            done = data.results.length < data.page_size;
            countEl.textContent = count ? `${count.toLocaleString()}${done ? "" : "+"} ${count === 1 ? "result" : "results"}` : "";
            if (count === 0) {
                hint.style.display = "";
                hint.textContent = query ? `No ${kinds[kind].label} match "${query}" -n-`
                    : kind === "players" ? "Nobody is online right now -n-" : `No ${kinds[kind].label} yet -n-`;
            } else hint.style.display = done ? "none" : "";
        } catch (err) {
            if (mine !== request) return;
            list.querySelectorAll(".sr-skel").forEach(el => el.remove());
            hint.style.display = "";
            hint.textContent = `Couldn't load ${kinds[kind].label} right now. Scroll to try again.`;
        } finally {
            if (mine === request) loading = false;
        }
        if (mine === request && !done && more.getBoundingClientRect().top < innerHeight + 400) load();
    }

    let typing;
    search.addEventListener("input", () => {
        clearTimeout(typing);
        typing = setTimeout(() => { query = search.value.trim(); reset(); }, 300);
    });
    tabs.forEach(t => t.addEventListener("click", () => {
        if (t.dataset.kind === kind) return;
        kind = t.dataset.kind; reset();
    }));
    sortTabs.forEach(t => t.addEventListener("click", () => {
        if (t.dataset.sort === sort) return;
        sort = t.dataset.sort; reset();
    }));
    rankedBox.addEventListener("change", reset);
    // "/" jumps to the search box, like the hint in the field says
    document.addEventListener("keydown", e => {
        if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
        const t = e.target;
        if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
        e.preventDefault();
        search.focus();
        search.select();
    });
    new IntersectionObserver(e => { if (e[0].isIntersecting) load(); }, { rootMargin: "400px" }).observe(more);

    reset();
})();
