const hostname = window.location.hostname;
console.log("Hostname:", hostname);
if (hostname == "qlute.pxki.us.to") {
    fetch('/static/html/warning.html')
      .then(response => response.text())
      .then(html => {
        const div = document.createElement('div');
        div.innerHTML = html;
        document.body.appendChild(div);
      })
      .catch(err => console.error("Failed to load warning.html:", err));
}