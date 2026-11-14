// "About me" editor on your own profile, like osu!'s "me!": BBCode toolbar, preview, save (POST /apiv2/bio).
(function () {
  const box = document.getElementById("profile-bio");
  const view = document.getElementById("bio-view");
  const raw = document.getElementById("bio-raw");
  const editBtn = document.getElementById("bio-edit");
  if (!box || !view || !raw || !editBtn) return;
  const max = Number(raw.dataset.max) || 3000;
  let saved = raw.value;

  const TOOLS = [
    ["B", "Bold", "[b]", "[/b]", "bold"],
    ["I", "Italic", "[i]", "[/i]", "italic"],
    ["U", "Underline", "[u]", "[/u]", "underline"],
    ["S", "Strikethrough", "[s]", "[/s]", "strike"],
    ["Heading", "Heading", "[heading]", "[/heading]"],
    ["Centre", "Centre", "[centre]", "[/centre]"],
    ["Link", "Link", "[url=https://]", "[/url]"],
    ["Image", "Image (https link)", "[img]", "[/img]"],
    ["Quote", "Quote", "[quote]", "[/quote]"],
    ["Spoiler", "Spoiler (hover to show)", "[spoiler]", "[/spoiler]"],
    ["Box", "Collapsible box", "[box=title]", "[/box]"],
    ["List", "List", "[list]\n[*]", "\n[/list]"],
    ["Code", "Code block", "[code]\n", "\n[/code]"],
  ];

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // ---- the editor (built once, shown on Edit)
  const editor = el("div", "bio-editor");
  editor.hidden = true;
  const bar = el("div", "bio-toolbar");
  const area = el("textarea", "bio-area");
  area.maxLength = max;
  area.rows = 10;
  area.spellcheck = true;
  area.setAttribute("aria-label", "About me (BBCode)");

  function wrap(open, close) {
    const a = area.selectionStart, b = area.selectionEnd, v = area.value;
    area.value = v.slice(0, a) + open + v.slice(a, b) + close + v.slice(b);
    area.focus();
    area.setSelectionRange(a + open.length, b + open.length);
    update();
  }
  for (const [label, title, open, close, cls] of TOOLS) {
    const b = el("button", "bio-tool" + (cls ? " " + cls : ""), label);
    b.type = "button"; b.title = title;
    b.addEventListener("click", () => wrap(open, close));
    bar.appendChild(b);
  }
  // colour + size pickers
  const colour = el("input", "bio-colour");
  colour.type = "color"; colour.value = "#f3baff"; colour.title = "Colour";
  colour.addEventListener("change", () => wrap(`[color=${colour.value}]`, "[/color]"));
  bar.appendChild(colour);
  // text size: a small dark menu (a native <select> pops up in the browser's own light style)
  const size = el("div", "bio-size");
  const sizeBtn = el("button", "bio-tool bio-size-btn", "Size ▾");
  sizeBtn.type = "button"; sizeBtn.title = "Text size";
  sizeBtn.setAttribute("aria-haspopup", "menu"); sizeBtn.setAttribute("aria-expanded", "false");
  const sizeMenu = el("div", "bio-size-menu");
  sizeMenu.setAttribute("role", "menu");
  sizeMenu.hidden = true;
  const showSizes = on => { sizeMenu.hidden = !on; sizeBtn.setAttribute("aria-expanded", on ? "true" : "false"); };
  for (const [v, t, px] of [["50", "Tiny", 11], ["85", "Small", 13], ["100", "Normal", 15], ["150", "Large", 19]]) {
    const o = el("button", "bio-size-option", t);
    o.type = "button"; o.setAttribute("role", "menuitem");
    o.style.fontSize = px + "px"; // a hint of the size, still readable
    o.addEventListener("click", () => { showSizes(false); wrap(`[size=${v}]`, "[/size]"); });
    sizeMenu.appendChild(o);
  }
  sizeBtn.addEventListener("click", () => showSizes(sizeMenu.hidden));
  document.addEventListener("click", e => { if (!size.contains(e.target)) showSizes(false); });
  size.addEventListener("keydown", e => { if (e.key === "Escape") { showSizes(false); sizeBtn.focus(); } });
  size.append(sizeBtn, sizeMenu);
  bar.appendChild(size);

  const foot = el("div", "bio-foot");
  const count = el("span", "bio-count");
  const status = el("span", "bio-status");
  const buttons = el("div", "bio-buttons");
  const previewBtn = el("button", "profile-action", "Preview");
  const cancelBtn = el("button", "profile-action", "Cancel");
  const saveBtn = el("button", "profile-action bio-save", "Save");
  for (const b of [previewBtn, cancelBtn, saveBtn]) { b.type = "button"; buttons.appendChild(b); }
  foot.append(count, status, buttons);
  const preview = el("div", "profile-bio-text bb bio-preview");
  preview.hidden = true;
  editor.append(bar, area, preview, foot);
  box.appendChild(editor);

  function update() {
    count.textContent = `${area.value.length} / ${max}`;
    saveBtn.disabled = area.value === saved;
  }
  area.addEventListener("input", () => { status.textContent = ""; status.className = "bio-status"; update(); });

  function open() {
    area.value = saved;
    editor.hidden = false; view.hidden = true; editBtn.hidden = true;
    preview.hidden = true; area.hidden = false; bar.hidden = false; previewBtn.textContent = "Preview";
    update();
    area.focus();
  }
  function close() {
    editor.hidden = true; view.hidden = false; editBtn.hidden = false;
  }
  async function post(path, text) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Chikara": "1" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || "Something went wrong.");
    return data;
  }

  editBtn.addEventListener("click", open);
  cancelBtn.addEventListener("click", () => {
    if (area.value !== saved && !confirm("Throw away your changes?")) return;
    close();
  });
  previewBtn.addEventListener("click", async () => {
    if (!preview.hidden) {
      preview.hidden = true; area.hidden = false; bar.hidden = false; previewBtn.textContent = "Preview"; area.focus();
      return;
    }
    try {
      const data = await post("/apiv2/bio/preview", area.value);
      preview.innerHTML = data.html || '<p class="profile-bio-empty">Nothing to show.</p>';
      preview.hidden = false; area.hidden = true; bar.hidden = true; previewBtn.textContent = "Keep editing";
    } catch (e) { status.className = "bio-status error"; status.textContent = e.message; }
  });
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    status.className = "bio-status"; status.textContent = "Saving...";
    try {
      const data = await post("/apiv2/bio", area.value);
      saved = raw.value = data.bio;
      view.innerHTML = data.html || '<p class="profile-bio-empty">You haven\'t written anything about yourself yet.</p>';
      status.textContent = "";
      close();
    } catch (e) {
      status.className = "bio-status error"; status.textContent = e.message;
      update();
    }
  });
  area.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !saveBtn.disabled) { e.preventDefault(); saveBtn.click(); }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
      const k = e.key.toLowerCase();
      if (k === "b") { e.preventDefault(); wrap("[b]", "[/b]"); }
      if (k === "i") { e.preventDefault(); wrap("[i]", "[/i]"); }
      if (k === "u") { e.preventDefault(); wrap("[u]", "[/u]"); }
    }
  });
  window.addEventListener("beforeunload", e => { if (!editor.hidden && area.value !== saved) e.preventDefault(); });
  if (location.hash === "#profile-bio") open();
})();
