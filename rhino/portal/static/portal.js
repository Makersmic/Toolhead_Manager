/* Rhino tool manager front end. No frameworks, no inline HTML: everything is built with
   textContent, so nothing a user types (tool names, notes) can ever run as markup.

   Sections:  1 helpers   2 api   3 library & pins   4 add wizard   5 editor   6 boot            */
(() => {
"use strict";

/* ============================ 1. helpers ============================ */
const $ = (id) => document.getElementById(id);
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") { el.className = v; if (v === "table-wrap") { el.tabIndex = 0; el.setAttribute("role", "region"); el.setAttribute("aria-label", "Table (scrolls sideways)"); } }
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false)
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
const pct = (x) => Math.round(Number(x) * 1000) / 10;      // 0.45 -> 45
const frac = (x) => Number(x) / 100;                         // 45 -> 0.45
let toastTimer;
function toast(msg, isError = false, action = null) {      // action: [label, fn] adds one button
  const t = clear($("toast")); t.append(h("span", { text: msg }));
  if (action) t.append(h("button", { class: "btn small", text: action[0], onclick: () => { t.classList.add("hidden"); action[1](); } }));
  t.className = "toast" + (isError ? " error" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), isError ? 8000 : action ? 9000 : 3500);
}
function showError(boxId, msg) { const b = $(boxId); b.textContent = msg || ""; b.classList.toggle("hidden", !msg); }

/* ============================ 2. api ============================ */
const TOKEN = document.querySelector('meta[name="rhino-token"]').content;
async function api(method, url, body) {
  const opt = { method, headers: { "X-Rhino-Token": TOKEN } };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let res, data;
  try { res = await fetch(url, opt); data = await res.json(); }
  catch (e) { throw new Error("Cannot reach the portal - is it still running?"); }
  if (!res.ok || data.ok === false) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* ============================ 3. library & pins ============================ */
const S = { tools: [], pins: null, printer: {}, pending: false, pendingInfo: null, options: null, fetchedAt: 0, clockSkew: 0 };

async function refresh() {
  const d = await api("GET", "/api/state");
  Object.assign(S, { tools: d.tools, pins: d.pins, printer: d.printer, pending: d.restart_pending, pendingInfo: d.pending,
                     fetchedAt: Date.now(), clockSkew: d.server_time ? d.server_time * 1000 - Date.now() : 0 });
  renderChips(); renderLibrary(); renderPins(); renderHardware(); renderBanner();
  document.dispatchEvent(new CustomEvent("rhino:state", { detail: d }));
}

/* ---- restart banner: what is waiting, why the restart is blocked, and when the job ends ---- */
function dur(sec) {
  sec = Math.max(0, Math.round(sec));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  if (hh) return `${hh} h ${String(mm).padStart(2, "0")} m`;
  if (mm) return `${mm} m ${String(ss).padStart(2, "0")} s`;
  return `${ss} s`;
}
const clock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

function renderBanner() {
  const box = $("restartBanner"), p = S.pendingInfo || {}, pr = S.printer || {}, job = pr.job;
  box.classList.toggle("hidden", !S.pending);
  if (!S.pending) return;
  const changes = p.changes || [];
  $("bannerTitle").textContent = changes.length > 1 ? `${changes.length} tool changes are saved but not live yet.`
                                                    : "Tool changes are saved but not live yet.";
  const list = clear($("bannerChanges"));
  changes.slice(-6).forEach((c) => list.append(h("li", { text: c })));
  if (changes.length > 6) list.append(h("li", { text: `and ${changes.length - 6} earlier change(s)` }));
  const blocked = !!pr.restart_blocked, btn = $("restartBtn");
  btn.disabled = blocked || !pr.online;
  btn.title = blocked ? "Restarting Klipper now would stop the job." : "";
  if (!pr.online) $("bannerWhy").textContent = "Moonraker is offline, so the portal cannot restart Klipper. Restart it from Mainsail.";
  else if (blocked) $("bannerWhy").textContent = `Klipper loads them at its next restart, which waits until the job ${pr.print_state === "paused" ? "is finished (it is paused now)" : "finishes"} - restarting now would stop it.`;
  else if (p.restart_at) $("bannerWhy").textContent = "The job has finished. Klipper restarts by itself in a moment.";
  else $("bannerWhy").textContent = "Klipper has to restart to load them. The machine is idle, so it is safe now.";
  $("bannerJob").classList.toggle("hidden", !(blocked && job));
  $("autoRestartLbl").classList.toggle("hidden", !blocked);
  $("autoRestart").checked = !!p.auto_restart;
  $("bannerNote").textContent = p.note || "";
  $("bannerNote").classList.toggle("hidden", !p.note);
  tickBanner();
}

function tickBanner() {
  if (!S.pending) return;
  const pr = S.printer || {}, job = pr.job, p = S.pendingInfo || {};
  const since = (Date.now() - S.fetchedAt) / 1000, running = pr.print_state === "printing";
  if (p.restart_at && !pr.restart_blocked) {
    const left = p.restart_at - (Date.now() + S.clockSkew) / 1000;
    $("bannerWhy").textContent = left > 0 ? `The job has finished. Klipper restarts by itself in ${dur(left)}.` : "Restarting Klipper...";
  }
  if (!job || !pr.restart_blocked) return;
  const name = job.filename || "a job";
  const t = job.timing || {}, prog = Math.max(0, Math.min(1, job.progress || 0));
  $("bannerJobLine").textContent = (pr.print_state === "paused" ? "Paused: " : "Running: ") + name;
  $("bannerProgress").style.width = (prog * 100).toFixed(1) + "%";
  const elapsed = (t.elapsed || 0) + (running ? since : 0);
  const parts = [`${Math.round(prog * 100)}%`, `${dur(elapsed)} elapsed`];
  if (t.remaining != null) {
    const rem = Math.max(0, t.remaining - (running ? since : 0));
    parts.push(`about ${dur(rem)} left`);
    if (running) parts.push(`restart possible at about ${clock(Date.now() + rem * 1000)}`);
    if (t.method === "file") parts.push("(estimated from file progress)");
  } else parts.push("time left unknown - this file has no time estimate yet");
  if (pr.print_state === "paused") {
    const ps = job.paused_since ? ((Date.now() + S.clockSkew) / 1000 - job.paused_since) : null;
    parts.push(ps != null ? `paused for ${dur(ps)} - the timer is stopped` : "the timer is stopped while paused");
  }
  $("bannerJobTimes").textContent = parts.join(" · ");
}

async function setAutoRestart(on) {
  try { await api("POST", "/api/restart/auto", { on }); toast(on ? "Klipper will restart when the job finishes." : "Automatic restart cancelled."); }
  catch (e) { toast(e.message, true); }
  refresh().catch(() => {});
}
async function loadOptions() { S.options = await api("GET", "/api/options"); return S.options; }

function renderChips() {
  const p = S.printer, box = clear($("statusChips"));
  const chip = (text, cls) => box.append(h("span", { class: "chip " + cls, text }));
  if (!p.online) return chip("Moonraker offline", "bad");
  chip("Klipper: " + p.klippy, p.klippy === "ready" ? "ok" : "bad");
  if (p.klippy === "ready") {
    chip("Job: " + p.print_state, p.restart_blocked ? "warn" : "");
    const m = S.tools.find((t) => t.slot === p.mounted_slot);
    chip("Mounted: " + (m ? m.name : "none"), m ? "ok" : "");
  }
}

function renderLibrary() {
  /* compact cards: picture, name, what it is - the whole card opens the tool's own page */
  const grid = clear($("toolGrid"));
  const mounted = (S.printer || {}).mounted_slot;
  for (const t of S.tools) {
    const pic = t.image_dark ? [h("img", { class: "tc-img th-light", src: t.image, alt: "", loading: "lazy" }),   // line art: follows the theme
                                h("img", { class: "tc-img th-dark", src: t.image_dark, alt: "", loading: "lazy" })]
              : t.image ? h("img", { class: "tc-img", src: t.image, alt: "", loading: "lazy" })
              : h("span", { class: "tc-img tc-none", text: t.name.slice(0, 2) });
    const facts = [`${t.materials.length} material${t.materials.length === 1 ? "" : "s"}`,
                   t.macros && t.macros.length ? `${t.macros.length} macro${t.macros.length === 1 ? "" : "s"}` : null,
                   t.builtin ? "built-in" : "added"].filter(Boolean).join("  \u00B7  ");
    grid.append(h("button", { class: "tool-card" + (t.slot === mounted ? " on" : ""), type: "button",
        title: `Open ${t.name}`, onclick: () => openTool(t.name) },
      h("span", { class: "tc-pic" + (t.image_dark ? " lineart" : "") }, pic),
      h("span", { class: "tc-body" },
        h("span", { class: "tc-head" }, h("strong", { class: "tc-name", text: t.name }), h("span", { class: "badge slot", text: "Slot " + t.slot })),
        h("span", { class: "tc-kind", text: (t.category_label ? t.category_label + " \u00B7 " : "") + t.kind }),
        t.function && t.function !== t.kind ? h("span", { class: "tc-fn", text: t.function }) : null,
        h("span", { class: "tc-facts", text: facts }),
        t.slot === mounted ? h("span", { class: "badge slot tc-mounted", text: "Mounted" }) : null)));
  }
  if (!S.tools.length) grid.append(h("div", { class: "card empty", text: "No tools found." }));
}
let currentTool = "";
function openTool(name) { currentTool = name; showView("tool"); }

function contactStrip(used) {               /* 21 little boxes, the used ones filled - like the pin map in the manual */
  const set = new Set(used || []);
  return h("span", { class: "cstrip" }, Array.from({ length: 21 }, (_, i) => h("span", { class: "cbox" + (set.has(i + 1) ? " on" : ""), text: String(i + 1) })));
}
function renderPins() {
  if (!S.pins) return;
  const KIND = { switched: "Switched output", signal: "Signal", return: "Return / -", supply: "Supply +", stepper: "Stepper", spare: "Spare" };
  const ct0 = clear($("contactTable"));
  ct0.append(h("tr", {}, ["Contact", "Board pin", "Function", "Driven by", "Tools using it"].map((x) => h("th", { text: x }))));
  for (const c of S.pins.contacts || []) ct0.append(h("tr", { class: c.warning ? "row-warn" : "" },
    h("td", { class: "num", text: String(c.contact) }), h("td", { class: "mono", text: c.pin || "-" }),
    h("td", {}, h("span", { text: c.label }), h("div", { class: "hint", text: KIND[c.kind] || c.kind })),
    h("td", {}, h("span", { class: c.output ? "mono" : "muted", text: c.output || c.used_by || c.owner || "-" }), c.warning ? h("div", { class: "hint warn-text", text: c.warning }) : null),
    h("td", { class: "small", text: (c.tools || []).join(", ") || "-" })));
  const pt = clear($("pinTable"));
  pt.append(h("tr", {}, ["Pin", "Status", "Used by"].map((x) => h("th", { text: x }))));
  for (const p of S.pins.pins) pt.append(h("tr", {}, h("td", { text: p.pin }),
    h("td", { class: "state-" + p.state, text: { free: "Free", claimed: "In use (config)", tool: "Reserved by a tool" }[p.state] }),
    h("td", { text: p.owner || "-" })));
  const ct = clear($("channelTable"));
  ct.append(h("tr", {}, ["Output", "Type", "Contact", "Idle level", "Also used by"].map((x) => h("th", { text: x }))));
  for (const c of S.pins.channels) ct.append(h("tr", {}, h("td", { text: c.name }), h("td", { text: c.pwm ? "PWM" : "On/off" }),
    h("td", { text: c.contact ? String(c.contact) : c.hardware ? "system hardware" : "-" }),
    h("td", { text: c.value == null ? "-" : String(c.value) }), h("td", { text: c.shared_with || "-" })));
  const hw = clear($("hwPinTable"));
  hw.append(h("tr", {}, ["Name", "Board pin", "Does", "Category"].map((x) => h("th", { text: x }))));
  if (!(S.pins.hardware || []).length) hw.append(h("tr", {}, h("td", { colspan: 4, class: "muted", text: "None yet." })));
  for (const x of S.pins.hardware || []) hw.append(h("tr", {}, h("td", { class: "mono", text: x.name }),
    h("td", { text: x.pin + (x.header ? ` (${x.header})` : "") }), h("td", { text: x.purpose || roleLabel(x.role) }), h("td", { text: x.category_label })));
  document.querySelectorAll(".warnbox.missing-inc").forEach((x) => x.remove());
  if (S.pins.missing_includes.length) $("contactTable").after(h("p", { class: "warnbox missing-inc",
    text: "printer.cfg is missing include files: " + S.pins.missing_includes.join(", ") }));
}

/* ---- system hardware (board pins off the umbilical) ---- */
function renderHardware() {
  const box = $("hwList"); if (!box || !S.pins) return; clear(box);
  const list = S.pins.hardware || [];
  if (!list.length) { box.append(h("div", { class: "card empty" }, h("p", { text: "No system hardware yet." }),
    h("p", { class: "muted small", text: "Add enclosure fans and lights, an air or vacuum pump, a door switch... anything wired to the board rather than the tool connector." }),
    h("button", { class: "btn", type: "button", text: "+ Add system hardware", onclick: () => openHardware(null) }))); return; }
  const groups = {};
  for (const x of list) (groups[x.category_label] = groups[x.category_label] || []).push(x);
  for (const [cat, items] of Object.entries(groups)) {
    box.append(h("h2", { class: "group-title", text: cat }), h("div", { class: "grid" }, items.map((x) => h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h2", { class: "mono", text: x.name }), h("span", { class: "badge slot", text: x.pin + (x.header ? " · " + x.header : "") })),
      h("div", { class: "muted small", text: (x.purpose ? x.purpose + " - " : "") + describeControl(x) }),
      x.macros.length ? h("div", { class: "tags" }, x.macros.map((m) => h("span", { class: "badge", text: m }))) : null,
      x.notes ? h("div", { class: "note", text: x.notes }) : null,
      h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "Edit", onclick: () => openHardware(x) }),
        h("button", { class: "btn ghost small", type: "button", text: "Maintenance", onclick: () => window.RH.openAssetTasks && window.RH.openAssetTasks("hw:" + x.name) }))))));
  }
}
async function openHardware(x) {
  try { await loadOptions(); } catch (e) { return toast(e.message, true); }
  const list = [], opt = { hardware: true, toolName: () => "system hardware", reqBase: () => ({}), pinsTaken: () => [], pinsMine: () => (x ? [x.pin] : []),
    redraw: () => {}, original: x ? x.name : "" };
  if (x) { list.push(JSON.parse(JSON.stringify(x))); openControl(list, 0, opt); }
  else openControl(list, -1, opt);
}
async function deleteHardware() {
  const name = X.item.original;
  if (!X.confirmDel) { X.confirmDel = true; $("itemDelete").textContent = `Click again to remove ${name}`; return; }
  try { await api("DELETE", "/api/hardware/" + encodeURIComponent(name)); closeModal("itemModal"); await refresh(); toast(`${name} removed. Restart Klipper to apply.`); }
  catch (e) { showError("itemError", e.message); }
}

