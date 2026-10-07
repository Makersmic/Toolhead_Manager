/* Rhino portal - Admin screens: what the drop-down menus offer, and the maintenance status codes.
   Uses the helpers portal.js shares on window.RH; everything is built with textContent.

   Sections:  1 tool lists   2 maintenance lists   3 status codes   4 boot                              */
(() => {
"use strict";
const { h, clear, api, toast, field, textInput, numInput, selectInput, pct, frac } = window.RH;
const $ = (id) => document.getElementById(id);
const A = { tools: null, maint: null };
const saveBtn = (label, fn) => h("button", { class: "btn small", type: "button", text: label, onclick: async (e) => {
  e.target.disabled = true; try { await fn(); } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; } } });
const removeBtn = (fn, disabled, why) => h("button", { class: "btn ghost small", type: "button", text: "Remove", disabled: !!disabled, title: why || "", onclick: fn });

/* ============================ 1. tool lists ============================ */
async function loadTools() { A.tools = await api("GET", "/api/lists"); A.tools.edit = JSON.parse(JSON.stringify(A.tools.kinds)); return A.tools; }
function renderTools() {
  const L = A.tools, box = clear($("aTools"));
  if (!L) return;
  const used = L.in_use.kinds || {}, builtin = new Set(L.builtin_kinds);
  const beh = { PRINT_HEAD: "A print head (copies an extruder)", POWERED: "A power output", PASSIVE: "Nothing (unpowered)" };

  // kinds of tool, by category
  const kindsCard = h("div", { class: "card" }, h("h2", { text: "Kinds of tool" }),
    h("p", { class: "muted small", text: "Step 1 of Add a tool asks Additive, Subtractive or Passive, then offers the kinds listed under it. " +
      "What a kind needs (a print head, a power output, or nothing) is fixed once it exists; its name, help and starting values can change." }));
  for (const cat of L.categories) {
    const sec = h("div", { class: "admin-cat" }, h("h3", { class: "admin-h", text: cat.label }), h("div", { class: "hint", text: cat.help }));
    L.edit.forEach((k, i) => {
      if (k.category !== cat.value) return;
      const isNew = !k.id || !A.tools.kinds.some((x) => x.id === k.id);
      const inUse = (used[k.id] || []).length;
      const row = h("div", { class: "admin-row" },
        h("div", { class: "row" },
          field("Name", textInput(k, "label", { maxlength: 60 })),
          isNew ? field("It needs", selectInput(k, "behaviour", L.category_behaviours[cat.value].map((b) => [b, beh[b]]), { onchange: () => renderTools() }))
                : field("It needs", h("input", { type: "text", value: beh[k.behaviour], disabled: true })),
          field("Help shown in the wizard", textInput(k, "help", { maxlength: 200 }))));
      if (k.behaviour !== "PRINT_HEAD") {
        k._mats = k._mats ?? Object.entries(k.materials || {}).map(([n, m]) => `${n} ${m.power !== undefined ? pct(m.power) + "% " : ""}${m.feed_rate}`).join("\n");
        k._check = k._check ?? (k.checklist || []).join("\n");
        if (k.behaviour === "POWERED") { k._cap = k._cap ?? pct(k.cap ?? 1); k._on = k._on ?? (k.max_on_s ?? 300); }
        row.append(h("details", { class: "fold-inline" }, h("summary", { text: "Starting values for new tools of this kind" }),
          k.behaviour === "POWERED" ? h("div", { class: "row" }, field("Power cap %", numInput(k, "_cap", { min: 5, max: 100 })),
            field("Max time on (s)", numInput(k, "_on", { min: 1, max: 3600 }))) : null,
          h("div", { class: "row" },
            field("Materials (one per line: NAME " + (k.behaviour === "POWERED" ? "power% " : "") + "feed)", h("textarea", { class: "short mono", text: k._mats, oninput: (e) => { k._mats = e.target.value; } })),
            field("Pre-job checklist (one per line)", h("textarea", { class: "short", text: k._check, oninput: (e) => { k._check = e.target.value; } })))));
      }
      row.append(h("div", { class: "admin-row-foot" },
        h("span", { class: "hint", text: builtin.has(k.id) ? "Built in" + (inUse ? ` · used by ${used[k.id].join(", ")}` : "") : inUse ? "Used by " + used[k.id].join(", ") : "Not used yet" }),
        removeBtn(() => { L.edit.splice(i, 1); renderTools(); }, builtin.has(k.id) || inUse, builtin.has(k.id) ? "Built-in kinds can be renamed, not removed" : "Tools use it")));
      sec.append(row);
    });
    sec.append(h("button", { class: "btn ghost small", type: "button", text: `+ Add ${cat.value === "passive" ? "a" : "an"} ${cat.label.toLowerCase()} kind`, onclick: () => {
      L.edit.push({ id: "", category: cat.value, behaviour: L.category_behaviours[cat.value][0], label: "", help: "" }); renderTools(); } }));
    kindsCard.append(sec);
  }
  kindsCard.append(h("div", { class: "card-actions" }, saveBtn("Save kinds of tool", saveKinds)));
  box.append(kindsCard);

  // materials, nozzles, hardware categories
  const mats = Object.fromEntries(L.categories.map((c) => [c.value, (L.materials[c.value] || []).join(", ")]));
  box.append(h("div", { class: "card" }, h("h2", { text: "Material names" }),
    h("p", { class: "muted small", text: "Suggested in the material tables of Add a tool and Edit, by category. Any other name can still be typed." }),
    h("div", { class: "row" }, L.categories.map((c) => field(c.label, h("textarea", { class: "mono", rows: 4, text: mats[c.value], oninput: (e) => { mats[c.value] = e.target.value; } })))),
    h("div", { class: "hint", text: "Separate names with commas. Letters, digits and _ - spaces become _." }),
    h("div", { class: "card-actions" }, saveBtn("Save material names", async () => { const r = await api("POST", "/api/lists", { materials: mats }); toast("Material names saved."); await reloadTools(r); }))));
  const nz = { v: L.nozzles.join(", ") };
  box.append(h("div", { class: "card" }, h("h2", { text: "Nozzle sizes" }),
    h("p", { class: "muted small", text: "The sizes offered as tick boxes when you add a print head." }),
    field("Sizes (mm, comma separated)", textInput(nz, "v", { class: "mono" })),
    h("div", { class: "card-actions" }, saveBtn("Save nozzle sizes", async () => { const r = await api("POST", "/api/lists", { nozzles: nz.v }); toast("Nozzle sizes saved."); await reloadTools(r); }))));
  const cats = L.hw_categories.map((c) => ({ ...c })), hwUse = L.in_use.hw_categories || {};
  const catBox = h("div", {});
  const drawCats = () => { clear(catBox); cats.forEach((c, i) => catBox.append(h("div", { class: "area-row" }, textInput(c, "label", { maxlength: 40, "aria-label": "category" }),
    h("span", { class: "hint nowrap", text: (hwUse[c.id] || []).length ? `${hwUse[c.id].length} in use` : "" }),
    removeBtn(() => { cats.splice(i, 1); drawCats(); }, (hwUse[c.id] || []).length, "Hardware uses it")))); };
  drawCats();
  box.append(h("div", { class: "card" }, h("h2", { text: "System hardware categories" }),
    h("p", { class: "muted small", text: "How System hardware is grouped." }), catBox,
    h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "+ Add category", onclick: () => { cats.push({ id: "", label: "" }); drawCats(); } }),
      saveBtn("Save categories", async () => { const r = await api("POST", "/api/lists", { hw_categories: cats }); toast("Categories saved."); await reloadTools(r); }))));
}
function kindPayload(k) {
  const out = { id: k.id, category: k.category, behaviour: k.behaviour, label: k.label, help: k.help };
  if (k.behaviour === "PRINT_HEAD") return out;
  out.checklist = k._check !== undefined ? k._check : (k.checklist || []);
  if (k._mats !== undefined) {
    out.materials = {};
    for (const line of k._mats.split("\n").map((x) => x.trim()).filter(Boolean)) {
      const parts = line.split(/\s+/), name = parts[0].toUpperCase();
      if (k.behaviour === "POWERED") out.materials[name] = { power: frac(String(parts[1] || "50").replace("%", "")), feed_rate: Number(parts[2] || 600) };
      else out.materials[name] = { feed_rate: Number(parts[1] || 800) };
    }
  } else out.materials = k.materials;
  if (k.behaviour === "POWERED") { out.cap = k._cap !== undefined ? frac(k._cap) : k.cap; out.max_on_s = k._on !== undefined ? k._on : k.max_on_s; }
  return out;
}
async function saveKinds() {
  const r = await api("POST", "/api/lists", { kinds: A.tools.edit.map(kindPayload) });
  toast("Kinds of tool saved. Add a tool uses them straight away."); await reloadTools(r);
}
async function reloadTools() { await loadTools(); await window.RH.loadOptions().catch(() => {}); renderTools(); }

