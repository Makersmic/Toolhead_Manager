"""Add hardware wizard, steps 3 and 5: device writers (fans, heat, interlocks, spindles, air, lights, sensors, movement).
Run: python3 dev/test_hw_devices.py   (needs flask)

Design: docs/hardware-coverage.md; answers in docs/decisions.md (2026-10-26). Macro changes (interlock start check,
filament sensors off without a print head, job hooks) are NOT here: they wait for review (docs/proposal-macro-hooks.md)."""
import os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from rhino import hw_catalog, hw_devices, sections

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

GEN = os.path.join(CFG, "myrhino", "custom_tools.cfg")
fake = demo.start_fake()
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json() or {}
used = set()


def pick(kind, mosfet=None, adc=None):
    """A free pin for `kind` (main board or the test's second board) that no earlier test took."""
    for p in J(c.get(f"/api/hardware/pins?kind={kind}"))["pins"]:
        if p["pin"] in used or p["use"] == "driver" and kind not in ("step", "dir", "enable"):
            continue
        if mosfet is not None and p["mosfet"] != mosfet:
            continue
        if adc is not None and p["adc"] != adc:
            continue
        used.add(p["pin"])
        return p["pin"]
    raise SystemExit(f"no free pin for {kind}")


def save(body, preview=False):
    r = c.post("/api/preview/hardware/devices" if preview else "/api/hardware/devices", json=body, headers=H)
    return r.status_code, J(r)


def gen():
    return open(GEN).read()


# the demo machine, like the real one, has only two spare MOSFET headers: add a second board for room
r = c.post("/api/hardware/boards", json={"name": "aux", "preset": "octopus_v1_1", "link": "can", "canbus_uuid": "aabbccddeeff"}, headers=H)
ok(r.status_code == 200, "a second board 'aux' for test pins")

# ---------------------------------------------------------------- catalog
ok(hw_devices.WRITERS <= set(hw_catalog.DEVICES), "every writer is a catalog device")
ok(all(hw_catalog.DEVICES[d]["section"] in hw_catalog.KLIPPER_SECTIONS for d in hw_devices.WRITERS), "writers only write catalog sections")
cat = J(c.get("/api/hardware/catalog"))
st = {d["id"]: d["status"] for g in cat["groups"] for d in g["devices"]}
ok(all(st[d] == "ready" for d in hw_devices.WRITERS) and st["accelerometer"] == "planned", "the wizard shows built devices as ready, the rest as planned")

# ---------------------------------------------------------------- step 3: fans
fanpin = pick("pwm_out", mosfet=True)
code, r = save({"device": "controller_fan", "name": "driver_fan", "pins": {"pin": fanpin}})
ok(code == 200, f"controller_fan on a free board pin ({fanpin}) saves {r.get('error', '')}")
ok(f"[controller_fan driver_fan]" in gen() and "idle_timeout: 30" in gen(), "controller_fan written with idle_timeout 30")
code, r = save({"device": "controller_fan", "name": "fan2", "pins": {"pin": fanpin}})
ok(code == 400 and "already used" in r["error"], "a pin can't be taken twice")
ok(fanpin not in [p["pin"] for p in J(c.get("/api/hardware/pins?kind=pwm_out"))["pins"]], "a device's pin leaves the picker")
ok(fanpin not in [p["pin"] for p in J(c.get("/api/options"))["board_pins"]], "and the old hardware editor's list")
r = c.post("/api/hardware", json={"name": "lamp", "category": "lighting", "role": "switch", "pin": fanpin, "purpose": "x"}, headers=H)
ok(r.status_code == 400, "the old hardware form can't reuse a device's pin")

tf_pin, tf_sensor = pick("pwm_out", mosfet=True), pick("adc", adc=True)
code, r = save({"device": "temperature_fan", "name": "chamber_exhaust", "pins": {"pin": tf_pin, "sensor": tf_sensor}, "target_temp": 45})
ok(code == 200 and "max_temp: 55" in gen() and "shutdown_speed: 1" in gen(), "temperature_fan: max_temp = target + 10, full speed on shutdown")
ok(any("shuts down" in w for w in r["warnings"]), "temperature_fan warns where Klipper shuts down")
code, r = save({"device": "temperature_fan", "name": "bad_tf", "pins": {"pin": pick("pwm_out", mosfet=True), "sensor": pick("digital_in", adc=False)}}, preview=True)
ok(code == 400 and "analog" in r["error"], "a temperature sensor on a non-ADC pin is refused")