function focusables(root) {
  return [...root.querySelectorAll('button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
    .filter((e) => !e.disabled && e.offsetParent !== null);
}
let currentView = "dash";
function showView(name) {
  currentView = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== "view-" + name));
  document.querySelectorAll(".nav-btn[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
    if (b.dataset.view === name) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  const btn = document.querySelector(`.nav-btn[data-view="${name}"]`), g = btn && btn.closest(".nav-group");
  if (g && g.classList.contains("collapsed")) setGroup(g, true, false);
  setSidebar(false);
  document.dispatchEvent(new CustomEvent("rhino:view", { detail: name }));
}
function setSidebar(open) { $("sidebar").classList.toggle("open", open); $("menuBtn").setAttribute("aria-expanded", String(open)); }
/* collapsible sidebar groups; the open/closed state is a per-browser convenience only */
function navState() { try { return JSON.parse(localStorage.getItem("rhino.nav") || "{}"); } catch (e) { return {}; } }
function setGroup(g, open, remember = true) {
  g.classList.toggle("collapsed", !open); g.querySelector(".nav-group-head").setAttribute("aria-expanded", String(open));
  if (!remember) return;
  try { const st = navState(); st[g.dataset.group] = open; localStorage.setItem("rhino.nav", JSON.stringify(st)); } catch (e) { /* storage blocked */ }
}
function initNav() {
  const st = navState();
  document.querySelectorAll(".nav-group").forEach((g) => {
    setGroup(g, st[g.dataset.group] !== false, false);
    g.querySelector(".nav-group-head").onclick = () => setGroup(g, g.classList.contains("collapsed"));
  });
}

/* shared form builders */
let fieldSeq = 0;
function field(label, input, hint) {     // the label (and hint) are tied to the control, so screen readers announce them
  const lab = h("label", { text: label }), tip = hint ? h("div", { class: "hint", text: hint }) : null;
  const ctl = input && input.matches && (input.matches("input,select,textarea") ? input : input.querySelector("input,select,textarea"));
  if (ctl) {
    if (!ctl.id) ctl.id = "fld" + (++fieldSeq);
    lab.htmlFor = ctl.id;
    if (tip) { tip.id = ctl.id + "-hint"; ctl.setAttribute("aria-describedby", tip.id); }
  }
  return h("div", { class: "field" }, lab, input, tip);
}
function textInput(obj, key, props = {}) {
  return h("input", { type: "text", value: obj[key] ?? "", autocomplete: "off", ...props, oninput: (e) => { obj[key] = e.target.value; props.onchange && props.onchange(); } });
}
function numInput(obj, key, props = {}) {
  return h("input", { type: "number", step: "any", value: obj[key] ?? "", ...props, oninput: (e) => { obj[key] = e.target.value; props.onchange && props.onchange(); } });
}
function selectInput(obj, key, choices, props = {}) {      // choices: [[value, label], ...]
  const s = h("select", { ...props, onchange: (e) => { obj[key] = e.target.value; props.onchange && props.onchange(e); } },
    choices.map(([v, l]) => h("option", { value: v, text: l, selected: v === obj[key] })));
  if (obj[key] === undefined || !choices.some(([v]) => v === obj[key])) obj[key] = choices.length ? choices[0][0] : "";
  return s;
}

/* material table shared by wizard + editor */
const MAT_COLS = {
  POWERED: [["power", "Power %", true], ["feed_rate", "Feed mm/min"], ["z_offset", "Z offset mm"]],
  PASSIVE: [["feed_rate", "Feed mm/min"], ["z_offset", "Z offset mm"]],
  DEPOSITION: [["extruder_temp", "Nozzle C"], ["bed_temp", "Bed C"], ["z_offset", "Z offset mm"], ["fan_speed", "Fan %", true]],
};
function materialTable(rows, ttype, canEditNames, onRemove, category) {
  const cols = MAT_COLS[ttype];
  const names = ((S.options || {}).material_names || {})[category || ""] || [];
  const listId = "matNames" + Math.random().toString(36).slice(2, 7);
  const tb = h("table", { class: "tbl" }, h("tr", {}, h("th", { text: "Material" }), cols.map(([, l]) => h("th", { text: l })), onRemove ? h("th") : null));
  const draw = (r, i) => h("tr", {},
    h("td", {}, canEditNames ? textInput(r, "name", { maxlength: 32, "aria-label": "material name", list: names.length ? listId : undefined }) : h("span", { text: r.name })),
    cols.map(([k]) => h("td", {}, numInput(r, k, { "aria-label": k }))),
    onRemove ? h("td", {}, h("button", { class: "btn ghost small", type: "button", text: "Remove", onclick: () => onRemove(i) })) : null);
  rows.forEach((r, i) => tb.append(draw(r, i)));
  return h("div", { class: "table-wrap" }, tb, names.length ? h("datalist", { id: listId }, names.map((n) => h("option", { value: n }))) : null);
}
function rowsToPayload(rows, ttype) {
  return rows.filter((r) => (r.name || "").trim()).map((r) => {
    const o = { name: r.name.trim() };
    for (const [k, , isPct] of MAT_COLS[ttype]) if (r[k] !== "" && r[k] !== undefined) o[k] = isPct ? frac(r[k]) : r[k];
    return o;
  });
}

/* ============================ 4. add wizard ============================ */
const W = { d: null, step: 0, kinds: null, creating: false };

function newDraft() {
  return { category: "", kind: "", name: "", notes: "", outputs: [{ role: "power", source: "" }], contacts: [], cycle: "0.01",
           base: "", nozzles: ["0.4"], nozzles_other: "", cap: 50, min: 0, idle: 0, max_on_s: 600, s_max: 1000, materials: [], checklist: "", photos: [],
           controls: [], macros: [] };
}
function applyKindPreset(d) {
  const p = S.options.presets[d.kind] || {};
  if (d.kind === "PRINT_HEAD" || typeOf(d) === "DEPOSITION") { d.base = d.base || S.options.print_bases[0] || ""; return; }
  d.materials = Object.entries(p.materials || {}).map(([name, m]) => ({ name, power: m.power !== undefined ? pct(m.power) : "", feed_rate: m.feed_rate, z_offset: 0 }));
  d.checklist = (p.checklist || []).join("\n");
  if (p.cap !== undefined) { d.cap = pct(p.cap); d.max_on_s = p.max_on_s; }
}
const kindOf = (d) => S.options.kinds.find((k) => k.value === d.kind) || {};
const typeOf = (d) => kindOf(d).type;
function wizSteps() {
  const t = typeOf(W.d);
  if (t === "POWERED") return ["Tool", "Outputs", "Limits", "Materials", "Controls", "Macros", "Review"];
  if (t === "PASSIVE") return ["Tool", "Connector", "Materials", "Controls", "Macros", "Review"];
  if (t === "DEPOSITION") return ["Tool", "Hardware", "Controls", "Macros", "Review"];
  return ["Tool", "Review"];
}

async function openWizard() {
  try { await loadOptions(); } catch (e) { return toast(e.message, true); }
  W.d = newDraft(); W.step = 0; W.idleTouched = false;
  showError("wizError", ""); $("wizard").classList.remove("hidden"); drawWizard();
}
function closeModal(id) { $(id).classList.add("hidden"); }

function drawWizard() {
  const steps = wizSteps(), name = steps[W.step], body = clear($("wizBody"));
  clear($("wizSteps")).append(...steps.map((s, i) => h("li", { class: i === W.step ? "on" : i < W.step ? "done" : "", text: `${i + 1}. ${s}` })));
  ({ Tool: stepTool, Outputs: stepOutputs, Hardware: stepHardware, Connector: stepConnector, Limits: stepLimits, Materials: stepMaterials,
     Controls: stepControls, Macros: stepMacros, Review: stepReview })[name](body);
  $("wizBack").classList.toggle("hidden", W.step === 0);
  $("wizNext").textContent = name === "Review" ? "Create tool" : "Next";
  $("wizNext").disabled = false;
  const first = body.querySelector("input:not([type=radio]), select, textarea"); if (first && name !== "Tool") first.focus();
}

function stepTool(b) {
  const d = W.d, o = S.options;
  const card = (c) => h("label", { class: "cat-card" + (d.category === c.value ? " on" : "") },
    h("input", { type: "radio", name: "category", checked: d.category === c.value,
      onchange: () => { d.category = c.value; const ks = o.kinds.filter((k) => k.category === c.value);
        d.kind = ks.length === 1 ? ks[0].value : ""; if (d.kind) applyKindPreset(d); drawWizard(); } }),
    h("strong", { text: c.label }), h("span", { class: "hint", text: c.help }));
  b.append(h("div", { class: "field" }, h("label", { text: "What kind of tool is it?" }), h("div", { class: "cat-row" }, o.categories.map(card))));
  if (d.category) {
    const ks = o.kinds.filter((k) => k.category === d.category);
    const sel = selectInput(d, "kind", [["", "Choose one..."], ...ks.map((k) => [k.value, k.label])], { onchange: () => { if (d.kind) applyKindPreset(d); drawWizard(); } });
    b.append(field("Which " + o.categories.find((c) => c.value === d.category).label.toLowerCase() + " tool?", sel,
      kindOf(d).help || "Pick the closest match - it sets safe starting values you can change. The list is edited under Admin > Tool lists."));
  }
  b.append(field("Name", textInput(d, "name", { maxlength: 24, placeholder: "e.g. FoamWire" }),
      "2-24 characters: letters, digits and _, starting with a letter. This is the name used in G-code and slicers."),
    field("Notes (optional)", h("textarea", { maxlength: 1000, oninput: (e) => { d.notes = e.target.value; }, text: d.notes }),
      "Wiring, supplier, settings that worked... shown on the tool card. Not sent to Klipper."));
}

/* ---- outputs: which umbilical contacts the tool drives ---- */
function outputChoices(role) {
  const o = S.options, groups = [];
  const share = o.contacts.filter((c) => c.output && (role === "switch" || c.pwm)).map((c) => {
    const ch = [...o.pwm_channels, ...o.switch_channels].find((x) => x.name === c.output) || {};
    return ["contact:" + c.contact, `Contact ${c.contact} · ${c.pin} · ${c.output} (${c.pwm ? "PWM" : "on/off"})` + (ch.shared_with ? ` - shared: ${ch.shared_with}` : "")];
  });
  if (share.length) groups.push(["Share an output already on the umbilical", share]);
  const fresh = o.free_pins.map((p) => ["pin:" + p, `New output on ${p}` + (o.free_pin_contacts[p] ? ` (contact ${o.free_pin_contacts[p]})` : " (spare pin)")]);
  if (fresh.length) groups.push(["Make a new output on a spare pin", fresh]);
  const onContact = new Set(o.contacts.map((c) => c.output).filter(Boolean));
  const chans = role === "power" ? o.pwm_channels : [...o.switch_channels, ...o.pwm_channels];
  const hw = chans.filter((c) => c.hardware && !onContact.has(c.name)).map((c) => ["output:" + c.name, `${c.name} (system hardware, ${c.pwm ? "PWM" : "on/off"})`]);
  if (hw.length) groups.push(["System hardware (switches on with the tool)", hw]);
  const other = chans.filter((c) => !c.hardware && !onContact.has(c.name)).map((c) => ["output:" + c.name,
    `${c.name} (${c.pwm ? "PWM" : "on/off"}, contact unknown)` + (c.shared_with ? ` - shared: ${c.shared_with}` : "")]);
  if (other.length) groups.push(["Other outputs in the config", other]);
  return groups;
}
function groupedSelect(obj, key, groups, placeholder, onchange) {
  const all = groups.flatMap(([, items]) => items);
  if (obj[key] && !all.some(([v]) => v === obj[key])) obj[key] = "";
  return h("select", { onchange: (e) => { obj[key] = e.target.value; onchange && onchange(); } },
    h("option", { value: "", text: placeholder }),
    groups.map(([label, items]) => h("optgroup", { label }, items.map(([v, l]) => h("option", { value: v, text: l, selected: v === obj[key] })))));
}
function outputContact(src) {
  const [k, ref] = (src || "").split(":"), o = S.options;
  if (k === "contact") return Number(ref);
  if (k === "pin") return o.free_pin_contacts[ref] || null;
  return null;
}
function stepOutputs(b) {
  const d = W.d, o = S.options;
  b.append(h("p", { class: "muted small", text: "Which umbilical contacts power and switch this tool. Most tools have a main power feed and a signal or two: " +
    "add one row per output. The main power level is what M3 S sets; switch outputs turn on with the tool and off with it (an enable line, a relay, a vacuum)." }));
  const list = h("div", { class: "x-list" });
  d.outputs.forEach((r, i) => {
    const roleSel = selectInput(r, "role", o.output_roles, { "aria-label": "output job", onchange: () => drawWizard() });
    list.append(h("div", { class: "x-row out-row" },
      h("div", { class: "out-role" }, roleSel), h("div", { class: "out-src" }, groupedSelect(r, "source", outputChoices(r.role), "Choose the contact or pin...", () => drawWizard())),
      d.outputs.length > 1 ? h("button", { class: "btn ghost small", type: "button", text: "Remove", onclick: () => { d.outputs.splice(i, 1); drawWizard(); } }) : null));
  });
  b.append(h("fieldset", {}, h("legend", { text: "Outputs" }), list,
    d.outputs.length < 6 ? h("button", { class: "btn small", type: "button", text: "+ Add an output", onclick: () => { d.outputs.push({ role: "switch", source: "" }); drawWizard(); } }) : null));
  if (d.outputs.some((r) => (r.source || "").startsWith("pin:")))
    b.append(field("PWM cycle time for a new main power pin (s)", numInput(d, "cycle"), "0.01 (100 Hz) suits heaters and most drivers; use 0.0001 for fast power stages."));
  b.append(contactPicker(d, d.outputs.map((r) => outputContact(r.source)).filter(Boolean)));
}
function stepConnector(b) {
  b.append(h("p", { class: "muted small", text: "This tool has no power output. Tick the contacts it still connects to (the probe, a sensor, the tool-present line) " +
    "so the pin map on the Pins page and in the manual is complete." }), contactPicker(W.d, []));
}
function contactPicker(d, locked) {
  const o = S.options, lock = new Set(locked), set = new Set([...d.contacts.map(Number), ...lock]);
  const grid = h("div", { class: "contact-grid" }, o.contacts.map((c) => {
    const on = set.has(c.contact), fixed = lock.has(c.contact);
    return h("label", { class: "contact-cell" + (on ? " on" : "") + (fixed ? " fixed" : ""), title: c.label + (c.pin ? ` (${c.pin})` : "") },
      h("input", { type: "checkbox", checked: on, disabled: fixed, onchange: (e) => {
        const n = c.contact; d.contacts = d.contacts.filter((x) => Number(x) !== n); if (e.target.checked) d.contacts.push(n);
        e.target.closest(".contact-cell").classList.toggle("on", e.target.checked); } }),
      h("span", { class: "cn", text: String(c.contact) }), h("span", { class: "cl", text: c.label }));
  }));
  return h("fieldset", {}, h("legend", { text: "Contacts this tool uses" }), grid,
    h("div", { class: "hint", text: "Contacts its outputs and controls drive are ticked for you. Tick the returns, supplies and signal lines it also uses." }));
}

function stepHardware(b) {
  const d = W.d, o = S.options;
  const sizes = h("div", { class: "chip-row" }, o.nozzles.map((n) => { const v = String(n);
    return h("label", { class: "chip-check" + (d.nozzles.includes(v) ? " on" : "") }, h("input", { type: "checkbox", checked: d.nozzles.includes(v),
      onchange: (e) => { d.nozzles = d.nozzles.filter((x) => x !== v); if (e.target.checked) d.nozzles.push(v); drawWizard(); } }), v + " mm"); }));
  b.append(field("Copy settings from", selectInput(d, "base", o.print_bases.map((x) => [x, x])), "Same extruder, heater and thermistor as this tool; only the nozzle size changes."),
    h("div", { class: "field" }, h("label", { text: "Nozzle sizes" }), sizes),
    field("Other sizes (mm, optional)", textInput(d, "nozzles_other", { placeholder: "0.35, 1.4" }), "Sizes not in the list. The list itself is edited under Admin > Tool lists."),
    contactPicker(d, []));
}

function stepLimits(b) {
  const d = W.d, L = S.options.limits;
  const pw = d.outputs.find((r) => r.role === "power") || {};
  if (!W.idleTouched && pw.source && !pw.source.startsWith("pin:")) {
    const c = S.options.contacts.find((x) => "contact:" + x.contact === pw.source);
    const name = c ? c.output : pw.source.slice(7);
    const ch = S.options.pwm_channels.find((x) => x.name === name);
    if (ch && ch.value != null) d.idle = pct(ch.value);
  }
  b.append(h("p", { class: "muted small", text: "These limits protect the tool. Percentages are of the output's full range. Start low and raise them while watching the tool." }),
    h("div", { class: "row" },
      field("Power cap %", numInput(d, "cap", { min: pct(L.cap[0]), max: 100 }), "Hard ceiling, whatever the G-code asks for."),
      field("Minimum power %", numInput(d, "min", { min: 0, max: 100 }), "Output at the lowest non-zero request."),
      field("Idle level %", numInput(d, "idle", { min: 0, max: 100, onchange: () => { W.idleTouched = true; } }), "Output when the tool is OFF. Leave 0 unless the driver needs a neutral signal.")),
    h("div", { class: "row" },
      field("Max time on (s)", numInput(d, "max_on_s", { min: 1, max: 3600 }), "Watchdog: output is cut after this long without a new power command."),
      field("S value for full power", numInput(d, "s_max", { min: 1 }), "G-code M3 S<value> is scaled against this (1000 = S1000 is 100%).")));
}

function stepMaterials(b) {
  const d = W.d, t = typeOf(d);
  const redraw = () => drawWizard();
  b.append(h("p", { class: "muted small", text: "Materials are the presets you pick when starting a job: what to cut or draw, and how fast." }),
    materialTable(d.materials, t, true, (i) => { d.materials.splice(i, 1); redraw(); }, d.category),
    h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "+ Add material",
      onclick: () => { d.materials.push({ name: "", power: t === "POWERED" ? 50 : undefined, feed_rate: 600, z_offset: 0 }); redraw(); } })),
    field("Pre-job checklist (one item per line)", h("textarea", { oninput: (e) => { d.checklist = e.target.value; }, text: d.checklist }),
      "Shown as a confirmation list before every job with this tool."));
}

