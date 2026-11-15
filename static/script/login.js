document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById("menuprompt");
    const btn = document.getElementById("accountbutton");
    const form = document.getElementById("loginForm");

    // The account menu: the card in the header opens / closes it; Escape or a click outside closes it.
    function setOpen(open) {
        modal.style.display = open ? "block" : "none";
        modal.classList.toggle("open", open);
        if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
            const first = modal.querySelector("#controlpanel[style*='block'] .am-item, #loginprompt[style*='block'] input");
            if (first) first.focus({ preventScroll: true });
        }
    }

    if (btn) {
        btn.setAttribute("aria-haspopup", "dialog");
        btn.setAttribute("aria-expanded", "false");
        btn.onclick = function () { setOpen(modal.style.display !== "block"); };
        btn.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(modal.style.display !== "block"); }
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && modal.style.display === "block") { setOpen(false); btn.focus(); }
        });
    }

    window.onclick = function(event) {
        if (event.target == modal) {
            setOpen(false);
        }
    }
    
    function getCookie(name) {
        let matches = document.cookie.match(new RegExp(
            "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
        ));
        return matches ? decodeURIComponent(matches[1]) : undefined;
    }
    
    if (getCookie("username") && getCookie("password")) {
        // Execute your JavaScript here
        document.getElementById("loginprompt").style.display = "none";
        document.getElementById("controlpanel").style.display = "block";
    } else {
        document.getElementById("loginprompt").style.display = "block";
        document.getElementById("controlpanel").style.display = "none";
    }

    form.onsubmit = function(event) {
        event.preventDefault();
        const login_notice_text = document.getElementById("login_notice_text");
        login_notice_text.textContent = 'Please wait...';
        login_notice_text.className = 'am-notice';

        const formData = new FormData();
        formData.append("username", document.getElementById("username").value);
        formData.append("password", document.getElementById("password").value);

        fetch("/apiv2/login/", {
            method: "POST",
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                login_notice_text.textContent = 'Successful!';
                login_notice_text.className = 'am-notice ok';
                // Accounts on the old password hash pick a new password first.
                window.location.href = data.change_password ? '/changepassword' : '/';
                //modal.style.display = "none";
                //form.reset();
            } else {
                login_notice_text.textContent = 'Incorrect username and password';
                login_notice_text.className = 'am-notice bad';
            }
        })
        .catch(error => console.error("Error:", error));
    };

    
});
