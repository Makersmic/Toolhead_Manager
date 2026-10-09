// Rhino Tool Manager <-> Kiri:Moto bridge (runs inside Kiri:Moto; injected by init.js).
//
// The Tool Manager portal shows Kiri:Moto in its Slice tab and sends it messages shaped
// { rhino: {...} }. This mod answers them:
//   hello   -> replies "ready" once Kiri:Moto has finished starting
//   select  -> switches to the tool's mode (LASER for LightSaber), stores the tool's machine
//              profile and its material settings, and selects them; replies "selected"
// Messages are only taken from the page that embeds Kiri:Moto, and only when that page is on the
// same machine (same host name) - the portal and Kiri:Moto both run on the Rhino's Pi.
self.kiri.load(api => {
    let ready = false;
    const waiting = [];

    function reply(e, msg) {
        try { e.source.postMessage({ rhino: msg }, e.origin); } catch (err) { console.log('rhino reply failed', err); }
    }

    function trusted(e) {
        if (e.source !== window.parent || window.parent === window) return false;
        try { return new URL(e.origin).hostname === location.hostname; } catch (err) { return false; }
    }

    function select(e, m) {
        const { mode, deviceName, device, processes, process } = m;
        if (!mode || !deviceName || !device) {
            return reply(e, { type: 'error', message: 'select needs mode, deviceName and device' });
        }
        try {
            if (api.mode.get() !== mode) api.mode.set(mode);
            const conf = api.conf.get();
            // the machine profile: always replaced, the portal's copy is the source of truth
            conf.devices[deviceName] = Object.assign({}, device, { mode, deviceName });
            // material settings: full Kiri process records (Kiri's defaults + the Rhino values)
            const sproc = conf.sproc[mode] = conf.sproc[mode] || {};
            const base = api.clone(sproc.default || api.conf.proc() || {});
            const names = Object.keys(processes || {});
            for (const name of names) {
                sproc[name] = Object.assign(api.clone(base), processes[name], { processName: name });
            }
            // keep the material picked last time if it is still one of this tool's; else the portal's choice
            if (!names.includes(conf.devproc[deviceName]) && process) conf.devproc[deviceName] = process;
            api.conf.save();
            api.device.set(deviceName);
            api.devices.refresh();      // redraw the Machine and Profile drop-downs to show the Rhino ones
            reply(e, {
                type: 'selected', mode: api.mode.get(), deviceName: api.device.get(),
                process: api.process.get(), bed: [api.conf.dev().bedWidth, api.conf.dev().bedDepth],
                maxPower: api.conf.dev().laserMaxPower
            });
        } catch (err) {
            console.log('rhino select failed', err);
            reply(e, { type: 'error', message: String(err && err.message || err) });
        }
    }

    function handle(e) {
        const m = e.data && e.data.rhino;
        if (!m || typeof m !== 'object' || !trusted(e)) return;
        if (!ready) { waiting.push(e); return; }
        if (m.type === 'hello') reply(e, { type: 'ready', version: api.version || '' });
        else if (m.type === 'select') select(e, m);
    }

    window.addEventListener('message', handle);
    api.event.on('load-done', () => {
        ready = true;
        while (waiting.length) handle(waiting.shift());
    });
}, 'Rhino');