function wizNozzles(d) {
  return [...d.nozzles, ...String(d.nozzles_other || "").split(",").map((x) => x.trim()).filter(Boolean)].join(", ");
}
function wizPayload() {
  const d = W.d, t = typeOf(d), p = { name: d.name.trim(), kind: d.kind, notes: d.notes, contacts: d.contacts };
  if (t === "POWERED") {
    p.outputs = d.outputs.filter((r) => r.source).map((r) => ({ role: r.role, source: r.source }));
    p.cycle = d.cycle;
    Object.assign(p, { cap: frac(d.cap), min: frac(d.min), idle: frac(d.idle), max_on_s: d.max_on_s, s_max: d.s_max });
  }
  if (t === "POWERED" || t === "PASSIVE") { p.materials = rowsToPayload(d.materials, t); p.checklist = d.checklist; }
  if (t === "DEPOSITION") { p.base = d.base; p.nozzles = wizNozzles(d); }
  if (t) { p.controls = d.controls; p.macros = d.macros; }
  return p;
}

function checkStep() {                        // quick local checks so the person isn't sent to the server for typos
  const d = W.d, name = wizSteps()[W.step];
  if (name === "Tool") {
    if (!d.category) return "Choose Additive, Subtractive or Passive.";
    if (!d.kind) return "Choose which kind of tool it is.";
    if (!/^[A-Za-z][A-Za-z0-9_]{1,23}$/.test(d.name.trim())) return "Name must start with a letter, use only letters, digits and _, and be 2-24 characters.";
    if (S.tools.some((x) => x.name.toLowerCase() === d.name.trim().toLowerCase())) return "A tool with that name already exists.";
  }
  if (name === "Outputs") {
    if (d.outputs.filter((r) => r.role === "power").length !== 1) return "Give the tool exactly one main power output (the PWM level M3 S sets).";
    if (d.outputs.some((r) => !r.source)) return "Choose the contact or pin for every output, or remove the empty row.";
    const srcs = d.outputs.map((r) => r.source); if (new Set(srcs).size !== srcs.length) return "The same contact is chosen twice.";
  }
  if (name === "Hardware" && !d.base) return "Choose a tool to copy settings from.";
  if (name === "Hardware" && !wizNozzles(d)) return "Choose at least one nozzle size.";
  if (name === "Limits" && Number(d.min) > Number(d.cap)) return "Minimum power cannot be above the power cap.";
  return "";
}

