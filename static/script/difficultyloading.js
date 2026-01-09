async function getdifficulties() {
    let parts = window.location.pathname.replace(window.location.hostname,"").replace("/beatmapset","").replace("/beatmapset/","");
    parts = parts.split("/");
    console.log(parts)
    const beatmapset = parts[1];

    console.log(beatmapset);
    const res = fetch("/apiv2/getdifficulties", {
    method: "GET",
        headers: {
            BEATMAPSETID: beatmapset
        }
    }).then(response => {
    // Check if the request was successful (status in the 200s range)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    // Parse the response body as JSON and return a new promise
    return response.json();
  }).then(response => {

        const difficulties = document.getElementById("difficulties");
        difficulties.innerHTML = '';
        console.log(response);
        response.forEach((row, index) => {

        const img = document.createElement("img");
        img.src = "/static/img/difficultyrank.png"
        img.width = 48;
        img.height = 48;
        console.log(row.id);
        difficulties.appendChild(img);
        });
        }
    )

}
document.addEventListener("DOMContentLoaded", function() {
    getdifficulties();
});