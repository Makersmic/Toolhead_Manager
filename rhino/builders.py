"""Validate user input and build or edit ONE tool dict.

Input is a plain dict with lower-case keys - the web form, the CLI (KEY=VALUE) and tests all
produce the same shape, so every rule lives here exactly once. Nothing in this module touches
disk; service.py owns loading and saving.
"""
import re
from dataclasses import dataclass, field

from . import registry
from .errors import Fail
from .presets import (ACCEL, BEHAVIOUR_TYPE, DEPOSITION_KEY_RE, FIRST_CUSTOM_SLOT, LIMITS, MATERIAL_COMMON,
                      MATERIAL_FIELDS, MAT_RE, MAX_CHECKLIST_ITEMS, MAX_CHECKLIST_LEN, MAX_NOTES_LEN, MAX_OUTPUTS,
                      NAME_RE, PASSIVE_PRESET, PIN_RE, POWER_PRESETS, SAFE_TEXT, SAFE_TEXT_HELP,
                      SHARED_CHANNELS)


@dataclass
class Context:
    """Everything validation needs to know about the machine, gathered once per request."""
    builtin_map: dict        # {slot: name}
    builtin_tools: dict      # {name: tool dict}
    claimed: dict            # {PIN: 'file [section]'} from the Klipper config
    outs: dict               # {output_pin name: {'pwm': bool, 'value': float, ...}} incl. registry-owned
    reg: dict                # the registry being edited
    umbilical: list          # pins wired to the tool connector
    resolve: object = None   # alias resolver (ConfigTree.resolve)
    warnings: list = field(default_factory=list)
    macro_names: set = field(default_factory=set)        # every [gcode_macro] name in the config (UPPER)
    object_names: dict = field(default_factory=dict)     # {lower name: 'file [section]'} for named objects
    heaters: list = field(default_factory=list)          # extruder, heater_bed, heater_generic names
    umbilical_info: dict = field(default_factory=dict)   # {pin: {"type", "label"}}
    kinds: dict = field(default_factory=dict)            # {kind id: kind dict} from lists.py (Admin screen)
    contacts: list = field(default_factory=list)         # the 21-pin connector (ConfigTree.contacts)

    @property
    def all_tools(self):
        return {**self.builtin_tools, **self.reg["tools"]}

    def used_slots(self):
        return {int(k) for k in self.builtin_map} | {int(t["slot"]) for t in self.reg["tools"].values()}


# ----------------------------------------------------------------------------- primitives
def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def num(f, key, lo, hi, default=None, integer=False, label=None):
    label = label or key
    v = f.get(key)
    if _blank(v):
        if default is None:
            raise Fail(f"{label} is required")
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Fail(f"{label} {v!r} is not a number")
    if x != x or x in (float("inf"), float("-inf")) or not (lo <= x <= hi):
        raise Fail(f"{label} {x:g} is out of range {lo:g} to {hi:g}")
    return int(round(x)) if integer else x


def text(s, label, maxlen=None):
    s = (s or "").strip()
    if maxlen and len(s) > maxlen:
        raise Fail(f"{label} is too long (max {maxlen} characters)")
    if not SAFE_TEXT.match(s):
        raise Fail(f"{label} may only contain {SAFE_TEXT_HELP}")
    return s


def checklist(value):
    items = value.splitlines() if isinstance(value, str) else list(value or [])
    items = [text(i, "checklist item", MAX_CHECKLIST_LEN) for i in items if str(i).strip()]
    if len(items) > MAX_CHECKLIST_ITEMS:
        raise Fail(f"at most {MAX_CHECKLIST_ITEMS} checklist items")
    return items


def notes(value):
    """Portal-only free text. Stored in the JSON but never written into the Klipper config."""
    s = (value or "").strip()
    if len(s) > MAX_NOTES_LEN:
        raise Fail(f"notes are too long (max {MAX_NOTES_LEN} characters)")
    return s


# ----------------------------------------------------------------------------- pins
def free_pins(ctx, exclude_tool=None):
    """Umbilical pins nobody has: not in the Klipper config and not created by another tool."""
    taken = registry.pins_in_use({"tools": {n: t for n, t in ctx.reg["tools"].items() if n != exclude_tool}})
    return [p for p in ctx.umbilical if p not in ctx.claimed and p not in taken]