function describeOutput(src) {
  const [k, ref] = (src || "").split(":"), c = k === "contact" ? S.options.contacts.find((x) => x.contact === Number(ref)) : null;
  if (c) return `contact ${c.contact} (${c.pin}, ${c.output})`;
  if (k === "pin") return `new output on ${ref}` + (S.options.free_pin_contacts[ref] ? `, contact ${S.options.free_pin_contacts[ref]}` : "");
  return ref;
}
async function stepReview(b) {
  const d = W.d, p = wizPayload(), t = typeOf(d);
  $("wizNext").disabled = true;
  const dl = h("dl", { class: "review" });
  const row = (k, v) => dl.append(h("dt", { text: k }), h("dd", { text: v }));
  row("Name", p.name); row("Kind", S.options.categories.find((c) => c.value === d.category).label + " - " + kindOf(d).label);
  if (t === "POWERED") {
    row("Main power", describeOutput((d.outputs.find((r) => r.role === "power") || {}).source));
    const sw = d.outputs.filter((r) => r.role === "switch");
    row("Switch outputs", sw.map((r) => describeOutput(r.source)).join("; ") || "none");
    row("Limits", `cap ${d.cap}%, min ${d.min}%, idle ${d.idle}%, max ${d.max_on_s}s on, S${d.s_max} = full`);
  }
  if (t === "DEPOSITION") { row("Copies", d.base); row("Nozzles", p.nozzles); }
  if (p.materials) row("Materials", p.materials.map((m) => m.name).join(", ") || "-");
  if (p.controls) row("Controls", p.controls.map((c) => `${c.name} (${roleLabel(c.role)}, ${c.pin})`).join(", ") || "none");
  if (p.macros) row("Macros", [...p.macros.map((m) => m.name), ...ctlMacroNames(p.controls)].join(", ") || "none");
  b.append(h("div", {}, dl), h("div", { class: "hint", text: "Checking everything against your Klipper config..." }));
  const photoInput = h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", multiple: true,
    onchange: (e) => { d.photos = [...e.target.files].slice(0, 6); } });
  try {
    const r = await api("POST", "/api/tools/check", p);
    showError("wizError", "");
    b.lastChild.remove();
    for (const w of r.warnings) b.append(h("div", { class: "warnbox", text: w }));
    b.append(h("p", { class: "muted small", text: `Ready: this becomes slot ${r.slot}.` }), field("Photos (optional, up to 6)", photoInput));
    $("wizNext").disabled = false;
  } catch (e) { b.lastChild.remove(); showError("wizError", e.message); }
}

