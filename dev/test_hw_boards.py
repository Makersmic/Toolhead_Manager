"""Add hardware wizard, step 2: pin capabilities, the pin picker and second boards ([mcu name]).
Run: python3 dev/test_hw_boards.py   (needs flask)

Design: docs/hardware-coverage.md section 2 and build step 2; answers in docs/decisions.md (2026-10-26)."""
import os, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from rhino import hw_boards as B
from rhino.errors import Fail

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

PRINTER = os.path.join(CFG, "printer.cfg")
GEN = os.path.join(CFG, "myrhino", "custom_tools.cfg")
# a second board the user wrote by hand: its pins must count as taken and its name can't be reused
with open(PRINTER, "a") as f:
    f.write("\n[mcu tool]\nserial: /dev/serial/by-id/usb-hand-written-if00\n\n[output_pin tool_led]\npin: tool:PA9\n")

# ---------------------------------------------------------------- the tables
probs = B.check()
ok(probs == [], "board tables are clean" + ("" if not probs else ": " + "; ".join(probs)))
need = {"octopus_v1_1", "skr_mini_e3_v3", "ebb_v1_2", "ebb_sb_v1_0", "skr_pico_v1_0", "rpi_pico", "generic_stm32", "generic_rp2040"}
ok(need <= set(B.PRESETS), "presets: Octopus, SKR Mini E3, EBB, EBB SB, SKR Pico, Pico, and the two generic boards")
octo = B.PRESETS[B.MAIN_PRESET]["pins"]
ok(all(octo[p]["use"] == "heater" for p in ("PA2", "PA3", "PB10", "PB11", "PA1")), "Octopus HE0-HE3 and the bed are heater MOSFETs")
ok(all(octo[p]["use"] == "fan" for p in ("PA8", "PE5", "PD12", "PD13", "PD14", "PD15")), "Octopus FAN0-FAN5 are fan MOSFETs")
ok({p for p, d in octo.items() if d["use"] == "thermistor"} == {"PF3", "PF4", "PF5", "PF6", "PF7"}, "Octopus thermistor headers are TB, T0-T3")
ok(octo["PF4"]["header"] == "T0" and octo["PA8"]["header"] == "FAN0", "Octopus silk labels kept from BOARD_HEADERS")

# ---------------------------------------------------------------- references
b = {"ebb": {"preset": "ebb_v1_2"}, "pico": {"preset": "rpi_pico"}, "hand": {"preset": None}}
for ref, want in [("pf4", "PF4"), ("!^PA8", "PA8"), ("mcu:PC0", "PC0"), ("!ebb:pa3", "ebb:PA3"), ("pico:GPIO26", "pico:gpio26"),
                  ("hand:gpio3", "hand:gpio3"), ("hand:pb3", "hand:PB3"), ("nope:PA1", ""), ("gpio5", ""), ("ebb:gpio5", ""), ("PZ1", "")]:
    ok(B.canon(ref, b) == want, f"canon({ref!r}) -> {want!r}")

# ---------------------------------------------------------------- capabilities and the electrical rules
c = B.caps("PA8", b)
ok(c["mosfet"] and not B.check_kind("digital_in", c)[0], "a fan MOSFET can't be a digital input")
ok(B.check_kind("pwm_out", c)[0] and "supply voltage" in B.check_kind("pwm_out", c)[1][0], "a MOSFET PWM output warns it switches supply voltage")
ok(B.check_kind("adc", B.caps("PB1", b)) == (True, []), "PB1 is an ADC pin on the F446")
ok(not B.check_kind("adc", B.caps("PG12", b))[0], "PG12 can't read analog")
ok(any("pull-up" in w for w in B.check_kind("adc", B.caps("PF4", b))[1]), "a thermistor header says it has a pull-up")
ok(B.caps("pico:gpio26", b)["adc"] and not B.caps("pico:gpio7", b)["adc"], "Pico: gpio26 is ADC, gpio7 isn't")
ok(B.caps("hand:PB3", b)["adc"] is None and not B.caps("hand:PB3", b)["known"], "an unknown board: ADC unknown, pin not in a table")
ok(any("pinout" in w for w in B.check_kind("digital_out", B.caps("hand:PB3", b))[1]), "an unknown board's pin says to check the pinout")
try:
    B.check_sensor("pnp", B.caps("PB1", b)); ok(False, "PNP on a direct pin is refused")
