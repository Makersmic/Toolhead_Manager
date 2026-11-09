"""Host health for Rhino Studio's Settings > Host health: what Moonraker doesn't report.

Read only, from /proc and /sys, nothing run and nothing written. Moonraker already sends the per-core load and one CPU
temperature every second; this adds what is needed to troubleshoot the host itself:

- every temperature sensor the kernel knows (coretemp gives one per core plus the package; also drives, chipset, Wi-Fi);
- each core's clock, the governor and any cores kept apart for Klipper (isolcpus);
- load average and pressure stall (how long tasks waited for CPU, memory or the disk in the last 10 s);
- memory with swap, and free space where it matters;
- the Rhino's own programs (Klipper, Moonraker, the Portal, cameras, nginx, PrusaSlicer) and the busiest others: CPU %,
  memory, the core each last ran on and the cores it may use.

CPU % is measured between two calls (the last sample is kept in memory); the first call has none.
`root` lets the tests point everything at a pretend tree.
"""
import os
import threading
import time

# (shown name, test on the process's command line). The first match wins.
OWN = [
    ("Klipper", lambda c: "klippy.py" in c or "/klippy/" in c),
    ("Moonraker", lambda c: "moonraker" in c and "python" in c),
    ("Rhino Portal", lambda c: "rhino.portal" in c or "-m rhino" in c),
    ("Cameras", lambda c: any(k in c for k in ("crowsnest", "ustreamer", "camera-streamer"))),
    ("nginx", lambda c: c.startswith("nginx")),
    ("PrusaSlicer", lambda c: "prusa-slicer" in c.lower() or "prusaslicer" in c.lower()),
]
OTHERS = 5  # busiest other processes shown

_lock = threading.Lock()
_last = {"t": None, "ticks": {}}