async function wizNext() {
  const steps = wizSteps();
  if (steps[W.step] !== "Review") {
    const err = checkStep(); showError("wizError", err);
    if (err) return;
    W.step++; return drawWizard();
  }
  if (W.creating) return;
  W.creating = true; $("wizNext").disabled = true;
  try {
    const r = await api("POST", "/api/tools", wizPayload());
    let failed = 0;
    for (const f of W.d.photos) {
      const fd = new FormData(); fd.append("photo", f);
      try { await api("POST", `/api/tools/${r.name}/photos`, fd); } catch (e) { failed++; }
    }
    closeModal("wizard"); await refresh();
    toast(`${r.name} added.${failed ? ` ${failed} photo(s) could not be saved.` : ""} Restart Klipper to use it.`, false,
      window.RH.onToolAdded ? ["Add maintenance tasks", () => window.RH.onToolAdded(r.name)] : null);
  } catch (e) { showError("wizError", e.message); $("wizNext").disabled = false; }
  finally { W.creating = false; }
}

function wizPinRows() { return W.d.outputs.filter((r) => (r.source || "").startsWith("pin:")).map((r) => r.source.slice(4)); }
function wizDraftCtx() {
  const d = W.d, pins = wizPinRows();
  return { draft: { name: d.name.trim(), new_pin: pins[0] || "", new_enable_pin: pins[1] || "", controls: d.controls, macros: d.macros } };
}
function wizPinsHere() { return typeOf(W.d) === "POWERED" ? wizPinRows() : []; }
function stepControls(b) {
  b.append(controlsPanel(W.d.controls, { reqBase: wizDraftCtx, pinsTaken: wizPinsHere, pinsMine: () => [], toolName: () => W.d.name.trim() || "NewTool",
    redraw: drawWizard }));
}
function stepMacros(b) {
  b.append(macrosPanel(W.d.macros, W.d.controls, { reqBase: wizDraftCtx, toolName: () => W.d.name.trim() || "NewTool", redraw: drawWizard }));
}

/* ============================ 4b. controls + macros (wizard and editor share these) ============================ */
const roleLabel = (r) => ({ switch: "on/off", level: "level", fan: "fan", heater_fan: "heater fan", servo: "servo", input: "input" })[r] || r;
function ctlMacroNames(controls) {                // mirrors sections.control_macros (names only)
  const out = [];
  for (const c of controls || []) {
    if (!c.make_macros) continue;
    const up = c.name.toUpperCase();
    if (c.role === "switch") out.push(up + "_ON", up + "_OFF");
    if (c.role === "level" || c.role === "fan") out.push(up + "_SET", up + "_OFF");
    if (c.role === "servo") out.push(up + "_ANGLE", up + "_OFF");
  }
  return out;
}
function describeControl(c) {
  const bits = [roleLabel(c.role), c.pin + (c.invert ? " (inverted)" : "")];
  const acts = (S.options && S.options.input_actions) || [["none", "Do nothing"], ["message", "Show a message"], ["pause", "Pause the job"], ["estop", "Emergency stop (M112)"], ["command", "Run a command or macro"]];
  if (c.role === "input") bits.push("on trigger: " + (acts.find(([k]) => k === (c.on_press || {}).action) || [, "-"])[1].toLowerCase());
  if (c.safe_off) bits.push("off when made safe");
  if (c.make_macros) bits.push("macros: " + ctlMacroNames([c]).join(", "));
  return bits.join(" · ");
}

function controlsPanel(list, opt) {
  const wrap = h("div", {});
  wrap.append(h("p", { class: "muted small", text: "Extra outputs and inputs this tool brings: a vacuum relay, a cooling fan, a servo, a lid switch... " +
    "Describe what each one does and the portal works out the Klipper section for it. The tool's main power output is separate (the Hardware step)." }));
  const tb = h("div", { class: "x-list" });
  if (!list.length) tb.append(h("div", { class: "x-empty", text: "No extra controls yet." }));
  list.forEach((c, i) => tb.append(h("div", { class: "x-row" },
    h("div", { class: "x-main" }, h("strong", { text: c.name }), h("div", { class: "hint", text: (c.purpose ? c.purpose + " - " : "") + describeControl(c) })),
    h("button", { class: "btn ghost small", type: "button", text: "Edit", onclick: () => openControl(list, i, opt) }),
    h("button", { class: "btn ghost small", type: "button", text: "Delete", onclick: () => { list.splice(i, 1); opt.redraw(); } }))));
  wrap.append(tb, h("div", { class: "card-actions" }, h("button", { class: "btn small", type: "button", text: "+ Add a control", onclick: () => openControl(list, -1, opt) })));
  return wrap;
}

function macrosPanel(list, controls, opt) {
  const wrap = h("div", {});
  wrap.append(h("p", { class: "muted small", text: "G-code macros that belong to this tool: a purge, a test cut, a park move... " +
    "They are written to custom_tools.cfg with the tool and removed with it." }));
  const tb = h("div", { class: "x-list" });
  if (!list.length) tb.append(h("div", { class: "x-empty", text: "No macros yet." }));
  list.forEach((m, i) => tb.append(h("div", { class: "x-row" },
    h("div", { class: "x-main" }, h("strong", { class: "mono", text: m.name }),
      h("div", { class: "hint", text: (m.purpose || "no purpose given") + (m.mounted_only ? " · only while mounted" : "") })),
    h("button", { class: "btn ghost small", type: "button", text: "Edit", onclick: () => openMacro(list, i, controls, opt) }),
    h("button", { class: "btn ghost small", type: "button", text: "Delete", onclick: () => { list.splice(i, 1); opt.redraw(); } }))));
  const gen = ctlMacroNames(controls);
  if (gen.length) tb.append(h("div", { class: "x-row x-generated" }, h("div", { class: "x-main" },
    h("strong", { text: "Made by your controls" }), h("div", { class: "hint mono", text: gen.join("  ") }),
    h("div", { class: "hint", text: "Change these on the Controls tab." }))));
  wrap.append(tb, h("div", { class: "card-actions" }, h("button", { class: "btn small", type: "button", text: "+ Add a macro", onclick: () => openMacro(list, -1, controls, opt) })));
  return wrap;
}

/* one popup (#itemModal) for both; the server preview is the only judge of what is valid */
const X = { kind: "", list: null, index: -1, item: null, opt: null, last: null, seq: 0, timer: null };
function openItemModal(kind, list, index, opt, item) {
  Object.assign(X, { kind, list, index, opt, item, last: null, confirmDel: false });
  showError("itemError", ""); $("itemModal").classList.remove("hidden");
  $("itemSave").textContent = index < 0 ? (kind === "macro" ? "Add macro" : opt.hardware ? "Add hardware" : "Add control") : "Save";
  $("itemDelete").classList.toggle("hidden", !(opt.hardware && index >= 0));
  $("itemDelete").textContent = "Remove hardware";
  drawItem(); schedulePreview(0);
}
function openMacro(list, i, controls, opt) {
  const m = i >= 0 ? { ...list[i], original: list[i].name } : { name: "", purpose: "", body: "", mounted_only: true };
  openItemModal("macro", list, i, { ...opt, controls }, m);
}
function openControl(list, i, opt) {
  const c = i >= 0 ? JSON.parse(JSON.stringify(list[i])) : { name: "", purpose: "", dir: "out", role: "switch", pin: "", invert: false,
    start_on: false, on_shutdown: "off", safe_off: true, make_macros: true, mounted_only: true, cycle: 0.01, max_power: 1, kick_start: 0.1,
    heater: (S.options.heaters || [])[0] || "", heater_temp: 50, max_angle: 180, min_pulse: 0.001, max_pulse: 0.002, pullup: true,
    wiring: "ground", swap: false, on_press: { action: "message", message: "" }, on_release: { action: "none" } };
  if (opt.hardware && i < 0) Object.assign(c, { safe_off: false, mounted_only: false, category: (S.options.hw_categories[0] || {}).id || "", notes: "" });
  c.max_pct = pct(c.max_power ?? 1); c.min_ms = (c.min_pulse ?? 0.001) * 1000; c.max_ms = (c.max_pulse ?? 0.002) * 1000;
  if (i >= 0) { c.original = c.name; c.dir = c.role === "input" ? "in" : "out";
    if (c.role === "input") { c.wiring = c.pullup ? "ground" : "drive"; c.swap = c.pullup ? !c.invert : !!c.invert; } }
  openItemModal("control", list, i, opt, c);
}