except Fail:
    ok(True, "PNP on a direct pin is refused")
ok(B.check_sensor("pnp", B.caps("PB1", b), isolated=True) != [], "PNP is allowed once an optocoupler/divider is confirmed (still warns)")
ok(any("5 V tolerant" in w for w in B.check_sensor("optical", B.caps("pico:gpio7", b))), "optical on an RP2040 pin warns: not 5 V tolerant")
ok(not any("5 V tolerant" in w for w in B.check_sensor("optical", B.caps("PB1", b))), "optical on an STM32 FT pin doesn't")

# ---------------------------------------------------------------- the Portal
fake = demo.start_fake()
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
svc = app.config["SERVICE"]
ports = tempfile.mkdtemp(prefix="rhino-serial-")
svc.SERIAL_DIR = ports
open(os.path.join(ports, "usb-Klipper_stm32g0b1xx_EBB-if00"), "w").close()
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json()

r = J(c.get("/api/hardware/pins?kind=adc"))
ok(r["ok"] and r["pins"] and all(p["adc"] for p in r["pins"]), f"ADC picker lists only ADC pins ({len(r['pins'])})")
r = J(c.get("/api/hardware/pins?kind=digital_in"))
ok(r["pins"] and not any(p["mosfet"] for p in r["pins"]) and r["hidden"] > 0, "digital-in picker hides MOSFET outputs")
st = J(c.get("/api/state"))
umb = {x["pin"] for x in st["pins"]["contacts"] if x.get("pin")}
ok(not ({p["pin"] for p in r["pins"]} & umb), "the picker never offers umbilical pins")
ok(c.get("/api/hardware/pins?kind=nonsense").status_code == 400, "an unknown pin kind is refused")
r = J(c.get("/api/hardware/pins?kind=digital_in&sensor=pnp"))
ok(all(p["needs_isolation"] for p in r["pins"]), "with a PNP sensor every pin needs the isolation confirm")

r = J(c.get("/api/hardware/boards"))
ok(any(x["name"] == "tool" and not x["added_here"] for x in r["boards"]), "a hand-written [mcu tool] is listed, read-only")
ok([p["path"] for p in r["serial_ports"]] == [f"{ports}/usb-Klipper_stm32g0b1xx_EBB-if00"], "USB serial ports are listed")

SER = f"{ports}/usb-Klipper_stm32g0b1xx_EBB-if00"
for body, why in [({"name": "mcu", "preset": "ebb_v1_2", "link": "usb", "serial": SER}, "'mcu'"),
                  ({"name": "tool", "preset": "ebb_v1_2", "link": "usb", "serial": SER}, "already used"),
                  ({"name": "ebb", "preset": "nope", "link": "usb", "serial": SER}, "Choose the board"),
                  ({"name": "ebb", "preset": "ebb_v1_2", "link": "usb", "serial": "/tmp/x"}, "by-id"),
                  ({"name": "ebb", "preset": "ebb_v1_2", "link": "usb", "serial": "/dev/serial/by-id/usb-hand-written-if00"}, "already"),
                  ({"name": "ebb", "preset": "ebb_v1_2", "link": "can", "canbus_uuid": "xyz"}, "12 hex")]:
    res = c.post("/api/preview/hardware/boards", json=body, headers=H)
    msg = (J(res) or {}).get("error", "")
    ok(res.status_code == 400 and why in msg, f"board refused ({why}): {msg[:70]}")

