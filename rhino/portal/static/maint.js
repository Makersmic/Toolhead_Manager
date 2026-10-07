/* Rhino portal - preventive maintenance screens. Uses the helpers portal.js shares on window.RH.
   Same rules as portal.js: everything is built with textContent, nothing typed can run as markup.

   Sections:  1 data   2 due & upcoming   3 tasks   4 work log   5 meters   6 task + library-task editor
              7 log work + status   8 Task Library + Task Books   9 assign   10 boot                       */
(() => {
"use strict";
const { h, clear, api, toast, showError, field, textInput, numInput, selectInput, closeModal, S } = window.RH;
const $ = (id) => document.getElementById(id);
const M = { data: null, loadedAt: 0, filter: "all", histFilter: "", lib: null, libTab: "books" };
const VIEWS = ["mdue", "mtasks", "mhistory", "mmeters", "mlib"];
const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
const fmtDateTime = (ts) => new Date(ts * 1000).toLocaleString([], { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
function fmtVal(v, unit) {
  if (v == null) return "-";
  if (unit === "h") return (v < 10 ? v.toFixed(1) : Math.round(v).toLocaleString()) + " h";
  if (unit === "m") return (v < 10 ? v.toFixed(1) : Math.round(v).toLocaleString()) + " m";
  return Math.round(v).toLocaleString();
}

/* ============================ 1. data ============================ */
async function load(force) {
  if (!force && M.data && Date.now() - M.loadedAt < 8000) return M.data;
  M.data = await api("GET", "/api/maint"); M.loadedAt = Date.now();
  renderBadge();
  return M.data;
}
const sdef = (id) => (M.data.statuses || []).find((x) => x.id === id) || { label: id, hex: "#8d8f99" };
const customStatuses = () => (M.data.statuses || []).filter((x) => !x.builtin);
function assetChoices(withMachine) {
  const d = M.data;
  return [...(withMachine ? [["machine", "Whole machine (each task in its own area)"]] : []),
    ...d.areas.map((a) => ["machine:" + a.id, "Machine - " + a.label]), ...d.tools.map((t) => ["tool:" + t.name, "Tool - " + t.name]),
    ...(d.hardware || []).map((x) => ["hw:" + x.name, "System hardware - " + x.label])];
}
const isTool = (asset) => (asset || "").startsWith("tool:");

/* a coloured status pill. Colours come from data, so they are set through CSSOM (the CSP forbids style="") */
function pill(label, hex, extraClass) {
  const el = h("span", { class: "badge st-badge pill " + (extraClass || ""), text: label });
  el.style.setProperty("--pill", hex); return el;
}
function statePill(st) {
  if (!st) return pill(sdef("paused").label, sdef("paused").hex);
  if (st.snoozed) return pill(sdef("snoozed").label, sdef("snoozed").hex);
  const s = sdef(st.state); return pill(s.label, s.hex);
}

function renderBadge() {
  const c = M.data ? M.data.counts : null;
  if (!c) return;
  const n = c.overdue || c.due_soon;
  for (const b of [$("mBadge"), $("mBadgeGroup")]) {
    if (!b) continue;
    b.textContent = String(n); b.className = "nav-badge" + (c.overdue ? " bad" : c.due_soon ? " warn" : " hidden");
    b.title = `${c.overdue} overdue, ${c.due_soon} due soon`;
  }
  const chips = $("statusChips");
  chips.querySelectorAll(".chip-maint").forEach((x) => x.remove());
  if (c.overdue || c.due_soon) chips.append(h("button", { class: "chip chip-maint " + (c.overdue ? "bad" : "warn"), type: "button",
    text: c.overdue ? `Maintenance: ${c.overdue} overdue` : `Maintenance: ${c.due_soon} due soon`, onclick: () => window.RH.showView("mdue") }));
}

/* ============================ 2. due & upcoming ============================ */
function bar(frac, state) {                 // width via CSSOM: the page's CSP forbids style="" attributes
  const inner = h("div", { class: "progress-bar st-" + state });
  inner.style.width = (frac * 100).toFixed(1) + "%";
  return h("div", { class: "progress thin" }, inner);
}
function taskCard(t, compact) {
  const st = t.status || { state: "ok", rules: [] }, state = st.snoozed ? "snoozed" : st.state, hold = st.hold;
  const card = h("div", { class: `card task-card st-${state}` + (hold ? " held" : "") });
  if (hold) card.style.setProperty("--pill", hold.hex);
  card.append(h("div", { class: "card-head" },
    h("div", {}, h("h2", { text: t.title }), h("div", { class: "muted small", text: t.asset_label + " · " + (M.data.types[t.type] || t.type) +
      (t.priority && t.priority !== "normal" ? " · " + M.data.priorities[t.priority] + " priority" : "") + (t.link ? " · from the Task Library" : "") })),
    h("div", { class: "pill-stack" }, hold ? pill(hold.label, hold.hex) : null, statePill(st))));
  if (hold) card.append(h("div", { class: "hold-line" }, h("strong", { text: hold.label }),
    hold.note ? h("span", { text: " - " + hold.note }) : null,
    h("div", { class: "hint", text: `Set ${fmtDate(hold.since)}` + (hold.until ? ` · ends by itself ${fmtDate(hold.until)}` : hold.expiry === "meter" ? " · ends when the machine is used again" : "") +
      (hold.clock === "pause" ? " · clock paused" : "") })));
  for (const r of st.rules) {
    const frac = Math.max(0, Math.min(1, r.fraction || 0));
    card.append(h("div", { class: "rule-line" },
      h("div", { class: "rule-text" }, h("span", { class: "dot st-" + r.state }), h("span", { text: r.summary + " - " + r.text })),
      r.event || r.state === "done" ? null : bar(frac, r.state)));
  }
  if (st.snoozed) card.append(h("div", { class: "hint", text: "Snoozed until " + fmtDateTime(t.snooze_until) }));
  if ((st.state === "overdue" || st.state === "due_soon") && t.parts && t.parts.length)
    card.append(h("div", { class: "have-ready" }, h("strong", { text: "Have ready: " }), t.parts.join(", ")));
  if (!compact && (t.minutes || t.tools_needed)) card.append(h("div", { class: "hint", text: [t.minutes ? `About ${t.minutes} min` : "", t.tools_needed].filter(Boolean).join(" · ") }));
  if (t.last && t.last.at) card.append(h("div", { class: "hint", text: `Last ${t.last.action === "skipped" ? "skipped" : "done"} ${fmtDate(t.last.at)}` }));
  const snoozeSel = h("select", { class: "small-select", "aria-label": "Snooze", onchange: (e) => { if (e.target.value) snooze(t, Number(e.target.value)); } },
    h("option", { value: "", text: "Snooze..." }), [[1, "1 day"], [3, "3 days"], [7, "1 week"], [14, "2 weeks"]].map(([v, l]) => h("option", { value: v, text: l })),
    t.snooze_until ? h("option", { value: "0", text: "Cancel snooze" }) : null);
  card.append(h("div", { class: "card-actions" },
    h("button", { class: "btn small", type: "button", text: "Log work", onclick: () => openDone(t) }),
    h("button", { class: "btn ghost small", type: "button", text: hold ? "Change status" : "Set status", onclick: () => openStatus(t) }),
    (st.state === "overdue" || st.state === "due_soon" || t.snooze_until) && !hold ? snoozeSel : null,
    h("button", { class: "btn ghost small", type: "button", text: "Details", onclick: () => openTask(t) })));
  return card;
}

function renderDue() {
  const box = clear($("mDue")), d = M.data, live = d.tasks.filter((t) => t.status);
  const order = (a, b) => (b.status.fraction || 0) - (a.status.fraction || 0);
  const held = (t) => t.status.hold, list = (t) => held(t) ? held(t).list : "";
  const due = live.filter((t) => !held(t) || list(t) === "due");
  const over = due.filter((t) => t.status.state === "overdue" && !t.status.snoozed).sort(order);
  const soon = due.filter((t) => t.status.state === "due_soon" && !t.status.snoozed).sort(order);
  const snoozed = live.filter((t) => t.status.snoozed && !held(t));
  const own = {};
  for (const t of live.filter((x) => list(x) === "own")) (own[held(t).id] = own[held(t).id] || []).push(t);
  const upHeld = live.filter((t) => list(t) === "upcoming");
  const later = [...upHeld, ...due.filter((t) => t.status.state === "ok" && !held(t)).sort(order).slice(0, Math.max(0, 8 - upHeld.length))];
  box.append(h("div", { class: "summary-row" },
    sumTile(over.length, sdef("overdue").label.toLowerCase(), "bad"), sumTile(soon.length, sdef("due_soon").label.toLowerCase() + " (early alarm)", "warn"),
    sumTile(Object.values(own).flat().length + upHeld.length, "with a status set", ""), sumTile(live.length, "active tasks", "ok")));
  if (!d.tasks.length) {
    box.append(h("div", { class: "card empty" }, h("p", { text: "No maintenance tasks yet." }),
      h("p", { class: "muted small", text: "Open the Task Library and assign a Task Book to the machine and to each tool, then tune the intervals to your machine." }),
      h("button", { class: "btn", type: "button", text: "Open the Task Library", onclick: () => window.RH.showView("mlib") })));
    return;
  }
  const group = (title, items, hint, hex) => { if (!items.length) return;
    const t = h("h2", { class: "group-title" + (hex ? " tinted" : ""), text: title }); if (hex) t.style.setProperty("--pill", hex);
    box.append(t, hint ? h("p", { class: "muted small", text: hint }) : null, h("div", { class: "grid" }, items.map((x) => taskCard(x)))); };
  if (!over.length && !soon.length) box.append(h("div", { class: "card ok-card", text: "Nothing is due. Upcoming work is listed below." }));
  group(sdef("overdue").label, over, "Past the due point. Nothing is blocked - fit it in when it suits you.");
  group(sdef("due_soon").label, soon, "Inside the early alarm: time to plan the work and get the parts.");
  for (const [id, items] of Object.entries(own)) group(sdef(id).label, items, sdef(id).help, sdef(id).hex);
  group(sdef("snoozed").label, snoozed);
  group("Coming up", later, "The next tasks by how close they are to due.");
  if (d.settings.boot_reminder) box.append(h("p", { class: "muted small", text: "Overdue and due-soon tasks are also shown in Mainsail once after each Klipper start (Usage meters > Reminders)." }));
}
const sumTile = (n, label, cls) => h("div", { class: "sum-tile " + cls }, h("div", { class: "sum-n", text: String(n) }), h("div", { class: "sum-l", text: label }));

/* ============================ 3. tasks ============================ */
function renderTasks() {
  const d = M.data, sel = clear($("mFilter"));
  const choices = [["all", "Every task"], ["due", "Overdue and due soon"], ["held", "With a status set"], ...assetChoices(), ["archived", "Archived"]];
  if (!choices.some(([v]) => v === M.filter)) M.filter = "all";
  choices.forEach(([v, l]) => sel.append(h("option", { value: v, text: l, selected: v === M.filter })));
  sel.onchange = (e) => { M.filter = e.target.value; renderTasks(); };
  const f = M.filter;
  let list = d.tasks.filter((t) => f === "archived" ? t.archived : !t.archived);
  if (f === "due") list = list.filter((t) => t.status && ["overdue", "due_soon"].includes(t.status.state));
  else if (f === "held") list = list.filter((t) => t.status && t.status.hold);
  else if (f.includes(":")) list = list.filter((t) => t.asset === f);
  const assetBox = clear($("mAsset"));
  if (f.includes(":")) assetBox.append(assetMeters(f));
  const box = clear($("mTaskList"));
  if (!list.length) { box.append(h("div", { class: "card empty", text: f === "all" ? "No tasks yet - add one, or assign a Task Book from the Task Library." : "No tasks here." })); return; }
  const tb = h("table", { class: "tbl task-table" }, h("tr", {}, ["Task", "For", "Schedule", "Status", "Last done", ""].map((x) => h("th", { text: x }))));
  const rank = { overdue: 0, due_soon: 1, ok: 2, done: 3 };
  list.sort((a, b) => (a.status ? rank[a.status.state] : 9) - (b.status ? rank[b.status.state] : 9) || a.title.localeCompare(b.title));
  for (const t of list) {
    const st = t.status;
    tb.append(h("tr", { class: "clickable", onclick: () => openTask(t) },
      h("td", {}, h("strong", { text: t.title }), t.link_info ? h("div", { class: "hint", text: "Library" + (t.link_info.book_name ? " · " + t.link_info.book_name : "") }) : null),
      h("td", { text: t.asset_label }),
      h("td", { class: "small", text: st ? st.rules.map((r) => r.summary).join(" or ") : "-" }),
      h("td", {}, h("div", { class: "pill-stack left" }, st && st.hold ? pill(st.hold.label, st.hold.hex) : null,
        t.archived ? pill("Archived", "#8d8f99") : statePill(st)), st && st.next ? h("div", { class: "hint", text: st.next.text }) : null),
      h("td", { class: "small", text: t.last && t.last.at ? fmtDate(t.last.at) : "never" }),
      h("td", {}, st ? h("button", { class: "btn ghost small", type: "button", text: "Log work", onclick: (e) => { e.stopPropagation(); openDone(t); } }) : null)));
  }
  box.append(h("div", { class: "card" }, h("div", { class: "table-wrap" }, tb)));
}

function assetMeters(asset) {
  const tool = isTool(asset) ? asset.slice(5) : null;
  const rows = tool ? M.data.meters.tools[tool] || [] : M.data.meters.machine;
  return h("div", { class: "card" }, h("h2", { text: tool ? `${tool} - usage` : "Machine usage" }),
    h("div", { class: "meter-grid" }, rows.map((m) => h("div", { class: "meter-tile" }, h("div", { class: "meter-v", text: fmtVal(m.value, m.unit) }),
      h("div", { class: "meter-l", text: m.label }), m.per_day ? h("div", { class: "hint", text: `≈ ${fmtVal(m.per_day, m.unit)} a day` }) : null))),
    tool ? null : h("p", { class: "hint", text: "Machine meters count every tool. Tool tasks can also count that tool's own hours." }));
}

/* ============================ 4. work log ============================ */
async function renderHistory() {
  const sel = clear($("mHistFilter"));
  [["", "Everything"], ...assetChoices()].forEach(([v, l]) => sel.append(h("option", { value: v, text: l, selected: v === M.histFilter })));
  sel.onchange = (e) => { M.histFilter = e.target.value; renderHistory(); };
  const r = await api("GET", "/api/maint/history" + (M.histFilter ? "?asset=" + encodeURIComponent(M.histFilter) : ""));
  const tb = clear($("mHistory"));
  tb.append(h("tr", {}, ["When", "For", "Task", "What", "Notes"].map((x) => h("th", { text: x }))));
  if (!r.records.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "muted", text: "Nothing logged yet." })));
  const act = { done: "Done", skipped: "Skipped", meter: "Meter set", status: "Status set", status_cleared: "Status cleared" };
  for (const x of r.records) {
    let what = x.action === "meter" ? `${fmtVal(x.from, "")} -> ${fmtVal(x.to, "")}` : (act[x.action] || x.action);
    if (x.action === "status" || x.action === "status_cleared") what += ": " + (x.status || "");
    else if (x.was && x.was !== "ok" && x.action !== "meter") what += ` (was ${sdef(x.was).label.toLowerCase()})`;
    tb.append(h("tr", {}, h("td", { class: "small", text: fmtDateTime(x.at) }), h("td", { text: x.asset_label }), h("td", { text: x.title }),
      h("td", { text: what }), h("td", { class: "note-cell", text: x.notes || "" })));
  }
}

/* ============================ 5. meters ============================ */
function renderMeters() {
  const d = M.data, mm = d.meters, box = clear($("mMeters"));
  const table = (rows, tool) => {
    const tb = h("table", { class: "tbl" }, h("tr", {}, ["Meter", "Reading", "Average", ""].map((x) => h("th", { text: x }))));
    for (const m of rows) tb.append(h("tr", {},
      h("td", {}, h("strong", { text: m.label }), h("div", { class: "hint", text: m.help })),
      h("td", { class: "num", text: fmtVal(m.value, m.unit) }),
      h("td", { class: "num muted", text: m.per_day ? fmtVal(m.per_day, m.unit) + " / day" : "-" }),
      h("td", {}, h("button", { class: "btn ghost small", type: "button", text: "Set", onclick: () => openMeter(tool ? "tool" : "machine", tool, m) }))));
    return h("div", { class: "table-wrap" }, tb);
  };
  box.append(h("div", { class: "card" }, h("h2", { text: "Machine" }),
    h("p", { class: "muted small", text: `Tracking since ${fmtDate(mm.tracking_since)}.` +
      (mm.imported_jobs ? ` ${mm.imported_jobs} earlier job(s) were imported from Moonraker's history as the starting reading.` : "") +
      " Use Set if the machine had hours before tracking started." }), table(mm.machine, null)));
  for (const [name, rows] of Object.entries(mm.tools)) box.append(h("details", { class: "card fold" }, h("summary", {}, h("strong", { text: name }),
    h("span", { class: "muted small", text: " " + rows.filter((r) => r.unit === "h").map((r) => `${r.label.toLowerCase()} ${fmtVal(r.value, r.unit)}`).slice(0, 2).join(" · ") })),
    table(rows, name)));
  const st = d.settings;
  box.append(h("div", { class: "card" }, h("h2", { text: "Reminders" }),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!st.boot_reminder, onchange: (e) => saveSettings({ boot_reminder: e.target.checked }) }),
      h("span", {}, "Show overdue and due-soon tasks in Mainsail after Klipper starts",
        h("div", { class: "hint", text: "Once per start, after the 'which tool is mounted?' question. It never blocks a job. PM_STATUS in the console lists them any time. A status code can leave its tasks out (Admin > Status codes)." })))),
    h("p", { class: "muted small", text: "Machine areas, kinds of work and priorities are edited under Admin > Maintenance lists." }));
}
async function saveSettings(f) { try { await api("POST", "/api/maint/settings", f); toast("Saved."); await refreshMaint(true); } catch (e) { toast(e.message, true); } }

