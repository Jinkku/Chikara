(function () {
    const form = document.getElementById("changepasswordform");
    const status = document.getElementById("cp-status");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        const current = document.getElementById("cp-current").value;
        const pw = document.getElementById("cp-new").value;
        const confirm = document.getElementById("cp-confirm").value;
        if (pw.length < 8) { status.textContent = "Your new password needs at least 8 characters."; return; }
        if (pw !== confirm) { status.textContent = "The new passwords don't match."; return; }
        status.textContent = "Saving...";
        try {
            const res = await fetch("/apiv2/password", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Chikara": "1" },
                body: JSON.stringify({ current: current, new: pw }),
            });
            const data = await res.json();
            if (data.ok) {
                status.textContent = "Password changed!";
                window.location.href = "/";
            } else {
                status.textContent = data.error || "Couldn't change your password.";
            }
        } catch (err) {
            status.textContent = "Couldn't reach the server. Try again.";
        }
    });
})();
