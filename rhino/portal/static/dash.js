/* Rhino portal - Dashboard. Toolheads on the left, maintenance on the right, given the same weight.
   Charts are plain SVG built here (no libraries, no external files - the CSP allows neither), every
   label goes in through textContent, and each chart has a table view so no value is colour- or
   hover-only. Colours: toolheads keep one categorical colour each (fixed by slot order, never by rank);
   maintenance uses the status colours the rest of the portal uses.                                   */
(() => {
"use strict";
const { h, clear, api, S } = window.RH;
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const D = { maint: null, jobs: null, hist: null, loadedAt: 0, tables: new Set(), chartW: 520 };

/* categorical slots (validated: dark on #1e1e1e, light on #fff) - a toolhead keeps its slot for good */
const CAT = {
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
};
const OTHER = "#8d8f99";
const mode = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
function toolColors() {
  const tools = [...(S.tools || [])].sort((a, b) => (a.slot || 99) - (b.slot || 99));
  const map = {};
  tools.forEach((t, i) => { map[t.name] = i < 8 ? CAT[mode()][i] : OTHER; });
  return map;
}

/* ------------------------------------------------------------------ small helpers */
function svg(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  kids.flat().forEach((k) => k && el.append(k));
  return el;
}
const fmtN = (v, d = 0) => (v == null ? "-" : Number(v).toLocaleString([], { maximumFractionDigits: d, minimumFractionDigits: 0 }));
function fmtH(v) { return v == null ? "-" : (v < 10 ? fmtN(v, 1) : fmtN(v)) + " h"; }
function fmtLen(m) { return m == null ? "-" : m >= 1000 ? fmtN(m / 1000, 2) + " km" : fmtN(m) + " m"; }
const meter = (list, key) => ((list || []).find((x) => x.meter === key) || {}).value || 0;
const perDay = (list, key) => ((list || []).find((x) => x.meter === key) || {}).per_day;
function dotEl(color) { const d = h("span", { class: "dash-dot" }); d.style.setProperty("--c", color); return d; }
function sdef(id) { return ((D.maint && D.maint.statuses) || []).find((x) => x.id === id) || { label: id, hex: OTHER }; }
const ICON = { overdue: "!", due_soon: "▲", ok: "✓", snoozed: "z", paused: "‖", done: "✓", held: "●" };

/* one tooltip for every chart: value first, label second */
const tip = h("div", { class: "dash-tip hidden", role: "tooltip" });
document.body.append(tip);
function showTip(e, value, label, color) {
  clear(tip).append(h("strong", { text: value }), h("span", { class: "dash-tip-l" }, color ? h("span", { class: "dash-key" }) : null, label));
  if (color) tip.querySelector(".dash-key").style.setProperty("--c", color);
  tip.classList.remove("hidden");
  const r = e.target.getBoundingClientRect ? e.target.getBoundingClientRect() : null;
  const x = e.clientX || (r ? r.left + r.width / 2 : 0), y = e.clientY || (r ? r.top : 0);
  const w = tip.offsetWidth, hgt = tip.offsetHeight;
  tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 12)) + "px";
  tip.style.top = Math.max(8, y - hgt - 12) + "px";
}
const hideTip = () => tip.classList.add("hidden");
function hover(el, value, label, color) {
  el.setAttribute("tabindex", "0");
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", `${label}: ${value}`);
  el.addEventListener("pointermove", (e) => showTip(e, value, label, color));
  el.addEventListener("pointerleave", hideTip);
  el.addEventListener("focus", (e) => showTip(e, value, label, color));
  el.addEventListener("blur", hideTip);
  el.classList.add("dash-mark");
}

