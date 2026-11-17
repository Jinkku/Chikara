// Profile "History" graph: rank / pp / ranked score over the last 90 days.
// Data: <script id="pf-history-data"> = [{d: "YYYY-MM-DD", rank, pp, score}, ...] oldest first (Chikara/stathistory.py).
(function () {
    const box = document.getElementById("profile-history");
    const dataEl = document.getElementById("pf-history-data");
    if (!box || !dataEl) return;
    let rows;
    try { rows = JSON.parse(dataEl.textContent); } catch (e) { return; }
    if (!rows || rows.length < 2) return;

    const chartEl = box.querySelector(".pf-hist-chart");
    const nowEl = box.querySelector(".pf-hist-now");
    const deltaEl = box.querySelector(".pf-hist-delta");
    const tabs = box.querySelectorAll(".pf-hist-tab");
    const series = {
        rank: { label: "Global rank", invert: true, fmt: v => "#" + v.toLocaleString(), axis: v => "#" + v.toLocaleString() },
        pp: { label: "Performance", fmt: v => v.toLocaleString() + " pp", axis: v => compact(v) },
        score: { label: "Ranked score", fmt: v => v.toLocaleString(), axis: v => compact(v) },
    };
    let key = "rank";
    try { if (series[localStorage.getItem("pf-hist-tab")]) key = localStorage.getItem("pf-hist-tab"); } catch (e) {}

    const NS = "http://www.w3.org/2000/svg";
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const day = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
    const dateLabel = s => { const t = day(s); return `${months[t.getMonth()]} ${t.getDate()}, ${t.getFullYear()}`; };

    function compact(v) {
        const a = Math.abs(v);
        if (a >= 1e9) return +(v / 1e9).toFixed(1) + "B";
        if (a >= 1e6) return +(v / 1e6).toFixed(1) + "M";
        if (a >= 1e3) return +(v / 1e3).toFixed(1) + "k";
        return String(Math.round(v));
    }
    // "nice" ticks: 1, 2, 2.5 or 5 x 10^n steps
    function ticks(lo, hi, n, integer) {
        if (hi === lo) { hi = lo + 1; lo = Math.max(integer ? 1 : 0, lo - 1); }
        const raw = (hi - lo) / n;
        const p = Math.pow(10, Math.floor(Math.log10(raw)));
        let step = [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw);
        if (integer) step = Math.max(1, Math.round(step));
        const start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
        const out = [];
        for (let v = start; v <= end + step / 2; v += step) out.push(+v.toFixed(6));
        return out;
    }
    function el(name, attrs, parent) {
        const n = document.createElementNS(NS, name);
        for (const k in attrs) n.setAttribute(k, attrs[k]);
        if (parent) parent.appendChild(n);
        return n;
    }

    function summary() {
        const s = series[key];
        const pts = rows.filter(r => r[key] != null);
        if (!pts.length) { nowEl.textContent = "-"; deltaEl.textContent = ""; return; }
        const first = pts[0][key], last = pts[pts.length - 1][key];
        nowEl.textContent = s.fmt(last);
        let diff = last - first;
        const better = s.invert ? diff < 0 : diff > 0;
        deltaEl.className = "pf-hist-delta" + (diff === 0 ? "" : better ? " up" : " down");
        if (diff === 0) { deltaEl.textContent = "no change"; return; }
        const arrow = better ? "▲" : "▼";
        const amount = Math.abs(diff);
        deltaEl.textContent = `${arrow} ${s.invert ? amount.toLocaleString() + (amount === 1 ? " place" : " places")
            : (key === "pp" ? amount.toLocaleString() + " pp" : compact(amount))}`;
    }

    function draw() {
        const s = series[key];
        const pts = rows.map((r, i) => ({ i, d: r.d, v: r[key] })).filter(p => p.v != null);
        chartEl.innerHTML = "";
        const W = Math.max(280, chartEl.clientWidth), H = W < 500 ? 200 : 240;
        const m = { l: 52, r: 14, t: 12, b: 26 };
        const iw = W - m.l - m.r, ih = H - m.t - m.b;
        const vals = pts.map(p => p.v);
        let lo = Math.min(...vals), hi = Math.max(...vals);
        const tv = ticks(s.invert ? Math.max(1, lo) : lo, hi, 4, key === "rank");
        lo = tv[0]; hi = tv[tv.length - 1];
        const n = rows.length - 1;
        const x = i => m.l + (n ? i / n : 0) * iw;
        const y = v => {
            const f = hi === lo ? 0.5 : (v - lo) / (hi - lo);
            return m.t + (s.invert ? f : 1 - f) * ih; // rank: #1 at the top
        };

        const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
            "aria-label": `${s.label} over the last 90 days: from ${s.fmt(pts[0].v)} to ${s.fmt(pts[pts.length - 1].v)}` }, chartEl);
        const defs = el("defs", {}, svg);
        const grad = el("linearGradient", { id: "pf-hist-fill", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
        el("stop", { offset: "0%", "stop-color": "#f3baff", "stop-opacity": s.invert ? 0.04 : 0.28 }, grad);
        el("stop", { offset: "100%", "stop-color": "#f3baff", "stop-opacity": s.invert ? 0.28 : 0 }, grad);

        // grid + y labels
        const grid = el("g", { class: "pf-hist-grid" }, svg);
        tv.forEach(v => {
            el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, grid);
            const t = el("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end" }, grid);
            t.textContent = s.axis(v);
        });
        // x labels: the 1st of each month in range
        rows.forEach((r, i) => {
            if (!r.d.endsWith("-01") || x(i) < m.l + 16 || x(i) > W - m.r - 16) return;
            const t = el("text", { x: x(i), y: H - 6, "text-anchor": "middle" }, grid);
            t.textContent = months[day(r.d).getMonth()];
        });

        // area + line (a step line: the value holds until the next day's snapshot)
        let line = "";
        pts.forEach((p, k) => {
            line += k === 0 ? `M${x(p.i)},${y(p.v)}` : `H${x(p.i)}V${y(p.v)}`;
        });
        const base = s.invert ? m.t : m.t + ih;
        el("path", { d: `${line}V${base}H${x(pts[0].i)}Z`, fill: "url(#pf-hist-fill)" }, svg);
        el("path", { d: line, class: "pf-hist-line" }, svg);
        const lastP = pts[pts.length - 1];
        el("circle", { cx: x(lastP.i), cy: y(lastP.v), r: 4, class: "pf-hist-end" }, svg);

        // hover: crosshair + marker + tooltip
        const cross = el("line", { y1: m.t, y2: m.t + ih, class: "pf-hist-cross" }, svg);
        const dot = el("circle", { r: 5, class: "pf-hist-dot" }, svg);
        cross.style.display = dot.style.display = "none";
        const tip = document.createElement("div");
        tip.className = "pf-hist-tip";
        tip.hidden = true;
        chartEl.appendChild(tip);
        const hit = el("rect", { x: m.l, y: 0, width: iw, height: H, fill: "transparent" }, svg);

        function show(clientX) {
            const r = svg.getBoundingClientRect();
            const px = (clientX - r.left) * (W / r.width);
            const i = Math.max(0, Math.min(n, Math.round((px - m.l) / iw * n)));
            let p = pts[0];
            for (const q of pts) if (q.i <= i) p = q; // the value that was in effect on that day
            const cx = x(i), cy = y(p.v);
            cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
            dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
            cross.style.display = dot.style.display = "";
            tip.innerHTML = `<span>${dateLabel(rows[i].d)}</span><b>${s.fmt(p.v)}</b>`;
            tip.hidden = false;
            const scale = r.width / W;
            const left = Math.min(Math.max(cx * scale - tip.offsetWidth / 2, 0), r.width - tip.offsetWidth);
            tip.style.left = left + "px";
            tip.style.top = Math.max(0, cy * scale - tip.offsetHeight - 12) + "px";
        }
        function hide() { cross.style.display = dot.style.display = "none"; tip.hidden = true; }
        hit.addEventListener("pointermove", e => show(e.clientX));
        hit.addEventListener("pointerdown", e => show(e.clientX));
        hit.addEventListener("pointerleave", hide);
    }

    function select(k) {
        key = k;
        tabs.forEach(t => {
            const on = t.dataset.key === key;
            t.classList.toggle("active", on);
            t.setAttribute("aria-selected", on);
        });
        try { localStorage.setItem("pf-hist-tab", key); } catch (e) {}
        summary();
        draw();
    }
    tabs.forEach(t => t.addEventListener("click", () => select(t.dataset.key)));
    let resize;
    new ResizeObserver(() => { clearTimeout(resize); resize = setTimeout(draw, 80); }).observe(chartEl);
    select(key);
})();