svc.SERIAL_DIR = ports   # the by-id check above used the real path prefix; ours is a temp dir
r = c.post("/api/preview/hardware/boards", json={"name": "ebb", "preset": "ebb_v1_2", "link": "can", "canbus_uuid": "0123456789AB"}, headers=H)
ok(r.status_code == 200 and "[mcu ebb]" in J(r)["cfg"] and "canbus_uuid: 0123456789ab" in J(r)["cfg"], "preview shows [mcu ebb] with the CAN UUID")
ok(any("won't start" in w for w in J(r)["warnings"]), "preview warns Klipper won't start without the board")
ok("[mcu ebb]" not in open(GEN).read(), "preview writes nothing")
r = c.post("/api/hardware/boards", json={"name": "EBB", "preset": "ebb_v1_2", "link": "can", "canbus_uuid": "0123456789ab"}, headers=H)
ok(r.status_code == 200 and J(r)["restart_pending"], "board ebb saved, restart pending")
gen = open(GEN).read()
ok("[mcu ebb]" in gen and "canbus_uuid: 0123456789ab" in gen, "generated file has [mcu ebb]")
r = c.post("/api/hardware/boards", json={"name": "ebb2", "preset": "ebb_v1_2", "link": "can", "canbus_uuid": "0123456789ab"}, headers=H)
ok(r.status_code == 400, "the same CAN UUID can't be a second board")

r = J(c.get("/api/hardware/pins?kind=adc"))
ok(any(p["pin"] == "ebb:PA3" for p in r["pins"]), "after adding ebb its thermistor pins appear in the ADC picker")
r = J(c.get("/api/hardware/pins?kind=digital_in"))
ok(not any(p["pin"] == "ebb:PB13" for p in r["pins"]) and any(p["pin"] == "ebb:PB4" for p in r["pins"]), "ebb's heater MOSFET is hidden for inputs, its switch pin shown")
ok(any(p["pin"].startswith("ebb:") for p in J(c.get("/api/options"))["board_pins"]), "the hardware editor's pin list includes ebb's pins")
r = J(c.get("/api/hardware/pins?kind=digital_out"))
ok(not any(p["pin"] == "tool:PA9" for p in r["pins"]), "a hand-written board's used pin isn't offered")

r = c.post("/api/hardware", json={"name": "head_btn", "category": "lighting", "role": "input", "pin": "ebb:PB13", "purpose": "x"}, headers=H)
ok(r.status_code == 400 and "MOSFET" in J(r)["error"], "an input on ebb's heater MOSFET is refused")
r = c.post("/api/hardware", json={"name": "head_light", "category": "lighting", "role": "switch", "pin": "ebb:pb4", "purpose": "x"}, headers=H)
ok(r.status_code == 200, f"system hardware on ebb:PB4 saved {J(r).get('error', '')}")
ok("pin: ebb:PB4" in open(GEN).read(), "generated section uses pin: ebb:PB4")
r = c.post("/api/hardware/pins/check", json={"pin": "ebb:PB4", "kind": "digital_out"}, headers=H)
ok(r.status_code == 400 and "already used" in J(r)["error"], "a typed pin that's in use is refused")
r = c.post("/api/hardware/pins/check", json={"pin": "tool:PB3", "kind": "digital_out"}, headers=H)
ok(r.status_code == 200 and any("pinout" in w for w in J(r)["warnings"]), "a typed pin on an unknown board is allowed with a warning")
free_in = J(c.get("/api/hardware/pins?kind=digital_in"))["pins"][0]["pin"]
r = c.post("/api/hardware/pins/check", json={"pin": free_in, "kind": "digital_in", "sensor": "pnp", "isolated": True}, headers=H)
ok(r.status_code == 200, f"PNP on {free_in} passes once isolation is confirmed")

r = c.delete("/api/hardware/boards/ebb", headers=H)
ok(r.status_code == 400 and "head_light" in J(r)["error"], "a board whose pins are used can't be removed")
r = c.post("/api/hardware/boards", json={"original": "ebb", "name": "ebb", "preset": "rpi_pico", "link": "can", "canbus_uuid": "0123456789ab"}, headers=H)
ok(r.status_code == 400 and "isn't a pin" in J(r)["error"], "changing ebb to a Pico is refused while an STM32 pin is used")
c.delete("/api/hardware/head_light", headers=H)
r = c.delete("/api/hardware/boards/ebb", headers=H)
ok(r.status_code == 200 and "[mcu ebb]" not in open(GEN).read(), "once nothing uses it, ebb is removed and [mcu ebb] is gone")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
fake.shutdown()
sys.exit(1 if fails else 0)
