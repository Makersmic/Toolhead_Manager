"""Pin labels (1.5.3): [board_pins rhino] from the registry, label save/change/remove, and using a label in a section.
Run: python3 dev/test_labels.py   (needs flask)"""
import json, os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from rhino.paths import resolve as resolve_paths
from rhino.klipper_cfg import ConfigTree
from rhino import pin_labels
from rhino.errors import Fail

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

PRINTER = os.path.join(CFG, "printer.cfg")
GEN = os.path.join(CFG, "myrhino", "custom_tools.cfg")
# a named [board_pins] of the user's own, as Klipper allows
with open(PRINTER, "a") as f:
    f.write("\n[board_pins mine]\naliases: PROBE_IN=PG10\n")

fake = demo.start_fake()
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json()
def pins(): return J(c.get("/api/state"))["pins"]

# ---------------------------------------------------------------- read
p = pins()
mine = {l["alias"]: l for l in p["labels"]}
ok("EXP2_3" in mine and mine["EXP2_3"]["pin"] == "PB1" and not mine["EXP2_3"]["editable"] and "printer.cfg [board_pins]" in mine["EXP2_3"]["source"],
   "aliases in printer.cfg's [board_pins] show, read-only, with where they are")
ok("PROBE_IN" in mine and mine["PROBE_IN"]["source"].endswith("[board_pins mine]"), "a named [board_pins mine] section is read too (it wasn't before)")
ok(not any(l["alias"] == "EXP1_9" for l in p["labels"]), "<GND>-style entries aren't listed as pins")
free = [x["pin"] for x in p["free_board_pins"]]
ok(len(free) >= 3 and "PF13" not in free, f"free pins for labels exclude the config's pins ({len(free)} free)")
A, B, C = free[0], free[1], free[2]
ok(any(r["key"] == "step_pin" and r["pin"] == "PF13" for r in p["raw_pin_lines"]), "raw pin lines are listed (for Scan Config / Use a label)")

# ---------------------------------------------------------------- refusals
for alias, pin, why in [("PB5", A, "looks like a pin"), ("x", A, "2-32 letters"), ("1LIGHT", A, "2-32 letters"),
                        ("EXP1_1", A, "already an alias"), ("ENCLOSURE_LIGHT", "PF13", "already used by"),
                        ("ENCLOSURE_LIGHT", "ZZ", "isn't a board pin")]:
    r = c.post("/api/pins/label", json={"alias": alias, "pin": pin}, headers=H)
    ok(r.status_code == 400 and why in J(r)["error"], f"{alias}={pin} refused: {why}")
r = c.post("/api/pins/label", json={"alias": "ENCLOSURE_LIGHT", "pin": A})
ok(r.status_code == 400, "no token: refused")
ok("board_pins rhino" not in open(GEN).read(), "nothing written by the refusals")

# ---------------------------------------------------------------- add
r = c.post("/api/preview/pins/label", json={"alias": "enclosure_light", "pin": A.lower()}, headers=H)
ok(r.status_code == 200 and J(r)["alias"] == "ENCLOSURE_LIGHT" and "board_pins rhino" not in open(GEN).read(), "preview: upper-cased, writes nothing")
r = c.post("/api/pins/label", json={"alias": "enclosure_light", "pin": A}, headers=H)
gen = open(GEN).read()
ok(r.status_code == 200 and J(r)["restart_pending"] and "[board_pins rhino]" in gen and f"ENCLOSURE_LIGHT={A}" in gen,
   "label saved: [board_pins rhino] in the generated file, restart pending")
reg = json.load(open(os.path.join(CFG, "myrhino", "custom_tools.json")))
ok(reg["labels"] == {"ENCLOSURE_LIGHT": A}, "registry keeps the labels")
p = pins()
ok(A not in [x["pin"] for x in p["free_board_pins"]] or any(x["pin"] == A and x["labelled"] for x in p["free_board_pins"]), "a labelled pin isn't offered as free to others")
r = c.post("/api/pins/label", json={"alias": "OTHER", "pin": A}, headers=H)
ok(r.status_code == 400 and "kept for pin label ENCLOSURE_LIGHT" in J(r)["error"], "a second label on the same pin is refused")
r = c.post("/api/hardware", json={"name": "lamp", "category": "lighting", "role": "switch", "pin": A, "purpose": "x"}, headers=H)
ok(r.status_code == 400, "system hardware can't take a labelled pin")