def board_pin(ctx, raw, label, exclude_tool=None):
    pin = ctx.resolve(raw) if ctx.resolve else str(raw).strip().upper()
    if not pin or not PIN_RE.match(pin):
        raise Fail(f"{label} {raw!r} is not a board pin name like PB1")
    if pin not in ctx.umbilical:
        raise Fail(f"{pin} is not wired to the tool connector. Pins you can use: "
                   f"{', '.join(free_pins(ctx, exclude_tool)) or 'none free'}")
    if pin in ctx.claimed:
        raise Fail(f"{pin} is already used by {ctx.claimed[pin]}. Free pins: "
                   f"{', '.join(free_pins(ctx, exclude_tool)) or 'none'}")
    other = registry.pins_in_use({"tools": {n: t for n, t in ctx.reg["tools"].items() if n != exclude_tool}})
    if pin in other:
        raise Fail(f"{pin} is already used by toolhead {other[pin]}")
    return pin


def board_pin_any(ctx, raw, label, exclude_hw=None):
    """A board pin for system hardware: any pin nothing uses that is NOT wired to the tool connector."""
    pin = ctx.resolve(raw) if ctx.resolve else str(raw).strip().upper()
    if not pin or not PIN_RE.match(pin):
        raise Fail(f"{label} {raw!r} is not a board pin name like PD15")
    if pin in ctx.umbilical or any(c["pin"] == pin for c in ctx.contacts):
        raise Fail(f"{pin} is wired to the tool connector - system hardware needs a board pin that is not "
                   f"on the umbilical (tool outputs are added with the tool)")
    if pin in ctx.claimed:
        raise Fail(f"{pin} is already used by {ctx.claimed[pin]}")
    reg = {"tools": ctx.reg["tools"], "hardware": {n: h for n, h in ctx.reg.get("hardware", {}).items() if n != exclude_hw}}
    other = registry.pins_in_use(reg)
    if pin in other:
        raise Fail(f"{pin} is already used by {other[pin]}")
    return pin


def existing_output(ctx, name, label, pwm_needed):
    if name not in ctx.outs:
        raise Fail(f"{label} {name!r} is not an [output_pin] in the config. Available: {', '.join(sorted(ctx.outs)) or 'none'}")
    if pwm_needed and not ctx.outs[name]["pwm"]:
        raise Fail(f"{label} {name} is not a PWM output")
    return name


# ----------------------------------------------------------------------------- materials
def material_defaults(ttype, base):
    m = dict(MATERIAL_COMMON)
    m["accel"] = ACCEL[ttype]
    m.update(base)
    return m


def apply_material_fields(entry, ttype, f, label):
    """Update known numeric fields of a material from `f`; returns the names changed."""
    allowed = MATERIAL_FIELDS[ttype]
    changed = []
    for key, (lo, hi) in allowed.items():
        if not _blank(f.get(key)):
            entry[key] = num(f, key, lo, hi, label=f"{label} {key}")
            changed.append(key)
    return changed


def build_materials(ttype, specs, preset_materials):
    """`specs`: optional list of {name, power, feed_rate, z_offset...}; else the kind's preset."""
    out = {}
    for s in (specs or []):
        name = (s.get("name") or "").strip()
        if not name:
            continue
        if not MAT_RE.match(name):
            raise Fail(f"material name {name!r} must be letters, digits or _ (max 32)")
        if name in out:
            raise Fail(f"material {name} is listed twice")
        base = preset_materials.get("DEFAULT") or next(iter(preset_materials.values()))
        entry = material_defaults(ttype, base)
        apply_material_fields(entry, ttype, s, f"material {name}")
        out[name] = entry
    if not out:
        out = {m: material_defaults(ttype, v) for m, v in preset_materials.items()}
    return out