let MT = null;
function openMeter(scope, tool, m) {
  MT = { scope, tool, meter: m.meter, value: m.unit ? Number(m.value.toFixed(2)) : Math.round(m.value), note: "" };
  $("meterTitle").textContent = `Set ${m.label}` + (tool ? ` - ${tool}` : "");
  const b = clear($("meterBody"));
  b.append(h("p", { class: "muted small", text: `Now ${fmtVal(m.value, m.unit)}. Tasks counting this meter keep their due points, so setting a higher reading brings them closer.` }),
    field("New reading" + (m.unit ? ` (${m.unit})` : ""), numInput(MT, "value", { min: 0 })),
    field("Why (optional)", textInput(MT, "note", { maxlength: 200, placeholder: "Hours on the machine before tracking started" })));
  showError("meterError", ""); $("meterModal").classList.remove("hidden");
}
async function saveMeter() {
  try { await api("POST", "/api/maint/meters", MT); closeModal("meterModal"); toast("Reading set and logged."); await refreshMaint(true); }
  catch (e) { showError("meterError", e.message); }
}

/* ============================ 6. task + library-task editor ============================ */
/* TE.mode "task" edits a task; "template" edits a Task Library task (no asset, no schedule state). */
const TE = { id: null, f: null, confirm: false, mode: "task", task: null };
const RULE_KINDS = [["time", "Every so often"], ["meter", "After so much use"], ["event", "After each event"], ["date", "Once, on a date"]];
function blankRule(kind, asset) {
  const tool = TE.mode === "template" ? true : isTool(asset);
  if (kind === "time") return { kind, every: 3, unit: "months", lead: 14, lead_unit: "days" };
  if (kind === "meter") return { kind, meter: tool ? "active_h" : "prod_h", scope: tool && TE.mode !== "template" ? "tool" : "machine", every: 100, lead: 10 };
  if (kind === "event") return { kind, meter: tool && TE.mode !== "template" ? "mounts" : "swaps", scope: tool && TE.mode !== "template" ? "tool" : "machine" };
  return { kind: "date", on: today(), lead: 7 };
}
function defToForm(t) {
  return { ...JSON.parse(JSON.stringify(t)), steps: (t.steps || []).join("\n"), parts: (t.parts || []).join("\n"), links: (t.links || []).join("\n") };
}
function blankDef(asset) {
  return { title: "", asset, type: Object.keys(M.data.types).includes("inspect") ? "inspect" : Object.keys(M.data.types)[0], priority: "normal",
           rules: [blankRule("time", asset)], anchor: "completion", first_due: today(), steps: "", parts: "", tools_needed: "", minutes: "", safety: "",
           notes: "", links: "", remind_boot: true, enabled: true, last_done: { when: "now", date: today(), readings: {} }, area: "" };
}
function openTask(t, presetAsset) {
  const d = M.data, asset = t ? t.asset : (presetAsset || (M.filter.includes(":") ? M.filter : "machine:" + d.areas[0].id));
  TE.mode = "task"; TE.id = t ? t.id : null; TE.confirm = false; TE.task = t || null;
  TE.f = t ? defToForm(t) : blankDef(asset);
  TE.f.rules = TE.f.rules.map((r) => r.kind === "meter" && r.event ? { ...r, kind: "event" } : { ...r });
  if (!TE.f.first_due) TE.f.first_due = today();
  $("taskTitle").textContent = t ? "Edit task" : "New maintenance task";
  $("taskDelete").classList.toggle("hidden", !t); $("taskDelete").textContent = "Delete task";
  $("taskSave").textContent = "Save";
  showError("taskError", ""); $("taskModal").classList.remove("hidden"); drawTask();
}
function openTemplate(tpl) {
  TE.mode = "template"; TE.id = tpl ? tpl.id : null; TE.confirm = false; TE.task = null;
  TE.f = tpl ? defToForm(tpl) : blankDef("");
  TE.f.rules = TE.f.rules.map((r) => r.kind === "meter" && r.event ? { ...r, kind: "event" } : { ...r });
  if (!TE.f.first_due) TE.f.first_due = today();
  TE.uses = tpl ? tpl.uses : [];
  $("taskTitle").textContent = tpl ? "Edit library task" : "New library task";
  $("taskDelete").classList.toggle("hidden", !tpl); $("taskDelete").textContent = "Delete library task";
  $("taskSave").textContent = tpl && tpl.uses.length ? `Save and update ${tpl.uses.length} task${tpl.uses.length > 1 ? "s" : ""}` : "Save";
  showError("taskError", ""); $("taskModal").classList.remove("hidden"); drawTask();
}

