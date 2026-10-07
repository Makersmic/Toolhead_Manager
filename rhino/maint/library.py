"""Starter maintenance tasks. Every interval is a placeholder to tune on the real machine: add them,
then edit the numbers. Templates are copied into your task list - changing this file never changes
tasks you already added."""

DEFAULT_AREAS = [
    {"id": "motion_xy", "label": "Motion X/Y"},
    {"id": "motion_z", "label": "Motion Z"},
    {"id": "frame", "label": "Frame and enclosure"},
    {"id": "electronics", "label": "Electronics"},
    {"id": "umbilical", "label": "Umbilical and tool connector"},
    {"id": "other", "label": "Other"},
]


def _t(n, unit="months", lead=None, lead_unit="days"):
    r = {"kind": "time", "every": n, "unit": unit}
    if lead is not None:
        r.update(lead=lead, lead_unit=lead_unit)
    return r


def _m(meter, n, lead=None, scope="machine"):
    r = {"kind": "meter", "meter": meter, "scope": scope, "every": n}
    if lead is not None:
        r["lead"] = lead
    return r


def _e(meter, scope="machine"):
    return {"kind": "meter", "meter": meter, "scope": scope, "every": 1, "lead": 0, "event": True}


MACHINE = [
    {"id": "xy_belts", "area": "motion_xy", "title": "Check and tension the X/Y belts", "type": "adjust",
     "rules": [_m("prod_h", 100, 10), _t(1, lead=7)],
     "steps": ["Motors off (M84) so the gantry moves freely", "Both CoreXY belts at the same tension - pluck and compare the note",
               "Look for frayed edges, missing teeth or a belt riding the pulley flange",
               "Check every pulley and idler grub screw", "Print or draw a square and measure the diagonals"],
     "parts": ["Spare GT2 belt (same width)"], "minutes": 20},
    {"id": "xy_guides", "area": "motion_xy", "title": "Clean and lubricate the X/Y linear guides", "type": "lubricate",
     "rules": [_m("prod_h", 200, 20), _t(3, lead=14)],
     "steps": ["Wipe old grease and dust off the rails", "Apply a thin film of lubricant along the rails",
               "Run each axis end to end a few times", "Wipe off the excess"],
     "parts": ["Rail grease or light machine oil", "Lint-free cloths"], "minutes": 20},
    {"id": "z_screws", "area": "motion_z", "title": "Clean and lubricate the Z leadscrews", "type": "lubricate",
     "rules": [_m("prod_h", 250, 25), _t(3, lead=14)],
     "steps": ["Clean the three leadscrews with a dry brush or cloth", "Apply leadscrew grease sparingly along the thread",
               "Run Z through its full travel", "Check the nuts for backlash"],
     "parts": ["Leadscrew grease (PTFE or lithium)"], "minutes": 20},
    {"id": "z_belt", "area": "motion_z", "title": "Check the Z belt drive (2:1 reduction)", "type": "inspect",
     "rules": [_m("prod_h", 500, 50), _t(6, lead=14)],
     "steps": ["Belt tension and condition", "Pulley set screws on the motor and all three leadscrews",
               "Turn the drive by hand: all three screws must move together", "Run Z_TILT_ADJUST afterwards"],
     "parts": ["Spare closed-loop belt for the Z drive"], "minutes": 30},
    {"id": "z_tilt", "area": "motion_z", "title": "Level the gantry (Z_TILT_ADJUST) and check the first layer", "type": "calibrate",
     "rules": [_t(1, lead=5)], "steps": ["Home all axes", "Run Z_TILT_ADJUST", "Print or cut a test and check it"], "minutes": 15},
    {"id": "frame", "area": "frame", "title": "Check frame bolts and squareness", "type": "inspect",
     "rules": [_t(6, lead=14)], "steps": ["Check the frame and gantry bolts", "Check the frame is square and does not rock"],
     "minutes": 30},
    {"id": "dust", "area": "electronics", "title": "Clean dust from the electronics bay and fans", "type": "clean",
     "rules": [_m("up_h", 1000, 100), _t(3, lead=14)],
     "steps": ["Power everything off and unplug it", "Blow dust off the Octopus, the Pi and the PSU",
               "Check every electronics fan spins freely"],
     "parts": ["Can of compressed air"], "minutes": 15,
     "safety": "Unplug the machine and wait for the PSU to discharge before opening the bay."},
    {"id": "wiring", "area": "electronics", "title": "Inspect wiring, connectors and cable chains", "type": "inspect",
     "rules": [_t(6, lead=14)], "steps": ["Look for rubbing, cracked insulation or loose crimps", "Check the screw terminals for tightness"],
     "minutes": 30, "safety": "Machine powered off."},
    {"id": "backup", "area": "electronics", "title": "Back up the Klipper config (BACKUP_CFG)", "type": "other", "priority": "low",
     "rules": [_t(1, lead=3)], "steps": ["Run BACKUP_CFG in the console", "Check the commit arrived on GitHub"], "minutes": 5},
    {"id": "umbilical", "area": "umbilical", "title": "Inspect the 21-pin umbilical connector and cable", "type": "inspect",
     "rules": [_m("swaps", 100, 10), _t(3, lead=14)],
     "steps": ["Look into both halves for bent, pushed-back or burnt pins", "Check the latch holds firmly",
               "Flex the cable along its length and watch the thermistor reading for drop-outs"],
     "parts": ["Spare connector pins / housing"], "minutes": 15},
    {"id": "estop", "area": "other", "title": "Inspect the machine after an emergency stop or shutdown", "type": "inspect",
     "priority": "high", "rules": [_e("shutdowns")],
     "steps": ["Find out why it stopped (Mainsail console, klippy.log)", "Check nothing crashed into the bed or a clamp",
               "Home and check the axes move freely before the next job"], "minutes": 10},
]