# a section of the user's own uses the label
with open(PRINTER, "a") as f:
    f.write("\n[output_pin enclosure_light]\npin: !ENCLOSURE_LIGHT   # the lid light\nvalue: 0\n")
p = pins()
lab = next(l for l in p["labels"] if l["alias"] == "ENCLOSURE_LIGHT")
ok(lab["editable"] and lab["used_by"] == ["printer.cfg [output_pin enclosure_light]"], "the label shows what uses it")
ok(any(x["pin"] == A and x["state"] == "claimed" for x in p["pins"]) or A not in [x["pin"] for x in p["pins"]], "the section claims the label's pin")

# ---------------------------------------------------------------- change the pin
r = c.post("/api/pins/label", json={"original": "ENCLOSURE_LIGHT", "alias": "ENCLOSURE_LIGHT", "pin": B}, headers=H)
ok(r.status_code == 200 and J(r)["previous"] == A and J(r)["pin"] == B, f"label moved {A} -> {B}, the previous pin is returned")
st = J(c.get("/api/state"))
ok(any(f"ENCLOSURE_LIGHT: {A} -> {B}" in ch for ch in (st.get("restart") or {}).get("changes", [])) or f"{A} -> {B}" in json.dumps(st),
   "the restart banner says what moved")
tree = ConfigTree(resolve_paths(CFG), extra_aliases={"ENCLOSURE_LIGHT": B})
ok(tree.claimed_pins.get(B) == "printer.cfg [output_pin enclosure_light]" and A not in tree.claimed_pins, "after the change the section claims the new pin, the old one is free")
r = c.post("/api/pins/label", json={"original": "ENCLOSURE_LIGHT", "alias": "LID_LIGHT", "pin": B}, headers=H)
ok(r.status_code == 400 and "can't be renamed" in J(r)["error"], "a label in use can't be renamed")
r = c.delete("/api/pins/label/ENCLOSURE_LIGHT", headers=H)
ok(r.status_code == 400 and "used by" in J(r)["error"], "a label in use can't be removed")

# ---------------------------------------------------------------- use a label in a section (one line rewritten)
with open(PRINTER, "a") as f:
    f.write(f"\n[fan_generic drybox]\npin: ^{C}  ; dry box fan\nmax_power: 1.0\n")
p = pins()
ok(any(r["section"] == "fan_generic drybox" and r["pin"] == C for r in p["raw_pin_lines"]), "the raw pin line shows up")
r = c.post("/api/pins/label/use", json={"file": "printer.cfg", "section": "fan_generic drybox", "key": "pin", "alias": "DRYBOX_FAN"}, headers=H)
txt = open(PRINTER).read()
ok(r.status_code == 200 and J(r)["made_label"] and "pin: ^DRYBOX_FAN  ; dry box fan" in txt, "the line now uses the new label; ^ and the comment kept")
bdir = os.path.join(os.path.dirname(CFG), "rhino_data", "config_backups")
ok(os.path.isdir(bdir) and any(n.startswith("printer.cfg.") for n in os.listdir(bdir)), "printer.cfg was copied to rhino_data/config_backups first")
ok(json.load(open(os.path.join(CFG, "myrhino", "custom_tools.json")))["labels"].get("DRYBOX_FAN") == C, "...and the label was made for the pin it named")
ok(txt.count("[fan_generic drybox]") == 1 and txt.count("ENCLOSURE_LIGHT") == 1, "nothing else in printer.cfg changed")
for body, why in [({"file": "../printer.cfg", "section": "x", "key": "pin", "alias": "AA_B"}, "isn't a file"),
                  ({"file": "/etc/passwd", "section": "x", "key": "pin", "alias": "AA_B"}, "isn't a file"),
                  ({"file": "myrhino/custom_tools.cfg", "section": "x", "key": "pin", "alias": "AA_B"}, "generated file"),
                  ({"file": "printer.cfg", "section": "nope", "key": "pin", "alias": "AA_B"}, "No pin line"),
                  ({"file": "printer.cfg", "section": "fan_generic drybox", "key": "pin", "alias": "ZZ_TOP"}, "already uses"),
                  ({"file": "printer.cfg", "section": "stepper_x", "key": "step_pin", "alias": "ENCLOSURE_LIGHT"}, "names")]:
    r = c.post("/api/pins/label/use", json=body, headers=H)
    ok(r.status_code == 400 and why in J(r)["error"], f"use refused: {why}")