function meterChoices(asset, events) {
  const mm = M.data.meters, out = [];
  const add = (scope, rows, prefix) => rows.forEach((m) => { if (events ? m.event : true) out.push([scope + "." + m.meter, prefix + (events ? m.event : m.label)]); });
  if (TE.mode === "template" || isTool(asset)) add("tool", (isTool(asset) && mm.tools[asset.slice(5)]) || Object.values(mm.tools)[0] || [], TE.mode === "template" ? "The tool's own: " : "This tool: ");
  add("machine", mm.machine, "Machine: ");
  return out;
}

function drawLinked(b, t) {
  const li = t.link_info || {};
  b.append(h("div", { class: "linkbox" },
    h("strong", { text: "This task comes from the Task Library" }),
    h("div", { class: "hint", text: `Library task "${li.template_title}"` + (li.book_name ? ` · Task Book "${li.book_name}"` : "") +
      ` · used by ${li.uses} task${li.uses === 1 ? "" : "s"}. Its steps and schedule are the library's: edit the library task to change every copy, or detach this one to customise it.` }),
    h("div", { class: "card-actions" },
      h("button", { class: "btn small", type: "button", text: "Edit the library task", onclick: async () => {
        await loadLib(); const tpl = M.lib.templates.find((x) => x.id === li.template); closeModal("taskModal"); if (tpl) openTemplate(tpl); } }),
      h("button", { class: "btn ghost small", type: "button", text: "Detach to customise", onclick: async () => {
        try { await api("POST", `/api/maint/tasks/${t.id}`, { detach: true }); toast("Detached - this task can now be edited on its own."); await refreshMaint(true);
              openTask(M.data.tasks.find((x) => x.id === t.id)); } catch (e) { showError("taskError", e.message); } } }))));
  const dl = h("dl", { class: "review" });
  const row = (k, v) => { if (v) dl.append(h("dt", { text: k }), h("dd", { text: v })); };
  row("For", t.asset_label); row("Kind of work", M.data.types[t.type] || t.type); row("Priority", M.data.priorities[t.priority]);
  row("Schedule", t.status ? t.status.rules.map((r) => r.summary).join(" or ") : ""); row("Now", t.status ? t.status.rules.map((r) => r.text).join("; ") : "");
  row("Steps", (t.steps || []).join(" · ")); row("Parts", (t.parts || []).join(", ")); row("Safety", t.safety);
  b.append(dl, h("fieldset", {}, h("legend", { text: "This task only" }),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: !TE.f.enabled, onchange: (e) => { TE.f.enabled = !e.target.checked; } }),
      h("span", {}, "Paused (keeps the task but stops tracking it)"))));
}

