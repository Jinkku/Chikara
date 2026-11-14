document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById("menuprompt");
    const btn = document.getElementById("accountbutton");
    const form = document.getElementById("loginForm");

    // Check if btn exists to avoid the error
    if (btn) {
        btn.onclick = function() {
            modal.style.display = "block";
        };
        btn.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); modal.style.display = "block"; }
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") modal.style.display = "none";
        });
    }

    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
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
                window.location.href = '/'; // Redirect to homepage
                //modal.style.display = "none";
                //form.reset();
            } else {
                login_notice_text.textContent = 'Incorrect username and password';
            }
        })
        .catch(error => console.error("Error:", error));
    };

    
});
