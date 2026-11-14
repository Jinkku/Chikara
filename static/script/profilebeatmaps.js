// Profile page: the beatmap sets the player uploaded or claimed, in Ranked / Special / Unranked tabs (counts come from the
// server, Chikara/views.py user()). Data: /apiv2/search?uploader=NAME&status=1|4|0 (Chikara/catalog.py), 50 per page.
(function () {
    const box = document.getElementById("profile-beatmaps");
    if (!box) return;
    const $ = id => document.getElementById(id);
    const user = box.dataset.user;
    const PER_PAGE = 50;
    const tabs = [...box.querySelectorAll(".pb-tab")];
    let status = null, page = 0, request = 0;

    async function load() {
        const mine = request;
        $("pb-more").hidden = true;
        try {
            const p = new URLSearchParams({ uploader: user, status, sort: "newest", page });
            const res = await fetch("/apiv2/search?" + p);
            if (!res.ok) throw new Error("HTTP " + res.status);
            const sets = await res.json();
            if (mine !== request) return; // switched tab meanwhile
            sets.forEach(s => $("pb-grid").appendChild(BeatmapCard.render(s)));
            page++;
            $("pb-hint").hidden = $("pb-grid").children.length > 0;
            $("pb-hint").textContent = "No beatmaps here yet -n-";
            $("pb-more").hidden = sets.length < PER_PAGE;
        } catch (e) {
            if (mine !== request) return;
            $("pb-hint").hidden = false;
            $("pb-hint").textContent = "Couldn't load the beatmaps right now.";
        }
    }

    function show(tab) {
        request++;
        BeatmapCard.stopPreview();
        tabs.forEach(t => { t.classList.toggle("on", t === tab); t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
        status = tab.dataset.status;
        page = 0;
        $("pb-grid").innerHTML = "";
        load();
    }

    tabs.forEach(t => t.addEventListener("click", () => show(t)));
    $("pb-more").addEventListener("click", load);
    show(tabs.find(t => Number(t.dataset.count) > 0) || tabs[0]);
})();