# ----------------------------------------------------------------------------- build
def build_tool(ctx, f):
    """Validate form `f` and return (name, tool). Raises Fail with a message for the person typing."""
    name = (f.get("name") or "").strip()
    if not NAME_RE.match(name):
        raise Fail("Name must start with a letter, use only letters, digits and _, and be 2 to 24 characters")
    if name.lower() in {n.lower() for n in ctx.all_tools}:
        raise Fail(f"A toolhead named {name} already exists")
    kind = (f.get("kind") or "").strip().upper()
    if kind not in ctx.kinds:
        raise Fail(f"Kind must be one of {', '.join(sorted(ctx.kinds))}")
    kdef = ctx.kinds[kind]
    ttype = BEHAVIOUR_TYPE[kdef["behaviour"]]
    used = ctx.used_slots()
    slot = num(f, "slot", FIRST_CUSTOM_SLOT, 99, default=max(used | {FIRST_CUSTOM_SLOT - 1}) + 1,
               integer=True, label="Slot")
    if slot in used:
        raise Fail(f"Slot {slot} is already used")
    tool = {"slot": slot, "type": ttype, "kind": kind, "category": kdef["category"], "extruder_count": 0,
            "notes": notes(f.get("notes")), "images": []}

    if ttype == "POWERED":
        if f.get("outputs") is not None:
            f = {**f, **outputs_to_fields(ctx, name, f["outputs"])}
        _build_powered(ctx, name, kdef, f, tool)
    elif ttype == "PASSIVE":
        tool["materials"] = build_materials("PASSIVE", f.get("materials"), kdef.get("materials") or PASSIVE_PRESET["materials"])
        tool["checklist"] = checklist(f["checklist"]) if "checklist" in f else list(kdef.get("checklist", PASSIVE_PRESET["checklist"]))
    else:
        _build_print_head(ctx, f, tool)
    tool["contacts"] = tool_contacts(ctx, tool, f.get("contacts"))
    return name, tool


# ----------------------------------------------------------------------------- outputs + contacts
def contact_of_pin(ctx, pin):
    return next((c["contact"] for c in ctx.contacts if pin and c["pin"] == pin), None)


def contact_of_output(ctx, out):
    pin = (ctx.outs.get(out) or {}).get("pin")
    return contact_of_pin(ctx, pin)


def outputs_to_fields(ctx, name, rows):
    """The wizard's output rows -> the fields _build_powered understands.

    rows: [{"role": "power"|"switch", "source": "contact:16" | "pin:PB1" | "output:SPINDLE_SPEED"}]
    Exactly one power row (the PWM level M3 S sets); any number of switch rows (on/off outputs switched
    on with the tool and off with it). The first switch row is the tool's enable line."""
    rows = [r for r in (rows or []) if r.get("source")]
    if len(rows) > MAX_OUTPUTS:
        raise Fail(f"At most {MAX_OUTPUTS} outputs per tool")
    power = [r for r in rows if r.get("role") == "power"]
    switches = [r for r in rows if r.get("role") == "switch"]
    if len(power) != 1:
        raise Fail("Choose exactly one main power output (the PWM level that M3 S sets)")
    if len(power) + len(switches) != len(rows):
        raise Fail("Each output needs a job: main power or switch with the tool")
    seen = set()

    def resolve(r):
        kind, _, ref = str(r["source"]).partition(":")
        if kind == "contact":
            try:
                n = int(ref)
            except ValueError:
                raise Fail(f"Contact {ref!r} is not a number")
            c = next((x for x in ctx.contacts if x["contact"] == n), None)
            if c is None:
                raise Fail(f"The tool connector has no contact {n}")
            if c["output"]:
                kind, ref = "output", c["output"]
            elif c["pin"] and c["pin"] in ctx.umbilical:
                kind, ref = "pin", c["pin"]
            else:
                raise Fail(f"Contact {n}{' (' + c['pin'] + ')' if c['pin'] else ''} is not driven by an output in the "
                           f"Klipper config, so a tool cannot switch it. Pick another contact or a free pin.")
        if kind not in ("pin", "output") or not ref:
            raise Fail("Choose where each output comes from")
        if ref in seen:
            raise Fail(f"{ref} is chosen twice")
        seen.add(ref)
        return kind, ref

    out = {"_output_rows": []}
    kind, ref = resolve(power[0])
    if kind == "pin":
        out["new_pin"] = ref
    else:
        out["power_pin"] = ref
    out["_output_rows"].append(("power", kind, ref))
    extra = []
    for i, r in enumerate(switches):
        kind, ref = resolve(r)
        out["_output_rows"].append(("switch", kind, ref))
        if i == 0:
            out["new_enable_pin" if kind == "pin" else "enable_pin"] = ref
        else:
            extra.append((kind, ref))
    out["_extra_switches"] = extra
    return out