/* ============================ 2. maintenance lists ============================ */
async function loadMaint() { A.maint = await api("GET", "/api/maint/lists"); return A.maint; }
function renderMaint() {
  const L = A.maint, box = clear($("aMaint"));
  if (!L) return;
  const areas = L.areas.map((a) => ({ ...a }));
  const areaBox = h("div", {});
  const drawAreas = () => { clear(areaBox); areas.forEach((a, i) => areaBox.append(h("div", { class: "area-row" }, textInput(a, "label", { maxlength: 40, "aria-label": "area name" }),
    removeBtn(() => { areas.splice(i, 1); drawAreas(); })))); };
  drawAreas();
  box.append(h("div", { class: "card" }, h("h2", { text: "Machine areas" }),
    h("p", { class: "muted small", text: "Machine tasks are grouped by area (the 'For' list of a task). An area with tasks cannot be removed." }), areaBox,
    h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "+ Add area", onclick: () => { areas.push({ id: "", label: "" }); drawAreas(); } }),
      saveBtn("Save areas", async () => { await api("POST", "/api/maint/areas", { areas }); toast("Areas saved."); await reloadMaint(); }))));
  const types = Object.entries(L.types).map(([id, label]) => ({ id, label }));
  const typeBox = h("div", {});
  const drawTypes = () => { clear(typeBox); types.forEach((t, i) => typeBox.append(h("div", { class: "area-row" }, textInput(t, "label", { maxlength: 30, "aria-label": "kind of work" }),
    h("span", { class: "hint nowrap", text: L.type_use[t.id] ? `${L.type_use[t.id]} task(s)` : "" }),
    removeBtn(() => { types.splice(i, 1); drawTypes(); }, L.type_use[t.id], "Tasks use it - rename it instead")))); };
  drawTypes();
  box.append(h("div", { class: "card" }, h("h2", { text: "Kinds of work" }),
    h("p", { class: "muted small", text: "Inspect, clean, lubricate... the 'Kind of work' list of a task." }), typeBox,
    h("div", { class: "card-actions" }, h("button", { class: "btn ghost small", type: "button", text: "+ Add kind of work", onclick: () => { types.push({ id: "", label: "" }); drawTypes(); } }),
      saveBtn("Save kinds of work", async () => { await api("POST", "/api/maint/lists", { types }); toast("Kinds of work saved."); await reloadMaint(); }))));
  const pr = { ...L.priorities };
  box.append(h("div", { class: "card" }, h("h2", { text: "Priorities" }),
    h("p", { class: "muted small", text: "Four levels, most urgent last. They order the Mainsail reminder; rename them to suit you." }),
    h("div", { class: "row" }, Object.keys(pr).map((k) => field(k[0].toUpperCase() + k.slice(1), textInput(pr, k, { maxlength: 20 })))),
    h("div", { class: "card-actions" }, saveBtn("Save priorities", async () => { await api("POST", "/api/maint/lists", { priorities: pr }); toast("Priorities saved."); await reloadMaint(); }))));
}
async function reloadMaint() { await loadMaint(); renderMaint(); renderStatus(); if (window.RH.maint) window.RH.maint.refreshMaint(true); }