def _read(path, default=None):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def _num(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def sensors(root="/"):
    """Every hwmon temperature: [{chip, label, c, high, crit}], in the kernel's order."""
    base = os.path.join(root, "sys/class/hwmon")
    out = []
    try:
        mons = sorted(os.listdir(base), key=lambda n: int("".join(ch for ch in n if ch.isdigit()) or 0))
    except OSError:
        return out
    for m in mons:
        d = os.path.join(base, m)
        chip = (_read(os.path.join(d, "name"), "") or "").strip() or m
        try:
            names = os.listdir(d)
        except OSError:
            continue
        ids = sorted({n[4:-6] for n in names if n.startswith("temp") and n.endswith("_input")}, key=lambda x: int(x or 0))
        for i in ids:
            v = _num(_read(os.path.join(d, f"temp{i}_input")))
            if v is None:
                continue
            label = (_read(os.path.join(d, f"temp{i}_label"), "") or "").strip() or f"temp{i}"
            high = _num(_read(os.path.join(d, f"temp{i}_max")))
            crit = _num(_read(os.path.join(d, f"temp{i}_crit")))
            ok = lambda x: round(x / 1000, 1) if x and 0 < x / 1000 < 200 else None  # drives report 65261.8 for "none"
            out.append({"chip": chip, "label": label, "c": round(v / 1000, 1), "high": ok(high), "crit": ok(crit)})
    return out


def cpu(root="/"):
    """Model, each core's clock in MHz, governor, online and isolated cores."""
    text = _read(os.path.join(root, "proc/cpuinfo"), "") or ""
    model, cores, cur = None, [], None
    for line in text.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k == "processor":
            cur = {"id": int(v), "mhz": None}
            cores.append(cur)
        elif k == "model name" and model is None:
            model = v
        elif k == "cpu MHz" and cur is not None:
            cur["mhz"] = round(_num(v, 0))
    sysd = os.path.join(root, "sys/devices/system/cpu")
    for c in cores:  # the cpufreq clock is fresher than cpuinfo's where it exists
        f = _num(_read(os.path.join(sysd, f"cpu{c['id']}/cpufreq/scaling_cur_freq")))
        if f:
            c["mhz"] = round(f / 1000)
    gov = (_read(os.path.join(sysd, "cpu0/cpufreq/scaling_governor"), "") or "").strip() or None
    return {"model": model, "cores": cores, "governor": gov,
            "online": (_read(os.path.join(sysd, "online"), "") or "").strip() or None,
            "isolated": (_read(os.path.join(sysd, "isolated"), "") or "").strip()}


def pressure(root="/"):
    """Pressure stall: % of the last 10 s that some (or all) tasks waited. None where the kernel has no PSI."""
    out = {}
    for what in ("cpu", "memory", "io"):
        text = _read(os.path.join(root, f"proc/pressure/{what}"))
        if text is None:
            continue
        row = {}
        for line in text.splitlines():
            kind, *fields = line.split()
            for fv in fields:
                k, _, v = fv.partition("=")
                if k == "avg10":
                    row[kind] = _num(v)
        out[what] = row
    return out or None


def memory(root="/"):
    vals = {}
    for line in (_read(os.path.join(root, "proc/meminfo"), "") or "").splitlines():
        k, _, v = line.partition(":")
        parts = v.split()
        if parts:
            vals[k.strip()] = int(parts[0]) * 1024
    return {"total": vals.get("MemTotal"), "available": vals.get("MemAvailable"),
            "swap_total": vals.get("SwapTotal"), "swap_free": vals.get("SwapFree")}


def disks(places):
    """Free space for each (label, path) that exists, once per filesystem (the first label wins)."""
    out, devs = [], set()
    for label, path in places:
        try:
            st = os.statvfs(path)
            dev = os.stat(path).st_dev
        except OSError:
            continue
        if dev in devs:
            continue
        devs.add(dev)
        out.append({"label": label, "path": path, "total": st.f_blocks * st.f_frsize, "free": st.f_bavail * st.f_frsize})
    return out


def _stat(root, pid):
    """(name, ticks, rss bytes, last core, nice, threads, allowed cores) or None if it has gone."""
    d = os.path.join(root, "proc", pid)
    s = _read(os.path.join(d, "stat"))
    if not s or ")" not in s:
        return None
    name = s[s.index("(") + 1:s.rindex(")")]
    f = s[s.rindex(")") + 2:].split()
    # fields after the name, counted from state (field 3): utime 14, stime 15, nice 19, threads 20, rss 24, processor 39
    try:
        ticks = int(f[11]) + int(f[12])
        nice, threads = int(f[16]), int(f[17])
        rss = int(f[21]) * os.sysconf("SC_PAGE_SIZE")
        core = int(f[36])
    except (IndexError, ValueError):
        return None
    allowed = None
    for line in (_read(os.path.join(d, "status"), "") or "").splitlines():
        if line.startswith("Cpus_allowed_list:"):
            allowed = line.split(":", 1)[1].strip()
    return name, ticks, rss, core, nice, threads, allowed


def processes(root="/", now=None):
    """The Rhino's programs (grouped by name) and the busiest others, with CPU % since the last call."""
    now = time.monotonic() if now is None else now
    hz = os.sysconf("SC_CLK_TCK")
    ncpu = os.cpu_count() or 1
    try:
        pids = [p for p in os.listdir(os.path.join(root, "proc")) if p.isdigit()]
    except OSError:
        pids = []
    seen = {}
    rows = []
    for pid in pids:
        st = _stat(root, pid)
        if not st:
            continue
        name, ticks, rss, core, nice, threads, allowed = st
        cmd = (_read(os.path.join(root, "proc", pid, "cmdline"), "") or "").replace("\0", " ").strip()
        seen[pid] = ticks
        if not cmd:
            continue  # kernel threads
        rows.append({"pid": int(pid), "proc": name, "cmd": cmd, "ticks": ticks, "rss": rss, "core": core,
                     "nice": nice, "threads": threads, "allowed": allowed})
    with _lock:
        prev_t, prev = _last["t"], _last["ticks"]
        dt = (now - prev_t) if prev_t is not None else None
        _last["t"], _last["ticks"] = now, seen
    for r in rows:
        before = prev.get(str(r["pid"]))
        # % of one core, like top: 100 = one core fully busy
        r["cpu"] = round((r["ticks"] - before) / hz / dt * 100, 1) if dt and dt > 0.2 and before is not None else None
    own, others = {}, []
    for r in rows:
        label = next((n for n, test in OWN if test(r["cmd"])), None)
        if label is None:
            others.append(r)
            continue
        g = own.setdefault(label, {"name": label, "pids": [], "cpu": None, "rss": 0, "core": r["core"],
                                   "allowed": r["allowed"], "nice": r["nice"], "threads": 0})
        g["pids"].append(r["pid"])
        g["rss"] += r["rss"]
        g["threads"] += r["threads"]
        if r["cpu"] is not None:
            g["cpu"] = round((g["cpu"] or 0) + r["cpu"], 1)
    others.sort(key=lambda r: (r["cpu"] or 0, r["rss"]), reverse=True)
    busy = [{"name": r["proc"], "pids": [r["pid"]], "cpu": r["cpu"], "rss": r["rss"], "core": r["core"],
             "allowed": r["allowed"], "nice": r["nice"], "threads": r["threads"]} for r in others[:OTHERS]]
    order = [n for n, _ in OWN]
    return {"cpus": ncpu, "own": sorted(own.values(), key=lambda g: order.index(g["name"])), "others": busy}


def uptime(root="/"):
    return _num((_read(os.path.join(root, "proc/uptime"), "") or "").split(" ")[0])


def snapshot(root="/", places=()):
    la = (_read(os.path.join(root, "proc/loadavg"), "") or "").split()
    return {"ok": True, "uptime": uptime(root), "cpu": cpu(root), "sensors": sensors(root),
            "load": [_num(x) for x in la[:3]] if len(la) >= 3 else None, "pressure": pressure(root),
            "memory": memory(root), "disks": disks(places), "processes": processes(root)}
