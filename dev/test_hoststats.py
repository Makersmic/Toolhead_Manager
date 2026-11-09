"""Host health (Studio Settings > Host health): rhino/hoststats.py against a pretend /proc and /sys, and GET /api/host/stats.
Run: python3 dev/test_hoststats.py  (needs flask)"""
import http.server, json, os, shutil, sys, tempfile, threading
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from rhino import hoststats as h

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

R = tempfile.mkdtemp(prefix="rhino-hoststats-")
def put(rel, text):
    p = os.path.join(R, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f: f.write(text)

# a 7050-like host: coretemp with a package and four cores, and a drive that reports a nonsense limit
put("sys/class/hwmon/hwmon0/name", "acpitz\n"); put("sys/class/hwmon/hwmon0/temp1_input", "27800\n")
put("sys/class/hwmon/hwmon2/name", "coretemp\n")
for i, (lab, v) in enumerate([("Package id 0", 51000), ("Core 0", 49000), ("Core 1", 50000), ("Core 2", 47000), ("Core 3", 52000)], 1):
    put(f"sys/class/hwmon/hwmon2/temp{i}_input", f"{v}\n"); put(f"sys/class/hwmon/hwmon2/temp{i}_label", lab + "\n")
    put(f"sys/class/hwmon/hwmon2/temp{i}_max", "100000\n"); put(f"sys/class/hwmon/hwmon2/temp{i}_crit", "100000\n")
put("sys/class/hwmon/hwmon10/name", "nvme\n"); put("sys/class/hwmon/hwmon10/temp1_input", "38900\n")
put("sys/class/hwmon/hwmon10/temp1_max", "65261850\n")
s = h.sensors(R)
ok([x["chip"] for x in s] == ["acpitz", "coretemp", "coretemp", "coretemp", "coretemp", "coretemp", "nvme"], "H1 sensors in hwmon order (2 before 10)")
ok(s[2] == {"chip": "coretemp", "label": "Core 0", "c": 49.0, "high": 100.0, "crit": 100.0}, "H2 a core's label, reading and limits")
ok(s[6]["high"] is None and s[0]["label"] == "temp1", "H3 a nonsense limit is dropped; an unlabelled sensor gets its file name")

put("proc/cpuinfo", "".join(f"processor\t: {i}\nmodel name\t: Intel(R) Core(TM) i5-7500T CPU @ 2.70GHz\ncpu MHz\t\t: 800.000\n\n" for i in range(4)))
put("sys/devices/system/cpu/cpu2/cpufreq/scaling_cur_freq", "3100000\n")
put("sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "performance\n")
put("sys/devices/system/cpu/online", "0-3\n"); put("sys/devices/system/cpu/isolated", "3\n")
c = h.cpu(R)
ok(c["model"].startswith("Intel(R) Core(TM) i5-7500T") and [x["mhz"] for x in c["cores"]] == [800, 800, 3100, 800], "H4 model and each core's clock (cpufreq wins)")
ok(c["governor"] == "performance" and c["isolated"] == "3" and c["online"] == "0-3", "H5 governor, online and isolated cores")

put("proc/pressure/cpu", "some avg10=1.50 avg60=0.40 avg300=0.10 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
put("proc/pressure/io", "some avg10=12.00 avg60=3.00 avg300=1.00 total=1\nfull avg10=8.25 avg60=0.00 avg300=0.00 total=0\n")
p = h.pressure(R)
ok(p == {"cpu": {"some": 1.5, "full": 0.0}, "io": {"some": 12.0, "full": 8.25}}, "H6 pressure stall avg10; a missing file is left out")
put("proc/meminfo", "MemTotal:        8000000 kB\nMemAvailable:    6000000 kB\nSwapTotal:       1000000 kB\nSwapFree:         900000 kB\n")
m = h.memory(R)
ok(m == {"total": 8192000000, "available": 6144000000, "swap_total": 1024000000, "swap_free": 921600000}, "H7 memory and swap in bytes")
ok([d["label"] for d in h.disks([("System disk", "/"), ("gone", R + "/nope")])] == ["System disk"], "H8 free space only where the path exists")
ok([d["label"] for d in h.disks([("System disk", "/"), ("again", "/")])] == ["System disk"], "H8b one row per filesystem")

# processes: Klipper (two threads' worth of ticks), Moonraker, a busy stranger, a kernel thread
def proc(pid, name, cmd, ticks, core, allowed="0-3", rss_pages=1000):
    rest = ["S"] + ["0"] * 10 + [str(ticks), "0"] + ["0"] * 3 + ["0", "3"] + ["0"] * 3 + [str(rss_pages)] + ["0"] * 14 + [str(core)]
    put(f"proc/{pid}/stat", f"{pid} ({name}) " + " ".join(rest) + "\n")
    put(f"proc/{pid}/cmdline", cmd.replace(" ", "\0"))
    put(f"proc/{pid}/status", f"Name:\t{name}\nCpus_allowed_list:\t{allowed}\n")
hz = os.sysconf("SC_CLK_TCK")
proc(100, "python", "/home/pi/klippy-env/bin/python /home/pi/klipper/klippy/klippy.py /home/pi/printer_data/config/printer.cfg", 1000, 3, "3")
proc(200, "python", "/home/pi/moonraker-env/bin/python /home/pi/moonraker/moonraker/moonraker.py", 500, 1)
proc(300, "stress", "stress --cpu 1", 0, 2)
proc(400, "kworker/0:1", "", 0, 0)
first = h.processes(R, now=100.0)
ok([g["name"] for g in first["own"]] == ["Klipper", "Moonraker"] and first["own"][0]["cpu"] is None, "H9 own programs found, no CPU % on the first call")
ok(first["own"][0]["allowed"] == "3" and first["own"][0]["core"] == 3 and first["own"][0]["threads"] == 3, "H10 core, allowed cores and threads")
ok([r["name"] for r in first["others"]] == ["stress"], "H11 kernel threads left out of the others")
proc(100, "python", "/home/pi/klippy-env/bin/python /home/pi/klipper/klippy/klippy.py", 1000 + hz // 2, 3, "3")  # half a core over 1 s
proc(300, "stress", "stress --cpu 1", hz, 2)                                                                   # one full core
second = h.processes(R, now=101.0)
ok(second["own"][0]["cpu"] == 50.0 and second["own"][1]["cpu"] == 0.0, "H12 CPU % between two calls (% of one core)")
ok(second["others"][0]["name"] == "stress" and second["others"][0]["cpu"] == 100.0, "H13 the busiest other first")
snap = h.snapshot(R, [])
ok(snap["ok"] and snap["load"] is None and snap["uptime"] is None and len(snap["sensors"]) == 7, "H14 snapshot copes with missing loadavg and uptime")

# the route, through the Portal's own access check
from rhino.portal import create_app
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/access/user": return self._send(200, {"result": {"username": "_TRUSTED_USER_"}})
        if self.path.startswith("/server/info"): return self._send(200, {"result": {"klippy_state": "ready"}})
        if self.path.startswith("/printer/objects/query"):
            return self._send(200, {"result": {"status": {"print_stats": {"state": "printing"}, "gcode_macro SWAP_TOOL": {"current_tool": 1}}}})
        self._send(404, {})
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
CFG = tempfile.mkdtemp(prefix="rhino-hoststats-cfg-") + "/printer_data/config"
shutil.copytree(os.path.dirname(HERE), CFG, ignore=shutil.ignore_patterns("__pycache__", "registry_backups", "node_modules", "manual", ".git"))
app = create_app(CFG, f"http://127.0.0.1:{srv.server_port}")
r = app.test_client().get("/api/host/stats", environ_base={"REMOTE_ADDR": "127.0.0.1"})
j = r.get_json() or {}
ok(r.status_code == 200 and j.get("ok") and isinstance(j.get("sensors"), list) and "processes" in j, "H15 GET /api/host/stats answers during a job (read only)")
ok([d["label"] for d in j.get("disks", [])][:1] == ["System disk"], "H16 the system disk is reported")

shutil.rmtree(R, ignore_errors=True)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
