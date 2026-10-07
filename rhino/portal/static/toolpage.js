/* Rhino portal - a toolhead's own page, laid out like its pages in the user manual: the facts, the
   tool connector and its pin table, materials and macros on the left; the tool's picture on the right.
   Everything goes in through textContent; the connector drawing is SVG built here.                  */
(() => {
"use strict";
const { h, clear, api, S } = window.RH;
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const T = { data: null, showAll: false, photo: 0 };

function svg(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  kids.flat().forEach((k) => k && el.append(k));
  return el;
}

/* the 21W4 D-sub as drawn in the manual: big contacts 1, 2 (left) and 11, 12 (right); top row 3-10 and 13;
   bottom row 21 ... 14. Contacts this tool uses are filled; each has a tooltip with what it does. */
const TOP = [3, 4, 5, 6, 7, 8, 9, 10, 13], BOT = [21, 20, 19, 18, 17, 16, 15, 14];
function connector(contacts, onPick) {
  const by = {}; contacts.forEach((c) => { by[c.contact] = c; });
  const s = svg("svg", { viewBox: "0 0 560 124", class: "tp-conn", role: "img", "aria-label": "Tool connector, contacts this tool uses are filled" });
  s.append(svg("path", { d: "M14 12 Q8 12 9 18 L40 104 Q42 110 48 110 L512 110 Q518 110 520 104 L551 18 Q552 12 546 12 Z", class: "tp-shell" }),
           svg("path", { d: "M24 20 L52 100 L508 100 L536 20 Z", class: "tp-shell-in" }));
  const pin = (n, x, y, r) => {
    const c = by[n] || {}, used = !!c.used;
    const g = svg("g", { class: "tp-pin" + (used ? " on" : ""), tabindex: "0", "data-contact": n });
    const t = svg("title"); t.textContent = `Contact ${n}: ${c.use || c.label || "not used"}${c.pin ? " (" + c.pin + ")" : ""}`;
    g.append(t, svg("circle", { cx: x, cy: y, r, class: "tp-pin-c" }));
    if (r > 12) g.append(svg("circle", { cx: x, cy: y, r: r - 4, class: "tp-pin-ring" }));
    const lab = svg("text", { x, y: y + r + 11, "text-anchor": "middle", class: "tp-pin-n" }); lab.textContent = n; g.append(lab);
    g.addEventListener("click", () => onPick(n)); g.addEventListener("keydown", (e) => { if (e.key === "Enter") onPick(n); });
    s.append(g);
  };
  pin(1, 75, 58, 17); pin(2, 120, 58, 17);
  TOP.forEach((n, i) => pin(n, 160 + i * 30, 38, 9.5));
  BOT.forEach((n, i) => pin(n, 175 + i * 30, 76, 9.5));
  pin(11, 440, 58, 17); pin(12, 485, 58, 17);
  return s;
}

function card(title, ...kids) { return h("section", { class: "card tp-card" }, h("h2", { text: title }), ...kids); }

function render() {
  const d = T.data, box = $("toolPage");
  if (!d || !box) return;
  clear(box);
  const mounted = (S.printer || {}).mounted_slot === d.slot;

  /* header */
  const actions = h("div", { class: "head-actions" },
    h("button", { class: "btn ghost", type: "button", text: "Maintenance tasks",
      onclick: () => (window.RH.openAssetTasks ? window.RH.openAssetTasks("tool:" + d.name) : window.RH.showView("mtasks")) }),
    d.builtin ? null : h("button", { class: "btn", type: "button", text: "Edit tool", onclick: () => window.RH.openEditor(d.name) }));
  box.append(h("div", { class: "tp-head" },
    h("div", {}, h("h1", { text: d.name }),
      h("div", { class: "tags" }, h("span", { class: "badge slot", text: "Slot " + d.slot }),
        h("span", { class: "badge builtin", text: d.builtin ? "Built-in" : "Added tool" }),
        mounted ? h("span", { class: "badge slot", text: "Mounted" }) : null,
        h("span", { class: "muted small", text: (d.category_label ? d.category_label + " · " : "") + d.kind }))),
    actions));

  const left = h("div", { class: "tp-left" }), right = h("div", { class: "tp-right" });
  box.append(h("div", { class: "tp-grid" }, left, right));

  /* about */
  const facts = [["Function", d.function], ["Slot", String(d.slot)], ["Set up a job with", d.setup], ["Outputs in Klipper", d.outputs_text]];
  left.append(card("About",
    d.about ? h("p", { class: "tp-about", text: d.about }) : null,
    h("dl", { class: "review tp-facts" }, facts.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v || "-" })]))));

  /* connector + pins */
  const rows = d.contacts.filter((c) => T.showAll || c.used);
  const tbl = h("table", { class: "tbl tp-pins" },
    h("thead", {}, h("tr", {}, h("th", { class: "num", text: "Pin" }), h("th", { text: "Use on this tool" }), h("th", { text: "Board pin" }))),
    h("tbody", {}, rows.map((c) => h("tr", { class: c.used ? "" : "tp-unused", "data-contact": c.contact },
      h("td", { class: "num", text: String(c.contact) }), h("td", { text: c.used ? c.use : "-" }), h("td", { class: "mono", text: c.pin || "" })))));
  const pick = (n) => {
    tbl.querySelectorAll("tr.tp-hit").forEach((r) => r.classList.remove("tp-hit"));
    let row = tbl.querySelector(`tr[data-contact="${n}"]`);
    if (!row && !T.showAll) { T.showAll = true; render(); row = $("toolPage").querySelector(`.tp-pins tr[data-contact="${n}"]`); }
    if (row) { row.classList.add("tp-hit"); row.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
  };
  left.append(card("Tool connector",
    h("p", { class: "muted small", text: `${d.contacts.filter((c) => c.used).length} of 21 contacts used. Select a contact to find it in the table.` }),
    connector(d.contacts, pick),
    h("div", { class: "table-wrap" }, tbl),
    (d.other_pins || []).length ? h("div", { class: "tp-other" }, h("div", { class: "lbl", text: "Wired to the board outside the connector" }),
      h("ul", {}, d.other_pins.map((p) => h("li", {}, h("code", { class: "mono", text: p.pin }), " ", p.use)))) : null,
    h("button", { class: "btn ghost small tp-toggle", type: "button", text: T.showAll ? "Show only the contacts it uses" : "Show all 21 contacts",
      onclick: () => { T.showAll = !T.showAll; render(); } })));

  /* materials */
  const mc = d.material_columns || [];
  left.append(card(`Materials (${d.material_rows.length})`,
    d.material_rows.length ? h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
      h("thead", {}, h("tr", {}, h("th", { text: "Material" }), mc.map((c) => h("th", { class: "num", text: c.unit ? `${c.label} (${c.unit})` : c.label })))),
      h("tbody", {}, d.material_rows.map((m) => h("tr", {}, h("td", { text: m.label }),
        m.values.map((v) => h("td", { class: "num", text: v === "" ? "-" : v })))))))
      : h("p", { class: "muted", text: "No materials yet." }),
    h("p", { class: "hint", text: d.builtin ? "Built-in materials are set in variables.cfg." : "Change materials with Edit tool." })));

  /* macros */
  left.append(card("Macros for this tool",
    d.macro_list.length ? h("ul", { class: "tp-macros" }, d.macro_list.map((m) => h("li", {},
      h("code", { class: "mono", text: m.name }), m.description ? h("span", { class: "muted small", text: m.description }) : null)))
      : h("p", { class: "muted", text: "No macros of its own." })));

  /* picture */
  const pics = d.builtin ? (d.image ? [d.image] : []) : d.photos;
  const big = d.image_dark   // built-in drawings: transparent line art, black lines in light mode, white in dark mode
    ? [h("img", { class: "tp-img th-light", src: d.image, alt: d.name }), h("img", { class: "tp-img th-dark", src: d.image_dark, alt: d.name })]
    : pics.length ? h("img", { class: "tp-img", src: pics[Math.min(T.photo, pics.length - 1)], alt: d.name })
    : h("div", { class: "tp-img tp-noimg", text: d.builtin ? "No picture" : "No picture yet - add one with Edit tool" });
  right.append(h("figure", { class: "tp-fig" }, h("div", { class: "tp-plate" + (d.image_dark ? " lineart" : "") }, big),
    pics.length > 1 ? h("div", { class: "thumbs" }, pics.map((p, i) => h("button", { class: "tp-thumb" + (i === T.photo ? " on" : ""), type: "button",
      onclick: () => { T.photo = i; render(); } }, h("img", { src: p, alt: `${d.name} photo ${i + 1}`, loading: "lazy" })))) : null,
    d.image_notes.length ? h("figcaption", {}, d.image_notes.map((n) => h("div", { text: "*" + n }))) : null));
}

async function load() {
  const name = window.RH.currentToolName();
  if (!name) return;
  if (!T.data || T.data.name !== name) { T.showAll = false; T.photo = 0; clear($("toolPage")).append(h("p", { class: "empty", text: "Loading..." })); }
  try { T.data = await api("GET", "/api/tools/" + encodeURIComponent(name) + "/sheet"); render(); }
  catch (e) { clear($("toolPage")).append(h("p", { class: "empty", text: e.message })); }
}
document.addEventListener("rhino:view", (e) => { if (e.detail === "tool") load(); });
document.addEventListener("rhino:state", () => { if (window.RH.currentView() === "tool" && T.data) load(); });
document.querySelectorAll("[data-view-link]").forEach((b) => { b.onclick = () => window.RH.showView(b.dataset.viewLink); });
})();