# the line rewrite on its own
t = "[a]\npin: PB5\n[b]\npin: PB5 # x\n[ b ]\n"
ok(pin_labels.rewrite_pin_line("[a]\npin: PB5\n[b]\npin: PB5 # x\n", "b", "pin", "PB5", "LAMP") == "[a]\npin: PB5\n[b]\npin: LAMP # x\n", "rewrite: only the named section's line")
try:
    pin_labels.rewrite_pin_line("[a]\npin: PB5\npin: PB5\n", "a", "pin", "PB5", "X")
    ok(False, "two matching lines refused")
except Fail:
    ok(True, "two matching lines refused (change it by hand)")

# ---------------------------------------------------------------- remove
with open(PRINTER, "r") as f:
    txt = f.read()
r = c.post("/api/pins/label", json={"alias": "SPARE_ONE", "pin": free[3]}, headers=H)
r = c.delete("/api/pins/label/SPARE_ONE", headers=H)
ok(r.status_code == 200 and "SPARE_ONE" not in open(GEN).read(), "an unused label is removed")

# ---------------------------------------------------------------- system hardware on a label (Scan Config picks one)
p = pins()
spare = [x["pin"] for x in p["free_board_pins"] if not x["connector"] and not x["labelled"]]
r = c.post("/api/pins/label", json={"alias": "SHOP_LAMP_PIN", "pin": spare[0]}, headers=H)
ok(r.status_code == 200, f"a label for a board header pin ({spare[0]})")
lamp = {"name": "shop_lamp", "role": "switch", "pin": "SHOP_LAMP_PIN", "category": "lighting", "purpose": "Shop lamp", "make_macros": False, "safe_off": False}
r = c.post("/api/hardware", json=lamp, headers=H)
gen = open(GEN).read()
ok(r.status_code == 200 and "[output_pin shop_lamp]" in gen and "pin: SHOP_LAMP_PIN" in gen.split("[output_pin shop_lamp]")[1].split("[")[0],
   "system hardware on a label: its section says pin: SHOP_LAMP_PIN")
lab = next(l for l in pins()["labels"] if l["alias"] == "SHOP_LAMP_PIN")
ok(lab["used_by"] == ["system hardware shop_lamp"], "the label shows the hardware uses it")
r = c.delete("/api/pins/label/SHOP_LAMP_PIN", headers=H)
ok(r.status_code == 400 and "system hardware shop_lamp" in J(r)["error"], "a label hardware uses can't be removed")
r = c.post("/api/pins/label", json={"original": "SHOP_LAMP_PIN", "alias": "SHOP_LAMP_PIN", "pin": spare[1]}, headers=H)
reg = json.load(open(os.path.join(CFG, "myrhino", "custom_tools.json")))
ok(r.status_code == 200 and reg["hardware"]["shop_lamp"]["pin"] == spare[1] and reg["hardware"]["shop_lamp"]["pin_label"] == "SHOP_LAMP_PIN",
   "moving the label moves the hardware with it")
r = c.post("/api/hardware", json={**lamp, "name": "lamp2", "pin": spare[1]}, headers=H)
ok(r.status_code == 400 and ("SHOP_LAMP_PIN" in J(r)["error"] or "system hardware shop_lamp" in J(r)["error"]), "a second piece of hardware can't take the label's pin")
r = c.post("/api/hardware", json={**lamp, "name": "exp_lamp", "pin": "EXP1_3"}, headers=H)
gen = open(GEN).read()
ok(r.status_code == 200 and "pin: EXP1_3" in gen, "an alias of your own (EXP1_3) works too, and is kept by name")

fake.shutdown()
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
