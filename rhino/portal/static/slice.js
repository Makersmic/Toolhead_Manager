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
  if (K.selected === c.profile.deviceName) return;   // already showing this tool
  chip(`Setting up ${c.profile.tool}...`);
  post({ type: "select", mode: c.profile.mode, deviceName: c.profile.deviceName, device: c.profile.device,
         processes: c.profile.processes, process: c.profile.process });
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
    const p = K.ctx.profile, mt = K.ctx.mounted;
    K.selected = m.deviceName;
    chip(`${p.tool} · ${m.mode === "LASER" ? "laser" : m.mode.toLowerCase()}`, "ok");
    bar(`${p.tool} is mounted (slot ${mt.slot}).`,
        `Kiri:Moto is in ${m.mode === "LASER" ? "Laser" : m.mode} mode with the ${m.deviceName} profile` +
        (m.process ? ` and the ${m.process} settings.` : "."));
  } else if (m.type === "error") {
    chip("Kiri:Moto error", "bad");
    bar("Kiri:Moto could not take the Rhino profile.", m.message || "");
  }
});

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
