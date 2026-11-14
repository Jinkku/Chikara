// Beatmap page: "submitted by" for submitted sets, and the edit panel for their uploader / the Qlute team.
// API: GET /apiv2/submit/info/SET, POST /apiv2/submit/edit/SET (submissions/views.py).
(function () {
    const page = document.getElementById("beatmap-page");
    const setId = page.dataset.set;
    const $ = id => document.getElementById(id);
    const form = $("bm-edit-form");
    const FIELDS = ["title", "title_unicode", "artist", "artist_unicode", "mapper", "source", "tags"];
    const STATUS_CLASS = { 0: "s0", 1: "s1", 2: "s2" };
    let info = null;
    let original = null; // what the form started with, to know what changed
    let ranked = 0;

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    function status(text, kind) {
        const s = $("bm-edit-status");
        s.textContent = text;
        s.className = "be-status" + (kind ? " " + kind : "");
    }

    async function load() {
        if (!setId || setId === "0") return;
        try {
            const res = await fetch("/apiv2/submit/info/" + setId);
            if (!res.ok) return;
            info = await res.json();
        } catch (e) {
            return;
        }
        if (info.submitted) showOwner();
        if (info.can_edit) $("bm-edit").hidden = false;
    }

    // beatmappage.js fills #bm-mapper and the Details box asynchronously: add the owner once it has.
    // A claimed (or self-uploaded) set's mapper is the owner (catalog.py mapper_users): the mapper name itself links
    // to their profile instead of a separate "submitted by".
    function showOwner() {
        const profile = name => "/user/" + encodeURIComponent(name);
        const linked = info.mapper_user;
        const mapper = $("bm-mapper");
        const add = () => {
            if (!mapper.textContent || mapper.dataset.owner) return;
            mapper.dataset.owner = "1";
            const b = mapper.querySelector("b");
            if (linked && b) {
                b.outerHTML = `<a class="bm-mapper-link" href="${profile(linked)}" title="${esc(linked)}'s profile"><b>${b.innerHTML}</b></a>`;
            }
            if (!linked || linked !== info.owner) {
                mapper.insertAdjacentHTML("beforeend",
                    ` &middot; <span class="bm-owner">submitted by <a href="${profile(info.owner)}"><b>${esc(info.owner)}</b></a></span>`);
            }
        };
        add();
        new MutationObserver(() => { if (!mapper.querySelector(".bm-owner, .bm-mapper-link")) delete mapper.dataset.owner; add(); })
            .observe(mapper, { childList: true });
        // and the Details box: the Mapper row links to the profile; "Submitted by" only when that's someone else
        const row = () => {
            const meta = $("bm-meta");
            if (!meta || !meta.children.length || meta.dataset.owner) return;
            meta.dataset.owner = "1";
            if (linked) {
                const dt = [...meta.querySelectorAll("dt")].find(d => d.textContent === "Mapper");
                const a = dt?.nextElementSibling?.querySelector("a");
                if (a) { a.href = profile(linked); a.title = `${linked}'s profile`; }
            }
            if (linked && linked === info.owner) return;
            meta.insertAdjacentHTML("afterbegin", `<div id="bm-meta-owner"><dt>Submitted by</dt><dd><a href="${profile(info.owner)}">${esc(info.owner)}</a>` +
                (info.updated && info.updated !== info.uploaded ? ` <span class="bm-dim">&middot; updated ${esc(new Date(info.updated * 1000).toLocaleDateString())}</span>` : "") + `</dd></div>`);
        };
        row();
        document.addEventListener("bm-meta-ready", () => { if (!$("bm-meta").querySelector("#bm-meta-owner, a[href^='/user/']")) delete $("bm-meta").dataset.owner; row(); });
    }

    // ------------------------------------------------------------ form

    function values() {
        const v = {};
        FIELDS.forEach(k => v[k] = form.elements[k].value.trim());
        v.difficulties = {};
        $("bm-edit-diffs").querySelectorAll("input").forEach(i => v.difficulties[i.dataset.id] = i.value.trim());
        v.ranked = ranked;
        v.genre = Number(form.elements.genre.value);
        v.language = Number(form.elements.language.value);
        v.nsfw = form.elements.nsfw.checked;
        return v;
    }

    function fill() {
        const f = info.fields;
        FIELDS.forEach(k => form.elements[k].value = f[k] ?? "");
        $("be-mapper-field").hidden = !info.can_edit_mapper;
        const options = list => (list || []).map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join("");
        form.elements.genre.innerHTML = options(info.genres);
        form.elements.language.innerHTML = options(info.languages);
        form.elements.genre.value = String(f.genre);
        form.elements.language.value = String(f.language);
        form.elements.nsfw.checked = !!f.nsfw;

        const owner = $("be-owner");
        owner.hidden = !info.submitted;
        owner.innerHTML = info.submitted ? `submitted by <b>${esc(info.owner)}</b>` : "";
        $("bm-edit-note").textContent = info.submitted
            ? "Changes are written into the beatmap's files too, so new downloads have them."
            : "This set came from osu!. Changes only apply on Qlute.";

        ranked = info.ranked;
        $("be-status-group").hidden = !info.team;
        $("be-status").innerHTML = (info.ranked_choices || []).map(c =>
            `<button type="button" role="radio" data-id="${c.id}" class="${STATUS_CLASS[c.id] || ""}">${esc(c.text)}</button>`).join("");
        $("be-status").querySelectorAll("button").forEach(b => b.addEventListener("click", () => { ranked = Number(b.dataset.id); refresh(); }));

        $("bm-edit-diffs").innerHTML = info.difficulties.map(d => `
            <label class="be-diff"><span class="be-lv" title="Level">Lv ${esc(d.level)}</span>
                <span class="be-sr">Difficulty name</span>
                <input data-id="${d.beatmapid}" value="${esc(d.version)}" maxlength="100" required></label>`).join("");

        original = values();
        status("");
        refresh();
    }

    function refresh() {
        const now = values();
        let dirty = now.ranked !== original.ranked;
        for (const k of ["genre", "language", "nsfw"]) {
            const changed = now[k] !== original[k];
            form.elements[k].classList.toggle("changed", changed);
            dirty ||= changed;
        }
        FIELDS.forEach(k => {
            const changed = now[k] !== original[k];
            form.elements[k].classList.toggle("changed", changed);
            dirty ||= changed;
        });
        $("bm-edit-diffs").querySelectorAll("input").forEach(i => {
            const changed = i.value.trim() !== original.difficulties[i.dataset.id];
            i.classList.toggle("changed", changed);
            dirty ||= changed;
        });
        $("be-status").querySelectorAll("button").forEach(b => {
            const on = Number(b.dataset.id) === ranked;
            b.classList.toggle("on", on);
            b.setAttribute("aria-checked", on);
        });
        const tags = now.tags.split(/\s+/).filter(Boolean).slice(0, 40);
        $("be-chips").innerHTML = tags.map(t => `<span>${esc(t)}</span>`).join("");
        $("bm-edit-save").disabled = !dirty;
    }

    function invalid() {
        const required = [...form.querySelectorAll("input[required]")].filter(i => !i.closest("[hidden]"));
        required.forEach(i => i.classList.toggle("invalid", !i.value.trim()));
        const empty = required.find(i => !i.value.trim());
        if (empty) { empty.focus(); return "Fill in the highlighted fields."; }
        const names = [...$("bm-edit-diffs").querySelectorAll("input")].map(i => i.value.trim().toLowerCase());
        if (new Set(names).size !== names.length) return "Two difficulties can't have the same name.";
        return null;
    }

    form.addEventListener("input", e => { e.target.classList.remove("invalid"); refresh(); });

    $("bm-edit").addEventListener("click", () => {
        const section = $("bm-edit-section");
        if (!section.hidden) { section.hidden = true; return; }
        fill();
        section.hidden = false;
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        form.elements.title.focus({ preventScroll: true });
    });
    $("bm-edit-cancel").addEventListener("click", () => { $("bm-edit-section").hidden = true; });

    form.addEventListener("submit", async e => {
        e.preventDefault();
        const problem = invalid();
        if (problem) return status(problem, "error");
        const now = values();
        const body = { difficulties: {} };
        FIELDS.forEach(k => { if (now[k] !== original[k]) body[k] = now[k]; });
        if (!info.can_edit_mapper) delete body.mapper;
        Object.entries(now.difficulties).forEach(([id, name]) => { if (name !== original.difficulties[id]) body.difficulties[id] = name; });
        if (info.team && now.ranked !== original.ranked) body.ranked = now.ranked;
        for (const k of ["genre", "language", "nsfw"]) if (now[k] !== original[k]) body[k] = now[k];
        $("bm-edit-save").disabled = true;
        status("Saving...");
        try {
            const res = await fetch("/apiv2/submit/edit/" + setId, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Chikara": "1" },
                body: JSON.stringify(body),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || "The server said " + res.status + ".");
            status("Saved! Reloading...", "ok");
            setTimeout(() => location.reload(), 700);
        } catch (err) {
            status(err.message, "error");
            refresh();
        }
    });

    load();
})();