function drawTask() {
  const f = TE.f, b = clear($("taskBody")), d = M.data, tmpl = TE.mode === "template";
  const redraw = () => drawTask();
  if (!tmpl && TE.task && TE.task.link) { drawLinked(b, TE.task); return; }
  if (tmpl && TE.uses && TE.uses.length) b.append(h("div", { class: "linkbox" }, h("strong", { text: `Used by ${TE.uses.length} task${TE.uses.length > 1 ? "s" : ""}` }),
    h("div", { class: "hint", text: "Saving updates every one of them: " + TE.uses.join(", ") + ". Their schedules carry on from where they are." })));
  b.append(h("div", { class: "row" },
    field("Task", textInput(f, "title", { maxlength: 80, placeholder: "Tension the X/Y belts" }), "Short - it is also shown in the Mainsail reminder."),
    tmpl ? field("Area when the book goes on the whole machine", selectInput(f, "area", [["", "Choose when assigned..."], ...d.areas.map((a) => [a.id, a.label])]),
      "Ignored on a toolhead or system hardware.")
      : field("For", selectInput(f, "asset", assetChoices(), { onchange: () => { f.rules = f.rules.map((r) => (r.kind === "meter" || r.kind === "event") && r.scope === "tool" && !isTool(f.asset) ? blankRule(r.kind, f.asset) : r); redraw(); } }))));
  b.append(h("div", { class: "row" },
    field("Kind of work", selectInput(f, "type", Object.entries(d.types))),
    field("Priority", selectInput(f, "priority", Object.entries(d.priorities)))));

  const sched = h("fieldset", {}, h("legend", { text: "When is it due? (whichever rule comes first)" }));
  f.rules.forEach((r, i) => sched.append(ruleRow(r, i)));
  if (f.rules.length < 4) sched.append(h("button", { class: "btn ghost small", type: "button", text: "+ Add another rule", onclick: () => { f.rules.push(blankRule("meter", f.asset)); redraw(); } }));
  if (tmpl) sched.append(h("p", { class: "hint", text: "A rule that counts the tool's own use makes this a toolhead-only task." }));
  if (f.rules.some((r) => r.kind === "time")) {
    const rad = (val, title, extra) => h("label", { class: "radio" + (f.anchor === val ? " on" : "") },
      h("input", { type: "radio", name: "anchor", checked: f.anchor === val, onchange: () => { f.anchor = val; redraw(); } }), h("span", {}, h("strong", { text: title }), extra || null));
    sched.append(h("div", { class: "lbl", text: "Time rules count..." }),
      rad("completion", "From when it was last done", h("div", { class: "hint", text: "Done late? The next one moves later too." })),
      rad("calendar", "On a fixed calendar", f.anchor === "calendar" ? h("div", { class: "row" }, field("First due on", h("input", { type: "date", value: f.first_due, onchange: (e) => { f.first_due = e.target.value; } }))) :
        h("div", { class: "hint", text: "Same dates every time, e.g. the 1st of every month." })));
  }
  b.append(sched);

  if (!TE.id && !tmpl) {                                   // where counting starts
    const ld = f.last_done;
    const rad = (val, title) => h("label", { class: "radio" + (ld.when === val ? " on" : "") },
      h("input", { type: "radio", name: "lastdone", checked: ld.when === val, onchange: () => { ld.when = val; redraw(); } }), h("span", {}, h("strong", { text: title })));
    const fs = h("fieldset", {}, h("legend", { text: "Start counting from" }), rad("now", "Now - treat it as just done"), rad("date", "The last time it was done"));
    if (ld.when === "date") {
      fs.append(field("Last done on", h("input", { type: "date", value: ld.date, max: today(), onchange: (e) => { ld.date = e.target.value; } })));
      const tool = isTool(f.asset) ? f.asset.slice(5) : null;
      for (const r of f.rules.filter((x) => x.kind === "meter")) {
        const key = r.scope + "." + r.meter, rows = r.scope === "tool" ? (M.data.meters.tools[tool] || []) : M.data.meters.machine;
        const m = rows.find((x) => x.meter === r.meter) || { label: r.meter, value: 0, unit: "" };
        if (ld.readings[key] === undefined) ld.readings[key] = m.unit ? Number((m.value || 0).toFixed(1)) : Math.round(m.value || 0);
        fs.append(field(`${m.label} reading when it was done`, numInput(ld.readings, key, { min: 0 }), `Now ${fmtVal(m.value, m.unit)}.`));
      }
    }
    b.append(fs);
  }

  b.append(h("fieldset", {}, h("legend", { text: "How to do it" }),
    field("Steps (one per line)", h("textarea", { oninput: (e) => { f.steps = e.target.value; }, text: f.steps })),
    h("div", { class: "row" },
      field("Parts and consumables (one per line)", h("textarea", { class: "short", oninput: (e) => { f.parts = e.target.value; }, text: f.parts }),
        "Listed as 'Have ready' once the early alarm goes off."),
      h("div", {}, field("Tools needed", textInput(f, "tools_needed", { maxlength: 200, placeholder: "2.5 mm hex key, belt tension gauge" })),
        field("Time needed (minutes)", numInput(f, "minutes", { min: 0, max: 1440 })))),
    field("Safety notes", h("textarea", { class: "short", oninput: (e) => { f.safety = e.target.value; }, text: f.safety })),
    field("Links (manuals, videos - one per line)", h("textarea", { class: "short", oninput: (e) => { f.links = e.target.value; }, text: f.links }))));
  const rem = h("fieldset", {}, h("legend", { text: "Reminders" }),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!f.remind_boot, onchange: (e) => { f.remind_boot = e.target.checked; } }),
      h("span", {}, "Remind me in Mainsail when Klipper starts and this is due")));
  if (!tmpl) rem.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: !f.enabled, onchange: (e) => { f.enabled = !e.target.checked; } }),
      h("span", {}, "Paused (keeps the task but stops tracking it)")));
  b.append(rem);
  if (!tmpl && TE.id) b.append(h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "Add this task to the Task Library",
    onclick: async () => { try { await api("POST", `/api/maint/tasks/${TE.id}/to-library`); toast("Added to the Task Library and linked."); closeModal("taskModal"); await refreshMaint(true); }
      catch (e) { showError("taskError", e.message); } } })));
  if (!tmpl && TE.id && f.status && f.status.rules.length) b.append(h("div", { class: "hint", text: "Now: " + f.status.rules.map((r) => r.text).join("; ") }));
}