/* a card with a title, an optional legend, the chart and a table view behind a toggle */
function chartCard(id, title, sub, chart, legend, tableRows, tableHead) {
  const tableOn = D.tables.has(id);
  const tbtn = h("button", { class: "btn ghost small dash-tbl-btn", type: "button", text: tableOn ? "Chart" : "Table",
    "aria-pressed": String(tableOn), onclick: () => { tableOn ? D.tables.delete(id) : D.tables.add(id); render(); } });
  const card = h("div", { class: "card dash-card" },
    h("div", { class: "dash-card-head" }, h("div", {}, h("h2", { text: title }), sub ? h("div", { class: "muted small", text: sub }) : null), tableRows ? tbtn : null));
  if (tableOn && tableRows) {
    card.append(h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
      h("thead", {}, h("tr", {}, tableHead.map((x, i) => h("th", { class: i ? "num" : "", text: x })))),
      h("tbody", {}, tableRows.map((r) => h("tr", {}, r.map((c, i) => h("td", { class: i ? "num" : "", text: String(c) }))))))));
  } else {
    if (legend && legend.length) card.append(h("div", { class: "dash-legend" }, legend.map(([c, l, shape]) =>
      h("span", { class: "dash-leg" }, (() => { const k = h("span", { class: "dash-sw" + (shape === "line" ? " line" : "") }); k.style.setProperty("--c", c); return k; })(), l))));
    const sv = chart && (chart.tagName && chart.tagName.toLowerCase() === "svg" ? chart : chart.querySelector && chart.querySelector("svg"));
    if (sv && !sv.getAttribute("aria-label")) sv.setAttribute("aria-label", title + (tableRows ? " - press Table for the numbers" : ""));
    card.append(chart);
  }
  return card;
}

/* round an axis maximum up to 1, 2, 2.5 or 5 x 10^n so the ticks (0, half, max) are clean numbers */
function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v))), n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/* horizontal bars, optionally stacked: rows [{label, color?, parts:[{v, color, name}]}], value label at the tip */
function hbars(rows, opts = {}) {
  const W = D.chartW, rowH = 30, barH = 16, left = Math.min(opts.left || 110, W * 0.3), right = 64, top = 4;
  const Hh = top + rows.length * rowH + 22;
  const max = niceMax(Math.max(1e-9, ...rows.map((r) => r.parts.reduce((a, p) => a + p.v, 0))));
  const x = (v) => (v / max) * (W - left - right);
  const s = svg("svg", { viewBox: `0 0 ${W} ${Hh}`, class: "dash-svg", role: "group", "aria-label": opts.aria || "" });
  // recessive grid: 0, half, max
  [0, 0.5, 1].forEach((f) => {
    const gx = left + f * (W - left - right);
    s.append(svg("line", { x1: gx, x2: gx, y1: top, y2: Hh - 20, class: f === 0 ? "dash-axis" : "dash-grid" }));
    const t = svg("text", { x: gx, y: Hh - 6, class: "dash-tick", "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle" });
    t.textContent = opts.fmt ? opts.fmt(max * f) : fmtN(max * f); s.append(t);
  });
  rows.forEach((r, i) => {
    const y = top + i * rowH + (rowH - barH) / 2;
    const lab = svg("text", { x: left - 10, y: y + barH / 2 + 4, class: "dash-label", "text-anchor": "end" });
    lab.textContent = r.label.length > 14 ? r.label.slice(0, 13) + "…" : r.label; s.append(lab);
    let cx = left; const total = r.parts.reduce((a, p) => a + p.v, 0);
    const parts = r.parts.filter((p) => p.v > 0);
    parts.forEach((p, j) => {
      const w = Math.max(0, x(p.v) - (j < parts.length - 1 ? 2 : 0));       // 2px surface gap between segments
      const last = j === parts.length - 1, rad = Math.min(4, w / 2);
      const d = last
        ? `M${cx},${y} h${Math.max(0, w - rad)} a${rad},${rad} 0 0 1 ${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 1 ${-rad},${rad} h${-Math.max(0, w - rad)} z`
        : `M${cx},${y} h${w} v${barH} h${-w} z`;
      const seg = svg("path", { d, fill: p.color });
      hover(seg, opts.fmt ? opts.fmt(p.v) : fmtN(p.v), `${r.label} - ${p.name}`, p.color);
      s.append(seg);
      cx += x(p.v);
    });
    const vt = svg("text", { x: left + x(total) + 6, y: y + barH / 2 + 4, class: "dash-value" });
    vt.textContent = opts.fmt ? opts.fmt(total) : fmtN(total); s.append(vt);
  });
  return s;
}