function drawItem() {
  const b = clear($("itemBody"));
  $("itemTitle").textContent = X.opt.hardware ? (X.index < 0 ? "New system hardware" : "Edit system hardware - " + X.item.original)
    : (X.index < 0 ? "New " : "Edit ") + (X.kind === "macro" ? "macro" : "control") + " - " + X.opt.toolName();
  (X.kind === "macro" ? drawMacroForm : drawControlForm)(b);
  b.append(h("div", { class: "field" }, h("label", { text: "Written to custom_tools.cfg" }),
    h("pre", { class: "cfg-preview", id: "itemPreview", text: "..." }), h("div", { id: "itemWarnings" })));
  paintPreview();
}
const onEdit = () => schedulePreview(350);

function drawMacroForm(b) {
  const m = X.item;
  b.append(h("div", { class: "row" },
    field("Macro name", textInput(m, "name", { maxlength: 40, placeholder: "NEEDLE_PURGE", class: "mono", onchange: onEdit }),
      "Letters, digits and _. Klipper ignores case, so it is saved in capitals. Must not clash with any other macro or command."),
    field("Purpose", textInput(m, "purpose", { maxlength: 120, placeholder: "Purge the needle before a cut", onchange: onEdit }),
      "One line. Shown in Mainsail's macro list and console autocomplete.")));
  b.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!m.mounted_only,
    onchange: (e) => { m.mounted_only = e.target.checked; onEdit(); } }), "Only run when this tool is mounted (refused with a message otherwise)"));
  b.append(field("Macro", h("textarea", { class: "code", spellcheck: "false", rows: 12, placeholder: "G91\nG1 Z5 F600\nG90",
    oninput: (e) => { m.body = e.target.value; onEdit(); }, text: m.body || "" }),
    "Klipper G-code and Jinja templates ({% if %}, {params.X}) exactly as in a [gcode_macro]. Checked before it is saved."));
}

function controlPins(c) {
  if (X.opt.hardware) {                          // board pins that are not on the umbilical
    const o = S.options, mine = X.opt.pinsMine();
    const pool = [...mine.filter((p) => !o.board_pins.some((x) => x.pin === p)).map((p) => ({ pin: p, header: "" })), ...o.board_pins];
    return pool.map((x) => {
      const heat = ["PA8", "PE5", "PD12", "PD13", "PD14", "PD15", "PA2", "PA3", "PB10", "PB11", "PA1"].includes(x.pin);
      const bad = heat && (c.role === "input" || c.role === "servo");
      return { pin: x.pin, bad, label: x.pin + (x.header ? ` - ${x.header}` : "") + (heat ? " (power output)" : "") };
    });
  }
  const o = S.options, taken = new Set([...X.opt.pinsTaken(), ...X.list.filter((x, i) => i !== X.index).map((x) => x.pin)]);
  const pool = [...new Set([...o.free_pins, ...X.opt.pinsMine()])].filter((p) => !taken.has(p));
  return pool.map((p) => {
    const info = o.pin_info[p] || {}, bad = info.type === "mosfet" && (c.role === "input" || c.role === "servo");
    return { pin: p, bad, label: p + (info.label ? ` - ${info.label}` : "") + (info.type ? ` (${info.type === "mosfet" ? "power output" : "logic"})` : "") };
  });
}

function drawControlForm(b) {
  const c = X.item, o = S.options;
  const redraw = () => { drawItem(); schedulePreview(0); };
  const radio = (key, val, title, desc, after) => h("label", { class: "radio" + (c[key] === val ? " on" : "") },
    h("input", { type: "radio", name: "x_" + key, checked: c[key] === val, onchange: () => { c[key] = val; after && after(); redraw(); } }),
    h("span", {}, h("strong", { text: title }), desc ? h("div", { class: "hint", text: desc }) : null));
  const tick = (key, label, hint) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!c[key],
    onchange: (e) => { c[key] = e.target.checked; redraw(); } }), h("span", {}, label, hint ? h("div", { class: "hint", text: hint }) : null));

  b.append(h("div", { class: "row" },
    field(X.opt.hardware ? "Name" : "Control name", textInput(c, "name", { maxlength: 32, placeholder: X.opt.hardware ? "enclosure_light" : "needle_vacuum", class: "mono", onchange: () => { c.name = c.name.toLowerCase(); onEdit(); } }),
      `Lower-case letters, digits and _. Used in G-code, e.g. SET_PIN PIN=${X.opt.hardware ? "enclosure_light" : "needle_vacuum"}.`),
    field("What is it?", textInput(c, "purpose", { maxlength: 80, placeholder: X.opt.hardware ? "Enclosure LED strip" : "Vacuum pump relay", onchange: onEdit }))));
  if (X.opt.hardware) b.append(h("div", { class: "row" },
    field("Category", selectInput(c, "category", o.hw_categories.map((x) => [x.id, x.label]), { onchange: onEdit }), "Edit the categories under Admin > Tool lists."),
    field("Notes (optional)", textInput(c, "notes", { maxlength: 300, placeholder: "24 V strip on the FAN5 header, 2 A", onchange: onEdit }))));

  b.append(h("fieldset", {}, h("legend", { text: "1. Which way does the signal go?" }),
    radio("dir", "out", X.opt.hardware ? "Rhino controls it" : "Rhino controls something on the tool", "A relay, fan, light, servo, driver...", () => { if (c.role === "input") c.role = "switch"; }),
    radio("dir", "in", X.opt.hardware ? "It sends a signal to Rhino" : "The tool sends a signal to Rhino", "A button, door switch, limit switch, sensor...", () => { c.role = "input"; })));

  if (c.dir === "out") {
    const roles = o.control_roles.filter((r) => r.value !== "input" && (r.value !== "heater_fan" || (o.heaters || []).length));
    b.append(h("fieldset", {}, h("legend", { text: "2. What should Rhino do with it?" }), roles.map((r) => radio("role", r.value, r.label, r.help))));
  }

  const pins = controlPins(c);
  if (c.pin && !pins.some((p) => p.pin === c.pin) && !(X.opt.hardware && c.pin_typed)) c.pin = "";
  const sel = h("select", { onchange: (e) => { c.pin = e.target.value; redraw(); } },
    h("option", { value: "", text: pins.length ? "Choose a pin..." : "No free tool-connector pins" }),
    pins.map((p) => h("option", { value: p.pin, text: p.label + (p.bad ? " - cannot do this" : ""), disabled: p.bad, selected: p.pin === c.pin })));
  const pinfo = (o.pin_info[c.pin] || {});
  if (X.opt.hardware) {
    b.append(h("fieldset", {}, h("legend", { text: (c.dir === "out" ? "3" : "2") + ". Which board pin is it wired to?" }),
      h("div", { class: "row" }, field("Pin", sel, "Free headers on the board that are not on the umbilical."),
        field("Or type another pin", textInput(c, "pin_typed", { maxlength: 5, placeholder: "PE11", class: "mono", onchange: () => { c.pin = (c.pin_typed || "").trim().toUpperCase(); onEdit(); } }),
          "Any free board pin, e.g. on the EXP headers. Checked against the whole config."))));
  } else
  b.append(h("fieldset", {}, h("legend", { text: (c.dir === "out" ? "3" : "2") + ". Which pin on the tool connector?" }),
    field("Pin", sel, c.pin ? pinfo.type_label : "Only free pins wired to the umbilical are listed. Describe pins in myrhino/umbilical.json to filter by what they can do.")));

  const n = c.dir === "out" ? 4 : 3;
  const det = h("fieldset", {}, h("legend", { text: `${n}. How does it behave?` }));
  if (c.role === "switch") det.append(
    tick("invert", "On means the pin is pulled LOW (active-low)", "Common on relay boards that switch when their input goes to ground."),
    h("div", { class: "row" }, field("At power-up", selectInput(c, "start_on", [[false, "Off"], [true, "On"]].map(([v, l]) => [v, l]),
      { onchange: (e) => { c.start_on = e.target.value === "true"; onEdit(); } }))));
  if (c.role === "level") det.append(h("div", { class: "row" },
      field("Maximum %", numInput(c, "max_pct", { min: 5, max: 100, onchange: onEdit }), "Ceiling for the generated _SET macro."),
      field("PWM cycle time (s)", numInput(c, "cycle", { onchange: onEdit }), "0.01 (100 Hz) for heaters and most drivers; 0.001 for LED dimmers.")),
    tick("invert", "Inverted (0% is the pin held high)"));
  if (c.role === "fan") det.append(h("div", { class: "row" },
      field("Maximum %", numInput(c, "max_pct", { min: 5, max: 100, onchange: onEdit })),
      field("Kick-start (s)", numInput(c, "kick_start", { onchange: onEdit }), "Full power this long to get it spinning."),
      field("PWM cycle time (s)", numInput(c, "cycle", { onchange: onEdit }))), tick("invert", "Inverted output"));
  if (c.role === "heater_fan") det.append(h("div", { class: "row" },
      field("Follows heater", selectInput(c, "heater", (o.heaters || []).map((x) => [x, x]), { onchange: onEdit })),
      field("On above (°C)", numInput(c, "heater_temp", { onchange: onEdit })),
      field("Speed %", numInput(c, "max_pct", { min: 5, max: 100, onchange: onEdit }))),
    h("p", { class: "hint", text: "Klipper switches this fan by itself, so it gets no macros and is not part of safe-off." }));
  if (c.role === "servo") det.append(h("div", { class: "row" },
      field("Maximum angle (°)", numInput(c, "max_angle", { onchange: onEdit })),
      field("Pulse at 0° (ms)", numInput(c, "min_ms", { step: "0.05", onchange: onEdit })),
      field("Pulse at max (ms)", numInput(c, "max_ms", { step: "0.05", onchange: onEdit }))),
    h("p", { class: "hint", text: "Most hobby servos: 1.0 ms to 2.0 ms over 180°. Check the servo's data sheet." }));
  if (c.role === "input") {
    det.append(h("div", { class: "lbl", text: "What is connected?" }),
      radio("wiring", "ground", "A switch or button that connects the pin to ground", "The pin's pull-up is turned on, so it reads 'off' until pressed."),
      radio("wiring", "drive", "A sensor or board that drives the line itself", "No pull-up."),
      tick("swap", "Swap pressed and released", "Tick if it reports the opposite of what you expect (normally-closed switches)."));
    const act = (key, label) => {
      const a = c[key] = c[key] || { action: "none" };
      const box = h("div", { class: "row" }, field(label, selectInput(a, "action", o.input_actions.filter(([k]) => key === "on_press" || k !== "pause" && k !== "estop"),
        { onchange: () => redraw() })));
      if (a.action === "message") box.append(field("Message", textInput(a, "message", { maxlength: 80, placeholder: `${c.name || "lid"} opened`, onchange: onEdit })));
      if (a.action === "command") box.append(field("Command", textInput(a, "command", { maxlength: 80, placeholder: "NEEDLE_VACUUM_OFF", class: "mono", onchange: onEdit })));
      return box;
    };
    det.append(act("on_press", "When it triggers"), act("on_release", "When it is released"));
  }
  b.append(det);

  if (c.dir === "out" && c.role !== "heater_fan") {
    const names = ctlMacroNames([{ ...c, make_macros: true, name: c.name || "name" }]);
    b.append(h("fieldset", {}, h("legend", { text: `${n + 1}. Safety and shortcuts` }),
      tick("safe_off", "Switch it off whenever the machine is made safe", "End of job, cancel, tool swap and emergency stop (_TOOL_SAFE_OFF)."),
      h("div", { class: "lbl", text: "If Klipper shuts down or loses the board" }),
      radio("on_shutdown", "off", "Switch it off (recommended)", ""),
      radio("on_shutdown", "on", "Leave it on", "Only for things that are safe left running, such as cooling."),
      tick("make_macros", "Make macros for it: " + names.join(", "), X.opt.hardware ? "Use them in job files, Mainsail's macro panel or the console." : "Shown on the Macros tab; use them in job files or the console."),
      c.make_macros && !X.opt.hardware ? tick("mounted_only", "Those macros only switch it on while this tool is mounted", "Switching it off always works.") : null));
  }
}