function ruleRow(r, i) {
  const f = TE.f, redraw = () => drawTask();
  const row = h("div", { class: "rule-row" });
  const kindSel = h("select", { "aria-label": "rule kind", onchange: (e) => { f.rules[i] = blankRule(e.target.value, f.asset); redraw(); } },
    RULE_KINDS.map(([v, l]) => h("option", { value: v, text: l, selected: v === r.kind })));
  row.append(kindSel);
  const unitSel = (obj, key) => selectInput(obj, key, [["days", "days"], ["weeks", "weeks"], ["months", "months"]]);
  if (r.kind === "time") row.append(h("span", { text: "every" }), numInput(r, "every", { min: 1, class: "n" }), unitSel(r, "unit"),
    h("span", { class: "rule-alarm", text: "early alarm" }), numInput(r, "lead", { min: 0, class: "n" }), unitSel(r, "lead_unit"), h("span", { text: "before" }));
  if (r.kind === "meter") {
    const key = r.scope + "." + r.meter, choices = meterChoices(f.asset, false);
    const ms = h("select", { "aria-label": "meter", onchange: (e) => { [r.scope, r.meter] = e.target.value.split("."); redraw(); } },
      choices.map(([v, l]) => h("option", { value: v, text: l, selected: v === key })));
    const unit = (meterChoicesUnit(r) || "");
    row.append(h("span", { text: "every" }), numInput(r, "every", { min: 0.1, class: "n" }), h("span", { text: unit }), ms,
      h("span", { class: "rule-alarm", text: "early alarm" }), numInput(r, "lead", { min: 0, class: "n" }), h("span", { text: (unit || "") + " before" }));
  }
  if (r.kind === "event") {
    const key = r.scope + "." + r.meter, choices = meterChoices(f.asset, true);
    row.append(h("select", { "aria-label": "event", onchange: (e) => { [r.scope, r.meter] = e.target.value.split("."); } },
      choices.map(([v, l]) => h("option", { value: v, text: l, selected: v === key }))));
  }
  if (r.kind === "date") row.append(h("input", { type: "date", value: r.on, onchange: (e) => { r.on = e.target.value; } }),
    h("span", { class: "rule-alarm", text: "early alarm" }), numInput(r, "lead", { min: 0, class: "n" }), h("span", { text: "days before" }));
  if (f.rules.length > 1) row.append(h("button", { class: "btn ghost small", type: "button", text: "Remove", onclick: () => { f.rules.splice(i, 1); redraw(); } }));
  return row;
}
function meterChoicesUnit(r) {
  const rows = r.scope === "tool" ? Object.values(M.data.meters.tools)[0] || [] : M.data.meters.machine;
  const m = rows.find((x) => x.meter === r.meter);
  return m ? (m.unit === "h" ? "h" : m.unit === "m" ? "m" : "") : "";
}