def tool_contacts(ctx, tool, ticked):
    """Contacts of the 21-pin connector the tool uses: the ones its outputs and controls drive, plus the
    ones the person ticked (returns, supplies, sensor lines, stepper). Used for the pin map only."""
    used = set()
    for raw in (ticked or []):
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise Fail(f"Contact {raw!r} is not a number")
        if not any(c["contact"] == n for c in ctx.contacts):
            raise Fail(f"The tool connector has no contact {n}")
        used.add(n)
    for o in tool.get("outputs", []):
        if o.get("contact"):
            used.add(o["contact"])
    for p in [tool.get("new_pin"), tool.get("new_enable_pin")] + list(tool.get("new_switch_pins", {}).values()):
        c = contact_of_pin(ctx, p)
        if c:
            used.add(c)
    for c in tool.get("controls", []):
        n = contact_of_pin(ctx, c.get("pin"))
        if n:
            used.add(n)
    return sorted(used)


def _build_powered(ctx, name, kdef, f, tool):
    pre = {"cap": kdef.get("cap", 1.0), "max_on_s": kdef.get("max_on_s", 300),
           "materials": kdef.get("materials") or POWER_PRESETS["POWERED"]["materials"],
           "checklist": kdef.get("checklist", [])}
    if not _blank(f.get("new_pin")):
        pin = board_pin(ctx, f["new_pin"], "Power pin")
        out = f"{name}_PWR"
        if out in ctx.outs:
            raise Fail(f"An output named {out} already exists")
        tool.update(power_pin=out, new_pin=pin, owns_power_pin=True,
                    new_pin_cycle=num(f, "cycle", *LIMITS["cycle"], default=0.01, label="PWM cycle time"))
        idle_default = 0.0
    elif not _blank(f.get("power_pin")):
        out = existing_output(ctx, f["power_pin"], "Power channel", pwm_needed=True)
        tool.update(power_pin=out, owns_power_pin=False)
        idle_default = float(ctx.outs[out].get("value") or 0.0)  # e.g. SPINDLE_SPEED idles at 0.3, not 0
        if out in SHARED_CHANNELS:
            ctx.warnings.append(f"{out} is also used by: {SHARED_CHANNELS[out]}. Only one of those tools is "
                                f"mounted at a time, but wire the tool to match.")
    else:
        raise Fail("Choose a power output: either a new pin or an existing PWM output")

    tool["enable_pin"], tool["owns_enable_pin"] = "", False
    if not _blank(f.get("new_enable_pin")):
        pin = board_pin(ctx, f["new_enable_pin"], "Enable pin", None)
        if pin == tool.get("new_pin"):
            raise Fail("The enable pin and the power pin must be different")
        out = f"{name}_EN"
        if out in ctx.outs:
            raise Fail(f"An output named {out} already exists")
        tool.update(enable_pin=out, new_enable_pin=pin, owns_enable_pin=True)
    elif not _blank(f.get("enable_pin")):
        en = existing_output(ctx, f["enable_pin"], "Enable channel", pwm_needed=False)
        if en == tool["power_pin"]:
            raise Fail("The enable output and the power output must be different")
        tool["enable_pin"] = en
        if en in SHARED_CHANNELS:
            ctx.warnings.append(f"{en} is also used by: {SHARED_CHANNELS[en]}.")

    # more on/off outputs that follow the tool (rows 2.. of the wizard's switch outputs)
    tool["also_on"], tool["also_on_owned"], tool["new_switch_pins"] = [], [], {}
    taken_pins = {p for p in (tool.get("new_pin"), tool.get("new_enable_pin")) if p}
    for i, (kind, ref) in enumerate(f.get("_extra_switches") or []):
        if kind == "pin":
            pin = board_pin(ctx, ref, "Switch output pin")
            if pin in taken_pins:
                raise Fail(f"{pin} is chosen twice")
            taken_pins.add(pin)
            out = f"{name}_EN{i + 2}"
            if out in ctx.outs:
                raise Fail(f"An output named {out} already exists")
            tool["new_switch_pins"][out] = pin
            tool["also_on_owned"].append(out)
        else:
            out = existing_output(ctx, ref, "Switch output", pwm_needed=False)
            if out in (tool["power_pin"], tool["enable_pin"]):
                raise Fail(f"{out} is chosen twice")
            if out in SHARED_CHANNELS:
                ctx.warnings.append(f"{out} is also used by: {SHARED_CHANNELS[out]}.")
        tool["also_on"].append(out)
    rows = []
    for role, kind, ref in f.get("_output_rows") or []:
        if role == "power":
            o = tool["power_pin"]
        elif kind == "pin":
            o = next((n for n, p in [(tool.get("enable_pin"), tool.get("new_enable_pin"))] + list(tool["new_switch_pins"].items()) if p == ref), ref)
        else:
            o = ref
        pin = ref if kind == "pin" else (ctx.outs.get(ref) or {}).get("pin", "")
        rows.append({"role": role, "output": o, "pin": pin, "new": kind == "pin", "contact": contact_of_pin(ctx, pin)})
    if not rows:                                       # added the old way (CLI / API fields)
        rows.append({"role": "power", "output": tool["power_pin"], "new": bool(tool.get("new_pin")),
                     "pin": tool.get("new_pin") or (ctx.outs.get(tool["power_pin"]) or {}).get("pin", "")})
        if tool["enable_pin"]:
            rows.append({"role": "switch", "output": tool["enable_pin"], "new": bool(tool.get("new_enable_pin")),
                         "pin": tool.get("new_enable_pin") or (ctx.outs.get(tool["enable_pin"]) or {}).get("pin", "")})
        for r in rows:
            r["contact"] = contact_of_pin(ctx, r["pin"])
    tool["outputs"] = rows

    tool["power_idle"] = num(f, "idle", *LIMITS["idle"], default=idle_default, label="Idle level")
    tool["power_min"] = num(f, "min", *LIMITS["min"], default=0.0, label="Minimum power")
    tool["power_cap"] = num(f, "cap", *LIMITS["cap"], default=pre["cap"], label="Power cap")
    if tool["power_min"] > tool["power_cap"]:
        raise Fail("Minimum power must not exceed the power cap")
    tool["s_max"] = num(f, "s_max", *LIMITS["s_max"], default=1000, integer=True, label="S max")
    tool["max_on_s"] = num(f, "max_on_s", *LIMITS["max_on_s"], default=pre["max_on_s"], integer=True,
                           label="Maximum on-time (s)")
    tool["default_power"] = 1.0
    tool["materials"] = build_materials("POWERED", f.get("materials"), pre["materials"])
    tool["checklist"] = checklist(f["checklist"]) if "checklist" in f else list(pre["checklist"])


