// Beatmap listing. Data: /apiv2/search (filters, sort, 50 sets per page) and /apiv2/beatmapfilters
// (genre / language / sort lists). Both in Chikara/catalog.py. Every filter lives in the URL, so links can be shared.
(function () {
    const $ = id => document.getElementById(id);
    const grid = $("catalog-grid"), hint = $("catalog-hint"), more = $("catalog-more"), search = $("catalog-search");
    const PER_PAGE = 50;
    const MINE = "mine";
    const SHOW_VIDEO_SB = false; // video / storyboard filter + badges: off until they're supported in game
    const REC = "rec";         // "Recommended Difficulty": apiv2/search?recommended=1 (Chikara/recommend.py)
    const MATCH = { id: "match", name: "Best match", desc: false };
    let rec = null;            // the player's profile from /apiv2/recommendation
    const me = decodeURIComponent((document.cookie.match(/(?:^|; )username=([^;]*)/) || [])[1] || "");
    const store = {
        get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (e) { } },
    };

    const DEFAULTS = { q: "", status: "1", genre: "", language: "", explicit: "show", extra: "", played: "", sort: "newest", dir: "" };
    const state = { ...DEFAULTS, explicit: store.get("catalog-explicit") || "show" };
    const params = new URLSearchParams(location.search);
    for (const k of Object.keys(DEFAULTS)) if (params.has(k)) state[k] = params.get(k);
    if (!SHOW_VIDEO_SB) state.extra = "";
    if ((state.status === MINE || state.status === REC) && !me) state.status = "1";
    if (!["1", "4", "0", MINE, REC].includes(state.status)) state.status = state.status === "2" ? "4" : "1";
    if (state.status === REC && !params.has("sort")) state.sort = MATCH.id;
    if (state.status !== REC && state.sort === MATCH.id) state.sort = "newest";
    const recLabel = () => rec ? `Recommended Difficulty (Lv. ${rec.level})` : "Recommended Difficulty";

    let sorts = [{ id: "newest", name: "Newest", desc: true }];
    let page = 0, loading = false, done = false, request = 0;
    search.value = state.q;

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    // ------------------------------------------------------------ filter chips

    // options: [{id, name}]; multi = comma list in state[key]
    function chips(box, key, options, multi) {
        box.innerHTML = options.map(o => `<button type="button" class="cf-chip${o.cls ? " " + o.cls : ""}" data-id="${esc(o.id)}"
            ${multi ? "" : 'role="radio"'}>${esc(o.name)}</button>`).join("");
        box.querySelectorAll(".cf-chip").forEach(b => b.addEventListener("click", () => {
            const id = b.dataset.id;
            if (multi) {
                const on = new Set(state[key].split(",").filter(Boolean));
                on.has(id) ? on.delete(id) : on.add(id);
                state[key] = [...on].join(",");
            } else {
                if (state[key] === id) return;
                state[key] = id;
            }
            if (key === "status") {
                // Recommended sorts by closeness to the player's level unless they pick another sort.
                if (id === REC && state.sort === "newest" && !state.dir) state.sort = MATCH.id;
                if (id !== REC && state.sort === MATCH.id) { state.sort = "newest"; state.dir = ""; }
                renderSorts();
            }
            if (key === "explicit") store.set("catalog-explicit", id);
            restart();
        }));
    }

    function paintChips() {
        document.querySelectorAll(".cf-chips").forEach(box => {
            const key = box.id.slice(3);
            const on = new Set(String(state[key] ?? "").split(","));
            box.querySelectorAll(".cf-chip").forEach(b => {
                const active = on.has(b.dataset.id);
                b.classList.toggle("on", active);
                b.setAttribute(b.getAttribute("role") === "radio" ? "aria-checked" : "aria-pressed", active);
            });
        });
        $("cs-options").querySelectorAll(".cs-option").forEach(b => {
            const active = b.dataset.id === state.sort;
            b.classList.toggle("on", active);
            b.setAttribute("aria-checked", active);
            const desc = active ? sortDesc() : shownSorts().find(s => s.id === b.dataset.id)?.desc;
            b.querySelector(".cs-dir").textContent = active ? (desc ? "↓" : "↑") : "";
            b.title = active ? `Sorted ${desc ? "high to low" : "low to high"}; click to flip` : "";
        });
        const count = ["genre", "language", "extra", "played"].filter(k => state[k]).length + (state.explicit === "hide" ? 1 : 0);
        $("cf-count").hidden = !count;
        $("cf-count").textContent = count;
        $("cf-reset").hidden = !count;
    }

    const shownSorts = () => state.status === REC ? [MATCH, ...sorts] : sorts;

    function sortDesc() {
        if (state.dir) return state.dir === "desc";
        return shownSorts().find(s => s.id === state.sort)?.desc ?? true;
    }

    function renderSorts() {
        $("cs-options").innerHTML = shownSorts().map(s =>
            `<button type="button" class="cs-option" role="radio" data-id="${esc(s.id)}">${esc(s.name)}<span class="cs-dir"></span></button>`).join("");
        $("cs-options").querySelectorAll(".cs-option").forEach(b => b.addEventListener("click", () => {
            if (state.sort === b.dataset.id) state.dir = sortDesc() ? "asc" : "desc";
            else { state.sort = b.dataset.id; state.dir = ""; }
            restart();
        }));
    }

    function buildFilters(lists) {
        const status = [{ id: "1", name: "Ranked", cls: "s1" }, { id: "4", name: "Special", cls: "s4" }, { id: "0", name: "Unranked", cls: "s0" }];
        if (me) status.push({ id: REC, name: recLabel(), cls: "rec" }, { id: MINE, name: "Yours", cls: "mine" });
        chips($("cf-status"), "status", status);
        chips($("cf-genre"), "genre", [{ id: "", name: "Any" }, ...lists.genres]);
        chips($("cf-language"), "language", [{ id: "", name: "Any" }, ...lists.languages]);
        chips($("cf-explicit"), "explicit", [{ id: "show", name: "Show" }, { id: "hide", name: "Hide" }]);
        if (SHOW_VIDEO_SB) chips($("cf-extra"), "extra", [{ id: "video", name: "Has video" }, { id: "storyboard", name: "Has storyboard" }], true);
        else $("cf-extra").closest(".cf-row").hidden = true;
        if (me) {
            $("cf-played-row").hidden = false;
            chips($("cf-played"), "played", [{ id: "", name: "Any" }, { id: "played", name: "Played" }, { id: "unplayed", name: "Unplayed" }]);
        }
        if (lists.sorts?.length) sorts = lists.sorts;
        renderSorts();
    }

    $("cf-reset").addEventListener("click", () => {
        Object.assign(state, { genre: "", language: "", extra: "", played: "", explicit: "show" });
        store.set("catalog-explicit", "show");
        restart();
    });

    // Filters fold away on small screens (and remember it).
    const filtersBox = $("catalog-filters"), toggle = $("catalog-filter-toggle");
    function setOpen(open) {
        filtersBox.hidden = !open;
        toggle.setAttribute("aria-expanded", open);
        toggle.classList.toggle("on", open);
    }
    setOpen((store.get("catalog-filters-open") ?? (matchMedia("(max-width: 700px)").matches ? "0" : "1")) === "1");
    toggle.addEventListener("click", () => { setOpen(filtersBox.hidden); store.set("catalog-filters-open", filtersBox.hidden ? "0" : "1"); });

    // ------------------------------------------------------------ results

    function setUrl() {
        const p = new URLSearchParams();
        for (const [k, v] of Object.entries(state)) {
            if (k === "explicit" ? v !== "show" : v !== DEFAULTS[k]) p.set(k, v);
        }
        history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
    }

    function apiUrl() {
        const p = new URLSearchParams({ query: state.q, page });
        if (state.status === MINE) p.set("uploader", me);
        else if (state.status === REC) p.set("recommended", "1");
        else p.set("status", state.status);
        for (const k of ["genre", "language", "extra", "played"]) if (state[k] && !(k === "played" && state.status === REC)) p.set(k, state[k]);
        if (state.explicit === "hide") p.set("explicit", "hide");
        p.set("sort", state.sort);
        if (state.dir) p.set("dir", state.dir);
        return "/apiv2/search?" + p;
    }

    // "Recommended Difficulty (Lv. X)" chip + the line explaining the pick.
    function setRec(profile) {
        if (profile) rec = { ...rec, ...profile };
        const chip = $("cf-status")?.querySelector(`[data-id="${REC}"]`);
        if (chip) chip.textContent = recLabel();
        let info = $("catalog-rec");
        if (!info) {
            info = document.createElement("p");
            info.id = "catalog-rec";
            info.className = "catalog-rec";
            grid.before(info);
        }
        info.hidden = state.status !== REC || !rec;
        if (info.hidden) return;
        info.innerHTML = rec.based_on
            ? `From your ${rec.based_on} best play${rec.based_on === 1 ? "" : "s"}, you're comfortable around <b>Lv ${rec.level}</b> (~${Math.round(rec.target_pp)}pp).
               Showing ranked difficulties <b>Lv ${rec.min_level}&ndash;${rec.max_level}</b> you haven't played yet, best match first.`
            : `Play a few ranked maps and this will match your skill. For now: beginner-friendly <b>Lv ${rec.min_level}&ndash;${rec.max_level}</b>.`;
    }

    function restart() {
        request++;
        loading = false;
        BeatmapCard.stopPreview();
        grid.innerHTML = "";
        page = 0;
        done = false;
        paintChips();
        setRec(null);
        setUrl();
        load();
    }

    function render(set) {
        const shown = state.status === MINE ? undefined : state.status === REC ? "1" : state.status;
        const badges = [
            set.nsfw ? '<span class="cc-badge explicit" title="Explicit content">explicit</span>' : "",
            SHOW_VIDEO_SB && set.video ? '<span class="cc-badge" title="Has a background video">video</span>' : "",
            SHOW_VIDEO_SB && set.storyboard ? '<span class="cc-badge" title="Has a storyboard">storyboard</span>' : "",
        ].join("");
        return BeatmapCard.render(set, { status: shown, badges });
    }

    async function load() {
        if (loading || done) return;
        loading = true;
        const mine = request;
        hint.style.display = "";
        hint.textContent = "Loading beatmaps...";
        try {
            const res = await fetch(apiUrl());
            if (!res.ok) throw new Error("HTTP " + res.status);
            const sets = await res.json();
            if (mine !== request) return;
            if (state.status === REC) {
                try { setRec(JSON.parse(res.headers.get("X-Qlute-Recommend") || "null")); } catch (e) { }
            }
            if (page === 0) backdrop(sets[0]);
            sets.forEach(s => grid.appendChild(render(s)));
            page++;
            done = sets.length < PER_PAGE;
            if (!grid.children.length) empty();
            else hint.style.display = done ? "none" : "";
        } catch (err) {
            if (mine !== request) return;
            hint.textContent = "Couldn't load beatmaps right now. Scroll to try again.";
        } finally {
            if (mine === request) loading = false;
        }
        if (mine === request && !done && more.getBoundingClientRect().top < innerHeight + 400) load();
    }

    function empty() {
        const filtered = !$("cf-count").hidden;
        if (state.status === MINE && !state.q && !filtered) {
            hint.innerHTML = "You haven't submitted any beatmaps yet.<br>Submit them from the game: right-click a set in song select and pick <b>Submit to Qlute</b>, or use File &rarr; Submit to Qlute in the editor.";
            return;
        }
        if (state.status === REC && !state.q && !filtered) {
            hint.innerHTML = "No unplayed ranked difficulties around your level right now -n-<br>Check back when new maps are ranked.";
            return;
        }
        hint.innerHTML = `Nothing matches${state.q ? ` "${esc(state.q)}"` : ""} here -n-` +
            (filtered ? '<br><button type="button" class="cf-reset inline" id="cf-reset-empty">Clear filters</button>' : "");
        $("cf-reset-empty")?.addEventListener("click", () => $("cf-reset").click());
    }

    // The top result's cover, blurred behind the search panel.
    function backdrop(set) {
        const url = set?.covers?.cover;
        $("catalog-backdrop").style.backgroundImage = url ? `url('${url.replace(/'/g, "%27")}')` : "";
    }

    let typing;
    search.addEventListener("input", () => {
        clearTimeout(typing);
        typing = setTimeout(() => { state.q = search.value.trim(); restart(); }, 300);
    });
    new IntersectionObserver(e => { if (e[0].isIntersecting) load(); }, { rootMargin: "400px" }).observe(more);

    // Filter lists come from the server; fall back to no genre/language rows if that fails.
    fetch("/apiv2/beatmapfilters").then(r => r.json()).catch(() => ({ genres: [], languages: [] })).then(lists => {
        buildFilters(lists);
        restart();
    });
    // The level shown on the "Recommended Difficulty (Lv. X)" chip.
    if (me) fetch("/apiv2/recommendation").then(r => r.json()).then(setRec).catch(() => { });
})();

// Search tips: clicking an example adds it to the search box (a "key=" one waits for you to type the value)
(function () {
    const box = document.getElementById("cf-tips"), input = document.getElementById("catalog-search");
    if (!box || !input) return;
    box.querySelectorAll("[data-tip]").forEach(b => b.addEventListener("click", () => {
        const tip = b.dataset.tip, key = tip.split(/[=<>!:]/)[0];
        // replace an earlier filter on the same key instead of piling them up
        const words = input.value.split(/\s+/).filter(w => w && !new RegExp("^" + key + "(>=|<=|!=|>|<|=|:)", "i").test(w));
        input.value = (words.join(" ") + " " + tip).trim();
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
        if (!tip.endsWith("=")) input.dispatchEvent(new Event("input", { bubbles: true }));
    }));
})();
