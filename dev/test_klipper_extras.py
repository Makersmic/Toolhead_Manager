"""The Klipper extras in klipper_extras/ against a fake Klipper: config reading, the angle unwrap, jam
detection only while printing, calibrate arithmetic, the saved circumference, and the tachometer's RPM.
    python3 dev/test_klipper_extras.py
Klipper's own RunoutHelper and FrequencyCounter are stood in for here (this checks our logic, not Klipper's);
dev/test_real_klipper.py loads the modules in real Klipper when a checkout is available."""
import importlib
import os
import shutil
import sys
import tempfile
import types
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# ---------------------------------------------------------------- a fake `extras` package around our modules
PKG = tempfile.mkdtemp(prefix="rhino-extras-")
os.makedirs(os.path.join(PKG, "extras"))
open(os.path.join(PKG, "extras", "__init__.py"), "w").close()
for f in ("filament_angle_sensor.py", "spindle_tachometer.py"):
    shutil.copy(os.path.join(REPO, "klipper_extras", f), os.path.join(PKG, "extras", f))
open(os.path.join(PKG, "extras", "filament_switch_sensor.py"), "w").write('''
class RunoutHelper:
    def __init__(self, config):
        self.calls = []
        self.sensor_enabled = True
        self.filament_present = True
    def note_filament_present(self, eventtime, present):
        self.calls.append((eventtime, present))
        self.filament_present = present
    def get_status(self, eventtime):
        return {"filament_detected": self.filament_present, "enabled": self.sensor_enabled}
''')
open(os.path.join(PKG, "extras", "pulse_counter.py"), "w").write('''
class FrequencyCounter:
    def __init__(self, printer, pin, sample_time, poll_time):
        self.args = (pin, sample_time, poll_time)
        self.freq = 0.
    def get_frequency(self):
        return self.freq
''')
sys.path.insert(0, PKG)
fas = importlib.import_module("extras.filament_angle_sensor")
tach = importlib.import_module("extras.spindle_tachometer")

# ---------------------------------------------------------------- the fake Klipper
_MISSING = object()


class Config:
    class error(Exception):
        pass

    def __init__(self, printer, name, values):
        self.printer, self.name, self.v = printer, name, dict(values)

    def get_printer(self):
        return self.printer

    def get_name(self):
        return self.name

    def get(self, k, default=_MISSING):
        if k in self.v:
            return self.v[k]
        if default is _MISSING:
            raise self.error("missing " + k)
        return default

    def _num(self, k, default, conv, minval=None, maxval=None, above=None):
        v = conv(self.get(k, default))
        if (minval is not None and v < minval) or (maxval is not None and v > maxval) or (above is not None and v <= above):
            raise self.error("%s out of range" % k)
        return v

    def getfloat(self, k, default=_MISSING, **kw):
        return self._num(k, default, float, **kw)

    def getint(self, k, default=_MISSING, **kw):
        return self._num(k, default, int, **kw)

    def getboolean(self, k, default=_MISSING):
        v = self.get(k, default)
        return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")


class Reactor:
    NOW, NEVER = 0., 9e9

    def __init__(self):
        self.now, self.timers = 100., {}

    def monotonic(self):
        return self.now

    def register_timer(self, cb, when=NEVER):
        self.timers[cb] = when
        return cb

    def update_timer(self, t, when):
        self.timers[t] = when

    def pause(self, until):
        self.now = max(self.now, until)

    def fire(self, dt=0.25):
        """Advance time and run every timer that is due (once each)."""
        self.now += dt
        for t, when in list(self.timers.items()):
            if when <= self.now:
                self.timers[t] = t(self.now)


class ADC:
    def __init__(self):
        self.sample, self.cb = None, None

    def setup_adc_sample(self, *a, **kw):
        self.sample = (a, kw)

    def setup_adc_callback(self, cb):
        self.cb = cb