TOOLS = [
    # print heads
    {"id": "nozzle_clean", "types": ["DEPOSITION"], "title": "Clean the nozzle and check it for wear", "type": "clean",
     "rules": [_m("active_h", 100, 10, "tool")], "steps": ["Heat the nozzle", "Brush the outside clean", "Check the tip for wear or a widened hole"],
     "parts": ["Brass brush"], "minutes": 10, "safety": "The nozzle is hot."},
    {"id": "nozzle_replace", "types": ["DEPOSITION"], "title": "Replace the nozzle", "type": "replace",
     "rules": [_m("active_h", 500, 50, "tool")], "steps": ["Heat to printing temperature", "Swap the nozzle and hot-tighten it",
                                                         "Re-check the Z offset"],
     "parts": ["Nozzle, same size and type"], "minutes": 20, "safety": "Hot-tighten with the right wrench; the heater block is hot."},
    {"id": "hotend_check", "types": ["DEPOSITION"], "title": "Check the hotend screws, heater and thermistor wiring", "type": "inspect",
     "rules": [_m("active_h", 200, 20, "tool"), _t(6, lead=14)], "minutes": 15},
    {"id": "extruder_gears", "types": ["DEPOSITION"], "title": "Clean the extruder drive gears", "type": "clean",
     "rules": [_m("filament_m", 1000, 100, "tool")], "steps": ["Unload filament", "Brush filament dust out of the gear teeth"], "minutes": 10},
    # LightSaber
    {"id": "laser_lens", "types": ["LASER"], "title": "Clean the laser lens / protective window", "type": "clean", "priority": "high",
     "rules": [_m("active_h", 10, 2, "tool")], "steps": ["Laser and power rail off", "Wipe the lens with lens tissue and isopropyl alcohol",
                                                      "Check for burn marks or pitting"],
     "parts": ["Lens tissue", "Isopropyl alcohol"], "minutes": 5,
     "safety": "Laser off and LASER_INITIALIZE off before touching the module. Wear laser goggles for any test fire."},
    {"id": "laser_focus", "types": ["LASER"], "title": "Check laser focus and alignment", "type": "calibrate",
     "rules": [_m("active_h", 50, 5, "tool")], "minutes": 15, "safety": "Laser goggles on for the test burn."},
    {"id": "laser_fan", "types": ["LASER"], "title": "Clean the laser module fan and air assist", "type": "clean",
     "rules": [_m("active_h", 25, 3, "tool"), _t(1, lead=5)], "minutes": 10},
    # HotJoe
    {"id": "collet", "types": ["CNC"], "title": "Clean the collet and collet nut", "type": "clean",
     "rules": [_m("active_h", 20, 2, "tool")], "steps": ["Remove the bit", "Clean resin and chips out of the collet and nut"],
     "minutes": 10, "safety": "Spindle relay off (Spindle_power) before touching the bit."},
    {"id": "runout", "types": ["CNC"], "title": "Check spindle runout and bearing noise", "type": "inspect",
     "rules": [_m("active_h", 100, 10, "tool")], "parts": ["Spare collet set"], "minutes": 20},
    {"id": "cnc_chips", "types": ["CNC"], "title": "Clear chips from the spindle mount and Z axis", "type": "clean",
     "rules": [_m("jobs", 10, 2, "tool")], "minutes": 10},
    # DragKnife
    {"id": "blade", "types": ["DRAG_KNIFE"], "title": "Inspect or replace the drag-knife blade", "type": "replace",
     "rules": [_m("prod_h", 20, 3, "tool")], "parts": ["Replacement blades"], "minutes": 5, "safety": "The blade is sharp."},
    {"id": "knife_bearing", "types": ["DRAG_KNIFE"], "title": "Clean the drag-knife bearing", "type": "clean",
     "rules": [_m("prod_h", 50, 5, "tool")], "minutes": 10},
    # user-added tools
    {"id": "hot_wire", "kinds": ["HOT_WIRE"], "title": "Check the hot-wire tension and replace a kinked wire", "type": "inspect",
     "rules": [_m("active_h", 10, 2, "tool")], "parts": ["Spare nichrome wire"], "minutes": 10, "safety": "Wire off and cool."},
    {"id": "needle", "kinds": ["NEEDLE"], "title": "Replace the needle or blade", "type": "replace",
     "rules": [_m("active_h", 20, 3, "tool")], "parts": ["Spare needles / blades"], "minutes": 10},
    {"id": "powered", "kinds": ["POWERED"], "title": "Inspect the tool and its power cable", "type": "inspect",
     "rules": [_m("active_h", 50, 5, "tool"), _t(3, lead=14)], "minutes": 10},
    {"id": "passive", "kinds": ["PASSIVE"], "title": "Inspect and clean the tool", "type": "clean", "rules": [_t(3, lead=14)], "minutes": 10},
    # every tool
    {"id": "tool_connector", "types": ["*"], "title": "Inspect the tool connector pins and latch", "type": "inspect",
     "rules": [_m("mounts", 50, 5, "tool")], "steps": ["Look for bent or burnt pins", "Check the latch and alignment pins"], "minutes": 5},
]