function itemPayload() {
  const it = { ...X.item };
  if (X.kind === "control") {
    it.role = it.dir === "in" ? "input" : it.role;
    if (it.role === "input") { it.pullup = it.wiring === "ground"; it.invert = it.pullup ? !it.swap : !!it.swap; }
    it.max_power = it.max_pct === "" ? "" : frac(it.max_pct);
    it.min_pulse = it.min_ms === "" ? "" : Number(it.min_ms) / 1000;
    it.max_pulse = it.max_ms === "" ? "" : Number(it.max_ms) / 1000;
    for (const k of ["dir", "wiring", "swap", "max_pct", "min_ms", "max_ms", "pin_typed"]) delete it[k];
    if (X.opt.hardware) it.original = X.opt.original || "";
  }
  return it;
}

function schedulePreview(ms) { clearTimeout(X.timer); X.last = null; X.timer = setTimeout(runPreview, ms); }
async function runPreview() {
  const seq = ++X.seq, item = itemPayload();
  const base = X.opt.reqBase();
  const others = X.list.filter((_, i) => i !== X.index);
  const body = { ...base, item };
  if (body.draft) body.draft = { ...body.draft, [X.kind === "macro" ? "macros" : "controls"]: others };
  else body[X.kind === "macro" ? "macros" : "controls"] = others;
  if (X.kind === "macro" && X.opt.controls) { if (body.draft) body.draft.controls = X.opt.controls; else body.controls = X.opt.controls; }
  try {
    const r = await api("POST", "/api/preview/" + (X.opt.hardware ? "hardware" : X.kind), X.opt.hardware ? { item } : body);
    if (seq !== X.seq) return;
    X.last = { ok: true, text: r.text, warnings: r.warnings, item: r.item }; showError("itemError", "");
  } catch (e) {
    if (seq !== X.seq) return;
    X.last = { ok: false, error: e.message };
  }
  if (X.last.ok) showError("itemError", "");
  paintPreview();
}
function paintPreview() {
  const pre = $("itemPreview"); if (!pre) return;
  const lbl = pre.parentNode.querySelector("label"); if (lbl) lbl.textContent = "Written to custom_tools.cfg";
  const L = X.last, warn = clear($("itemWarnings"));
  if (!L) { pre.textContent = "Checking..."; pre.classList.remove("bad"); $("itemSave").disabled = false; return; }
  pre.textContent = L.ok ? L.text : "Nothing is written until this is fixed:\n\n" + L.error;
  pre.classList.toggle("bad", !L.ok);
  if (L.ok) for (const w of L.warnings) warn.append(h("div", { class: "warnbox", text: w }));
  $("itemSave").disabled = !L.ok;
}
async function saveItem() {
  if (!X.last) { clearTimeout(X.timer); await runPreview(); }   // typed and pressed Save before the check ran
  if (!X.last || !X.last.ok) { showError("itemError", X.last ? X.last.error : "Could not check this yet - try again."); return; }
  if (X.opt.hardware) {
    $("itemSave").disabled = true;
    try { const r = await api("POST", "/api/hardware", itemPayload()); closeModal("itemModal"); await refresh();
          toast(`${r.name} saved.` + (r.restart_needed ? " Restart Klipper to use it." : "")); }
    catch (e) { showError("itemError", e.message); }
    finally { $("itemSave").disabled = false; }
    return;
  }
  if (X.index < 0) X.list.push(X.last.item); else X.list[X.index] = X.last.item;
  closeModal("itemModal"); X.opt.redraw();
}

/* ============================ 5. editor ============================ */
const E = { name: "", tool: null, f: null, rows: [], removed: [], confirmDelete: false, tab: "settings", controls: [], macros: [] };

async function openEditor(name) {
  try { await loadOptions(); const d = await api("GET", "/api/tools/" + encodeURIComponent(name)); E.tool = d.tool; }
  catch (e) { return toast(e.message, true); }
  const t = E.tool;
  E.name = name; E.removed = []; E.confirmDelete = false; E.tab = "settings";
  E.controls = JSON.parse(JSON.stringify(t.controls || [])); E.macros = JSON.parse(JSON.stringify(t.macros || []));
  E.f = { new_name: name, notes: t.notes || "", checklist: (t.checklist || []).join("\n"), cap: pct(t.power_cap ?? 0), min: pct(t.power_min ?? 0),
          idle: pct(t.power_idle ?? 0), max_on_s: t.max_on_s, s_max: t.s_max, contacts: [...(t.contacts || [])] };
  const toUi = (k, v) => (k === "power" || k === "fan_speed") ? pct(v) : v;
  E.rows = Object.entries(t.materials).map(([n, m]) => { const r = { name: n }; for (const [k] of MAT_COLS[t.type]) r[k] = toUi(k, m[k] ?? ""); return r; });
  showError("edError", ""); $("edDelete").textContent = "Delete tool"; $("editor").classList.remove("hidden"); drawEditor();
}