/* ============================ 3. status codes ============================ */
function colourSelect(obj, key, colors) {
  const sw = h("span", { class: "swatch" });
  const paint = () => sw.style.setProperty("--pill", colors[obj[key]] || "#8d8f99");
  const sel = selectInput(obj, key, Object.keys(colors).map((c) => [c, c[0].toUpperCase() + c.slice(1)]), { onchange: paint, "aria-label": "colour" });
  paint();
  return h("div", { class: "colour-pick" }, sw, sel);
}
function renderStatus() {
  const L = A.maint, box = clear($("aStatus"));
  if (!L) return;
  if (!A.statusEdit) A.statusEdit = { builtin: JSON.parse(JSON.stringify(L.statuses.builtin)), custom: JSON.parse(JSON.stringify(L.statuses.custom)) };
  const E = A.statusEdit;
  const bt = h("table", { class: "tbl" }, h("tr", {}, ["Status", "Name shown", "Colour", "When"].map((x) => h("th", { text: x }))));
  for (const [id, v] of Object.entries(E.builtin)) bt.append(h("tr", {}, h("td", { class: "mono small", text: id }),
    h("td", {}, textInput(v, "label", { maxlength: 30 })), h("td", {}, colourSelect(v, "color", L.colors)), h("td", { class: "small muted", text: L.builtin_status_help[id] })));
  box.append(h("div", { class: "card" }, h("h2", { text: "Built-in statuses" }),
    h("p", { class: "muted small", text: "Worked out from each task's schedule, the snooze and the pause switch. Rename them or change their colour; they cannot be removed." }),
    h("div", { class: "table-wrap" }, bt)));

  const list = h("div", {});
  E.custom.forEach((s, i) => {
    const inUse = L.status_use[s.id] || 0;
    const radio = (key, val, title) => h("label", { class: "radio compact" + (s[key] === val ? " on" : "") },
      h("input", { type: "radio", name: `${key}_${i}`, checked: s[key] === val, onchange: () => { s[key] = val; renderStatus(); } }), h("span", { text: title }));
    const tick = (key, title, hint) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!s[key], onchange: (e) => { s[key] = e.target.checked; } }),
      h("span", {}, title, hint ? h("div", { class: "hint", text: hint }) : null));
    const card = h("div", { class: "status-card" });
    card.style.setProperty("--pill", L.colors[s.color] || "#8d8f99");
    card.append(h("div", { class: "row" }, field("Name", textInput(s, "label", { maxlength: 40, placeholder: "Pending - Waiting on parts" })),
        field("Colour", colourSelect(s, "color", L.colors)), field("Description (shown when it is chosen)", textInput(s, "help", { maxlength: 200 }))),
      h("div", { class: "rule-grid" },
        h("div", {}, h("div", { class: "lbl", text: "1. Where does the task show?" }), Object.entries(L.status_lists).map(([v, t]) => radio("list", v, t))),
        h("div", {}, h("div", { class: "lbl", text: "2. What happens to its schedule?" }), Object.entries(L.status_clock).map(([v, t]) => radio("clock", v, t))),
        h("div", {}, h("div", { class: "lbl", text: "3. When does it end by itself?" }), Object.entries(L.status_expiry).map(([v, t]) => radio("expiry", v, t)),
          s.expiry === "days" ? field("Days", numInput(s, "expiry_days", { min: 1, max: 365 })) : null,
          h("div", { class: "hint", text: "When it ends, the task goes back to its built-in status. Logging the task done also ends it." }))),
      h("div", { class: "lbl", text: "4. Also" }),
      h("div", { class: "row" },
        tick("boot_prompt", "Keep it in the Mainsail reminder", "The task still shows after a Klipper start when it is due."),
        tick("note_required", "A note is required", "Whoever sets it has to say why (which parts, who, when)."),
        tick("log_option", "Offer it in the Log work list", "Next to Done and Skipped.")),
      h("div", { class: "admin-row-foot" }, h("span", { class: "hint", text: inUse ? `Set on ${inUse} task(s) now` : "" }),
        removeBtn(() => { E.custom.splice(i, 1); renderStatus(); }, inUse, "Clear it from those tasks first")));
    list.append(card);
  });
  box.append(h("div", { class: "card" }, h("h2", { text: "Your status codes" }),
    h("p", { class: "muted small", text: "Set by hand on a task, for example Pending - Waiting on parts. Answer the four questions and the portal applies the rules: " +
      "where the task is listed, whether its schedule keeps running, when the status ends, and the extras." }), list,
    E.custom.length < 20 ? h("button", { class: "btn ghost small", type: "button", text: "+ Add a status code", onclick: () => {
      E.custom.push({ id: "", label: "", color: "purple", help: "", list: "own", boot_prompt: false, note_required: false, clock: "none", expiry: "never", expiry_days: 7, log_option: true });
      renderStatus(); } }) : null,
    h("div", { class: "card-actions" }, saveBtn("Save status codes", async () => {
      await api("POST", "/api/maint/statuses", E); A.statusEdit = null; toast("Status codes saved."); await reloadMaint(); }),
      h("button", { class: "btn ghost small", type: "button", text: "Undo changes", onclick: () => { A.statusEdit = null; renderStatus(); } }))));
}

/* ============================ 4. boot ============================ */
document.addEventListener("rhino:view", async (e) => {
  try {
    if (e.detail === "atools") { await loadTools(); renderTools(); }
    if (e.detail === "amaint") { await loadMaint(); renderMaint(); }
    if (e.detail === "astatus") { A.statusEdit = null; await loadMaint(); renderStatus(); }
  } catch (err) { toast(err.message, true); }
});
})();
