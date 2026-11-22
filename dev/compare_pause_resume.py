#!/usr/bin/env python3
"""Does a changed pause / resume / cancel behave like the old one? (docs/proposal-own-pause-resume.md)

    python3 dev/compare_pause_resume.py <old config tree> <new config tree>

Each tree is a checkout (or copy) of this repo with its own dev/klippersim.py. The same 27 scenarios run in each tree's
simulated Klipper (print head pause, resume and cancel; X/Y/Z_MIN; RESTORE=0; unhomed; relative extrusion; cold extruder;
resume after an idle timeout; VELOCITY=; pause at a layer and at the next layer; laser, CNC and knife pause, refused Resume,
TOOL_RESUME and cancel), and what each emits (G-code in order, errors, pop-up title, console messages) is compared. The three
helpers the proposal renames are mapped first. The simulator is not Klipper: this shows the macros agree, not that Klipper accepts them."""
import json
import os
import subprocess
import sys

RENAMED = {"_CLIENT_RETRACT": "_RHINO_RETRACT", "_CLIENT_EXTRUDE": "_RHINO_EXTRUDE", "_TOOLHEAD_PARK_PAUSE_CANCEL": "_RHINO_PAUSE_PARK"}


def scenarios(root):
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.join(root, "dev"))
    from klippersim import Sim, KlipperError

    def fresh(slot, homed="xyz", x=200, y=150, z=20):
        s = Sim(root).load(); s.macro_vars["SWAP_TOOL"]["current_tool"] = slot; s.seed_meshes()
        s.place(x, y, z, homed=homed)
        s.objects["print_stats"]["state"] = "printing"; s.objects["extruder"]["can_extrude"] = True
        return s
    def cmds(s, n=0): return [str(x[1]) for x in s.log[n:] if x[0] == "cmd"]
    def run(s, script):
        n = len(s.log)
        try: s.run_script(script); err = None
        except KlipperError as e: err = str(e)[:90]
        return {"cmds": cmds(s, n), "err": err, "prompt": (s.prompt or {}).get("title") if s.prompt else None,
                "responds": [str(x[1]) for x in s.log[n:] if x[0] in ("echo", "error", "info")][:6]}

    out = {}
    s = fresh(1)
    out["print: pause"] = run(s, "PAUSE")
    out["print: resume"] = run(s, "RESUME")
    s.objects["print_stats"]["state"] = "printing"
    out["print: cancel"] = run(s, "CANCEL_PRINT")
    s = fresh(1); out["pause X Y Z_MIN"] = run(s, "PAUSE X=10 Y=20 Z_MIN=50")
    s = fresh(1); out["pause RESTORE=0"] = run(s, "PAUSE RESTORE=0")
    s = fresh(1, homed=""); out["pause unhomed"] = run(s, "PAUSE")
    s = fresh(1); s.objects["gcode_move"]["absolute_extrude"] = False; out["pause relative E"] = run(s, "PAUSE")
    s = fresh(1); run(s, "PAUSE"); s.objects["extruder"]["can_extrude"] = False; out["resume cold"] = run(s, "RESUME")
    s = fresh(1); s.objects["extruder"]["target"] = 210.0; run(s, "PAUSE"); s.objects["idle_timeout"]["state"] = "Idle"; s.objects["extruder"]["can_extrude"] = False
    out["resume after idle (restore 210)"] = run(s, "RESUME")
    s = fresh(1); run(s, "PAUSE"); out["resume VELOCITY=20"] = run(s, "RESUME VELOCITY=20")
    s = fresh(1); run(s, "SET_PAUSE_AT_LAYER LAYER=3"); out["pause at layer 2 (nothing)"] = run(s, "SET_PRINT_STATS_INFO CURRENT_LAYER=2 TOTAL_LAYER=10")
    out["pause at layer 3 (pauses)"] = run(s, "SET_PRINT_STATS_INFO CURRENT_LAYER=3 TOTAL_LAYER=10")
    s = fresh(1); run(s, "SET_PAUSE_NEXT_LAYER"); out["pause next layer"] = run(s, "SET_PRINT_STATS_INFO CURRENT_LAYER=1")
    s = fresh(1); out["cancel resets layer pauses"] = run(s, "SET_PAUSE_AT_LAYER LAYER=5"); out["cancel after layer set"] = run(s, "CANCEL_PRINT")
    for slot, name in ((3, "laser"), (4, "cnc"), (5, "knife")):
        s = fresh(slot); s.objects["extruder"]["can_extrude"] = False
        out[f"{name}: pause"] = run(s, "PAUSE"); out[f"{name}: resume refused"] = run(s, "RESUME")
        s.objects["extruder"]["can_extrude"] = True
        out[f"{name}: tool resume"] = run(s, "TOOL_RESUME")
        s.objects["print_stats"]["state"] = "printing"; out[f"{name}: cancel"] = run(s, "CANCEL_PRINT")
    return out


def normalise(r):
    r = json.loads(json.dumps(r))
    r["cmds"] = [RENAMED.get(c.split()[0], c.split()[0]) + c[len(c.split()[0]):] for c in r["cmds"]]
    return r


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--run":
        print(json.dumps(scenarios(sys.argv[2])))
        return 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    runs = [json.loads(subprocess.run([sys.executable, os.path.abspath(__file__), "--run", os.path.abspath(r)],
                                      capture_output=True, text=True, check=True).stdout) for r in sys.argv[1:3]]
    old, new = runs
    bad = [k for k in old if k not in new or normalise(old[k]) != normalise(new[k])]
    print(f"{len(old) - len(bad)} of {len(old)} scenarios identical (G-code, errors, pop-ups, messages)")
    for k in bad:
        print("DIFFERENT:", k)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