function taskPayload() {
  const f = TE.f;
  return { ...f, rules: f.rules.map((r) => r.kind === "event" ? { kind: "meter", meter: r.meter, scope: r.scope, every: 1, event: true } : r) };
}
async function saveTask() {
  $("taskSave").disabled = true;
  try {
    if (TE.mode === "template") {
      const r = await api("POST", "/api/maint/templates" + (TE.id ? "/" + encodeURIComponent(TE.id) : ""), taskPayload());
      closeModal("taskModal"); toast(r.updated_tasks ? `Library task saved - ${r.updated_tasks} linked task(s) updated.` : "Library task saved.");
      await refreshMaint(true); return;
    }
    if (TE.id) await api("POST", `/api/maint/tasks/${TE.id}`, taskPayload());
    else await api("POST", "/api/maint/tasks", taskPayload());
    closeModal("taskModal"); toast("Task saved."); await refreshMaint(true);
  } catch (e) { showError("taskError", e.message); }
  finally { $("taskSave").disabled = false; }
}
let delTimer;
async function deleteTask() {
  if (!TE.confirm) { TE.confirm = true; $("taskDelete").textContent = "Click again to delete";
    clearTimeout(delTimer); delTimer = setTimeout(() => { TE.confirm = false; $("taskDelete").textContent = TE.mode === "template" ? "Delete library task" : "Delete task"; }, 4000); return; }
  try {
    if (TE.mode === "template") { const r = await api("DELETE", `/api/maint/templates/${encodeURIComponent(TE.id)}`); closeModal("taskModal");
      toast(r.detached ? `Deleted. ${r.detached} task(s) made from it are kept as ordinary tasks.` : "Library task deleted."); }
    else { await api("DELETE", `/api/maint/tasks/${TE.id}`); closeModal("taskModal"); toast("Task deleted. Its work-log entries are kept."); }
    await refreshMaint(true);
  } catch (e) { showError("taskError", e.message); }
}

/* ============================ 7. log work + status ============================ */
const DN = { task: null, f: null };
function logOptions() {
  return [["done", "Done"], ["skipped", "Skipped - not needed this time"], ...customStatuses().filter((x) => x.log_option).map((x) => [x.id, x.label])];
}
function openDone(t) {
  DN.task = t; DN.f = { action: "done", date: today(), notes: "" };
  $("doneTitle").textContent = "Log work - " + t.title;
  drawDone(); showError("doneError", ""); $("doneModal").classList.remove("hidden");
}
function actionHelp(a) {
  if (a === "done") return "The schedule starts again from now (a part replaced starts its hours again too).";
  if (a === "skipped") return "Checked and nothing needed doing. The schedule also starts again.";
  const s = sdef(a);
  return (s.help ? s.help + " " : "") + ({ none: "The task keeps ageing.", pause: "Its clock pauses while the status is set.", done: "Counts as done: the interval starts again." })[s.clock || "none"] +
    (s.note_required ? " A note is required." : "");
}
function drawDone() {
  const t = DN.task, f = DN.f, b = clear($("doneBody"));
  b.append(h("div", { class: "muted small", text: t.asset_label + (t.status && t.status.next ? " · " + t.status.next.text : "") }));
  if (t.steps && t.steps.length) b.append(h("details", { class: "steps-box", open: true }, h("summary", { text: "Steps" }), h("ol", {}, t.steps.map((s) => h("li", { text: s })))));
  if (t.safety) b.append(h("div", { class: "warnbox", text: "Safety: " + t.safety }));
  const custom = !["done", "skipped"].includes(f.action);
  b.append(h("div", { class: "row" },
      field("What happened?", selectInput(f, "action", logOptions(), { onchange: () => drawDone() }), actionHelp(f.action)),
      custom ? null : field("When", h("input", { type: "date", value: f.date, max: today(), onchange: (e) => { f.date = e.target.value; } }))),
    field(custom && sdef(f.action).note_required ? "Note (required)" : "Notes (optional)", h("textarea", { class: "short", maxlength: 1000,
      placeholder: custom ? "Which parts, who, when..." : "What you found, parts used...", oninput: (e) => { f.notes = e.target.value; }, text: f.notes })),
    h("p", { class: "hint", text: custom ? "The status shows on the task until it is cleared, logged done, or ends by its own rule (Admin > Status codes)." :
      "The current meter readings are saved with this entry." }));
  $("doneSave").textContent = custom ? "Set status and log it" : "Save to the work log";
}
async function saveDone() {
  try { await api("POST", `/api/maint/tasks/${DN.task.id}/done`, DN.f); closeModal("doneModal"); closeModal("taskModal");
        toast(DN.f.action === "done" ? "Logged. The schedule starts again from here." : DN.f.action === "skipped" ? "Skipped and logged." : `Status set: ${sdef(DN.f.action).label}.`);
        await refreshMaint(true); }
  catch (e) { showError("doneError", e.message); }
}
async function snooze(t, days) {
  try { await api("POST", `/api/maint/tasks/${t.id}/snooze`, { days }); toast(days ? `Snoozed for ${days} day(s).` : "Snooze cancelled."); await refreshMaint(true); }
  catch (e) { toast(e.message, true); }
}
const ST = { task: null, f: null };
function openStatus(t) {
  ST.task = t; ST.f = { status: (t.status && t.status.hold) ? t.status.hold.id : (customStatuses()[0] || {}).id || "", note: (t.status && t.status.hold) ? t.status.hold.note : "" };
  $("statusTitle").textContent = "Status - " + t.title; drawStatus(); showError("statusError", ""); $("statusModal").classList.remove("hidden");
}
function drawStatus() {
  const b = clear($("statusBody")), f = ST.f, cs = customStatuses(), held = ST.task.status && ST.task.status.hold;
  if (!cs.length) { b.append(h("p", { class: "muted", text: "No status codes yet - add them under Admin > Status codes." })); return; }
  const choices = [...cs.map((x) => [x.id, x.label]), ...(held ? [["", "Clear the status"]] : [])];
  const s = sdef(f.status);
  b.append(field("Status", selectInput(f, "status", choices, { onchange: () => drawStatus() }), f.status ? actionHelp(f.status) : "Back to the schedule's own status."),
    field(f.status && s.note_required ? "Note (required)" : "Note (optional)", textInput(f, "note", { maxlength: 300, placeholder: "GT2 belt ordered, arrives Friday" })));
  if (f.status) b.append(h("div", { class: "hint", text: ({ due: "Shown with the due tasks.", upcoming: "Shown with the upcoming tasks.", own: "Shown in its own group on Due & upcoming." })[s.list] +
    (s.boot_prompt ? " Still in the Mainsail reminder when due." : " Left out of the Mainsail reminder.") }));
  $("statusSave").textContent = f.status ? "Set status" : "Clear status";
}
async function saveStatus() {
  try { await api("POST", `/api/maint/tasks/${ST.task.id}/status`, ST.f); closeModal("statusModal"); toast(ST.f.status ? `Status set: ${sdef(ST.f.status).label}.` : "Status cleared.");
        await refreshMaint(true); }
  catch (e) { showError("statusError", e.message); }
}