class Printer:
    def __init__(self):
        self.reactor = Reactor()
        self.events = {}
        self.adc = ADC()
        self.extruder = types.SimpleNamespace(pos=0., find_past_position=lambda pt: self.extruder.pos)
        self.scripts = []
        self.commands = {}
        self.objects = {
            "pins": types.SimpleNamespace(setup_pin=lambda kind, pin: self.adc),
            "extruder": self.extruder,
            "mcu": types.SimpleNamespace(estimated_print_time=lambda et: et),
            "toolhead": types.SimpleNamespace(wait_moves=lambda: None),
            "gcode": types.SimpleNamespace(
                register_mux_command=lambda cmd, key, val, fn, desc=None: self.commands.__setitem__(cmd, fn),
                run_script_from_command=self._run_script),
        }
        self.on_script = None

    def _run_script(self, s):
        self.scripts.append(s)
        if self.on_script:
            self.on_script(s)

    def get_reactor(self):
        return self.reactor

    def register_event_handler(self, name, fn):
        self.events.setdefault(name, []).append(fn)

    def lookup_object(self, name, default=_MISSING):
        if name in self.objects:
            return self.objects[name]
        if default is _MISSING:
            raise KeyError(name)
        return default

    def send(self, name, *a):
        for fn in self.events.get(name, []):
            fn(*a)


class GCmd:
    class error(Exception):
        pass

    def __init__(self, **p):
        self.p, self.out = p, []

    def get_float(self, k, default=None, **kw):
        return float(self.p.get(k, default))

    def get_int(self, k, default=None, **kw):
        return int(self.p.get(k, default))

    def respond_info(self, s):
        self.out.append(s)


def make(circumference=30., **extra):
    p = Printer()
    cfg = Config(p, "filament_angle_sensor enc", {"adc_pin": "PB1", "wheel_circumference": circumference, **extra})
    s = fas.load_config_prefix(cfg)
    p.send("klippy:connect")
    p.send("klippy:ready")
    return p, s


def feed(p, *values):
    for v in values:
        p.adc.cb(p.reactor.now, v)


# ---------------------------------------------------------------- filament encoder
p, s = make()
a, kw = p.adc.sample
ok(a[0] == 0.1 and a[1] == 0.001 and a[2] == 8 and kw.get("range_check_count") == 0 and kw.get("minval") == 0. and kw.get("maxval") == 1.,
   "FE-U1 ADC sampled every 0.1 s, 8 x 1 ms, no range shutdown")
ok("FILAMENT_ENCODER_CALIBRATE" in p.commands and "FILAMENT_ENCODER_RESET" in p.commands, "FE-U1b commands registered")

feed(p, 0.9, 0.95, 0.05, 0.1)
ok(abs(s.measured - 0.2 * 30.) < 1e-9 and abs(s.angle - 36.) < 1e-9, "FE-U2 forward across the wrap: 0.2 turns = 6 mm, angle 36")
feed(p, 0.05, 0.95, 0.9)
ok(abs(s.measured - 0.) < 1e-9, "FE-U3 back across the wrap undoes it")
feed(p, 0.6, 0.9)
ok(abs(s.measured - 0.) < 1e-9, "FE-U5 a noise burst (0.3 turns out and back) nets to nothing")
p2, s2 = make(invert=True)
feed(p2, 0.1, 0.2)
ok(abs(s2.measured + 3.) < 1e-9, "FE-U4 invert flips the direction")

# not printing: the extruder moves, nothing is compared
p, s = make()
p.extruder.pos = 50.
for _ in range(8):
    p.reactor.fire()
ok(s.runout_helper.calls == [] and not s.printing, "FE-U6 not printing: no comparison, no runout call")

# printing, filament stuck
p.send("idle_timeout:printing", 0.)
ok(s.printing and s.commanded_start == 50. and s.measured == 0., "FE-U7a printing resets the counters at the current extruder position")
p.extruder.pos = 54.
p.reactor.fire()
ok(s.runout_helper.calls == [], "FE-U7b 4 mm commanded, nothing yet (detection_length 7)")
p.extruder.pos = 58.
p.reactor.fire()
ok(s.runout_helper.calls and s.runout_helper.calls[-1][1] is False, "FE-U7c 8 mm commanded with 0 measured: runout (jam) reported")
st = s.get_status(p.reactor.now)
ok(st["slip_pct"] == 100. and st["commanded_mm"] == 8. and st["measured_mm"] == 0. and st["filament_detected"] is False,
   "FE-U7d status: slip 100 %%, commanded 8, measured 0 (%r)" % (st,))

# filament moving again
feed(p, 0.0, 0.1, 0.2, 0.3)      # 9 mm seen
p.extruder.pos = 66.
p.reactor.fire()
ok(s.runout_helper.calls[-1][1] is True and s.get_status(p.reactor.now)["slip_pct"] < 1., "FE-U8 8 mm commanded, 9 mm seen: present again, slip 0")

