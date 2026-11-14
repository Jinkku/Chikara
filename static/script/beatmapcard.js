// Beatmap set cards (styles in catalog.css), shared by /beatmaps (beatmapcatalog.js), profile favourites
// (profilefavorites.js) and profile beatmaps (profilebeatmaps.js). Sets come in the apiv2/search shape (Chikara/catalog.py).
window.BeatmapCard = (function () {
    const me = decodeURIComponent((document.cookie.match(/(?:^|; )username=([^;]*)/) || [])[1] || "");
    const statusNames = { 1: "Ranked", 2: "Special", 4: "Special", 0: "Unranked" };
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const submitted = ts => ts ? new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
    // level colour, shared with beatmappage.js: blue -> red over Lv 1-55, red -> magenta to Lv 69, black from Lv 70
    const lvStyle = l => { l = l || 0; return l >= 70 ? { cls: " lv-black", hue: 300 } : { cls: "", hue: Math.round(l <= 55 ? 200 - l * 200 / 55 : 360 - (l - 55) * 4) }; };

    const HEART = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';
    const DOWNLOAD = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z"/></svg>';

    // ------------------------------------------------------------ audio preview (one at a time, page-wide)
    let audio = null, playingBtn = null;
    function stopPreview() {
        if (audio) { audio.pause(); audio = null; }
        if (playingBtn) { playingBtn.innerHTML = "&#9654;"; playingBtn = null; }
    }
    function togglePreview(url, btn) {
        const same = btn === playingBtn;
        stopPreview();
        if (same || !url) return;
        audio = new Audio(url);
        audio.volume = 0.5;
        audio.play().catch(stopPreview);
        audio.addEventListener("ended", stopPreview);
        btn.innerHTML = "&#10074;&#10074;";
        playingBtn = btn;
    }

    // ------------------------------------------------------------ favourite: apiv2/favorites/add|remove (online/beatmapsocial.py)
    function paintFav(btn, on, count) {
        btn.classList.toggle("on", on);
        btn.dataset.on = on ? "1" : "";
        const label = !me ? "Log in to favourite" : on ? "Remove from favourites" : "Add to favourites";
        btn.title = label + (count ? ` (${count.toLocaleString("en-US")})` : "");
        btn.setAttribute("aria-label", label);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
    }
    async function toggleFav(btn, setId) {
        if (!me) { location.href = "/"; return; }
        btn.disabled = true;
        try {
            const res = await fetch(`/apiv2/favorites/${btn.dataset.on ? "remove" : "add"}/${setId}`,
                { method: "POST", headers: { "X-Chikara": "1", "Content-Type": "application/json" }, body: "{}" });
            const d = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(d.reason || "Something went wrong (" + res.status + ").");
            paintFav(btn, d.favorited, d.count);
            if (d.favorited) { btn.classList.remove("pop"); void btn.offsetWidth; btn.classList.add("pop"); }
        } catch (e) {
            alert(e.message);
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------ the card
    // opts.status: the status pill to show (default: the set's own); opts.badges: extra HTML after the level pills.
    function render(set, opts = {}) {
        const diffs = [...set.beatmaps].sort((a, b) => (a.level || 0) - (b.level || 0));
        const status = String(opts.status ?? diffs[0]?.ranked ?? 0);
        const cover = esc(set.covers?.card).replace(/'/g, "%27");
        // a claimed / self-uploaded set's mapper links to their profile (catalog.py mapper_users). The card is
        // itself a link, so this is a span that navigates on click rather than a nested <a>.
        const mapper = set.mapper_user
            ? `<b class="mapper-link" role="link" tabindex="0" data-user="${esc(set.mapper_user)}" title="${esc(set.mapper_user)}'s profile">${esc(set.creator)}</b>`
            : `<b>${esc(set.creator)}</b>`;
        const pill = d => {
            const lv = lvStyle(d.level);
            const title = (d.recommended ? "Recommended for you - " : "") + esc(d.version) + (d.pp ? " - " + Math.round(d.pp) + "pp" : "");
            return `<span class="mod${d.recommended ? " rec" : ""}${lv.cls}" style="--lv-hue:${lv.hue}" title="${title}">Lv ${esc(d.level)}</span>`;
        };
        const card = document.createElement("a");
        card.className = "catalog-card";
        card.href = "/beatmapset/" + set.id;
        card.style.setProperty("--cover", `url('${cover}')`);
        card.innerHTML = `
            <div class="catalog-cover" style="background-image:url('${cover}')">
                <button class="preview" type="button" title="Play preview" aria-label="Play preview">&#9654;</button>
            </div>
            <div class="catalog-body">
                <div class="catalog-head">
                    <span class="catalog-title" title="${esc(set.title)}">${esc(set.title)}</span>
                    <span class="catalog-status s${esc(status)}">${statusNames[status] ?? "Unknown"}</span>
                </div>
                <span class="line artist">${esc(set.artist)}</span>
                <span class="line mapper">mapped by ${mapper}</span>
                ${set.last_updated ? `<span class="line submitted">submitted <time datetime="${new Date(set.last_updated * 1000).toISOString()}">${submitted(set.last_updated)}</time></span>` : ""}
                <div class="catalog-diffs">${diffs.slice(0, 8).map(pill).join("")}${diffs.length > 8 ? `<span class="mod more">+${diffs.length - 8}</span>` : ""}${opts.badges || ""}</div>
            </div>
            <div class="catalog-actions">
                <button class="fav" type="button">${HEART}</button>
                <button class="download" type="button" title="Download" aria-label="Download">${DOWNLOAD}</button>
            </div>`;
        card.querySelector(".preview").addEventListener("click", e => { e.preventDefault(); togglePreview(set.preview_url, e.currentTarget); });
        card.querySelector(".download").addEventListener("click", e => { e.preventDefault(); location.href = set.download_url; });
        const fav = card.querySelector(".fav");
        paintFav(fav, !!set.favorited, set.favourite_count || 0);
        fav.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); toggleFav(fav, set.id); });
        const link = card.querySelector(".mapper-link");
        if (link) {
            const go = e => { e.preventDefault(); e.stopPropagation(); location.href = "/user/" + encodeURIComponent(link.dataset.user); };
            link.addEventListener("click", go);
            link.addEventListener("keydown", e => { if (e.key === "Enter") go(e); });
        }
        return card;
    }

    return { render, stopPreview, esc, me };
})();