/* ============================ 8. Task Library + Task Books ============================ */
async function loadLib() { M.lib = await api("GET", "/api/maint/tasklib"); return M.lib; }
function renderLib() {
  const L = M.lib; if (!L) return;
  const tabs = clear($("libTabs"));
  [["books", `Task Books (${L.books.length})`], ["tasks", `Library tasks (${L.templates.length})`]].forEach(([k, l]) => tabs.append(h("button", {
    class: "tab" + (M.libTab === k ? " on" : ""), type: "button", role: "tab", "aria-selected": String(M.libTab === k), text: l, onclick: () => { M.libTab = k; renderLib(); } })));
  const box = clear($("libBox"));
  if (M.libTab === "books") {
    box.append(h("div", { class: "grid books" }, L.books.map((bk) => {
      const titles = bk.templates.map((id) => (L.templates.find((x) => x.id === id) || {}).title).filter(Boolean);
      return h("div", { class: "card book-card" },
        h("div", { class: "card-head" }, h("h2", { text: bk.name }), h("span", { class: "badge" + (bk.origin === "starter" ? " builtin" : " cap"), text: bk.origin === "starter" ? "Starter" : "Yours" })),
        bk.description ? h("div", { class: "muted small", text: bk.description }) : null,
        h("ol", { class: "book-list" }, titles.map((x) => h("li", { text: x }))),
        h("div", { class: "lbl", text: bk.needs_tool ? "On (toolheads only)" : "On" }),
        h("div", { class: "tags" }, bk.assigned.length ? bk.assigned.map((a, i) => h("span", { class: "badge chip-x" }, bk.assigned_labels[i],
          h("button", { class: "x", type: "button", "aria-label": "Take the book off " + bk.assigned_labels[i], text: "×", onclick: () => unassignBook(bk, a, bk.assigned_labels[i]) })))
          : h("span", { class: "muted small", text: "Not assigned yet" })),
        h("div", { class: "card-actions" }, h("button", { class: "btn small", type: "button", text: "Assign...", onclick: () => openAssign("book", bk) }),
          h("button", { class: "btn ghost small", type: "button", text: "Edit", onclick: () => openBook(bk) })));
    })));
    if (!L.books.length) box.append(h("div", { class: "card empty", text: "No Task Books yet." }));
    return;
  }
  const tb = h("table", { class: "tbl" }, h("tr", {}, ["Library task", "Schedule", "Goes on", "In books", "Used by", ""].map((x) => h("th", { text: x }))));
  for (const x of L.templates) tb.append(h("tr", {},
    h("td", {}, h("strong", { text: x.title }), h("div", { class: "hint", text: (L.types[x.type] || x.type) + (x.origin === "starter" ? " · starter" : "") })),
    h("td", { class: "small", text: x.schedule }),
    h("td", { class: "small", text: x.applies === "tool" ? "Toolheads" : "Anything" + (x.area_label ? ` (machine: ${x.area_label})` : "") }),
    h("td", { class: "small", text: x.books.join(", ") || "-" }),
    h("td", { class: "small", text: x.uses.length ? x.uses.join(", ") : "-" }),
    h("td", { class: "nowrap" }, h("button", { class: "btn ghost small", type: "button", text: "Edit", onclick: () => openTemplate(x) }),
      h("button", { class: "btn ghost small", type: "button", text: "Add to...", onclick: () => openAssign("template", x) }))));
  box.append(h("div", { class: "card" }, h("div", { class: "table-wrap" }, tb)));
}
async function unassignBook(bk, asset, label) {
  try { await api("POST", `/api/maint/books/${encodeURIComponent(bk.id)}/assign`, { asset, on: false });
        toast(`${bk.name} taken off ${label}. Its tasks there are archived (history kept).`); await refreshMaint(true); }
  catch (e) { toast(e.message, true); }
}