/* donut for part-to-whole (<= 8 segments), centre figure + caption */
function donut(segs, centre, caption) {
  const S0 = 200, R = 80, r = 54, cx = S0 / 2, cy = S0 / 2;
  const s = svg("svg", { viewBox: `0 0 ${S0} ${S0}`, class: "dash-donut", role: "group" });
  const total = segs.reduce((a, g) => a + g.v, 0);
  if (!total) {
    s.append(svg("circle", { cx, cy, r: (R + r) / 2, fill: "none", class: "dash-track", "stroke-width": R - r }));
  } else {
    let a0 = -Math.PI / 2;
    const gap = segs.filter((g) => g.v > 0).length > 1 ? 0.025 : 0;           // surface gap between segments
    segs.filter((g) => g.v > 0).forEach((g) => {
      const a1 = a0 + (g.v / total) * Math.PI * 2;
      const s0 = a0 + gap / 2, s1 = Math.max(s0 + 0.001, a1 - gap / 2), big = s1 - s0 > Math.PI ? 1 : 0;
      const P = (rad, a) => `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)}`;
      const d = g.v === total
        ? `M${cx - R},${cy} a${R},${R} 0 1 0 ${2 * R},0 a${R},${R} 0 1 0 ${-2 * R},0 M${cx - r},${cy} a${r},${r} 0 1 1 ${2 * r},0 a${r},${r} 0 1 1 ${-2 * r},0`
        : `M${P(R, s0)} A${R},${R} 0 ${big} 1 ${P(R, s1)} L${P(r, s1)} A${r},${r} 0 ${big} 0 ${P(r, s0)} Z`;
      const p = svg("path", { d, fill: g.color, "fill-rule": "evenodd" });
      hover(p, `${fmtN(g.v, g.dec || 0)} (${Math.round((g.v / total) * 100)}%)`, g.name, g.color);
      s.append(p); a0 = a1;
    });
  }
  const t1 = svg("text", { x: cx, y: cy + 4, class: "dash-donut-n", "text-anchor": "middle" }); t1.textContent = centre;
  const t2 = svg("text", { x: cx, y: cy + 24, class: "dash-donut-c", "text-anchor": "middle" }); t2.textContent = caption;
  s.append(t1, t2);
  return s;
}

