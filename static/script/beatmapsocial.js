// Beatmap page: the Favourite button and the comments. Data: /apiv2/favorites/SET and /apiv2/comments/SET
// (online/beatmapsocial.py). Starts once beatmappage.js has found the set ("bm-meta-ready").
(function () {
    const page = document.getElementById("beatmap-page");
    const setId = page.dataset.set;
    const $ = id => document.getElementById(id);
    const me = decodeURIComponent((document.cookie.match(/(?:^|; )username=([^;]*)/) || [])[1] || "");
    const MAX = 1000;
    let started = false, commentPage = 0, total = 0, shown = 0;

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    function ago(unix) {
        let t = Math.max(0, Date.now() / 1000 - unix);
        const units = [[31536000, "year"], [2630000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"]];
        for (const [size, name] of units) {
            if (t >= size) { const x = Math.floor(t / size); return `${x} ${name}${x === 1 ? "" : "s"} ago`; }
        }
        return "just now";
    }
    async function call(path, body) {
        const opts = body === undefined ? {} : {
            method: "POST",
            headers: { "X-Chikara": "1", "Content-Type": "application/json" },
            body: JSON.stringify(body),
        };
        const res = await fetch("/apiv2/" + path, opts);
        let data = {};
        try { data = await res.json(); } catch (e) { }
        if (!res.ok) throw new Error(data.reason || "Something went wrong (" + res.status + ").");
        return data;
    }

    // ------------------------------------------------------------ favourite

    function paintFav(on, count) {
        const b = $("bm-fav");
        b.classList.toggle("on", on);
        b.querySelector(".bm-heart").innerHTML = on ? "&#9829;" : "&#9825;";
        $("bm-fav-label").textContent = on ? "Favourited" : "Favourite";
        $("bm-fav-count").textContent = count ? count.toLocaleString("en-US") : "";
        b.title = !me ? "Log in to favourite this map" : on ? "Remove from your favourites" : "Add to your favourites";
        b.dataset.on = on ? "1" : "";
    }

    async function loadFav() {
        try {
            const d = await call("favorites/" + setId);
            paintFav(d.favorited, d.count);
        } catch (e) { paintFav(false, 0); }
    }

    $("bm-fav").addEventListener("click", async () => {
        if (!me) { location.href = "/"; return; }
        const b = $("bm-fav");
        b.disabled = true;
        try {
            const d = await call(`favorites/${b.dataset.on ? "remove" : "add"}/${setId}`, {});
            paintFav(d.favorited, d.count);
        } catch (e) {
            alert(e.message);
        } finally {
            b.disabled = false;
        }
    });

    // ------------------------------------------------------------ comments

    function render(c) {
        const el = document.createElement("div");
        el.className = "bm-comment";
        el.dataset.id = c.id;
        el.innerHTML = `
            <a href="/user/${encodeURIComponent(c.username)}"><img class="bm-comment-pfp" src="${esc(c.pfp)}" alt="" loading="lazy"></a>
            <div class="bm-comment-body">
                <div class="bm-comment-head">
                    <a href="/user/${encodeURIComponent(c.username)}"><b>${esc(c.username)}</b></a>
                    <span class="bm-dim" title="${esc(new Date(c.created * 1000).toLocaleString())}">${esc(ago(c.created))}</span>
                    ${c.can_delete ? '<button type="button" class="bm-comment-delete" title="Delete this comment">Delete</button>' : ""}
                </div>
                <p class="bm-comment-text"></p>
            </div>`;
        el.querySelector(".bm-comment-text").textContent = c.text; // newlines kept by CSS (pre-wrap)
        el.querySelector(".bm-comment-delete")?.addEventListener("click", async () => {
            if (!confirm("Delete this comment?")) return;
            try {
                await call("comments/delete/" + c.id, {});
                el.remove();
                total--; shown--;
                paintCount();
            } catch (e) { alert(e.message); }
        });
        return el;
    }

    function paintCount() {
        $("bm-comments-count").textContent = total ? "· " + total.toLocaleString("en-US") : "";
        if (!total && !$("bm-comments").querySelector(".bm-comment"))
            $("bm-comments").innerHTML = '<p class="bm-empty">No comments yet. Say something nice!</p>';
        $("bm-comments-more").hidden = shown >= total;
    }

    async function loadComments() {
        const box = $("bm-comments");
        if (commentPage === 0) box.innerHTML = '<p class="bm-empty">Loading comments...</p>';
        try {
            const d = await call(`comments/${setId}?page=${commentPage}`);
            if (commentPage === 0) box.innerHTML = "";
            d.comments.forEach(c => box.appendChild(render(c)));
            total = d.total;
            shown += d.comments.length;
            commentPage++;
            paintCount();
        } catch (e) {
            if (commentPage === 0) box.innerHTML = '<p class="bm-empty">Couldn\'t load the comments. Try again in a bit.</p>';
        }
    }
    $("bm-comments-more").addEventListener("click", loadComments);

    const text = $("bm-comment-text");
    text.addEventListener("input", () => { $("bm-comment-left").textContent = MAX - text.value.length; });
    text.addEventListener("keydown", e => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("bm-comment-form").requestSubmit();
    });
    $("bm-comment-form").addEventListener("submit", async e => {
        e.preventDefault();
        if (!text.value.trim()) return;
        const send = $("bm-comment-send");
        send.disabled = true;
        $("bm-comment-status").textContent = "";
        try {
            const diff = Number($("bm-meta-diffid")?.textContent) || null;
            const d = await call("comments/" + setId, { text: text.value, beatmapid: diff });
            $("bm-comments").querySelector(".bm-empty")?.remove();
            $("bm-comments").prepend(render(d.comment));
            total++; shown++;
            paintCount();
            text.value = "";
            $("bm-comment-left").textContent = MAX;
        } catch (err) {
            $("bm-comment-status").textContent = err.message;
        } finally {
            send.disabled = false;
        }
    });

    function start() {
        if (started) return;
        started = true;
        $("bm-comments-section").hidden = false;
        $("bm-comment-form").hidden = !me;
        $("bm-comment-login").hidden = !!me;
        loadFav();
        loadComments();
    }
    document.addEventListener("bm-meta-ready", start);
    if (!$("bm-meta-section").hidden) start();
})();