# ---------------------------------------------------------------- step 3: heat
hp, hs = pick("pwm_out", mosfet=True), pick("adc", adc=True)
code, r = save({"device": "heater", "name": "chamber", "pins": {"pin": hp, "sensor": hs}, "max_temp": 121}, preview=True)
ok(code == 400 and "120" in r["error"], "a heater above 120 C is refused")
code, r = save({"device": "heater", "name": "chamber", "pins": {"pin": hs, "sensor": hp}}, preview=True)
ok(code == 400, "a heater's sensor on a MOSFET output is refused")
code, r = save({"device": "heater", "name": "chamber", "pins": {"pin": hp, "sensor": hs}, "max_temp": 80, "expose": ["control", "dashboard", "macros"]}, preview=True)
ok(code == 200 and "[heater_generic chamber]" in r["text"] and "max_temp: 80" in r["text"] and "control: watermark" in r["text"],
   "heater preview: heater_generic, watermark, max_temp 80")
ok("|min" in r["text"] and "CHAMBER_SET" in r["text"], "the heater's SET macro clamps the target to its max")
ok(r["item"]["safe_off"], "a heater is always switched off by _TOOL_SAFE_OFF (live)")
code, r = save({"device": "heater", "name": "chamber", "pins": {"pin": hp, "sensor": hs}, "max_temp": 80, "safe_off": False})
ok(code == 200, "heater saved")
ok("SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0" in gen().split("[gcode_macro _RHINO_CONTROLS_OFF]")[1], "_RHINO_CONTROLS_OFF turns the heater off (safe_off can't be unticked)")
code, r = save({"device": "temp_sensor", "name": "pi_temp", "source": "host"})
ok(code == 200 and "sensor_type: temperature_host" in gen(), "host temperature needs no pin")
code, r = save({"device": "temp_sensor", "name": "room", "source": "thermistor"}, preview=True)
ok(code == 400 and "pin" in r["error"], "a thermistor readout needs a pin")

# ---------------------------------------------------------------- step 3: interlocks and other inputs
ip = pick("digital_in")
code, r = save({"device": "interlock", "name": "lid", "pins": {"pin": ip}, "sensor_type": "pnp"}, preview=True)
ok(code == 400 and "optocoupler" in r["error"], "PNP interlock refused without the isolation confirm")
code, r = save({"device": "interlock", "name": "lid", "pins": {"pin": ip}, "sensor_type": "mech_nc"})
ok(code == 200 and f"pin: ^{ip}" in gen() and "PAUSE" in gen().split("[gcode_button lid]")[1].split("[")[0], "interlock: ^pin (NC), pauses a running job")
d = J(c.get("/api/hardware/devices"))["devices"]
lid = next(x for x in d if x["name"] == "lid")
ok(lid["settings"]["must_close_laser"] and lid["settings"]["must_close_spindle"], "interlock: must be closed to start, on for laser and spindle by default")
code, r = save({"device": "flame", "name": "flame", "pins": {"pin": pick("digital_in")}, "sensor_type": "mech_no"})
ok(code == 200 and "M112" in gen().split("[gcode_button flame]")[1].split("[")[0], "flame sensor: emergency stop")
ok("^!" in gen().split("[gcode_button flame]")[1].split("\n")[2], "normally-open switch writes ^!")
ok(any("not a hardware E-stop" in w for w in r["warnings"]), "the E-stop honesty note is shown")

# ---------------------------------------------------------------- step 5: spindles, air, coolant
sp, sd, se = pick("pwm_out", mosfet=False), pick("digital_out", mosfet=False), pick("digital_out", mosfet=False)
code, r = save({"device": "spindle_pwm", "name": "router", "pins": {"pin": sp, "direction": sd, "enable": se},
                "expose": ["control", "macros"], "safe_off": False})
g = gen()
ok(code == 200 and "[pwm_tool router]" in g and "[output_pin router_direction]" in g and "[output_pin router_enable]" in g,
   "spindle PWM: pwm_tool plus direction and enable outputs")
