// Profile page: the player's favourite beatmap sets as /beatmaps-style cards. Data: /apiv2/favorites?user=NAME
// (online/beatmapsocial.py), 50 sets per page in the apiv2/search shape.
(function () {
    const box = document.getElementById("profile-favorites");
    if (!box) return;
    const $ = id => document.getElementById(id);
    const user = box.dataset.user;
    let page = 0, shown = 0;
    const card = set => BeatmapCard.render(set);

    async function load() {
        $("pf-more").hidden = true;
        try {
            const res = await fetch(`/apiv2/favorites?user=${encodeURIComponent(user)}&page=${page}`);
            const d = await res.json();
            if (!res.ok) throw new Error(d.reason);
            d.sets.forEach(s => $("pf-grid").appendChild(card(s)));
            shown += d.sets.length;
            page++;
            $("pf-count").textContent = d.count ? "· " + d.count.toLocaleString("en-US") : "";
            if (!shown) {
                $("pf-hint").innerHTML = user === BeatmapCard.me
                    ? 'No favourites yet. Press <b>&#9825; Favourite</b> on a beatmap\'s page (or in the game) to keep it here.'
                    : "No favourite beatmaps yet -n-";
            } else {
                $("pf-hint").hidden = true;
            }
            $("pf-more").hidden = shown >= d.count || d.sets.length === 0;
        } catch (e) {
            $("pf-hint").textContent = "Couldn't load the favourites right now.";
        }
    }
    $("pf-more").addEventListener("click", load);
    load();
})();
