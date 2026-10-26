"""Add hardware wizard catalog (step 1). Run: python3 dev/test_hw_catalog.py  (needs flask)

Design: docs/hardware-coverage.md; answers in docs/decisions.md (2026-10-26). Checks the tables agree,
today's six roles are all 'ready', the safety answers are in the data, and the read-only route serves it."""
import json, os, shutil, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-hwcat-test-")
CFG = ROOT + "/printer_data/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT
from rhino import hw_catalog as C, presets
from rhino.portal import create_app

fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


# ---------------------------------------------------------------- the tables agree
probs = C.check()
ok(probs == [], "catalog check is clean" + ("" if not probs else ": " + "; ".join(probs)))
ok([g for g, _ in C.GROUPS][:3] == ["power", "spindle", "air"], "menu starts Power, Spindles, Coolant/air/dust")
ok(len({d["label"] for d in C.DEVICES.values()}) == len(C.DEVICES), "every device label is unique")

# ---------------------------------------------------------------- today's roles keep working (status ready)
ready = {d["role"] for d in C.DEVICES.values() if d["status"] == "ready"}
ok(ready == set(presets.CONTROL_ROLES), f"all six existing roles are ready devices ({sorted(ready)})")
ok(all(d["status"] == "planned" for d in C.DEVICES.values() if d["role"] is None), "every new type is 'planned' until its step")

# ---------------------------------------------------------------- decisions are in the data
ok(C.HEATER_MAX_TEMP == 120.0, "heater_generic cap is 120 C")
il = C.INPUT_PURPOSES["interlock"]
ok(il["must_close_to_start"] and set(il["must_close_default_for"]) == {"laser", "spindle"}, "interlocks: must be closed to start, on for laser and spindle")
ok(C.DEVICES["board"]["section"] == "mcu" and C.DEVICES["board"]["group"] == "boards", "a second board is in the catalog")
ok(C.DEVICES["heater"]["hardware_only"] and C.DEVICES["controller_fan"]["hardware_only"], "heater and controller fan are system hardware only")
ok(C.DEVICES["heater"]["live"] and C.DEVICES["spindle_pwm"]["live"] and C.DEVICES["pwm_tool"]["live"], "heater, spindle and laser-style power are live (behind the padlock)")

# ---------------------------------------------------------------- sensor types write the right flags
S = C.SENSOR_TYPES
ok(S["mech_nc"]["recommended"] and S["mech_nc"]["pullup"] and not S["mech_nc"]["invert"], "NC switch: recommended, pull-up, not inverted")
ok(S["mech_no"]["invert"], "NO switch is inverted")
ok(S["pnp"].get("refuse_direct") is True, "PNP sensors are refused on a direct pin")
ok(all("6-36 V" in S[k]["warn"] for k in ("npn_no", "npn_nc")), "NPN sensors warn about supply voltage")
ok(S["thermistor"]["pin_kind"] == "adc", "thermistors need an ADC pin")
ok(all(p["action"] in presets.INPUT_ACTIONS for p in C.INPUT_PURPOSES.values()), "every purpose's action exists today")

# ---------------------------------------------------------------- the route
app = create_app(CFG, "http://127.0.0.1:9")
r = app.test_client().get("/api/hardware/catalog")
J = r.get_json() or {}
ok(r.status_code == 200 and J.get("ok"), "GET /api/hardware/catalog answers")
ok([g["id"] for g in J.get("groups", [])] == [g for g, _ in C.GROUPS], "groups come back in menu order")
ok(sum(len(g["devices"]) for g in J.get("groups", [])) == len(C.DEVICES), "every device is in exactly one group")
ok(J.get("limits", {}).get("heater_max_temp") == 120.0, "limits are served")
ok(json.loads(json.dumps(J)) == J, "the catalog is plain JSON")
r = app.test_client().post("/api/hardware/catalog")
ok(r.status_code == 405, "the catalog route is read-only")

shutil.rmtree(ROOT, ignore_errors=True)
print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