off = g.split("[gcode_macro _RHINO_CONTROLS_OFF]")[1]
ok("SET_PIN PIN=router VALUE=0" in off and "SET_PIN PIN=router_enable VALUE=0" in off, "spindle and its enable are switched off by _TOOL_SAFE_OFF")
code, r = save({"device": "relay", "name": "router_direction"}, preview=True)
ok(code == 400, "the old-role devices aren't written here (they keep their path)")
r2 = c.post("/api/hardware", json={"name": "router_enable", "category": "lighting", "role": "switch", "pin": pick("digital_out"), "purpose": "x"}, headers=H)
ok(r2.status_code == 400 and "router" in J(r2)["error"], "an object a device generates can't be reused by name")

code, r = save({"device": "coolant", "name": "mist", "pins": {"pin": pick("digital_out", mosfet=False)}, "follows": "gcode", "gcode": "M7"})
code2, r2 = save({"device": "air_assist", "name": "air", "pins": {"pin": pick("digital_out", mosfet=False)}, "follows": "gcode", "gcode": "M8"})
g = gen()
ok(code == 200 and code2 == 200 and "[gcode_macro M7]" in g and "[gcode_macro M8]" in g and "[gcode_macro M9]" in g, "coolant/air following G-code write M7, M8, M9")
m9 = g.split("[gcode_macro M9]")[1].split("[")[0]
ok("PIN=mist VALUE=0" in m9 and "PIN=air VALUE=0" in m9, "M9 turns both off")
code, r = save({"device": "dust", "name": "dust", "pins": {"pin": pick("digital_out")}, "follows": "output"}, preview=True)
ok(code == 400 and "job hooks" in r["error"], "following another output waits for job hooks")
code, r = save({"device": "dust", "name": "dust", "pins": {"pin": pick("digital_out", mosfet=False)}, "scope": "category",
                "scope_values": ["subtractive"], "expose": ["control", "macros"]})
on = (gen().split("[gcode_macro DUST_ON]") + [""])[1].split("\n[")[0]
ok(code == 200 and "not in [" in on and "action_raise_error" in on, "a category-scoped ON macro refuses unless a matching tool is mounted")
code, r = save({"device": "dust", "name": "dust2", "pins": {"pin": pick("digital_out")}, "scope": "tools", "scope_values": ["NoSuchTool"]}, preview=True)
ok(code == 400, "scope to an unknown tool is refused")

# ---------------------------------------------------------------- step 5: lights, sensors, movement
code, r = save({"device": "led", "name": "case_light", "pins": {"white": pick("pwm_out", mosfet=True)}})
ok(code == 200 and "white_pin:" in gen() and not r.get("error"), "plain LED with a white channel")
code, r = save({"device": "neopixel", "name": "strip", "pins": {"pin": pick("data")}, "chain_count": 30})
ok(code == 200 and "chain_count: 30" in gen(), "neopixel with 30 LEDs")
code, r = save({"device": "runout", "name": "runout", "pins": {"pin": pick("digital_in")}, "sensor_type": "mech_no"})
ok(code == 200 and "[filament_switch_sensor runout]" in gen() and any("SET_FILAMENT_SENSOR" in w for w in r["warnings"]),
   "runout sensor, with the 'disable it for laser/CNC' note until the swap macro change")
code, r = save({"device": "jam", "name": "jam", "pins": {"pin": pick("digital_in")}, "sensor_type": "mech_no", "extruder": "nope"}, preview=True)
ok(code == 400, "jam sensor needs a real extruder")
code, r = save({"device": "manual_stepper", "name": "rotary", "pins": {"step": pick("step"), "dir": pick("dir"), "enable": pick("enable")},
                "rotation_distance": 360})
ok(code == 200 and "[manual_stepper rotary]" in gen() and any("driver" in w for w in r["warnings"]), "manual stepper, with the driver note")

# ---------------------------------------------------------------- whole file parses like Klipper, and removal
try:
    cp = sections.parse_like_klipper(gen()); parsed = True
except Exception as e:
    parsed = False; print("   ", e)
ok(parsed, "the generated file parses the way Klipper reads it")
r = c.delete("/api/hardware/devices/router", headers=H)
ok(r.status_code == 200 and "[pwm_tool router]" not in gen() and "router_enable" not in gen(), "removing the spindle removes its sections and safe-off lines")
code, r = save({"original": "chamber", "device": "heater", "name": "enclosure", "pins": {"pin": hp, "sensor": hs}, "max_temp": 70})
ok(code == 200 and "[heater_generic enclosure]" in gen() and "[heater_generic chamber]" not in gen(), "renaming a device keeps its pins")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
fake.shutdown()
sys.exit(1 if fails else 0)
