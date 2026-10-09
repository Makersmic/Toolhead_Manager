/* Rhino portal - Slice tab (PROTOTYPE). Shows Kiri:Moto (its own small server on this machine,
   port 8090 by default) and opens it on the mounted tool: the portal sends the tool's machine
   profile, built from variables.cfg, and the Rhino mod inside Kiri:Moto selects it.

   Nothing happens unless /api/slice/context says slicing is enabled (myrhino/slicer.json); the tab
   button stays hidden and no frame is ever created.                                                */
(() => {
"use strict";
const { h, clear, api } = window.RH;
const $ = (id) => document.getElementById(id);
const K = { ctx: null, frame: null, origin: "", ready: false, selected: "", helloTimer: null, waitStart: 0 };

function chip(text, cls = "") { const c = $("sliceChip"); c.textContent = text; c.className = "chip" + (cls ? " " + cls : ""); }
function bar(tool, why) { $("sliceTool").textContent = tool; $("sliceWhy").textContent = why || ""; }

function showProblems(list) {
  const ul = clear($("sliceProblems"));
  (list || []).forEach((p) => ul.append(h("li", { text: p })));
  ul.classList.toggle("hidden", !(list || []).length);
}

async function loadContext() {
  const d = await api("GET", "/api/slice/context");
  K.ctx = d.enabled ? d : null;
  return K.ctx;
}

function post(msg) {
  if (K.frame && K.frame.contentWindow && K.origin) K.frame.contentWindow.postMessage({ rhino: msg }, K.origin);
}

function startFrame() {
  if (K.frame) return;
  K.origin = `${location.protocol}//${location.hostname}:${K.ctx.kiri_port}`;
  K.frame = h("iframe", { class: "slice-frame", src: `${K.origin}/kiri/`, title: "Kiri:Moto slicer",
                          allow: "clipboard-write", referrerpolicy: "same-origin" });
  clear($("sliceWrap")).append(K.frame);
  chip("Starting Kiri:Moto...", "");
  K.waitStart = Date.now();
  K.helloTimer = setInterval(() => {                 // Kiri:Moto takes a few seconds to start; ask until it answers
    if (K.ready) { clearInterval(K.helloTimer); return; }
    if (Date.now() - K.waitStart > 60000) {
      clearInterval(K.helloTimer);
      chip("Kiri:Moto not answering", "bad");
      bar("Kiri:Moto did not answer.", `Nothing replied on port ${K.ctx.kiri_port}. Is the Kiri:Moto service running on this machine?`);
      return;
    }
    post({ type: "hello" });
  }, 700);
}

function selectMounted() {
  const c = K.ctx, m = c.mounted || {};
  if (!c.profile) {
    chip(m.name ? `${m.name} mounted` : "No profile", "warn");
    bar(m.name ? `${m.name} is mounted (slot ${m.slot}).` : "Mounted tool unknown.", c.why);
    return;
  }
  if (K.selected === c.profile.deviceName) { if (K.lastSel) showSelected(K.lastSel); return; }   // already showing this tool
  chip(`Setting up ${c.profile.tool}...`);
  post({ type: "select", mode: c.profile.mode, deviceName: c.profile.deviceName, device: c.profile.device,
         processes: c.profile.processes, process: c.profile.process });
}

function showSelected(m) {
  const p = K.ctx.profile, mt = K.ctx.mounted;
  if (!p) return;
  chip(`${p.tool} · ${m.mode === "LASER" ? "laser" : m.mode.toLowerCase()}`, "ok");
  bar(`${p.tool} is mounted (slot ${mt.slot}).`,
      `Kiri:Moto is in ${m.mode === "LASER" ? "Laser" : m.mode} mode with the ${m.deviceName} profile` +
      (m.process ? ` and the ${m.process} settings.` : "."));
}

window.addEventListener("message", (e) => {
  if (!K.frame || e.source !== K.frame.contentWindow || e.origin !== K.origin) return;
  const m = e.data && e.data.rhino;
  if (!m) return;
  if (m.type === "ready") {
    if (K.ready) return;
    K.ready = true;
    selectMounted();
  } else if (m.type === "selected") {
    K.selected = m.deviceName; K.lastSel = m;
    showSelected(m);
  } else if (m.type === "error") {
    chip("Kiri:Moto error", "bad");
    bar("Kiri:Moto could not take the Rhino profile.", m.message || "");
  } else if (m.type === "gcode" && typeof m.text === "string") {
    received(m);
  }
});

/* ---------------------------------------------------------------- send to the Rhino, then start
   Every check runs on the portal (server side) again when sending and again when starting; the
   button state here only mirrors it. Nothing is sent while any check fails.                         */
const TOKEN = document.querySelector('meta[name="rhino-token"]').content;
const J = { name: "", text: "", tool: "", state: "", conflicts: null, file: "", msg: "", err: "", poll: null, busy: false };

function stampOf(text) {
  const lines = text.split(/\r?\n/, 50);
  for (const l of lines) { const mm = /^;\s*RHINO_TOOL=([A-Za-z0-9_-]{1,40})\s*$/.exec(l.trim()); if (mm) return mm[1]; }
  return "";
}

async function postJSON(url, body) {           // like RH.api, but keeps the list of conflicts from a refusal
  let res, data;
  try {
    res = await fetch(url, { method: "POST", headers: { "X-Rhino-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    data = await res.json();
  } catch (e) { return { ok: false, error: "Cannot reach the portal - is it still running?" }; }
  return data;
}

function received(m) {
  Object.assign(J, { name: m.name || "job.gcode", text: m.text, tool: stampOf(m.text), state: "check", conflicts: null,
                     file: "", msg: "", err: "", busy: false });
  recheck();
  clearInterval(J.poll);
  J.poll = setInterval(() => {               // keep the checks live while the file waits to be sent or started
    if (!["check", "sent"].includes(J.state) || $("view-slice").classList.contains("hidden")) return;
    recheck();
  }, 3000);
}

async function recheck() {
  try {
    const d = await api("GET", "/api/slice/check?tool=" + encodeURIComponent(J.tool));
    J.conflicts = d.conflicts; J.err = "";
    if (K.ctx && d.mounted !== ((K.ctx.mounted || {}).name || "")) onOpen();   // tool swapped: refresh the bar and profile
  } catch (e) { J.conflicts = null; J.err = e.message; }
  drawSend();
}

async function doSend() {
  J.busy = true; drawSend();
  const d = await postJSON("/api/slice/send", { name: J.name, gcode: J.text });
  J.busy = false;
  if (d.ok) { Object.assign(J, { state: "sent", file: d.file, conflicts: d.conflicts || [], err: "" }); recheck(); return; }
  J.conflicts = d.conflicts || J.conflicts; J.err = d.conflicts ? "" : (d.error || "Not sent.");
  drawSend();
}

async function doStart() {
  J.busy = true; drawSend();
  const d = await postJSON("/api/slice/start", { file: J.file });
  J.busy = false;
  if (d.ok) { Object.assign(J, { state: "started", err: "" }); clearInterval(J.poll); drawSend(); return; }
  J.conflicts = d.conflicts || J.conflicts; J.err = d.conflicts ? "" : (d.error || "Not started.");
  drawSend();
}

function mainsailUrl() { return (K.ctx && K.ctx.mainsail_url) || `${location.protocol}//${location.hostname}/`; }

function checksList() {
  const ul = h("ul", { class: "slice-checks" });
  if (J.err) ul.append(h("li", {}, h("span", { class: "tag bad", text: "Error" }), h("span", { text: J.err })));
  else if (J.conflicts === null) ul.append(h("li", { class: "muted", text: "Checking the printer..." }));
  else if (!J.conflicts.length) ul.append(h("li", {}, h("span", { class: "tag ok", text: "Clear" }),
      h("span", { text: `${J.tool} is mounted, Klipper is ready and no job is running.` })));
  else J.conflicts.forEach((c) => ul.append(h("li", {}, h("span", { class: "tag bad", text: "Fix" }), h("span", { text: c }))));
  return ul;
}

function drawSend() {
  const box = clear($("sliceSend"));
  box.classList.toggle("hidden", !J.state);
  if (!J.state) return;
  const blocked = J.conflicts === null || J.conflicts.length > 0 || !!J.err;
  const lines = J.text.split("\n").length;
  const close = h("button", { class: "btn ghost small", text: "Close", onclick: () => { J.state = ""; clearInterval(J.poll); drawSend(); } });
  if (J.state === "check") {
    box.append(h("h2", { text: "Send to the Rhino" }),
      h("p", { class: "muted small", text: `${J.name} from Kiri:Moto - ${lines} lines` + (J.tool ? `, sliced for ${J.tool}` : ", no Rhino tool stamp") }),
      checksList(),
      h("div", { class: "card-actions" },
        h("button", { class: "btn", text: J.busy ? "Sending..." : "Send to Rhino", disabled: blocked || J.busy, onclick: doSend }),
        h("button", { class: "btn ghost", text: "Check again", disabled: J.busy, onclick: recheck }), close,
        blocked && !J.busy ? h("span", { class: "muted small", text: "Sending is blocked until every item above is fixed." }) : null));
  } else if (J.state === "sent") {
    box.append(h("h2", { text: `Sent: ${J.file}` }),
      h("p", { class: "muted small", text: "It is in Mainsail's G-Code Files. Start the guided laser setup for it:" }),
      h("ol", { class: "slice-steps" },
        h("li", { text: "Safety checklist" }), h("li", { text: "Focus with Set Z zero" }),
        h("li", { text: "Test mark" }), h("li", { text: "Start the cut - the file runs" })),
      checksList(),
      h("div", { class: "card-actions" },
        h("button", { class: "btn", text: J.busy ? "Starting..." : "Start laser setup", disabled: blocked || J.busy, onclick: doStart }),
        h("button", { class: "btn ghost", text: "Check again", disabled: J.busy, onclick: recheck }), close));
  } else if (J.state === "started") {
    box.append(h("h2", { text: "Laser setup started" }),
      h("p", { text: `Answer its questions in Mainsail - the safety checklist is showing there now. ${J.file} starts when you press Start the cut.` }),
      h("div", { class: "card-actions" },
        h("a", { class: "btn", href: mainsailUrl(), target: "_blank", rel: "noopener", text: "Open Mainsail" }), close));
  }
}

async function onOpen() {
  try { await loadContext(); } catch (e) { chip("Portal error", "bad"); bar("Could not ask the portal about slicing.", e.message); return; }
  if (!K.ctx) return;
  showProblems(K.ctx.problems);
  const before = K.selected;
  startFrame();
  if (K.ready) {
    if (K.ctx.profile && before !== K.ctx.profile.deviceName) K.selected = "";
    selectMounted();
  } else {
    const m = K.ctx.mounted || {};
    bar(m.name ? `${m.name} is mounted (slot ${m.slot}).` : "Mounted tool unknown.", K.ctx.why || "Waiting for Kiri:Moto to start...");
  }
}

document.addEventListener("rhino:view", (e) => { if (e.detail === "slice") onOpen(); });

/* boot: show the tab only when slicing is turned on */
loadContext().then((c) => { if (c) $("navSlice").classList.remove("hidden"); }).catch(() => {});
})();