function edCtx() { return { tool: E.name }; }
function drawEditor() {
  const t = E.tool, b = clear($("edBody")), f = E.f;
  $("edTitle").textContent = `Edit ${E.name}`;
  const tabs = [["settings", "Settings"], ["controls", `Controls (${E.controls.length})`], ["macros", `Macros (${E.macros.length + ctlMacroNames(E.controls).length})`]];
  b.append(h("div", { class: "tabs", role: "tablist" }, tabs.map(([k, l]) => h("button", { class: "tab" + (E.tab === k ? " on" : ""), type: "button", role: "tab",
    "aria-selected": String(E.tab === k), text: l, onclick: () => { E.tab = k; drawEditor(); } }))));
  if (E.tab === "controls") {
    const savedPins = (t.controls || []).map((c) => c.pin);
    b.append(controlsPanel(E.controls, { reqBase: edCtx, pinsTaken: () => [t.new_pin, t.new_enable_pin].filter(Boolean), pinsMine: () => savedPins,
      toolName: () => E.name, redraw: drawEditor }));
    return;
  }
  if (E.tab === "macros") { b.append(macrosPanel(E.macros, E.controls, { reqBase: edCtx, toolName: () => E.name, redraw: drawEditor })); return; }
  b.append(h("div", { class: "row" }, field("Name", textInput(f, "new_name", { maxlength: 24 }), "Renaming changes the name used in G-code and slicers."),
    field("Kind", h("input", { type: "text", value: t.kind + " (" + t.type.toLowerCase() + ")", disabled: true }))));
  if (t.type === "POWERED") {
    const wire = (t.outputs || []).map((o) => `${o.role === "power" ? "power" : "switch"}: ${o.output}${o.contact ? " (contact " + o.contact + ")" : o.pin ? " (" + o.pin + ")" : ""}`).join(" · ") || t.power_pin;
    b.append(h("fieldset", {}, h("legend", { text: "Power limits - outputs: " + wire }),
      h("div", { class: "row" },
        field("Power cap %", numInput(f, "cap")), field("Minimum %", numInput(f, "min")), field("Idle %", numInput(f, "idle"))),
      h("div", { class: "row" }, field("Max time on (s)", numInput(f, "max_on_s")), field("S for full power", numInput(f, "s_max")))));
  }
  const ro = t.type === "DEPOSITION";
  b.append(h("fieldset", {}, h("legend", { text: "Materials" }),
    ro ? h("p", { class: "hint", text: "Print-head materials come from the base tool. Adjust temperatures and offsets here." }) : null,
    materialTable(E.rows, t.type, !ro, ro ? null : (i) => { const [r] = E.rows.splice(i, 1); if (r.existing !== false) E.removed.push(r.name); drawEditor(); }),
    ro ? null : h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "+ Add material",
      onclick: () => { E.rows.push({ name: "", power: t.type === "POWERED" ? 50 : undefined, feed_rate: 600, z_offset: 0, existing: false }); drawEditor(); } }))));
  if (t.type !== "DEPOSITION") b.append(field("Pre-job checklist (one item per line)", h("textarea", { oninput: (e) => { f.checklist = e.target.value; }, text: f.checklist })));
  const locked = (t.outputs || []).map((o) => o.contact).filter(Boolean);
  b.append(contactPicker(E.f, locked));
  b.append(field("Notes", h("textarea", { maxlength: 1000, oninput: (e) => { f.notes = e.target.value; }, text: f.notes })));
  const ph = h("div", { class: "photo-edit" }, (t.images || []).map((fn) => h("figure", {},
    h("img", { src: `/media/${E.name}/${fn}`, alt: "photo" }),
    h("button", { class: "btn danger small", type: "button", text: "x", "aria-label": "Delete photo", onclick: () => photoDelete(fn) }))));
  b.append(h("div", { class: "field" }, h("label", { text: "Photos" }), ph, h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", multiple: true,
    "aria-label": "Add photos", onchange: (e) => photoUpload([...e.target.files]) })));
}

async function photoUpload(files) {
  for (const file of files) {
    const fd = new FormData(); fd.append("photo", file);
    try { const r = await api("POST", `/api/tools/${E.name}/photos`, fd); E.tool.images = r.images; }
    catch (e) { showError("edError", e.message); break; }
  }
  drawEditor(); refresh();
}
async function photoDelete(fn) {
  try { const r = await api("DELETE", `/api/tools/${E.name}/photos/${fn}`); E.tool.images = r.images; drawEditor(); refresh(); }
  catch (e) { showError("edError", e.message); }
}

async function saveEditor() {
  const t = E.tool, f = E.f; let name = E.name;
  $("edSave").disabled = true;
  try {
    if (f.new_name.trim() !== name) {
      const r = await api("POST", `/api/tools/${name}/rename`, { new_name: f.new_name.trim() });
      name = r.name; E.name = name;
    }
    const body = { notes: f.notes, materials: rowsToPayload(E.rows, t.type), delete_materials: E.removed, controls: E.controls, macros: E.macros, contacts: f.contacts };
    if (t.type !== "DEPOSITION") body.checklist = f.checklist;
    if (t.type === "POWERED") Object.assign(body, { cap: frac(f.cap), min: frac(f.min), idle: frac(f.idle), max_on_s: f.max_on_s, s_max: f.s_max });
    const r = await api("POST", `/api/tools/${name}/edit`, body);
    closeModal("editor"); await refresh(); toast(`${name} saved.` + (r.restart_needed ? " Restart Klipper to apply." : ""));
  } catch (e) { showError("edError", e.message); await refresh().catch(() => {}); }
  finally { $("edSave").disabled = false; }
}

let delTimer;
async function deleteTool() {
  if (!E.confirmDelete) {                          // two-click confirm, no browser dialog
    E.confirmDelete = true; $("edDelete").textContent = `Click again to delete ${E.name}`;
    clearTimeout(delTimer); delTimer = setTimeout(() => { E.confirmDelete = false; $("edDelete").textContent = "Delete tool"; }, 4000); return;
  }
  try { await api("DELETE", "/api/tools/" + encodeURIComponent(E.name)); closeModal("editor"); await refresh(); toast(`${E.name} removed. Restart Klipper to apply.`); }
  catch (e) { showError("edError", e.message); }
}

/* ============================ 6. boot ============================ */
async function restartKlipper() {
  const btn = $("restartBtn"); btn.disabled = true;
  try {
    await api("POST", "/api/restart"); toast("Restarting Klipper...");
    for (let i = 0; i < 30; i++) {                  // wait for it to come back
      await new Promise((r) => setTimeout(r, 2000));
      try { await refresh(); if (S.printer.klippy === "ready") { toast("Klipper restarted - your tool changes are live."); break; } } catch (e) { /* still booting */ }
    }
  } catch (e) { toast(e.message, true); }
  finally { renderBanner(); }
}

/* ---- follow Mainsail's appearance: dark/light mode and primary colour (Settings > UI-Settings in Mainsail) ---- */
function onAccent(hex) {                       // white or black text on the accent, whichever reads better
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  if (!m) return "#fff";
  const lin = (c) => { c = parseInt(c, 16) / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const L = 0.2126 * lin(m[1]) + 0.7152 * lin(m[2]) + 0.0722 * lin(m[3]);
  return (1.05) / (L + 0.05) >= (L + 0.05) / 0.05 ? "#fff" : "#000";
}
async function applyTheme() {
  try {
    const t = await api("GET", "/api/theme"), root = document.documentElement;
    root.dataset.theme = t.mode === "light" ? "light" : "dark";
    root.style.setProperty("--accent", t.primary);
    root.style.setProperty("--on-accent", onAccent(t.primary));
    document.dispatchEvent(new CustomEvent("rhino:theme", { detail: t }));
  } catch (e) { /* keep the built-in dark theme */ }
}

function init() {
  $("menuBtn").onclick = () => setSidebar(!$("sidebar").classList.contains("open"));
  document.querySelectorAll(".nav-btn[data-view]").forEach((b) => { b.onclick = () => showView(b.dataset.view); });
  $("navAdd").onclick = () => { setSidebar(false); openWizard(); };
  $("addBtn").onclick = openWizard;
  $("wizNext").onclick = wizNext;
  $("wizBack").onclick = () => { if (W.step > 0) { W.step--; showError("wizError", ""); drawWizard(); } };
  $("edSave").onclick = saveEditor; $("edDelete").onclick = deleteTool; $("restartBtn").onclick = restartKlipper;
  $("autoRestart").onchange = (e) => setAutoRestart(e.target.checked);
  $("itemSave").onclick = saveItem; $("itemDelete").onclick = deleteHardware;
  document.querySelectorAll("[data-hwnew]").forEach((b) => { b.onclick = () => openHardware(null); });
  initNav();
  setInterval(tickBanner, 1000);
  document.querySelectorAll("[data-close]").forEach((b) => { b.onclick = () => b.closest(".modal").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => {          // Esc closes the top-most dialog only; Tab stays inside it
    const open = [...document.querySelectorAll(".modal:not(.hidden)")];
    if (!open.length) return;
    const top = open[open.length - 1];
    if (e.key === "Escape") { top.classList.add("hidden"); return; }
    if (e.key !== "Tab") return;
    const f = focusables(top);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (!top.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  // every dialog: on open, remember who opened it and move focus in; on close, give focus back
  document.querySelectorAll(".modal").forEach((m) => new MutationObserver(() => {
    const shown = !m.classList.contains("hidden");
    if (shown && !m._opener) {
      m._opener = document.activeElement;
      setTimeout(() => { const f = focusables(m.querySelector(".modal-body") || m)[0] || focusables(m)[0]; if (f) f.focus(); }, 0);
    } else if (!shown && m._opener) {
      const o = m._opener; m._opener = null;
      if (o && document.contains(o) && o.offsetParent !== null) o.focus();
    }
  }).observe(m, { attributes: true, attributeFilter: ["class"] }));
  applyTheme(); setInterval(applyTheme, 120000);
  refresh().catch((e) => toast(e.message, true));
  setInterval(() => { if (!document.querySelector(".modal:not(.hidden)")) refresh().catch(() => {}); }, 10000);
}
/* shared with maint.js (loaded after this file) */
window.RH = { h, clear, api, toast, showError, field, textInput, numInput, selectInput, closeModal, showView, dur, pct, frac,
              openEditor: (n) => openEditor(n), openTool, currentToolName: () => currentTool,
              S, refresh, loadOptions, contactStrip, currentView: () => currentView, onToolAdded: null, openAssetTasks: null };
init();
})();
