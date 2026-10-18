// /net: keep or undo a waiting network change (config 1.4.8). No inline script: the CSP forbids it.
(function () {
  "use strict";
  var token = document.querySelector('meta[name="rhino-token"]').content;
  var left = document.getElementById("netLeft");
  var msg = document.getElementById("netMsg");
  function tick() {
    if (!left) return;
    var s = Math.max(0, Math.ceil(Number(left.dataset.expires) - Date.now() / 1000));
    left.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    if (s > 0) setTimeout(tick, 1000);
  }
  function send(path, done) {
    fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Rhino-Token": token }, body: "{}" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        msg.textContent = d.ok ? done : d.error || "That didn't work.";
        if (d.ok) document.querySelectorAll(".net-actions button").forEach(function (b) { b.disabled = true; });
      })
      .catch(function () { msg.textContent = "Can't reach the Portal."; });
  }
  var keep = document.getElementById("netKeep");
  var undo = document.getElementById("netUndo");
  if (keep) keep.addEventListener("click", function () { send("/api/net/keep", "Kept. Use this address from now on."); });
  if (undo) undo.addEventListener("click", function () { send("/api/net/undo", "Switching back to the old settings."); });
  tick();
})();
