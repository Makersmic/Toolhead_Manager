#!/usr/bin/env python3
"""Build a demo config whose maintenance records look like a year of real use, for screenshots.

    python3 dev/maint_year_demo.py /tmp/rhino-year      # makes /tmp/rhino-year/printer_data/config
    python3 dev/demo_server.py --config /tmp/rhino-year/printer_data/config --port 5077

Runs the real maintenance service day by day on a simulated clock: the Task Books are assigned on day one,
usage meters grow with simulated jobs and tool swaps, and work is logged when tasks come due (usually a few
days in, now and then skipped or held for parts), so every number on the screens comes from the same rules
the portal uses on the machine. Also writes jobs.json (the last 12 weeks of jobs) for the fake Moonraker.
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import demo_server as demo  # noqa: E402
from rhino.paths import Paths  # noqa: E402
from rhino.service import ToolService  # noqa: E402
from rhino.maint import MaintService  # noqa: E402

DAY = 86400.0
DAYS = 380
random.seed(11)

NOTES = {
    "xy_belts": ["Both belts at 110 Hz, no change", "Re-tensioned the Y belt slightly", "Teeth look good, no fraying"],
    "xy_guides": ["Wiped the rails, fresh grease on the carriages", "Light grease, carriage runs smooth"],
    "z_screws": ["Cleaned and re-lubed all three screws", "Some dust on the rear screw - cleaned"],
    "z_belt": ["Belt tension good on all three", "Tightened the front-left idler"],
    "z_tilt": ["Z_TILT_ADJUST within 0.02 mm", "Re-trammed, first layer looks even", "Within tolerance"],
    "frame": ["All bolts snug, frame square", "Snugged two panel screws"],
    "dust": ["Blew out the cabinet and PSU fans", "Cleaned the board fan grill"],
    "wiring": ["No chafing in the drag chains", "Re-tied a loose bundle by the Z motor"],
    "backup": ["Klipper-Backup pushed to GitHub", "Config backed up"],
    "umbilical": ["Pins clean, latch firm", "Reseated the Cat5 strain relief"],
    "estop": ["Checked after the e-stop - no damage", "Shutdown from a power blip, all fine"],
    "nozzle_clean": ["Brushed and cold-pulled", "Nozzle clean, no wear visible", "Cold pull, small carbon bits"],
    "nozzle_replace": ["New 0.4 mm brass nozzle", "Swapped to a fresh nozzle"],
    "hotend_check": ["Heater and thermistor screws snug", "Wiring OK"],
    "extruder_gears": ["Brushed filament dust out of the BMG gears", "Gears clean"],
    "laser_lens": ["Lens wiped with IPA", "Light smoke film on the window - cleaned", "Lens clean"],
    "laser_focus": ["Focus checked with the height gauge", "Re-aligned slightly"],
    "laser_fan": ["Cleaned the module fan and air assist nozzle", "Fan clean"],
    "collet": ["Collet and nut cleaned", "Cleaned out MDF dust from the collet"],
    "runout": ["Runout under 0.02 mm, bearings quiet", "Bearings quiet"],
    "cnc_chips": ["Vacuumed chips off the mount and Z", "Cleared chips"],
    "blade": ["New 45° blade", "Blade still sharp", "Replaced blade - vinyl was tearing"],
    "knife_bearing": ["Bearing cleaned and spins freely"],
    "tool_connector": ["Pins clean, no burn marks", "Latch and pins fine"],
}

# share of working days each tool is mounted, and per-job (hours, filament m)
TOOLS = {"BlockOne": (0.55, (1.0, 5.5), 6.0), "SwitchFly": (0.12, (1.0, 4.0), 5.0), "LightSaber": (0.17, (0.2, 1.2), 0),
         "HotJoe": (0.09, (0.3, 1.5), 0), "DragKnife": (0.07, (0.1, 0.6), 0)}
JOB_NAMES = {"BlockOne": ["bracket", "enclosure_lid", "gear", "knob", "cable_clip", "spool_holder", "hinge"],
             "SwitchFly": ["two_tone_sign", "dual_color_badge", "logo_coaster"],
             "LightSaber": ["coaster_engrave", "plywood_box", "sign_cut", "acrylic_tag"],
             "HotJoe": ["pcb_mill", "aluminium_plate", "wood_inlay"],
             "DragKnife": ["vinyl_decal", "stencil", "cardstock_card"]}


def main(root):
    cfg = demo.make_config(root)
    clock = {"now": time.time() - DAYS * DAY}
    now = lambda: clock["now"]  # noqa: E731
    svc = ToolService(Paths(cfg))
    m = MaintService(Paths(cfg), svc, now=now)
    st = m.meters
    st.data["tracking_since"] = clock["now"]
    m.library()                                   # seeds the Task Library and its starter books
    books = {"b_rhino": "machine", "b_printhead": ["tool:BlockOne", "tool:SwitchFly"], "b_laser": ["tool:LightSaber"],
             "b_spindle": ["tool:HotJoe"], "b_knife": ["tool:DragKnife"]}
    for bid, assets in books.items():
        for a in ([assets] if isinstance(assets, str) else assets):
            m.book_assign(bid, a)
    pending = {}                                  # task id -> day it will be logged
    jobs, mounted, parts_hold = [], "BlockOne", None
    names = list(TOOLS)
    for day in range(DAYS):
        clock["now"] = time.time() - (DAYS - day) * DAY + 8 * 3600
        st.roll_day(clock["now"])
        working = random.random() < 0.8
        if working:
            st.add("machine", "up_h", random.uniform(6, 11))
            want = random.choices(names, [TOOLS[n][0] for n in names])[0]
            if want != mounted:
                st.add("machine", "swaps", 1)
                st.add("tool", "mounts", 1, want)
                mounted = want
            share, (lo, hi), fil = TOOLS[mounted]
            st.add("tool", "mounted_h", random.uniform(5, 10), mounted)
            for _ in range(random.choice([1, 1, 2, 2, 3])):
                h = random.uniform(lo, hi)
                status = random.choices(["completed", "cancelled", "error"], [0.9, 0.07, 0.03])[0]
                done_h = h if status == "completed" else h * random.uniform(0.1, 0.6)
                for scope, tool in (("machine", None), ("tool", mounted)):
                    st.add(scope, "prod_h", done_h, tool)
                    if status == "completed":
                        st.add(scope, "jobs", 1, tool)
                    if fil:
                        st.add(scope, "filament_m", done_h * fil * random.uniform(0.8, 1.2), tool)
                st.add("tool", "active_h", done_h * random.uniform(0.85, 0.98), mounted)
                jobs.append({"filename": f"{random.choice(JOB_NAMES[mounted])}_{mounted}.gcode", "status": status,
                             "end_time": clock["now"] + random.uniform(1, 10) * 3600, "total_duration": done_h * 3600,
                             "filament_used": done_h * fil * 1000})
        if day in (97, 233):
            st.add("machine", "shutdowns", 1)
        st.save(force=True)
        # log work: due tasks get done a few days after they come due
        d = m._load_tasks()
        for tid, t in d["tasks"].items():
            if t.get("archived") or not t.get("enabled", True) or tid == parts_hold:
                continue
            state = m.status_of(t)["state"]
            if state in ("due_soon", "overdue"):
                when = pending.setdefault(tid, day + random.choice([0, 0, 1, 1, 2, 3, 4] if state == "due_soon" else [0, 1]))
                if day >= when and (day < DAYS - 5 or state == "overdue"):
                    key = (t.get("link") or {}).get("template", "").split(":")[-1]
                    action = "skipped" if random.random() < 0.06 else "done"
                    note = "Not needed - only light use since last time" if action == "skipped" else random.choice(NOTES.get(key, ["Done"]))
                    m.complete(tid, {"action": action, "notes": note})
                    pending.pop(tid, None)
        if day == DAYS - 9 and parts_hold is None:   # one job waiting on a part right now
            for tid, t in m._load_tasks()["tasks"].items():
                if "nozzle_replace" in (t.get("link") or {}).get("template", "") and t["asset"] == "tool:SwitchFly":
                    m.set_status(tid, {"status": "s_parts", "note": "0.4 mm hardened nozzle on order"})
                    parts_hold = tid
    clock["now"] = time.time()
    for tid, t in m._load_tasks()["tasks"].items():     # a well-kept machine: nothing left overdue today
        if not t.get("archived") and tid != parts_hold and m.status_of(t)["state"] == "overdue":
            key = (t.get("link") or {}).get("template", "").split(":")[-1]
            m.complete(tid, {"action": "done", "notes": random.choice(NOTES.get(key, ["Done"])),
                             "date": time.strftime("%Y-%m-%d", time.localtime(time.time() - DAY))})
    st.save(force=True)
    cutoff = time.time() - 84 * DAY
    with open(os.path.join(root, "jobs.json"), "w") as f:
        json.dump([j for j in jobs if j["end_time"] > cutoff and j["end_time"] < time.time()], f)
    ov = m.overview()
    states = {}
    for t in ov.get("tasks", []):
        states[t["status"]["state"]] = states.get(t["status"]["state"], 0) + 1
    print(cfg)
    print("tasks:", states, "history:", len(m._load_history()), "jobs:", len(jobs))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rhino-year")