def for_tool(tool):
    """Templates that apply to one tool (tool = {'name', 'type', 'kind'})."""
    out = []
    for t in TOOLS:
        if "kinds" in t:
            if tool.get("kind_code") in t["kinds"]:
                out.append(t)
        elif "*" in t["types"] or tool.get("type") in t["types"]:
            out.append(t)
    return out


def by_id():
    return {**{f"machine:{t['id']}": t for t in MACHINE}, **{f"tool:{t['id']}": t for t in TOOLS}}


# ----------------------------------------------------------------------------- starter Task Books
# Seeded into the Task Library the first time it opens. A book groups library tasks under one name;
# assigning it to a toolhead (or the whole machine) adds all its tasks there, linked to the library,
# so editing a library task updates every copy. "suggest" picks the book offered for a new tool.
STARTER_BOOKS = [
    {"id": "b_rhino", "name": "Rhino motion system and frame", "for": "machine",
     "description": "Belts, guides, leadscrews, frame, electronics and the umbilical. Assign it to the whole machine.",
     "templates": [f"machine:{t['id']}" for t in MACHINE]},
    {"id": "b_printhead", "name": "3D print head", "suggest": {"types": ["DEPOSITION"]},
     "description": "Nozzle, hotend and extruder care for any print head.",
     "templates": ["tool:nozzle_clean", "tool:nozzle_replace", "tool:hotend_check", "tool:extruder_gears", "tool:tool_connector"]},
    {"id": "b_laser", "name": "Laser module", "suggest": {"types": ["LASER"]},
     "description": "Lens, focus and module cooling.", "templates": ["tool:laser_lens", "tool:laser_focus", "tool:laser_fan", "tool:tool_connector"]},
    {"id": "b_spindle", "name": "CNC spindle", "suggest": {"types": ["CNC"]},
     "description": "Collet, runout and chip clearing.", "templates": ["tool:collet", "tool:runout", "tool:cnc_chips", "tool:tool_connector"]},
    {"id": "b_knife", "name": "Drag knife", "suggest": {"types": ["DRAG_KNIFE"], "kinds": ["BLADE"]},
     "description": "Blade and bearing.", "templates": ["tool:blade", "tool:knife_bearing", "tool:tool_connector"]},
    {"id": "b_hotwire", "name": "Hot wire cutter", "suggest": {"kinds": ["HOT_WIRE"]},
     "description": "Wire tension and the connector.", "templates": ["tool:hot_wire", "tool:tool_connector"]},
    {"id": "b_needle", "name": "Needle cutter", "suggest": {"kinds": ["NEEDLE"]},
     "description": "Needle or blade and the connector.", "templates": ["tool:needle", "tool:tool_connector"]},
    {"id": "b_powered", "name": "Powered tool", "suggest": {"types": ["POWERED"]},
     "description": "General checks for any powered tool you add.", "templates": ["tool:powered", "tool:tool_connector"]},
    {"id": "b_passive", "name": "Passive tool", "suggest": {"types": ["PASSIVE"]},
     "description": "General checks for any unpowered tool you add.", "templates": ["tool:passive", "tool:tool_connector"]},
]


_DEF_DEFAULTS = {"priority": "normal", "anchor": "completion", "steps": [], "parts": [], "tools_needed": "", "minutes": 0,
                 "safety": "", "notes": "", "links": [], "remind_boot": True}


def starter_templates():
    """{library id: template} for the Task Library's first run (ids are the old starter keys)."""
    out = {}
    for t in MACHINE:
        out[f"machine:{t['id']}"] = {**_DEF_DEFAULTS, **{k: v for k, v in t.items() if k != "id"}, "origin": "starter", "for": "machine"}
    for t in TOOLS:
        out[f"tool:{t['id']}"] = {**_DEF_DEFAULTS, **{k: v for k, v in t.items() if k not in ("id", "types", "kinds")}, "origin": "starter", "for": "tool"}
    return out


def suggested_book(tool):
    """The starter book that fits a tool best ({'type', 'kind_code'}), or None."""
    for b in STARTER_BOOKS:
        s = b.get("suggest", {})
        if tool.get("kind_code") and tool["kind_code"] in s.get("kinds", []):
            return b["id"]
    for b in STARTER_BOOKS:
        if tool.get("type") in b.get("suggest", {}).get("types", []):
            return b["id"]
    return None