const BK = { id: null, f: null, filter: "", confirm: false };
function openBook(bk) {
  BK.id = bk ? bk.id : null; BK.confirm = false; BK.filter = "";
  BK.f = bk ? { name: bk.name, description: bk.description || "", templates: [...bk.templates] } : { name: "", description: "", templates: [] };
  BK.assigned = bk ? bk.assigned_labels : [];
  $("bookTitle").textContent = bk ? "Edit Task Book" : "New Task Book";
  $("bookDelete").classList.toggle("hidden", !bk); $("bookDelete").textContent = "Delete book";
  showError("bookError", ""); $("bookModal").classList.remove("hidden"); drawBook();
}
function drawBook() {
  const b = clear($("bookBody")), f = BK.f, L = M.lib;
  b.append(h("div", { class: "row" }, field("Book name", textInput(f, "name", { maxlength: 60, placeholder: "Wide-nozzle print head" })),
    field("Description (optional)", textInput(f, "description", { maxlength: 200, placeholder: "What the book covers" }))));
  if (BK.assigned.length) b.append(h("div", { class: "linkbox" }, h("strong", { text: "Assigned to " + BK.assigned.join(", ") }),
    h("div", { class: "hint", text: "Tasks you add are added there too; tasks you take out are archived there (their work log is kept)." })));
  const list = h("div", { class: "pick-list" });
  const draw = () => {
    clear(list);
    const q = BK.filter.toLowerCase();
    for (const grp of [["any", "Goes on anything"], ["tool", "Toolheads only (counts the tool's own use)"]]) {
      const items = L.templates.filter((x) => x.applies === grp[0] && (!q || x.title.toLowerCase().includes(q)));
      if (!items.length) continue;
      list.append(h("div", { class: "lbl", text: grp[1] }));
      for (const x of items) list.append(h("label", { class: "check lib-item" }, h("input", { type: "checkbox", checked: f.templates.includes(x.id),
        onchange: (e) => { f.templates = f.templates.filter((y) => y !== x.id); if (e.target.checked) f.templates.push(x.id); $("bookCount").textContent = `${f.templates.length} selected`; } }),
        h("span", {}, x.title, h("div", { class: "hint", text: x.schedule }))));
    }
  };
  b.append(h("fieldset", {}, h("legend", { text: "Tasks in the book" }),
    h("div", { class: "filter-row" }, h("input", { type: "text", placeholder: "Find a library task...", value: BK.filter, oninput: (e) => { BK.filter = e.target.value; draw(); } }),
      h("span", { class: "muted small nowrap", id: "bookCount", text: `${f.templates.length} selected` })), list,
    h("div", { class: "hint", text: "Need a task that is not here? Add it with + Library task first." })));
  draw();
}
async function saveBook() {
  $("bookSave").disabled = true;
  try { const r = await api("POST", "/api/maint/books" + (BK.id ? "/" + encodeURIComponent(BK.id) : ""), BK.f); closeModal("bookModal");
        toast("Task Book saved." + (r.added ? ` ${r.added} task(s) added where it is assigned.` : "")); await refreshMaint(true); }
  catch (e) { showError("bookError", e.message); }
  finally { $("bookSave").disabled = false; }
}
let bookDelTimer;
async function deleteBook() {
  if (!BK.confirm) { BK.confirm = true; $("bookDelete").textContent = "Click again to delete";
    clearTimeout(bookDelTimer); bookDelTimer = setTimeout(() => { BK.confirm = false; $("bookDelete").textContent = "Delete book"; }, 4000); return; }
  try { await api("DELETE", `/api/maint/books/${encodeURIComponent(BK.id)}`); closeModal("bookModal"); toast("Task Book deleted. Its tasks are archived where it was assigned."); await refreshMaint(true); }
  catch (e) { showError("bookError", e.message); }
}

/* ============================ 9. assign a book or a library task ============================ */
const AS = { kind: "", item: null, f: null };
function openAssign(kind, item, presetAsset) {
  AS.kind = kind; AS.item = item;
  const choices = assetChoices(true).filter(([v]) => !(item.needs_tool || item.applies === "tool") || v.startsWith("tool:"));
  AS.f = { asset: presetAsset || (choices[0] || [""])[0] };
  $("assignTitle").textContent = (kind === "book" ? "Assign the book " : "Add ") + `"${kind === "book" ? item.name : item.title}"`;
  const b = clear($("assignBody"));
  b.append(field(kind === "book" ? "Assign it to" : "Add it to", selectInput(AS.f, "asset", choices)),
    h("p", { class: "hint", text: kind === "book"
      ? `Adds ${item.templates.length} task(s), linked to the library: editing a library task updates them. "Whole machine" puts each task in its own area.`
      : "Adds one task, linked to the library task." }));
  if (item.needs_tool || item.applies === "tool") b.append(h("p", { class: "hint", text: "Only toolheads are listed: these tasks count a tool's own use." }));
  $("assignSave").textContent = kind === "book" ? "Assign book" : "Add task";
  showError("assignError", ""); $("assignModal").classList.remove("hidden");
}
async function saveAssign() {
  try {
    const url = AS.kind === "book" ? `/api/maint/books/${encodeURIComponent(AS.item.id)}/assign` : `/api/maint/templates/${encodeURIComponent(AS.item.id)}/assign`;
    const r = await api("POST", url, { asset: AS.f.asset });
    closeModal("assignModal"); toast(r.added ? `${r.added} task(s) added.` : "Already there - nothing added."); await refreshMaint(true);
  } catch (e) { showError("assignError", e.message); }
}

/* ============================ 10. boot ============================ */
async function refreshMaint(force) {
  try { await load(force); } catch (e) { return; }
  const v = window.RH.currentView();
  if (v === "mdue") renderDue();
  if (v === "mtasks") renderTasks();
  if (v === "mmeters") renderMeters();
  if (v === "mhistory") renderHistory().catch((e) => toast(e.message, true));
  if (v === "mlib" || M.lib) { try { await loadLib(); } catch (e) { return; } if (window.RH.currentView() === "mlib") renderLib(); }
}
document.addEventListener("rhino:view", (e) => { if (VIEWS.includes(e.detail)) refreshMaint(true); });
document.addEventListener("rhino:state", () => {
  const v = window.RH.currentView(), modal = document.querySelector(".modal:not(.hidden)");
  if (modal) { if (M.data) renderBadge(); return; }
  if (VIEWS.includes(v) && v !== "mhistory" && v !== "mlib") refreshMaint(true);
  else if (Date.now() - M.loadedAt > 60000) load(true).catch(() => {}); else if (M.data) renderBadge();
});
document.querySelectorAll("[data-mnew]").forEach((b) => { b.onclick = async () => { await load(); openTask(null); }; });
document.querySelectorAll("[data-mlibview]").forEach((b) => { b.onclick = () => window.RH.showView("mlib"); });
$("taskSave").onclick = saveTask; $("taskDelete").onclick = deleteTask; $("doneSave").onclick = saveDone;
$("meterSave").onclick = saveMeter; $("statusSave").onclick = saveStatus;
$("bookSave").onclick = saveBook; $("bookDelete").onclick = deleteBook; $("assignSave").onclick = saveAssign;
$("tplNew").onclick = async () => { await load(); await loadLib(); openTemplate(null); };
$("bookNew").onclick = async () => { await load(); await loadLib(); openBook(null); };
window.RH.onToolAdded = async (name) => {          // after Add a tool: offer the Task Book that fits it
  await load(true); await loadLib(); await window.RH.refresh();
  const bid = M.lib.suggested[name], bk = M.lib.books.find((x) => x.id === bid) || M.lib.books.find((x) => x.needs_tool);
  if (bk) openAssign("book", bk, "tool:" + name);
};
window.RH.openAssetTasks = async (asset) => { M.filter = asset; window.RH.showView("mtasks"); };
window.RH.maint = { load: () => load(true), refreshMaint, M };
load(true).catch(() => {});
})();