def _build_print_head(ctx, f, tool):
    base_name = (f.get("base") or "").strip()
    base = ctx.all_tools.get(base_name)
    if not base or base.get("type") != "DEPOSITION":
        raise Fail(f"Base {base_name!r} must be an existing 3D-print toolhead")
    raw = f.get("nozzles") or "0.4"
    sizes = raw if isinstance(raw, list) else [s for s in str(raw).split(",") if s.strip()]
    if not sizes:
        raise Fail("Give at least one nozzle size")
    mats = {}
    for s in sizes:
        try:
            size = float(s)
        except (TypeError, ValueError):
            raise Fail(f"Nozzle size {s!r} is not a number")
        if not (LIMITS["nozzle"][0] <= size <= LIMITS["nozzle"][1]):
            raise Fail(f"Nozzle size {size:g} is out of range {LIMITS['nozzle'][0]:g} to {LIMITS['nozzle'][1]:g}")
        suffix = str(size).replace(".", "_")
        have = {k: v for k, v in base["materials"].items() if abs(float(v.get("nozzle_size", 0)) - size) < 1e-9}
        if not have:  # derive from the base's smallest nozzle, rewriting the size in each key
            smallest = min(float(v.get("nozzle_size", 99)) for v in base["materials"].values())
            old = str(smallest).replace(".", "_")
            for k, v in base["materials"].items():
                if abs(float(v.get("nozzle_size", 0)) - smallest) < 1e-9:
                    nv = dict(v)
                    nv["nozzle_size"] = size
                    have[re.sub(r"_" + re.escape(old) + r"(?=(_T\d)?$)", "_" + suffix, k)] = nv
        mats.update({k: dict(v) for k, v in have.items()})
    bad = [k for k in mats if not DEPOSITION_KEY_RE.match(k)]
    if bad:
        raise Fail(f"Could not derive material names from {base_name} ({bad[0]})")
    tool.update(extruder_count=int(base.get("extruder_count", 1)), base=base_name, materials=mats)


