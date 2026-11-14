// "Is this your map?" on beatmap pages of sets taken from osu!: claim it by logging into osu! (see submissions/claims.py).
(function () {
    const page = document.getElementById("beatmap-page");
    const box = document.getElementById("bm-claim");
    const setId = page && page.dataset.set;
    if (!box || !setId || setId === "0") return;
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    fetch("/apiv2/submit/claim/" + encodeURIComponent(setId)).then(r => r.json()).then(d => {
        if (!d || !d.osu_set) return;
        const mine = d.mine;
        let html = "";
        if (mine && mine.status === "accepted" && d.owner) {
            html = `<span class="bm-claim-pill good">&#10003; You own this map on Qlute</span>`;
        } else if (mine && mine.status === "pending") {
            html = `<span class="bm-claim-pill wait">&#9203; Your claim is waiting for the Qlute team</span>`;
        } else {
            if (mine && mine.status === "declined")
                html += `<span class="bm-claim-pill bad">Your claim was declined${mine.note ? ": " + esc(mine.note) : "."}</span>`;
            if (d.can_claim)
                html += `<a class="bm-claim-btn" href="/osu/claim/${encodeURIComponent(setId)}"
                    title="Log into osu! to prove you made this set">Is this your map? <b>Claim it with osu!</b></a>`;
        }
        if (!html) return;
        box.innerHTML = html;
        box.hidden = false;
    }).catch(() => { });
})();