/* stacked columns per week: weeks [{label, parts:[{v,color,name}]}] */
function columns(weeks, opts = {}) {
  const W = D.chartW, Hh = 190, left = 30, right = 6, top = 10, bottom = 26;
  const totals = weeks.map((w) => w.parts.reduce((a, p) => a + p.v, 0));
  const rawMax = Math.max(1, ...totals), step = rawMax <= 5 ? 1 : Math.ceil(rawMax / 4);
  const max = Math.ceil(rawMax / step) * step;
  const y = (v) => top + (1 - v / max) * (Hh - top - bottom);
  const band = (W - left - right) / weeks.length, bw = Math.min(24, band * 0.62);
  const s = svg("svg", { viewBox: `0 0 ${W} ${Hh}`, class: "dash-svg", role: "group" });
  for (let v = 0; v <= max; v += step) {
    s.append(svg("line", { x1: left, x2: W - right, y1: y(v), y2: y(v), class: v === 0 ? "dash-axis" : "dash-grid" }));
    const t = svg("text", { x: left - 6, y: y(v) + 4, class: "dash-tick", "text-anchor": "end" }); t.textContent = fmtN(v); s.append(t);
  }
  weeks.forEach((w, i) => {
    const x0 = left + i * band + (band - bw) / 2;
    let acc = 0; const parts = w.parts.filter((p) => p.v > 0);
    parts.forEach((p, j) => {
      const yTop = y(acc + p.v), yBot = y(acc) - (j > 0 ? 2 : 0), hh = Math.max(0, yBot - yTop);
      const last = j === parts.length - 1, rad = Math.min(4, hh / 2, bw / 2);
      const d = last ? `M${x0},${yBot} v${-(hh - rad)} a${rad},${rad} 0 0 1 ${rad},${-rad} h${bw - 2 * rad} a${rad},${rad} 0 0 1 ${rad},${rad} v${hh - rad} z`
                     : `M${x0},${yBot} v${-hh} h${bw} v${hh} z`;
      const seg = svg("path", { d, fill: p.color });
      hover(seg, fmtN(p.v), `${w.label} - ${p.name}`, p.color);
      s.append(seg); acc += p.v;
    });
    const every = band < 34 ? 3 : 2;
    if ((weeks.length - 1 - i) % every === 0) {                   // every 2nd/3rd week label, always the latest
      const t = svg("text", { x: x0 + bw / 2, y: Hh - 8, class: "dash-tick", "text-anchor": "middle" }); t.textContent = w.label; s.append(t);
    }
  });
  return s;
}

/* ------------------------------------------------------------------ data */
async function load(force) {
  if (!force && D.maint && Date.now() - D.loadedAt < 30000) return;
  const [m, j, hi] = await Promise.all([api("GET", "/api/maint"), api("GET", "/api/dash/jobs").catch(() => null),
                                       api("GET", "/api/maint/history").catch(() => null)]);
  Object.assign(D, { maint: m, jobs: j, hist: hi, loadedAt: Date.now() });
}

/* worst state first: overdue > held (own status) > due soon > snoozed > ok */
const RANK = { overdue: 0, held: 1, due_soon: 2, snoozed: 3, ok: 4, paused: 5, done: 6 };
function taskState(t) {
  const st = t.status || {};
  if (st.hold) return { key: "held", label: st.hold.label, hex: st.hold.hex };
  const k = st.state || "ok", d = sdef(k);
  return { key: k, label: d.label, hex: d.hex };
}
const active = (t) => t.enabled !== false && !t.archived && !["done", "paused"].includes((t.status || {}).state);

