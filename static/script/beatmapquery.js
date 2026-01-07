async function getLeaderboard() {
    const parts = window.location.pathname.split("/");

    const beatmapset = parts[parts.length - 2];
    const id = parts[parts.length - 1];

    console.log(beatmapset);
    console.log(id);
    const res = fetch("/apiv2/getleaderboard", {
    method: "GET",
        headers: {
            BEATMAPID: id
        }
    }).then(response => {
    // Check if the request was successful (status in the 200s range)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    // Parse the response body as JSON and return a new promise
    return response.json();
  }).then(response => {

        const leaderboard = document.getElementById("leaderboard");
        leaderboard.innerHTML = '<table class="tablebar column verticalpadding"><trhead><tr><th>Rank</th><th>Username</th><th>Points</th><th>Score</th><th>Accuracy</th><th>Perfect</th><th>Great</th><th>Meh</th><th>Miss</th><th>Mods</th><th>Time</th></tr></trhead><tbody id="leaderboard-body"></tbody>';
        const tbody = document.getElementById("leaderboard-body");
        response.forEach((row, index) => {
        const accuracy = (
            (row.MAX + (row.GOOD / 2) + (row.MEH / 3) ) /
            (row.MAX + row.GOOD + row.MEH + row.BAD)
        ) * 100;

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="lbar">${index + 1}</td>
            <td class="cbar"><a href="/user/${row.username}">${row.username}</a></td>
            <td class="cbar">${row.points.toFixed(0)}pp</td>
            <td class="cbar">${row.score}</td>
            <td class="cbar">${accuracy.toFixed(2)}%</td>
            <td class="cbar">${row.MAX}</td>
            <td class="cbar">${row.GOOD}</td>
            <td class="cbar">${row.MEH}</td>
            <td class="cbar">${row.BAD}</td>
            <td class="cbar">${row.mods}</td>
            <td class="ebar">${timeform(Math.floor(Date.now() / 1000) - row.time)}</td>
        `;

        tbody.appendChild(tr);
        });

    })

}

function timeform(clock) {
    let suffix = "";
    const sec = false;
    if (clock >= 31536000) {
        suffix = "yr";
        clock = clock / 31536000;
    } else if (clock >= 2630000) {
        suffix = "mh";
        clock = clock / 2630000;
    } else if (clock >= 86400) {
        suffix = "dy";
        clock = clock / 86400;
    } else if (clock >= 3600) {
        suffix = "h";
        clock = clock / 3600;
    } else if (clock >= 60) {
        suffix = "m";
        clock = clock / 60;
    } else if (clock < 60) {
        suffix = "s";
        clock = clock;
        sec = true;
    } 
    if (clock > 1 & !sec) {
        suffix += "s"
    }
    return `${Math.floor(clock)}${suffix}`;
}
document.addEventListener("DOMContentLoaded", function() {
    console.log("DOM is fully loaded!");
    getLeaderboard();
});