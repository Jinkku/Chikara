// Add / remove friends (profile page "Add friend" button and the /friends page). Uses apiv2/friends/...
(function () {
    if (window.qluteFriendsLoaded) return;
    window.qluteFriendsLoaded = true;

    async function send(action, name) {
        const res = await fetch(`/apiv2/friends/${action}/${encodeURIComponent(name)}`, {
            method: "POST", headers: { "X-Chikara": "1" },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.error) throw new Error(data.reason || "Something went wrong. Try again?");
        return data;
    }

    function ready(fn) {
        if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn);
    }

    ready(() => {
        document.querySelectorAll(".friend-toggle").forEach(b => b.addEventListener("click", async () => {
            const name = b.dataset.target, on = b.classList.contains("on");
            b.disabled = true;
            try {
                const data = await send(on ? "remove" : "add", name);
                b.classList.toggle("on", !on);
                b.textContent = on ? "Add friend" : (data.mutual ? "Mutual friends ✓" : "Friend ✓");
                b.title = on ? "Add to your friends list" : "Remove from your friends";
            } catch (e) {
                alert(e.message);
            }
            b.disabled = false;
        }));

        document.querySelectorAll(".friend-remove").forEach(b => b.addEventListener("click", async () => {
            const row = b.closest(".friend-row"), name = b.dataset.target;
            if (row.classList.contains("gone")) {
                b.disabled = true;
                try { await send("add", name); row.classList.remove("gone"); b.textContent = "Remove"; }
                catch (e) { alert(e.message); }
                b.disabled = false;
                return;
            }
            b.disabled = true;
            try { await send("remove", name); row.classList.add("gone"); b.textContent = "Undo"; }
            catch (e) { alert(e.message); }
            b.disabled = false;
        }));
    });
})();
