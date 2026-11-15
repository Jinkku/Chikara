// User settings: avatar upload. The image is cropped to a square and shrunk to 256x256 in the browser
// (so uploads stay small), then the server checks and re-encodes it: POST /apiv2/avatar.
document.addEventListener("DOMContentLoaded", () => {
  const SIZE = 256;
  const drop = document.getElementById("avatar-drop");
  const preview = document.getElementById("avatar-preview");
  const fileInput = document.getElementById("avatarupload");
  const uploadBtn = document.getElementById("avatarbutton");
  const removeBtn = document.getElementById("avatarremove");
  const status = document.getElementById("avatar-status");
  let busy = false;

  function setBusy(on, text) {
    busy = on;
    drop.classList.toggle("busy", on);
    uploadBtn.disabled = removeBtn.disabled = on;
    status.className = "avatar-status";
    status.textContent = text || "";
  }
  function fail(text) {
    setBusy(false);
    status.className = "avatar-status error";
    status.textContent = text;
  }

  // Centre-crop + resize on a canvas; keeps transparency when the source can have it.
  function shrink(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = SIZE;
        const ctx = canvas.getContext("2d");
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, 0, 0, SIZE, SIZE);
        URL.revokeObjectURL(url);
        const type = file.type === "image/jpeg" ? "image/jpeg" : "image/png";
        canvas.toBlob(b => b ? resolve(b) : reject(new Error("Couldn't process that image.")), type, 0.92);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file isn't an image we can read.")); };
      img.src = url;
    });
  }

  async function send(form) {
    const res = await fetch("/apiv2/avatar", { method: "POST", headers: { "X-Chikara": "1" }, body: form });
    let data = {};
    try { data = await res.json(); } catch (e) { }
    if (!res.ok) throw new Error(data.error || "The server said " + res.status + ".");
    return data;
  }

  // Swap every copy of the avatar on the page (the header one too).
  function show(src) {
    preview.src = src;
    const top = document.getElementById("userpfp");
    if (top && top !== preview) top.src = src;
  }

  async function upload(file) {
    if (busy || !file) return;
    if (!file.type.startsWith("image/")) return fail("Please choose an image file.");
    if (file.size > 20 * 1024 * 1024) return fail("That image is too big (20 MB max before resizing).");
    setBusy(true, "Uploading...");
    try {
      const blob = await shrink(file);
      const form = new FormData();
      form.append("avatar", blob, blob.type === "image/jpeg" ? "avatar.jpg" : "avatar.png");
      await send(form);
      show(URL.createObjectURL(blob)); // the new file may take a moment to appear on the image server
      setBusy(false, "Avatar updated!");
    } catch (err) {
      fail(err.message);
    }
    fileInput.value = "";
  }

  uploadBtn.addEventListener("click", () => fileInput.click());
  drop.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => upload(fileInput.files[0]));

  ["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => upload(e.dataTransfer.files[0]));
  // Dropping anywhere else on the page shouldn't open the image in the tab.
  window.addEventListener("dragover", e => e.preventDefault());
  window.addEventListener("drop", e => e.preventDefault());

  removeBtn.addEventListener("click", async () => {
    if (busy || !confirm("Go back to the default avatar?")) return;
    setBusy(true, "Removing...");
    try {
      const form = new FormData();
      form.append("remove", "1");
      const data = await send(form);
      show(data.url);
      setBusy(false, "Avatar reset to the default.");
    } catch (err) {
      fail(err.message);
    }
  });

  // ---------------------------------------------------------------- profile banner: POST /apiv2/banner
  // The server centre-crops it to 1600x500 and re-encodes it; here we only shrink big files so uploads stay small.
  const bDrop = document.getElementById("banner-drop");
  const bPreview = document.getElementById("banner-preview");
  const bInput = document.getElementById("bannerupload");
  const bUpload = document.getElementById("bannerbutton");
  const bRemove = document.getElementById("bannerremove");
  const bStatus = document.getElementById("banner-status");
  let bBusy = false;

  function showBanner(url) {
    bPreview.style.backgroundImage = url ? `url("${url.replace(/"/g, "%22")}")` : "";
    bDrop.classList.toggle("has", !!url);
    bRemove.hidden = !url;
  }
  function bannerState(on, text, error) {
    bBusy = on;
    bDrop.classList.toggle("busy", on);
    bUpload.disabled = bRemove.disabled = on;
    bStatus.className = "avatar-status" + (error ? " error" : "");
    bStatus.textContent = text || "";
  }
  // Scale down to at most 2400 px wide (keeps the shape; the server does the crop).
  function shrinkBanner(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, 2400 / img.naturalWidth);
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        const ctx = canvas.getContext("2d");
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob(b => b ? resolve(b) : reject(new Error("Couldn't process that image.")), "image/jpeg", 0.92);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file isn't an image we can read.")); };
      img.src = url;
    });
  }
  async function sendBanner(form) {
    const res = await fetch("/apiv2/banner", { method: "POST", headers: { "X-Chikara": "1" }, body: form });
    let data = {};
    try { data = await res.json(); } catch (e) { }
    if (!res.ok) throw new Error(data.error || "The server said " + res.status + ".");
    return data;
  }
  // Banners are a supporter perk: locked pickers explain that instead of uploading.
  const bLocked = bDrop.dataset.locked === "1";
  if (bLocked) {
    bDrop.classList.add("locked");
    bUpload.textContent = "Become a supporter";
    bDrop.querySelector(".banner-hint").textContent = "Profile banners are a supporter perk";
  }
  const supportLink = document.querySelector(".banner-perk a");
  function lockedClick() {
    if (supportLink) window.open(supportLink.href, "_blank", "noopener");
  }
  async function uploadBanner(file) {
    if (bBusy || !file) return;
    if (bLocked) return bannerState(false, "Profile banners are a supporter perk.", true);
    if (!file.type.startsWith("image/")) return bannerState(false, "Please choose an image file.", true);
    if (file.size > 30 * 1024 * 1024) return bannerState(false, "That image is too big (30 MB max before resizing).", true);
    bannerState(true, "Uploading...");
    try {
      const blob = await shrinkBanner(file);
      const form = new FormData();
      form.append("banner", blob, "banner.jpg");
      await sendBanner(form);
      showBanner(URL.createObjectURL(blob)); // the new file may take a moment to appear on the image server
      bannerState(false, "Banner updated!");
    } catch (err) {
      bannerState(false, err.message, true);
    }
    bInput.value = "";
  }
  showBanner(bDrop.dataset.banner);
  bUpload.addEventListener("click", () => bLocked ? lockedClick() : bInput.click());
  bDrop.addEventListener("click", () => bLocked ? lockedClick() : bInput.click());
  bInput.addEventListener("change", () => uploadBanner(bInput.files[0]));
  ["dragenter", "dragover"].forEach(t => bDrop.addEventListener(t, e => { e.preventDefault(); bDrop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => bDrop.addEventListener(t, e => { e.preventDefault(); bDrop.classList.remove("over"); }));
  bDrop.addEventListener("drop", e => uploadBanner(e.dataTransfer.files[0]));
  bRemove.addEventListener("click", async () => {
    if (bBusy || !confirm("Remove your profile banner?")) return;
    bannerState(true, "Removing...");
    try {
      const form = new FormData();
      form.append("remove", "1");
      await sendBanner(form);
      showBanner("");
      bannerState(false, "Banner removed.");
    } catch (err) {
      bannerState(false, err.message, true);
    }
  });

  // ---------------------------------------------------------------- card border
  const grid = document.getElementById("border-grid");
  const borderImg = document.getElementById("bp-border");
  const borderStatus = document.getElementById("border-status");
  const current = grid.dataset.current; // users.cardborder, e.g. "/cardborders/x.png"
  const hasPerks = grid.dataset.perks === "1"; // supporter-only borders are a supporter perk

  function previewBorder(url) {
    borderImg.hidden = !url;
    if (url) borderImg.src = url;
  }

  function option(id, name, url) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "border-option";
    b.dataset.id = id;
    b.innerHTML = url ? `<img alt="" loading="lazy"><span></span>` : `<div class="none-box">No border</div><span></span>`;
    if (url) b.querySelector("img").src = url;
    b.querySelector("span").textContent = name;
    b.addEventListener("mouseenter", () => previewBorder(url));
    b.addEventListener("mouseleave", () => previewBorder(grid.querySelector(".selected")?.dataset.url));
    b.dataset.url = url || "";
    b.addEventListener("click", () => choose(b));
    return b;
  }

  async function choose(b) {
    if (b.classList.contains("selected")) return;
    if (b.classList.contains("locked")) {
      borderStatus.className = "avatar-status error";
      borderStatus.innerHTML = 'That border is a supporter perk. <a href="/support">Become a supporter</a> &lt;3';
      return;
    }
    borderStatus.className = "avatar-status";
    borderStatus.textContent = "Saving...";
    try {
      const res = await fetch("/apiv2/cardborder", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Chikara": "1" },
        body: JSON.stringify({ id: Number(b.dataset.id) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "The server said " + res.status + ".");
      grid.querySelectorAll(".selected").forEach(x => x.classList.remove("selected"));
      b.classList.add("selected");
      previewBorder(b.dataset.url);
      borderStatus.textContent = "Card border saved! The game picks it up next time you log in.";
    } catch (err) {
      borderStatus.className = "avatar-status error";
      borderStatus.textContent = err.message;
    }
  }

  fetch("/apiv2/cardborders").then(r => r.json()).then(data => {
    grid.innerHTML = "";
    grid.appendChild(option(0, "None", ""));
    let found = !current;
    for (const border of data.results) {
      const b = option(border.id, border.name, border.url);
      if (border.supporter_only) {
        b.classList.add("supporter-only");
        b.querySelector("span").insertAdjacentHTML("afterbegin", '<i class="sup-heart" title="Supporter perk">&#9829;</i> ');
        if (!hasPerks) {
          b.classList.add("locked");
          b.title = "Supporter perk: become a supporter to use this border";
        }
      }
      if (current && border.url.endsWith(current)) { b.classList.add("selected"); found = true; }
      grid.appendChild(b);
    }
    if (!current) grid.firstChild.classList.add("selected");
    else if (!found && current) {
      // Wearing a border that's no longer offered (or was set by hand): show it, unselectable.
      const url = current.startsWith("http") ? current : grid.dataset.dataurl + current;
      const keep = option(-1, "Current (no longer offered)", url);
      keep.disabled = true;
      keep.classList.add("selected");
      grid.insertBefore(keep, grid.children[1] || null);
    }
    previewBorder(grid.querySelector(".selected")?.dataset.url);
  }).catch(() => { grid.innerHTML = '<p class="avatar-rules">Couldn\'t load card borders right now.</p>'; });
});