# ----------------------------------------------------------------------------- edit
POWER_FIELDS = (("cap", "power_cap", "cap", False), ("min", "power_min", "min", False),
                ("idle", "power_idle", "idle", False), ("max_on_s", "max_on_s", "max_on_s", True),
                ("s_max", "s_max", "s_max", True), ("default_power", "default_power", "power", False))


def apply_edit(ctx, name, f):
    """Edit tool `name` in ctx.reg in place from the fields present in `f`. Returns a list of changes."""
    t = ctx.reg["tools"].get(name)
    if t is None:
        raise Fail(f"{name!r} is not a user-added toolhead (built-in tools are edited in variables.cfg)")
    changes = []

    if "notes" in f:
        t["notes"] = notes(f["notes"]); changes.append("notes")
    if "checklist" in f and t["type"] != "DEPOSITION":
        t["checklist"] = checklist(f["checklist"]); changes.append("checklist")

    power_keys = [k for k, *_ in POWER_FIELDS if not _blank(f.get(k))]
    if power_keys and t["type"] != "POWERED":
        raise Fail(f"{name} is a {t['type'].lower()} tool - power settings do not apply")
    if t["type"] == "POWERED":
        for key, dest, lim, integer in POWER_FIELDS:
            if not _blank(f.get(key)):
                t[dest] = num(f, key, *LIMITS[lim], integer=integer, label=key)
                changes.append(dest)
        if t["power_min"] > t["power_cap"]:
            raise Fail("Minimum power must not exceed the power cap")
        if t.get("owns_power_pin") and not _blank(f.get("new_pin")):
            t["new_pin"] = board_pin(ctx, f["new_pin"], "Power pin", exclude_tool=name); changes.append("new_pin")
        if t.get("owns_power_pin") and not _blank(f.get("cycle")):
            t["new_pin_cycle"] = num(f, "cycle", *LIMITS["cycle"], label="PWM cycle time"); changes.append("cycle")

    specs = list(f.get("materials") or [])
    if (f.get("material") or "").strip():          # CLI form: one material per call
        specs.append({**f, "name": f["material"]})
    for spec in specs:
        changes += _edit_material(t, name, spec)
    for d in list(f.get("delete_materials") or []) + ([f["del_material"]] if not _blank(f.get("del_material")) else []):
        if d not in t["materials"] or len(t["materials"]) <= 1:
            raise Fail(f"Cannot delete material {d}: not found, or it is the only one")
        del t["materials"][d]
        changes.append(f"material {d} deleted")
    return changes


def _edit_material(t, tool_name, spec):
    mat = (spec.get("name") or "").strip()
    if not MAT_RE.match(mat):
        raise Fail("Material name must be letters, digits or _ (max 32)")
    changes = []
    if mat not in t["materials"]:
        if t["type"] == "DEPOSITION":
            raise Fail(f"{mat} is not one of {tool_name}'s materials. Print-head materials come from the base "
                       f"tool; edit their values here, or re-create the tool with another nozzle size.")
        preset = POWER_PRESETS["POWERED"] if t["type"] == "POWERED" else PASSIVE_PRESET
        t["materials"][mat] = material_defaults(t["type"], preset["materials"].get("DEFAULT") or {})
        changes.append(f"material {mat} added")
    done = apply_material_fields(t["materials"][mat], t["type"], spec, f"material {mat}")
    return changes + [f"{mat}.{k}" for k in done]