/* ------------------------------------------------------------------ render */
function render() {
  const box = $("dashBody");
  if (!box || !D.maint) return;
  const colors = toolColors(), m = D.maint, mm = m.meters || {}, pr = S.printer || {};
  const tools = [...(S.tools || [])].sort((a, b) => (a.slot || 99) - (b.slot || 99));
  const mounted = tools.find((t) => t.slot === pr.mounted_slot);
  const tasks = (m.tasks || []).filter(active);
  const counts = m.counts || {};
  clear(box);

  /* ---- stat tiles ---- */
  const state = !pr.online ? "Offline" : pr.klippy !== "ready" ? (pr.klippy || "Starting") : pr.job
    ? `${pr.print_state === "paused" ? "Paused" : "Running"} ${Math.round((pr.job.progress || 0) * 100)}%` : "Ready";
  const jobsW = (D.jobs && D.jobs.weeks) || [];
  const j12 = jobsW.reduce((a, w) => ({ c: a.c + w.completed, n: a.n + w.completed + w.cancelled + w.error }), { c: 0, n: 0 });
  const tile = (label, value, sub, cls, dotC) => h("div", { class: "dash-tile" + (cls ? " " + cls : "") },
    h("div", { class: "dash-tile-l", text: label }), h("div", { class: "dash-tile-v" }, dotC ? dotEl(dotC) : null, value),
    sub ? h("div", { class: "dash-tile-s", text: sub }) : null);
  const ud = perDay(mm.machine, "prod_h");
  box.append(h("div", { class: "dash-tiles" },
    tile("Machine", state, mounted ? `${mounted.name} mounted` : "No tool confirmed", pr.job ? "live" : "", mounted ? colors[mounted.name] : null),
    tile("Production hours", fmtH(meter(mm.machine, "prod_h")), ud ? `about ${fmtN(ud, 1)} h a day` : "jobs running, pauses not counted"),
    tile("Jobs", fmtN(meter(mm.machine, "jobs")), j12.n ? `${Math.round((j12.c / j12.n) * 100)}% finished, last 12 weeks` : "finished jobs"),
    tile("Filament used", fmtLen(meter(mm.machine, "filament_m")), `${fmtN(meter(mm.machine, "swaps"))} tool swaps`),
    tile("Overdue", fmtN(counts.overdue || 0), counts.overdue ? "maintenance past due" : "nothing past due", counts.overdue ? "st bad" : "st"),
    tile("Due soon", fmtN(counts.due_soon || 0), counts.held ? `${counts.held} on hold` : "inside the early alarm", counts.due_soon ? "st warn" : "st")));

  const left = h("section", { class: "dash-col", "aria-labelledby": "dashToolsH" }, h("h2", { class: "dash-col-h", id: "dashToolsH", text: "Toolheads" }));
  const right = h("section", { class: "dash-col", "aria-labelledby": "dashMaintH" }, h("h2", { class: "dash-col-h", id: "dashMaintH", text: "Maintenance" }));
  box.append(h("div", { class: "dash-cols" }, left, right));
  D.chartW = Math.max(280, Math.round(left.clientWidth - 34));     // draw at real size, so text stays readable on a phone

  /* ---- LEFT 1: hours by toolhead ---- */
  const tm = mm.tools || {};
  const prodC = CAT[mode()][0], idleC = mode() === "light" ? "#a9c9ef" : "#2c4f78";
  const hrRows = tools.map((t) => {
    const mh = meter(tm[t.name], "mounted_h"), ph = Math.min(mh, meter(tm[t.name], "prod_h"));
    return { label: t.name, parts: [{ v: ph, color: prodC, name: "Producing" }, { v: Math.max(0, mh - ph), color: idleC, name: "Mounted, not producing" }] };
  });
  left.append(chartCard("hours", "Hours by toolhead", "Time each tool has been mounted, and how much of it was spent on jobs",
    hbars(hrRows, { fmt: fmtH, aria: "Hours by toolhead" }), [[prodC, "Producing"], [idleC, "Mounted, not producing"]],
    tools.map((t) => [t.name, fmtH(meter(tm[t.name], "prod_h")), fmtH(meter(tm[t.name], "mounted_h"))]), ["Toolhead", "Producing", "Mounted"]));

  /* ---- LEFT 2: jobs by toolhead ---- */
  const jobSegs = tools.map((t) => ({ v: meter(tm[t.name], "jobs"), color: colors[t.name], name: t.name }));
  const jobsTotal = jobSegs.reduce((a, g) => a + g.v, 0);
  const jl = h("div", { class: "dash-donut-wrap" }, donut(jobSegs, fmtN(jobsTotal), "jobs"),
    h("ul", { class: "dash-list" }, jobSegs.map((g) => h("li", {}, dotEl(g.color), h("span", { class: "dash-list-l", text: g.name }),
      h("span", { class: "dash-list-v", text: `${fmtN(g.v)}  ·  ${jobsTotal ? Math.round((g.v / jobsTotal) * 100) : 0}%` })))));
  left.append(chartCard("jobs", "Jobs by toolhead", "Finished jobs run with each tool", jl, null,
    jobSegs.map((g) => [g.name, fmtN(g.v), (jobsTotal ? Math.round((g.v / jobsTotal) * 100) : 0) + "%"]), ["Toolhead", "Jobs", "Share"]));

  /* ---- LEFT 3: toolhead cards with their maintenance health ---- */
  const byAsset = {};
  tasks.forEach((t) => { (byAsset[t.asset] = byAsset[t.asset] || []).push(t); });
  const health = (asset) => {
    const list = (byAsset[asset] || []).slice().sort((a, b) => (RANK[taskState(a).key] - RANK[taskState(b).key]) || ((b.status || {}).fraction || 0) - ((a.status || {}).fraction || 0));
    return list[0] || null;
  };
  const cards = h("div", { class: "dash-tools" });
  tools.forEach((t) => {
    const worst = health("tool:" + t.name), ws = worst ? taskState(worst) : null;
    const isOn = mounted && mounted.name === t.name;
    const c = h("button", { class: "dash-tool" + (isOn ? " on" : ""), type: "button", title: `Open ${t.name}'s maintenance tasks`,
      onclick: () => { if (window.RH.openAssetTasks) window.RH.openAssetTasks("tool:" + t.name); else window.RH.showView("mtasks"); } },
      h("div", { class: "dash-tool-h" }, dotEl(colors[t.name]), h("strong", { text: t.name }), isOn ? h("span", { class: "badge slot", text: "Mounted" }) : null),
      h("div", { class: "muted small", text: `${t.category_label || ""} · ${t.kind || t.type}` }),
      h("div", { class: "dash-tool-stats" },
        h("span", {}, h("b", { text: fmtN(meter(tm[t.name], "jobs")) }), " jobs"),
        h("span", {}, h("b", { text: fmtH(meter(tm[t.name], "prod_h")) }), " producing"),
        h("span", {}, h("b", { text: fmtN(meter(tm[t.name], "mounts")) }), " mounts")));
    if (ws) {
      const f = Math.min(1, (worst.status || {}).fraction || 0);
      const bar = h("div", { class: "progress thin dash-meter" }, h("div", { class: "progress-bar" }));
      bar.firstChild.style.width = Math.round(f * 100) + "%"; bar.firstChild.style.background = ws.hex;
      const p = h("span", { class: "badge pill dash-pill", text: `${ICON[ws.key] || ""} ${ws.label}` }); p.style.setProperty("--pill", ws.hex);
      c.append(h("div", { class: "dash-tool-m" }, p, h("span", { class: "small dash-tool-next", text: worst.title })), bar,
        h("div", { class: "hint", text: ((worst.status || {}).next || {}).text || "" }));
    } else {
      c.append(h("div", { class: "hint dash-tool-m", text: "No maintenance tasks yet - assign a Task Book in the Task Library." }));
    }
    cards.append(c);
  });
  left.append(h("div", { class: "card dash-card" }, h("div", { class: "dash-card-head" }, h("div", {}, h("h2", { text: "Toolheads at a glance" }),
    h("div", { class: "muted small", text: "Use per tool, and its most urgent maintenance task. Select one to see its tasks." }))), cards));

  /* ---- RIGHT 1: task status donut ---- */
  const order = ["overdue", "held", "due_soon", "snoozed", "ok"];
  const groups = {};
  tasks.forEach((t) => { const s = taskState(t); const k = s.key === "held" ? "held:" + s.label : s.key;
    (groups[k] = groups[k] || { v: 0, color: s.hex, name: s.label, key: s.key }).v += 1; });
  const statSegs = Object.values(groups).sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  const need = (counts.overdue || 0) + (counts.due_soon || 0);
  const sl = h("div", { class: "dash-donut-wrap" }, donut(statSegs, fmtN(need), need === 1 ? "needs attention" : "need attention"),
    h("ul", { class: "dash-list" }, statSegs.length ? statSegs.map((g) => h("li", {}, dotEl(g.color),
      h("span", { class: "dash-list-l", text: `${ICON[g.key] || ""} ${g.name}` }), h("span", { class: "dash-list-v", text: fmtN(g.v) })))
      : h("li", { class: "muted", text: "No tasks yet" })));
  right.append(chartCard("status", "Task status", `${fmtN(tasks.length)} active tasks on the machine and its tools`, sl, null,
    statSegs.map((g) => [g.name, fmtN(g.v)]), ["Status", "Tasks"]));

  /* ---- RIGHT 2: next up ---- */
  const next = tasks.slice().sort((a, b) => (RANK[taskState(a).key] - RANK[taskState(b).key]) || (((b.status || {}).fraction || 0) - ((a.status || {}).fraction || 0))).slice(0, 6);
  const nl = h("ul", { class: "dash-next" });
  next.forEach((t) => {
    const s = taskState(t), f = Math.min(1, (t.status || {}).fraction || 0);
    const p = h("span", { class: "badge pill dash-pill", text: `${ICON[s.key] || ""} ${s.label}` }); p.style.setProperty("--pill", s.hex);
    const bar = h("div", { class: "progress thin dash-meter" }, h("div", { class: "progress-bar" }));
    bar.firstChild.style.width = Math.round(f * 100) + "%"; bar.firstChild.style.background = s.hex;
    const tool = (t.asset || "").startsWith("tool:") ? t.asset.slice(5) : null;
    nl.append(h("li", {}, h("div", { class: "dash-next-h" }, h("strong", { text: t.title }), p),
      h("div", { class: "small muted dash-next-a" }, tool && colors[tool] ? dotEl(colors[tool]) : null, t.asset_label || ""), bar,
      h("div", { class: "hint", text: ((t.status || {}).next || {}).text || "" })));
  });
  right.append(h("div", { class: "card dash-card" }, h("div", { class: "dash-card-head" }, h("div", {}, h("h2", { text: "Next up" }),
    h("div", { class: "muted small", text: "The most urgent tasks; the bar shows how far each is through its interval" })),
    h("button", { class: "btn ghost small", type: "button", text: "All tasks", onclick: () => window.RH.showView("mdue") })),
    next.length ? nl : h("p", { class: "muted", text: "No maintenance tasks yet." })));

  /* ---- RIGHT 3: tasks by asset ---- */
  const assets = [...new Set(tasks.map((t) => t.asset.startsWith("machine") ? "machine" : t.asset))];
  const label = (a) => a === "machine" ? "Machine" : a.startsWith("tool:") ? a.slice(5) : (tasks.find((t) => t.asset === a) || {}).asset_label || a;
  const stOrder = ["overdue", "held", "due_soon", "snoozed", "ok"];
  const keyOf = (t) => taskState(t).key;
  const assetRows = assets.sort((a, b) => (a === "machine" ? -1 : b === "machine" ? 1 : 0)).map((a) => {
    const list = tasks.filter((t) => (t.asset.startsWith("machine") ? "machine" : t.asset) === a);
    return { label: label(a), parts: stOrder.map((k) => ({ v: list.filter((t) => keyOf(t) === k).length,
      color: k === "held" ? "#8e24aa" : sdef(k).hex, name: k === "held" ? "On hold" : sdef(k).label })) };
  });
  const used = stOrder.filter((k) => assetRows.some((r) => r.parts[stOrder.indexOf(k)].v));
  right.append(chartCard("assets", "Tasks by machine and toolhead", "How many tasks each has, by status",
    assetRows.length ? hbars(assetRows, { fmt: (v) => fmtN(v), aria: "Tasks by asset" }) : h("p", { class: "muted", text: "No tasks yet." }),
    used.map((k) => [k === "held" ? "#8e24aa" : sdef(k).hex, k === "held" ? "On hold" : sdef(k).label]),
    assetRows.map((r) => [r.label, ...r.parts.map((p) => p.v)]), ["", ...stOrder.map((k) => k === "held" ? "On hold" : sdef(k).label)]));

  /* ---- bottom pair, one per side: jobs per week | work logged per week ---- */
  const wkLabel = (ts) => new Date(ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
  const good = "#0ca30c", warnC = "#fab219", crit = "#d03b3b";
  if (D.jobs && D.jobs.available !== false) {
    const wk = jobsW.map((w) => ({ label: wkLabel(w.start), parts: [{ v: w.completed, color: good, name: "Finished" },
      { v: w.cancelled, color: warnC, name: "Cancelled" }, { v: w.error, color: crit, name: "Failed" }] }));
    left.append(chartCard("jobsweek", "Jobs per week", "Last 12 weeks, from Moonraker's job history", columns(wk),
      [[good, "✓ Finished"], [warnC, "■ Cancelled"], [crit, "! Failed"]],
      jobsW.map((w) => [wkLabel(w.start), w.completed, w.cancelled, w.error, fmtH(w.hours)]), ["Week of", "Finished", "Cancelled", "Failed", "Job hours"]));
  } else {
    left.append(h("div", { class: "card dash-card" }, h("h2", { text: "Jobs per week" }), h("p", { class: "muted", text: "Moonraker's job history is not available." })));
  }
  const recs = ((D.hist && D.hist.records) || []);
  const start0 = jobsW.length ? jobsW[0].start : (Date.now() / 1000 - 84 * 86400);
  const wkStarts = jobsW.length ? jobsW.map((w) => w.start) : Array.from({ length: 12 }, (_, i) => start0 + i * 7 * 86400);
  const work = wkStarts.map((s) => ({ s, done: 0, skip: 0 }));
  recs.forEach((r) => {
    const t = r.at || 0; if (t < wkStarts[0]) return;
    const i = Math.min(work.length - 1, Math.floor((t - wkStarts[0]) / (7 * 86400)));
    if (r.action === "done") work[i].done++; else if (r.action === "skip" || r.action === "skipped") work[i].skip++;
  });
  const doneC = sdef("ok").hex, skipC = OTHER;
  right.append(chartCard("workweek", "Maintenance logged per week", "Last 12 weeks, from the work log",
    columns(work.map((w) => ({ label: wkLabel(w.s), parts: [{ v: w.done, color: doneC, name: "Done" }, { v: w.skip, color: skipC, name: "Skipped" }] }))),
    [[doneC, "✓ Done"], [skipC, "Skipped"]], work.map((w) => [wkLabel(w.s), w.done, w.skip]), ["Week of", "Done", "Skipped"]));

  $("dashUpdated").textContent = "Updated " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

async function refreshDash(force) {
  if (window.RH.currentView() !== "dash") return;
  try { await load(force); } catch (e) { const b = $("dashBody"); if (b && !D.maint) clear(b).append(h("p", { class: "empty", text: e.message })); return; }
  try { render(); }
  catch (e) {                                  // never leave the page stuck on "Loading...": say what broke
    const b = $("dashBody");
    if (b) clear(b).append(h("div", { class: "card" }, h("h2", { text: "The dashboard could not be drawn" }),
      h("p", { class: "muted", text: "Please send this line to get it fixed:" }), h("pre", { class: "cfg-preview bad", text: String(e && e.stack || e) })));
  }
}
document.addEventListener("rhino:view", (e) => { if (e.detail === "dash") refreshDash(true); });
document.addEventListener("rhino:state", () => { if (window.RH.currentView() === "dash") { if (Date.now() - D.loadedAt > 30000) refreshDash(true); else render(); } });
document.addEventListener("rhino:theme", () => { if (window.RH.currentView() === "dash") render(); });
window.addEventListener("scroll", hideTip, { passive: true });
let resizeT = 0, lastW = 0;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => {
  if (window.RH.currentView() === "dash" && Math.abs(window.innerWidth - lastW) > 40) { lastW = window.innerWidth; render(); } }, 250); });
})();