# a retract and unretract never counts
n = len(s.runout_helper.calls)
p.extruder.pos = 61.             # retract 5 (the wheel turns back a little)
feed(p, 0.2)
p.reactor.fire()
p.extruder.pos = 66.             # back
feed(p, 0.3, 0.37)
p.reactor.fire()
ok(len(s.runout_helper.calls) == n, "FE-U9a a 5 mm retract and unretract completes no window")
p.extruder.pos = 72.             # 6 mm on, 11 mm since the window restarted at the retract's end
feed(p, 0.47, 0.57)
p.reactor.fire()
ok(len(s.runout_helper.calls) == n + 1 and s.runout_helper.calls[-1][1] is True, "FE-U9 the window restarted at the retract: present, no false jam")
p.send("idle_timeout:ready", 0.)
p.extruder.pos = 200.
for _ in range(4):
    p.reactor.fire()
ok(len(s.runout_helper.calls) == n + 1 and not s.printing, "FE-U9b after the job nothing is compared again")

# calibrate: 100 mm commanded, the wheel reports 90 mm with circumference 30 -> 33.3333
p, s = make()
def on_script(script):
    if "G1 E100" in script:
        p.extruder.pos += 100.
        feed(p, *[(i % 10) / 10. for i in range(31)])   # 3 turns = 90 mm
p.on_script = on_script
g = GCmd(LENGTH=100, SAVE=0)
p.commands["FILAMENT_ENCODER_CALIBRATE"](g)
ok(any("33.3333" in o for o in g.out) and s.circumference == 30. and not any("SAVE_VARIABLE" in x for x in p.scripts),
   "FE-U11a calibrate reports 33.3333 and changes nothing without SAVE (%r)" % (g.out,))
g = GCmd(LENGTH=100, SAVE=1)
p.commands["FILAMENT_ENCODER_CALIBRATE"](g)
ok(abs(s.circumference - 100. / 3.) < 1e-3 and any("SAVE_VARIABLE VARIABLE=filament_encoder_enc_circumference VALUE=33.3333" in x for x in p.scripts),
   "FE-U11b SAVE=1 keeps it in variables.cfg and uses it")
p.on_script = lambda script: None
try:
    p.commands["FILAMENT_ENCODER_CALIBRATE"](GCmd(LENGTH=100, SAVE=0))
    ok(False, "FE-U11c")
except GCmd.error as e:
    ok("saw 0.0 mm" in str(e), "FE-U11c a wheel that doesn't turn is an error, not a result")

# saved circumference wins at connect
p = Printer()
p.objects["save_variables"] = types.SimpleNamespace(allVariables={"filament_encoder_enc_circumference": 31.5})
s = fas.load_config_prefix(Config(p, "filament_angle_sensor enc", {"adc_pin": "PB1", "wheel_circumference": 30.}))
p.send("klippy:connect")
ok(s.circumference == 31.5, "FE-U12 a saved circumference overrides the config")

# config limits
def bad(values):
    try:
        fas.load_config_prefix(Config(Printer(), "filament_angle_sensor x", values))
        return False
    except Config.error:
        return True
ok(bad({"adc_pin": "PB1"}) and bad({"adc_pin": "PB1", "wheel_circumference": 0}) and bad({"adc_pin": "PB1", "wheel_circumference": 30, "report_time": 0.01}),
   "FE-U13 wheel_circumference required and > 0; report_time at least 0.02 s")

# ---------------------------------------------------------------- spindle tachometer
p = Printer()
t = tach.load_config_prefix(Config(p, "spindle_tachometer spindle", {"pin": "^PC5", "pulses_per_rev": 7}))
ok(t.counter.args == ("^PC5", 0.5, 0.0001), "SP-U1 counter on ^PC5, 0.5 s samples, 0.0001 s poll by default")
t.counter.freq = 700.
ok(t.get_status(0.) == {"rpm": 3000, "edges_per_second": 700., "pulses_per_rev": 7}, "SP-U2 700 edges/s at 7 ppr = 3000 RPM (both edges counted)")
t.counter.freq = 0.
ok(t.get_status(0.)["rpm"] == 0, "SP-U3 no pulses: 0 RPM")
try:
    tach.load_config_prefix(Config(Printer(), "spindle_tachometer x", {"pin": "PC5", "poll_interval": 0.05}))
    ok(False, "SP-U4")
except Config.error:
    ok(True, "SP-U4 a poll interval over 0.01 s is refused")

shutil.rmtree(PKG, ignore_errors=True)
print("\n%d failure(s)" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
