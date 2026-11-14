// /submit: lists your submitted sets (submitting itself is game-only). API: /apiv2/submit/mine (submissions/views.py).
(function () {
    const page = document.getElementById("submit-page");
    const $ = id => document.getElementById(id);
    const dataUrl = page.dataset.dataurl || "";
    const statusNames = { 0: "Unranked", 1: "Ranked", 2: "Special" };

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const asset = p => !p ? "" : /^https?:/.test(p) ? p : dataUrl + p.split("/").map(encodeURIComponent).join("/");

    async function loadMine() {
        const box = $("sb-mine");
        let rows;
        try {
            const res = await fetch("/apiv2/submit/mine");
            rows = (await res.json()).results || [];
        } catch (e) {
            box.innerHTML = '<p class="sb-dim">Couldn\'t load your beatmaps. Try refreshing.</p>';
            return;
        }
        if (!rows.length) {
            box.innerHTML = '<p class="sb-dim">You haven\'t submitted anything yet.</p>';
            return;
        }
        box.innerHTML = '<div class="sb-list">' + rows.map(r => `
            <a class="sb-card" href="/beatmapset/${r.setid}" style="background-image:url('${esc(asset(r.background)).replace(/'/g, "%27")}')">
                <span class="sb-badge s${r.ranked}">${statusNames[r.ranked] ?? "Unknown"}</span>
                <b>${esc(r.artist)} - ${esc(r.title)}</b>
                <span>${r.difficulties.map(esc).join(", ")}</span>
                <span>Updated ${new Date(r.updated * 1000).toLocaleDateString()}</span>
            </a>`).join("") + "</div>";
    }

    loadMine();
})();
