"""The one API both front ends (command line and web portal) call.

Every mutating method works on a copy of the registry, validates the result against the live
Klipper config, then saves JSON + generated .cfg together. If anything raises, nothing on disk
changed. Methods return plain dicts so they serialise straight to JSON for the portal.
"""
import copy
import os
import re
import shutil

from . import builders, extras, hw_boards, hw_catalog, hw_devices, lists, pin_labels, registry, sections, tooldocs
from .errors import Fail
from .klipper_cfg import ConfigTree
from .paths import Paths
from .klipper_cfg import PIN_TYPES
from .presets import (BEHAVIOUR_TYPE, BEHAVIOURS, BOARD_HEADERS, BUILTIN_CATEGORY, BUILTIN_CONTACTS, CATEGORIES, CATEGORY_BEHAVIOURS,
                      CATEGORY_HELP, CONTROL_LIMITS, CONTROL_ROLES, FIRST_CUSTOM_SLOT, INPUT_ACTIONS, LIMITS, MAX_HARDWARE,
                      NAME_RE, OUTPUT_ROLES, SHARED_CHANNELS)

MAX_IMAGES = 6
RESTART_NOTE = "Klipper must be restarted to load the change."


def capabilities(t):
    """Short badges describing what a tool can do (shown on library cards)."""
    ty = t.get("type")
    if ty == "POWERED":
        n = (1 if t.get("enable_pin") else 0) + len(t.get("also_on", []))
        return ["PWM power"] + ([f"{n} switch output{'s' if n > 1 else ''}"] if n else [])
    return {"DEPOSITION": [f"Extruder x{t.get('extruder_count', 1)}"], "LASER": ["PWM laser"],
            "CNC": ["Spindle (ESC)"], "DRAG_KNIFE": ["Passive"], "PASSIVE": ["Passive"]}.get(ty, [])


class ToolService:
    def __init__(self, paths: Paths):
        self.paths = paths

    # ---------------------------------------------------------------- context
    def _ctx(self, reg=None):
        reg = reg if reg is not None else registry.load(self.paths)
        # the Rhino pin labels are in the generated file the tree skips: Klipper sees them, so the tree must too
        tree = ConfigTree(self.paths, extra_aliases=reg.get("labels", {}), extra_boards=reg.get("boards", {}))
        bmap, btools = tree.builtin_tools()
        outs = dict(tree.output_pins)
        for n, o in registry.owned_outputs(reg).items():
            outs[n] = {"pwm": o["pwm"], "value": 0.0, "pin": "", "file": "myrhino/custom_tools.cfg"}
        for n, hw in reg.get("hardware", {}).items():          # system hardware a tool can switch on with it
            if hw["role"] in ("switch", "level"):
                outs[n] = {"pwm": hw["role"] == "level", "value": 0.0, "pin": hw["pin"], "file": "myrhino/custom_tools.cfg",
                           "hardware": True}
        info = tree.umbilical_info()
        lst = lists.load(self.paths)
        return builders.Context(builtin_map=bmap, builtin_tools=btools, claimed=tree.claimed_pins, outs=outs,
                                reg=reg, umbilical=list(info), resolve=tree.resolve, macro_names=tree.macro_names,
                                object_names=tree.object_names, heaters=tree.heaters, umbilical_info=info,
                                kinds=lists.kinds_by_id(lst), contacts=tree.contacts(), boards=tree.boards), tree

    # ---------------------------------------------------------------- mutations
    def add(self, fields, dry_run=False):
        ctx, _ = self._ctx()
        name, tool = builders.build_tool(ctx, fields)
        ctx.warnings += extras.apply(ctx, name, tool, fields.get("macros") or [], fields.get("controls") or [])
        tool["contacts"] = builders.tool_contacts(ctx, tool, fields.get("contacts"))
        ctx.reg["tools"][name] = tool
        self._audit(ctx)
        if not dry_run:
            registry.save(self.paths, ctx.reg)
        return {"ok": True, "name": name, "slot": tool["slot"], "type": tool["type"], "warnings": ctx.warnings,
                "dry_run": dry_run, "restart_needed": not dry_run}

    def edit(self, name, fields):
        ctx, _ = self._ctx(copy.deepcopy(registry.load(self.paths)))
        before_cfg = registry.render_cfg(registry.load(self.paths))
        changes = builders.apply_edit(ctx, name, fields)
        t = ctx.reg["tools"][name]
        if "controls" in fields or "macros" in fields:
            before = (copy.deepcopy(t.get("controls", [])), copy.deepcopy(t.get("macros", [])))
            ctx.warnings += extras.apply(ctx, name, t, fields.get("macros"), fields.get("controls"))
            if t.get("controls", []) != before[0]:
                changes.append("controls")
            if t.get("macros", []) != before[1]:
                changes.append("macros")
        if "contacts" in fields:
            new = builders.tool_contacts(ctx, t, fields.get("contacts"))
            if new != t.get("contacts"):
                t["contacts"] = new
                changes.append("connector contacts")
        elif "controls" in fields:
            t["contacts"] = builders.tool_contacts(ctx, t, t.get("contacts"))
        if not changes:
            raise Fail("Nothing to change - no recognised field was given")
        self._audit(ctx)
        registry.save(self.paths, ctx.reg)
        # notes, photos and the pin map are portal-only: Klipper only needs a restart if its file changed
        return {"ok": True, "name": name, "changes": changes, "warnings": ctx.warnings,
                "restart_needed": registry.render_cfg(ctx.reg) != before_cfg}

    def rename(self, name, new_name):
        ctx, _ = self._ctx()
        if name not in ctx.reg["tools"]:
            raise Fail(f"{name!r} is not a user-added toolhead")
        if not NAME_RE.match(new_name or ""):
            raise Fail("Name must start with a letter, use only letters, digits and _, and be 2 to 24 characters")
        if new_name.lower() in {n.lower() for n in ctx.all_tools if n != name}:
            raise Fail(f"A toolhead named {new_name} already exists")
        ctx.reg["tools"] = {(new_name if n == name else n): t for n, t in ctx.reg["tools"].items()}
        registry.save(self.paths, ctx.reg)
        # variables.save may still say set_material_toolhead=<old name>; the restore prompt and
        # SET_TOOLHEAD fail safe (unknown tool) until a material is chosen again.
        return {"ok": True, "name": new_name, "restart_needed": True,
                "warnings": ["If this tool was the selected toolhead, choose its material again after the restart."]}

    def remove(self, name):
        ctx, _ = self._ctx()
        t = ctx.reg["tools"].get(name)
        if t is None:
            raise Fail(f"{name!r} is not a user-added toolhead")
        mine = {p for p in (t["power_pin"] if t.get("owns_power_pin") else "",
                            t["enable_pin"] if t.get("owns_enable_pin") else "") if p}
        mine |= set(t.get("new_switch_pins", {}))
        mine |= {c["name"] for c in t.get("controls", []) if c["role"] in ("switch", "level")}
        users = sorted(n for n, o in ctx.reg["tools"].items()
                       if n != name and (o.get("power_pin") in mine or o.get("enable_pin") in mine
                                         or mine & set(o.get("also_on", []))))
        if users:
            raise Fail(f"Cannot remove {name}: {', '.join(users)} use its output pin. Remove or re-wire those first.")
        del ctx.reg["tools"][name]
        registry.save(self.paths, ctx.reg)
        return {"ok": True, "name": name, "restart_needed": True,
                "images": [i for i in t.get("images", [])]}

    def check(self):
        """Re-validate everything and regenerate custom_tools.cfg (after hand edits or config changes)."""
        ctx, _ = self._ctx()
        self._audit(ctx)
        registry.save(self.paths, ctx.reg)
        return {"ok": True, "tools": len(ctx.reg["tools"]), "missing_includes": self._tree_missing()}

    def set_images(self, name, images):
        ctx, _ = self._ctx()
        t = ctx.reg["tools"].get(name)
        if t is None:
            raise Fail(f"{name!r} is not a user-added toolhead")
        if len(images) > MAX_IMAGES:
            raise Fail(f"At most {MAX_IMAGES} photos per tool")
        t["images"] = list(images)
        registry.save(self.paths, ctx.reg)   # JSON only changes; generated cfg is identical, no restart needed
        return {"ok": True, "name": name, "images": t["images"], "restart_needed": False}

    # ---------------------------------------------------------------- audit
    def _audit(self, ctx):
        """Fail unless the whole registry is consistent with the live Klipper config."""
        hw_devices.refresh_scope_slots(ctx)
        problems, slots, pins = [], {}, {}
        builtin_lower = {n.lower() for n in ctx.builtin_tools}
        for n, t in ctx.reg["tools"].items():
            if not NAME_RE.match(n) or n.lower() in builtin_lower:
                problems.append(f"{n}: bad name or collides with a built-in tool")
            s = int(t["slot"])
            if s in ctx.builtin_map or s in slots or s < FIRST_CUSTOM_SLOT:
                problems.append(f"{n}: slot {s} is not available")
            slots[s] = n
            for c in t.get("controls", []):
                p = c["pin"]
                if p in ctx.claimed:
                    problems.append(f"{n}: control {c['name']} pin {p} is now used by {ctx.claimed[p]}")
                elif p not in ctx.umbilical:
                    problems.append(f"{n}: control {c['name']} pin {p} is not on the tool connector")
                elif p in pins:
                    problems.append(f"{n}: control {c['name']} pin {p} is also used by {pins[p]}")
                pins[p] = f"{n} ({c['name']})"
                if c["role"] == "heater_fan" and c.get("heater") not in ctx.heaters:
                    problems.append(f"{n}: control {c['name']} follows heater {c.get('heater')}, which no longer exists")
            if t["type"] != "POWERED":
                continue
            for key, p in [("new_pin", t.get("new_pin")), ("new_enable_pin", t.get("new_enable_pin"))] + \
                    [(o, p) for o, p in t.get("new_switch_pins", {}).items()]:
                if not p:
                    continue
                if p in ctx.claimed:
                    problems.append(f"{n}: pin {p} is now used by {ctx.claimed[p]}")
                elif p not in ctx.umbilical:
                    problems.append(f"{n}: pin {p} is not on the tool connector")
                elif p in pins:
                    problems.append(f"{n}: pin {p} is also used by {pins[p]}")
                pins[p] = n
            for key, owns in (("power_pin", "owns_power_pin"), ("enable_pin", "owns_enable_pin")):
                if t.get(key) and not t.get(owns) and t[key] not in ctx.outs:
                    problems.append(f"{n}: output {t[key]} no longer exists in the config")
            for o in t.get("also_on", []):
                if o not in t.get("new_switch_pins", {}) and o not in ctx.outs:
                    problems.append(f"{n}: output {o} no longer exists in the config")
            if t["power_min"] > t["power_cap"]:
                problems.append(f"{n}: minimum power exceeds the cap")
        for n, hw in ctx.reg.get("hardware", {}).items():
            p = hw["pin"]
            if p in ctx.claimed:
                problems.append(f"system hardware {n}: pin {p} is now used by {ctx.claimed[p]}")
            elif p in ctx.umbilical:
                problems.append(f"system hardware {n}: pin {p} is now listed as a tool-connector pin")
            elif p in pins:
                problems.append(f"system hardware {n}: pin {p} is also used by {pins[p]}")
            pins[p] = f"system hardware {n}"
            if n.lower() in builtin_lower or n in {c["name"] for t in ctx.reg["tools"].values() for c in t.get("controls", [])}:
                problems.append(f"system hardware {n}: the name is also used by a tool")
            if hw["role"] == "heater_fan" and hw.get("heater") not in ctx.heaters:
                problems.append(f"system hardware {n} follows heater {hw.get('heater')}, which no longer exists")
        if problems:
            raise Fail("; ".join(problems))

    def _tree_missing(self):
        return ConfigTree(self.paths).missing_includes

    # ---------------------------------------------------------------- reads
    def list_tools(self):
        ctx, _ = self._ctx()
        out = []
        for slot, name in sorted(ctx.builtin_map.items()):
            t = ctx.builtin_tools.get(name, {})
            out.append(self._summary(ctx, name, t, slot, builtin=True))
        for name, t in registry.by_slot(ctx.reg):
            out.append(self._summary(ctx, name, t, int(t["slot"]), builtin=False))
        return out

    @staticmethod
    def _summary(ctx, name, t, slot, builtin):
        k = ctx.kinds.get(t.get("kind", ""))
        cat = t.get("category") or (k or {}).get("category") or BUILTIN_CATEGORY.get(t.get("type", ""), "")
        return {"name": name, "slot": slot, "builtin": builtin, "type": t.get("type", "?"),
                "kind": k["label"] if k else {"DEPOSITION": "3D printing", "LASER": "Laser engraving and cutting",
                                              "CNC": "CNC milling", "DRAG_KNIFE": "Drag-knife cutting"}.get(t.get("type"), t.get("type", "")),
                "kind_code": t.get("kind", ""), "category": cat, "category_label": CATEGORIES.get(cat, ""),
                "contacts": list(t.get("contacts", BUILTIN_CONTACTS.get(name, []) if builtin else [])), "outputs": list(t.get("outputs", [])),
                "capabilities": capabilities(t),
                "materials": sorted(t.get("materials", {})), "notes": t.get("notes", ""),
                "images": list(t.get("images", [])), "power_pin": t.get("power_pin", ""),
                "image": (f"/static/img/tools/{tooldocs.BUILTIN_DOCS[name]['image']}-light.png" if builtin and name in tooldocs.BUILTIN_DOCS
                          else f"/media/{name}/{t['images'][0]}" if t.get("images") else ""),
                "image_dark": (f"/static/img/tools/{tooldocs.BUILTIN_DOCS[name]['image']}-dark.png" if builtin and name in tooldocs.BUILTIN_DOCS
                               else ""),
                "function": (tooldocs.BUILTIN_DOCS.get(name, {}).get("function", "") if builtin else ""),
                "enable_pin": t.get("enable_pin", ""),
                "pins": [p for p in (t.get("new_pin"), t.get("new_enable_pin")) if p] + list(t.get("new_switch_pins", {}).values())
                        + [c["pin"] for c in t.get("controls", [])],
                "controls": [{"name": c["name"], "role": c["role"]} for c in t.get("controls", [])],
                "macros": [m["name"] for m in t.get("macros", [])] +
                          [mn for c in t.get("controls", []) for mn, *_ in sections.control_macros(name, slot, c)]}

    def sheet(self, name):
        """Everything the portal's tool page shows: what the tool is, the connector contacts it uses and for
        what, its picture, its materials (with the settings that matter for its type) and its macros."""
        ctx, tree = self._ctx()
        slot_of = {n: s for s, n in ctx.builtin_map.items()}
        builtin = name in slot_of
        if builtin:
            t, slot = ctx.builtin_tools.get(name, {}), slot_of[name]
        elif name in ctx.reg["tools"]:
            t = ctx.reg["tools"][name]
            slot = int(t["slot"])
        else:
            raise Fail(f"No toolhead called {name!r}")
        summary = self._summary(ctx, name, t, slot, builtin)
        doc = tooldocs.BUILTIN_DOCS.get(name, {}) if builtin else {}
        descs = {}
        for _, cp in tree.files:
            for sec in cp.sections():
                if sec.startswith("gcode_macro ") and cp.has_option(sec, "description"):
                    descs[sec[len("gcode_macro "):].strip().upper()] = cp.get(sec, "description").strip()

        # contacts: built-in tools use the literature's per-tool wording, added tools say which output/control
        uses = dict(doc.get("pins", {}))
        if not builtin:
            for o in t.get("outputs", []):
                if o.get("contact"):
                    uses[o["contact"]] = f"{OUTPUT_ROLES.get(o.get('role'), 'Output')} ({o.get('output') or o.get('pin')})"
            for c in t.get("controls", []):
                cn = builders.contact_of_pin(ctx, c.get("pin"))
                if cn:
                    uses[cn] = f"Control: {c['name']}"
        used = set(summary["contacts"]) | set(uses)
        other_pins = []                                   # outputs/controls on board pins that are not connector contacts
        if not builtin:
            for o in t.get("outputs", []):
                if o.get("pin") and not o.get("contact"):
                    other_pins.append({"pin": o["pin"], "use": f"{OUTPUT_ROLES.get(o.get('role'), 'Output')} ({o.get('output') or o['pin']})"})
            for c in t.get("controls", []):
                if c.get("pin") and not builders.contact_of_pin(ctx, c.get("pin")):
                    other_pins.append({"pin": c["pin"], "use": f"Control: {c['name']}"})
        contacts = [{"contact": c["contact"], "pin": c["pin"], "label": c["label"], "kind": c["kind"],
                     "use": uses.get(c["contact"], c["label"] if c["contact"] in used else ""),
                     "used": c["contact"] in used} for c in ctx.contacts]

        # materials, with the columns that matter for this kind of tool
        ttype = t.get("type", "")
        cols = tooldocs.MATERIAL_COLUMNS.get(ttype, tooldocs.MATERIAL_COLUMNS["PASSIVE"])
        mats = []
        for key in sorted(t.get("materials", {})):
            m = t["materials"][key] or {}
            parts = key.split("_")
            label = key
            if ttype == "DEPOSITION" and len(parts) >= 3 and parts[1].isdigit():
                label = f"{parts[0]} \u00b7 {parts[1]}.{parts[2]} mm" + (f" \u00b7 {parts[3]}" if len(parts) > 3 else "")
            vals = []
            for f, _, unit in cols:
                v = m.get(f)
                if v is None or v == "":
                    vals.append("")
                elif f in tooldocs.PERCENT_FIELDS:
                    vals.append(f"{round(float(v) * 100)}")
                else:
                    vals.append(f"{v:g}" if isinstance(v, float) else str(v))
            mats.append({"key": key, "label": label, "values": vals})

        # macros: the built-in tool's own, or an added tool's macros and control macros
        macros = []
        if builtin:
            for mn in doc.get("macros", []):
                if mn.upper() in descs or mn.upper() in tree.macro_names or mn in tree.macro_names:
                    macros.append({"name": mn, "description": descs.get(mn.upper(), "")})
        else:
            macros.append({"name": "TOOL_JOB_SETUP", "description": descs.get("TOOL_JOB_SETUP", "Guided job set-up for added tools")})
            for m in t.get("macros", []):
                macros.append({"name": m["name"], "description": m.get("purpose", "")})
            for c in t.get("controls", []):
                for mn, pu, *_ in sections.control_macros(name, slot, c):
                    macros.append({"name": mn, "description": pu})

        image = summary["image"]
        return {"ok": True, **summary, "function": doc.get("function") or summary["kind"],
                "about": doc.get("about") or t.get("notes", ""), "setup": doc.get("setup") or "TOOL_JOB_SETUP FILE=<name>.gcode",
                "outputs_text": doc.get("outputs") or ", ".join(f"{o.get('output')}" for o in t.get("outputs", [])) or "None",
                "image": image, "image_notes": doc.get("image_notes", []),
                "photos": [f"/media/{name}/{f}" for f in t.get("images", [])],
                "contacts": contacts, "other_pins": other_pins, "material_columns": [{"field": f, "label": l, "unit": u} for f, l, u in cols],
                "material_rows": mats, "macro_list": macros}

    def get(self, name):
        ctx, _ = self._ctx()
        t = ctx.reg["tools"].get(name)
        if t is None:
            raise Fail(f"{name!r} is not a user-added toolhead")
        t = copy.deepcopy(t)
        t.setdefault("controls", [])
        t.setdefault("macros", [])
        return {"name": name, **t, "capabilities": capabilities(t),
                "control_macros": [{"name": mn, "purpose": pu, "control": c["name"]} for c in t["controls"]
                                   for mn, pu, *_ in sections.control_macros(name, t["slot"], c)],
                "limits": {k: list(v) for k, v in LIMITS.items()}}

    def preview(self, kind, body):
        """Preview one macro (kind='macro') or control (kind='control') for an existing tool
        (body.tool) or for the tool being created (body.draft: name, slot, new_pin, new_enable_pin,
        controls, macros). Nothing is saved."""
        if kind not in ("macro", "control"):
            raise Fail("unknown preview kind")
        ctx, _ = self._ctx()
        raw = body.get("item") or {}
        if body.get("tool"):
            name = body["tool"]
            if name not in ctx.reg["tools"]:
                raise Fail(f"{name!r} is not a user-added toolhead")
            tool = copy.deepcopy(ctx.reg["tools"][name])
            # unsaved controls/macros in the editor count (names, pins, generated macros)
            if isinstance(body.get("controls"), list):
                tool["controls"] = body["controls"]
            if isinstance(body.get("macros"), list):
                tool["macros"] = body["macros"]
        else:
            d = body.get("draft") or {}
            name = (d.get("name") or "").strip() or "NewTool"
            tool = {"slot": max(ctx.used_slots() | {FIRST_CUSTOM_SLOT - 1}) + 1,
                    "new_pin": d.get("new_pin") or "", "new_enable_pin": d.get("new_enable_pin") or "",
                    "controls": list(d.get("controls") or []), "macros": list(d.get("macros") or [])}
        tool.setdefault("controls", [])
        tool.setdefault("macros", [])
        return {"ok": True, **extras.preview(ctx, name, tool, kind, raw)}

    def pin_report(self):
        """The tool connector (all 21 contacts), the spare pins new tools can use, the output channels
        tools can share, and the system hardware on other board pins."""
        ctx, tree = self._ctx()
        mine = registry.pins_in_use(ctx.reg)
        pins = []
        for p in ctx.umbilical:
            if p in mine:
                pins.append({"pin": p, "state": "tool", "owner": mine[p]})
            elif p in ctx.claimed:
                pins.append({"pin": p, "state": "claimed", "owner": ctx.claimed[p]})
            else:
                pins.append({"pin": p, "state": "free", "owner": ""})
        users = {}                                        # contact -> tools that use it
        for name, t in list(ctx.builtin_tools.items()) + list(ctx.reg["tools"].items()):
            for n in t.get("contacts", BUILTIN_CONTACTS.get(name, [])):
                users.setdefault(n, []).append(name)
        contacts = []
        for c in ctx.contacts:
            row = dict(c, tools=users.get(c["contact"], []), owner=mine.get(c["pin"], "") if c["pin"] else "")
            if c["pin"] and not c["used_by"] and not row["owner"] and c["kind"] in ("switched", "signal"):
                row["warning"] = f"Nothing in the Klipper config uses {c['pin']} - check the wiring against printer.cfg"
            contacts.append(row)
        channels = [{"name": n, "pwm": o["pwm"], "value": o.get("value"), "shared_with": SHARED_CHANNELS.get(n, ""),
                     "pin": o.get("pin", ""), "contact": builders.contact_of_pin(ctx, o.get("pin")), "hardware": bool(o.get("hardware"))}
                    for n, o in sorted(ctx.outs.items())]
        return {"pins": pins, "channels": channels, "contacts": contacts, "hardware": self.hardware_list(ctx),
                "missing_includes": tree.missing_includes, **pin_labels.report(ctx, tree),
                "free_board_pins": self._label_choices(ctx, tree)}

    # ---------------------------------------------------------------- pin labels (1.5.3)
    def _label_choices(self, ctx, tree):
        """Pins a label may point at: known board headers and connector pins nothing else has."""
        held = registry.pins_in_use({**ctx.reg, "labels": {}})
        on_umb = set(ctx.umbilical) | {c["pin"] for c in ctx.contacts if c["pin"]}
        out = []
        for p in list(BOARD_HEADERS) + [x for x in ctx.umbilical if x not in BOARD_HEADERS]:
            if p in ctx.claimed or p in held:
                continue
            labelled = [a for a, q in ctx.reg.get("labels", {}).items() if q == p]
            out.append({"pin": p, "header": BOARD_HEADERS.get(p, ""), "connector": p in on_umb, "labelled": labelled})
        return out

    def label_save(self, raw, dry_run=False):
        """Add a pin label, or change one (raw["original"] = its current name)."""
        reg = copy.deepcopy(registry.load(self.paths))
        ctx, tree = self._ctx(reg)
        alias = pin_labels.clean_alias(raw.get("alias"))
        pin = pin_labels.clean_pin(raw.get("pin"))
        original = (raw.get("original") or "").strip().upper() or None
        if original and original not in reg["labels"]:
            raise Fail(f"No pin label called {original}")
        warnings = pin_labels.check_label(ctx, tree, alias, pin, original)
        before = reg["labels"].get(original or alias)
        if original:
            del reg["labels"][original]
        reg["labels"][alias] = pin
        for hw in reg.get("hardware", {}).values():      # system hardware on this label follows it
            if hw.get("pin_label") == (original or alias):
                hw["pin"], hw["pin_label"] = pin, alias
        if dry_run:
            return {"ok": True, "alias": alias, "pin": pin, "warnings": warnings}
        old_cfg = registry.render_cfg(registry.load(self.paths))
        registry.save(self.paths, reg)
        used = [u["where"] for u in pin_labels.uses_of(tree, original or alias, ctx.reg)]
        return {"ok": True, "alias": alias, "pin": pin, "previous": before, "warnings": warnings, "used_by": used,
                "restart_needed": registry.render_cfg(reg) != old_cfg}

    def label_remove(self, alias):
        reg = copy.deepcopy(registry.load(self.paths))
        alias = str(alias or "").strip().upper()
        if alias not in reg["labels"]:
            raise Fail(f"No pin label called {alias}")
        _, tree = self._ctx(reg)
        users = pin_labels.uses_of(tree, alias, reg)
        if users:
            raise Fail(f"{alias} is used by {', '.join(u['where'] for u in users)} - change those to a pin first")
        del reg["labels"][alias]
        registry.save(self.paths, reg)
        return {"ok": True, "alias": alias, "restart_needed": True}

    def label_use(self, raw):
        """Make one section's pin line use a label instead of the raw pin (one line in one of your files).
        With raw["new_label"], the label is made first for the pin that line names."""
        reg = copy.deepcopy(registry.load(self.paths))
        ctx, tree = self._ctx(reg)
        rel, section, key = str(raw.get("file") or ""), str(raw.get("section") or ""), str(raw.get("key") or "")
        full = pin_labels.safe_rel(self.paths, rel)
        line = next((u for u in tree.pin_uses if u["file"] == rel and u["section"] == section and u["key"] == key), None)
        if not line:
            raise Fail(f"No {key} line in {rel} [{section}]")
        if line["alias"]:
            raise Fail(f"[{section}] already uses the label {line['alias']}")
        if not line["pin"]:
            raise Fail(f"{line['value']} isn't a plain board pin")
        alias = pin_labels.clean_alias(raw.get("alias"))
        made = False
        if alias not in reg["labels"] and alias not in tree.aliases:
            # a new label for the pin this line already names: the line itself is its only user
            if line["pin"] in registry.pins_in_use({**reg, "labels": {}}):
                raise Fail(f"{line['pin']} is kept for something else")
            reg["labels"][alias] = line["pin"]
            made = True
        target = reg["labels"].get(alias) or tree.aliases.get(alias)
        if target != line["pin"]:
            raise Fail(f"{alias} names {target}, but [{section}] uses {line['pin']}")
        prefix = re.match(r"^[!^~]*", line["value"]).group(0)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        new_text = pin_labels.rewrite_pin_line(text, section, key, line["value"], prefix + alias)
        backup = pin_labels.backup_file(self.paths, rel)
        if made:
            registry.save(self.paths, reg)
        tmp = full + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp, full)
        # read it back the way Klipper will: the section must still claim the same pin
        check = ConfigTree(self.paths, extra_aliases=reg["labels"])
        again = next((u for u in check.pin_uses if u["file"] == rel and u["section"] == section and u["key"] == key), None)
        if not again or again["pin"] != line["pin"] or again["alias"] != alias:
            shutil.copy2(backup, full)
            raise Fail(f"After the change [{section}] didn't read back as {alias} ({line['pin']}) - the file was put back")
        return {"ok": True, "alias": alias, "pin": line["pin"], "file": rel, "section": section, "made_label": made,
                "backup": os.path.relpath(backup, self.paths.state_dir), "restart_needed": True}

    def options(self):
        """Everything the add-tool wizard (and the hardware editor) needs to build its drop-downs."""
        ctx, tree = self._ctx()
        rep = self.pin_report()
        lst = lists.load(self.paths)
        kinds = [{"value": k["id"], "label": k["label"], "type": BEHAVIOUR_TYPE[k["behaviour"]], "category": k["category"],
                  "behaviour": k["behaviour"], "help": k.get("help", ""), "builtin": k["id"] in lists.BUILTIN_KIND_IDS}
                 for k in lst["kinds"]]
        presets = {}
        for k in lst["kinds"]:
            if k["behaviour"] == "POWERED":
                presets[k["id"]] = {"cap": k["cap"], "max_on_s": k["max_on_s"], "checklist": k["checklist"], "materials": k["materials"]}
            elif k["behaviour"] == "PASSIVE":
                presets[k["id"]] = {"checklist": k["checklist"], "materials": k["materials"]}
        free = builders.free_pins(ctx)
        return {"kinds": kinds, "categories": [{"value": c, "label": l, "help": CATEGORY_HELP[c]} for c, l in CATEGORIES.items()],
                "behaviours": [{"value": b, "label": l} for b, l in BEHAVIOURS.items()],
                "category_behaviours": {c: list(v) for c, v in CATEGORY_BEHAVIOURS.items()},
                "free_pins": free,
                "free_pin_contacts": {p: builders.contact_of_pin(ctx, p) for p in free},
                "contacts": rep["contacts"], "output_roles": [[k, v] for k, v in OUTPUT_ROLES.items()],
                "pwm_channels": [c for c in rep["channels"] if c["pwm"]],
                "switch_channels": [c for c in rep["channels"] if not c["pwm"]],
                "print_bases": sorted(n for n, t in ctx.all_tools.items() if t.get("type") == "DEPOSITION"),
                "pin_info": {p: {**ctx.umbilical_info.get(p, {}), "type_label": PIN_TYPES[ctx.umbilical_info.get(p, {}).get("type", "")]}
                             for p in ctx.umbilical},
                "heaters": list(ctx.heaters),
                "control_roles": [{"value": k, **v} for k, v in CONTROL_ROLES.items()],
                "input_actions": [[k, v] for k, v in INPUT_ACTIONS.items()],
                "control_limits": {k: list(v) for k, v in CONTROL_LIMITS.items()},
                "next_slot": max(ctx.used_slots() | {FIRST_CUSTOM_SLOT - 1}) + 1,
                "presets": presets, "material_names": lst["materials"], "nozzles": lst["nozzles"],
                "hw_categories": lst["hw_categories"], "board_pins": self._board_pins(ctx),
                "limits": {k: list(v) for k, v in LIMITS.items()}}

    # ---------------------------------------------------------------- system hardware
    def _board_pins(self, ctx, exclude_hw=None):
        """Suggested pins for system hardware: known board headers nothing uses and not on the umbilical."""
        taken = registry.pins_in_use({"tools": ctx.reg["tools"], "devices": ctx.reg.get("devices", {}),
                                      "hardware": {n: h for n, h in ctx.reg.get("hardware", {}).items() if n != exclude_hw}})
        on_umb = set(ctx.umbilical) | {c["pin"] for c in ctx.contacts if c["pin"]}
        main = [{"pin": p, "header": h} for p, h in BOARD_HEADERS.items()
                if p not in ctx.claimed and p not in taken and p not in on_umb]
        extra = [{"pin": ref, "header": f"{ref.split(':')[0]} {hw_boards.caps(ref, ctx.boards)['header']}".strip()}
                 for ref in self._candidate_pins(ctx, main=False) if ref not in ctx.claimed and ref not in taken]
        return main + extra

    # ---------------------------------------------------------------- second boards + pin picker (hardware wizard step 2)
    SERIAL_DIR = "/dev/serial/by-id"

    def _candidate_pins(self, ctx, main=True):
        """Every pin a picker may offer: the main board's known headers, then each added board's (preset) pins."""
        out = list(hw_boards.PRESETS[hw_boards.MAIN_PRESET]["pins"]) if main else []
        for name, b in sorted(ctx.boards.items()):
            preset = hw_boards.PRESETS.get(b.get("preset") or "")
            if preset:
                out += [f"{name}:{p}" for p in preset["pins"]]
        return out

    def _held(self, ctx, exclude_hw=None):
        reg = {"tools": ctx.reg["tools"], "labels": ctx.reg.get("labels", {}),
               "hardware": {n: h for n, h in ctx.reg.get("hardware", {}).items() if n != exclude_hw},
               "devices": {n: d for n, d in ctx.reg.get("devices", {}).items() if n != exclude_hw}}
        on_umb = set(ctx.umbilical) | {c["pin"] for c in ctx.contacts if c["pin"]}
        return registry.pins_in_use(reg), on_umb

    @staticmethod
    def _kind_and_sensor(kind, sensor):
        if kind not in hw_catalog.PIN_KINDS or kind == "i2c":
            raise Fail(f"Unknown pin kind {kind!r}")
        if sensor and sensor not in hw_catalog.SENSOR_TYPES:
            raise Fail(f"Unknown sensor type {sensor!r}")

    def pin_choices(self, kind, sensor=None, exclude_hw=None):
        """Free pins that can do `kind` (a hw_catalog pin kind), each with its capabilities and warnings."""
        self._kind_and_sensor(kind, sensor)
        ctx, _ = self._ctx()
        held, on_umb = self._held(ctx, exclude_hw)
        pins, hidden = [], 0
        for ref in self._candidate_pins(ctx):
            if ref in ctx.claimed or ref in held or ref in on_umb:
                continue
            c = hw_boards.caps(ref, ctx.boards)
            ok, warnings = hw_boards.check_kind(kind, c)
            if not ok:
                hidden += 1
                continue
            isolate = False
            if sensor:
                try:
                    warnings += hw_boards.check_sensor(sensor, c)
                except Fail as e:
                    isolate = True
                    warnings.append(str(e))
            pins.append({**c, "warnings": warnings, "needs_isolation": isolate})
        order = ["gpio", "endstop", "probe", "servo", "rgb", "thermistor", "fan", "heater", "spi", "led", "driver"]
        pins.sort(key=lambda p: (p["board"] != "main", p["board"], order.index(p["use"]) if p["use"] in order else 99))
        typed = sorted(n for n, b in ctx.boards.items() if not hw_boards.PRESETS.get(b.get("preset") or "", {}).get("pins"))
        return {"ok": True, "kind": kind, "pins": pins, "hidden": hidden, "type_pin_on": typed}

    def pin_check(self, raw):
        """One typed pin, e.g. on an 'Other board': is it free, can it do the kind, what to watch for."""
        kind, sensor = raw.get("kind"), raw.get("sensor") or None
        self._kind_and_sensor(kind, sensor)
        ctx, _ = self._ctx()
        ref = ctx.resolve(str(raw.get("pin") or ""))
        if not ref:
            raise Fail(f"{raw.get('pin')!r} isn't a pin on the main board or an added board (like PB1 or ebb:PA1)")
        held, on_umb = self._held(ctx, raw.get("exclude_hw"))
        if ref in on_umb:
            raise Fail(f"{ref} is wired to the tool connector")
        used = ctx.claimed.get(ref) or held.get(ref)
        if used:
            raise Fail(f"{ref} is already used by {used}")
        c = hw_boards.caps(ref, ctx.boards)
        ok, warnings = hw_boards.check_kind(kind, c)
        if not ok:
            raise Fail(warnings[0])
        if sensor:
            warnings += hw_boards.check_sensor(sensor, c, isolated=bool(raw.get("isolated")))
        return {"ok": True, **c, "warnings": warnings}

    def _config_serials(self, tree):
        """{serial or canbus_uuid: '[mcu ...]'} from your own files."""
        out = {}
        for rel, cp in tree.files:
            for sec in cp.sections():
                if sec == "mcu" or sec.startswith("mcu "):
                    for key in ("serial", "canbus_uuid"):
                        v = cp.get(sec, key, fallback="").strip()
                        if v:
                            out[v.lower() if key == "canbus_uuid" else v] = f"{rel} [{sec}]"
        return out

    def boards_list(self):
        ctx, tree = self._ctx()
        mine = ctx.reg.get("boards", {})
        boards = [{"name": n, **b, "added_here": True} for n, b in sorted(mine.items())]
        boards += [{"name": n, "where": b["where"], "added_here": False} for n, b in sorted(tree.boards.items()) if n not in mine]
        used = self._config_serials(tree)
        used.update({b["serial"]: f"board {n}" for n, b in mine.items() if b.get("serial")})
        try:
            ports = sorted(os.listdir(self.SERIAL_DIR))
        except OSError:
            ports = []
        ports = [{"path": f"{self.SERIAL_DIR}/{p}", "used_by": used.get(f"{self.SERIAL_DIR}/{p}", "")} for p in ports]
        return {"ok": True, "presets": hw_boards.presets_for_ui(), "boards": boards, "serial_ports": ports,
                "max_boards": hw_boards.MAX_BOARDS}

    def board_save(self, raw, dry_run=False):
        """Add a second board, or change its connection / type (raw["original"] = its name; renames aren't allowed)."""
        reg = copy.deepcopy(registry.load(self.paths))
        ctx, tree = self._ctx(reg)
        boards = reg["boards"]
        original = (raw.get("original") or "").strip().lower() or None
        if original and original not in boards:
            raise Fail(f"No added board called {original}")
        taken = {n: b["where"] for n, b in tree.boards.items() if n not in boards and b.get("where")}
        if not original:
            taken.update({n: "another added board" for n in boards})
        name, item = hw_boards.clean_board(raw, taken, {n: b for n, b in boards.items() if n != original})
        if original and name != original:
            raise Fail("A board can't be renamed: remove it (nothing may use its pins) and add it again")
        conn = item.get("serial") or item.get("canbus_uuid")
        clash = self._config_serials(tree).get(conn)
        if clash:
            raise Fail(f"That connection is already {clash}")
        if original and item["preset"] != boards[original]["preset"]:
            fam = hw_boards.family_of(item)
            for ref, where in {**ctx.claimed, **registry.pins_in_use(reg)}.items():
                if ref.startswith(name + ":") and not hw_boards.canon_pin(ref.split(":", 1)[1], fam):
                    raise Fail(f"{ref} ({where}) isn't a pin on a {item['label']}")
        warnings = [f"Klipper won't start while {name} is unplugged or off. Remove it here to run without it."]
        if item["link"] == "usb":
            try:
                present = item["serial"].rsplit("/", 1)[-1] in os.listdir(self.SERIAL_DIR)
            except OSError:
                present = False
            if not present:
                warnings.append(f"{item['serial']} isn't connected right now.")
        boards[name] = item
        if dry_run:
            return {"ok": True, "name": name, "board": item, "warnings": warnings, "cfg": "\n".join(hw_boards.board_lines({"boards": {name: item}}))}
        registry.save(self.paths, reg)
        return {"ok": True, "name": name, "board": item, "warnings": warnings, "restart_needed": True}

    # ---------------------------------------------------------------- devices (hardware wizard steps 3 and 5)
    def devices_list(self):
        ctx, _ = self._ctx()
        out = []
        for n, d in sorted(ctx.reg.get("devices", {}).items()):
            out.append({**d, "name": n, "headers": {k: hw_boards.caps(p, ctx.boards)["header"] for k, p in d["pins"].items()},
                        "macros": [m for m, *_ in hw_devices.macros_of(n, d)], "live": hw_catalog.DEVICES[d["device"]]["live"]})
        return {"ok": True, "devices": out, "max": hw_devices.MAX_DEVICES}

    def device_save(self, raw, dry_run=False):
        """Add a device from the catalog, or replace one (raw["original"] = its current name)."""
        reg = copy.deepcopy(registry.load(self.paths))
        ctx, _ = self._ctx(reg)
        devs = reg["devices"]
        original = (raw.get("original") or "").strip().lower() or None
        if original and original not in devs:
            raise Fail(f"No hardware named {original}")
        if not original and len(devs) >= hw_devices.MAX_DEVICES:
            raise Fail(f"At most {hw_devices.MAX_DEVICES} pieces of hardware")
        held, _ = self._held(ctx, exclude_hw=original)
        name, item, warnings = hw_devices.clean(ctx, raw, held)
        if name in reg.get("hardware", {}) and name != original:
            raise Fail(f"The name {name} is already used by system hardware")
        before = registry.render_cfg(registry.load(self.paths))
        if original:
            del devs[original]
        devs[name] = item
        self._audit(ctx)
        text = "\n".join(hw_devices.lines(name, item)) + "\n"
        for mn, desc, body in hw_devices.macros_of(name, item):
            text += "\n" + "\n".join(sections.macro_section(mn, desc, "\n".join(body), owner=f"made by hardware {name}")) + "\n"
        if item["safe_off"] and hw_devices.off_lines(name, item):
            text += "\n# also switched off by _TOOL_SAFE_OFF (end of job, cancel, tool swap, emergency stop):\n"
            text += "".join(f"#   {l}\n" for l in hw_devices.off_lines(name, item))
        if dry_run:
            return {"ok": True, "name": name, "item": item, "warnings": warnings, "text": text}
        registry.save(self.paths, reg)
        return {"ok": True, "name": name, "warnings": warnings, "renamed_from": original if original and original != name else "",
                "restart_needed": registry.render_cfg(reg) != before}

    def device_remove(self, name):
        reg = copy.deepcopy(registry.load(self.paths))
        name = str(name or "").strip().lower()
        if name not in reg["devices"]:
            raise Fail(f"No hardware named {name}")
        del reg["devices"][name]
        registry.save(self.paths, reg)
        return {"ok": True, "name": name, "restart_needed": True}

    def board_remove(self, name):
        reg = copy.deepcopy(registry.load(self.paths))
        name = str(name or "").strip().lower()
        if name not in reg["boards"]:
            raise Fail(f"No added board called {name}")
        ctx, _ = self._ctx(reg)
        users = sorted({w for ref, w in {**ctx.claimed, **registry.pins_in_use(reg)}.items() if ref.startswith(name + ":")})
        if users:
            raise Fail(f"{name}'s pins are used by {', '.join(users)} - change those first")
        del reg["boards"][name]
        registry.save(self.paths, reg)
        return {"ok": True, "name": name, "restart_needed": True}

    def hardware_list(self, ctx=None):
        ctx = ctx or self._ctx()[0]
        cats = {c["id"]: c["label"] for c in lists.load(self.paths)["hw_categories"]}
        out = []
        for n, hw in sorted(ctx.reg.get("hardware", {}).items()):
            out.append({**copy.deepcopy(hw), "name": n, "category_label": cats.get(hw.get("category"), hw.get("category", "")),
                        "header": BOARD_HEADERS.get(hw["pin"], ""),
                        "macros": [mn for mn, *_ in sections.control_macros("", None, hw)]})
        return out

    def hardware_save(self, raw, dry_run=False):
        """Add (no 'original') or replace (original = its current name) one piece of system hardware."""
        ctx, _ = self._ctx(copy.deepcopy(registry.load(self.paths)))
        cats = {c["id"] for c in lists.load(self.paths)["hw_categories"]}
        original = (raw.get("original") or "").strip().lower()
        hw = ctx.reg["hardware"]
        if original and original not in hw:
            raise Fail(f"No system hardware named {original}")
        if not original and len(hw) >= MAX_HARDWARE:
            raise Fail(f"At most {MAX_HARDWARE} pieces of system hardware")
        name, item, warnings = extras.clean_hardware(ctx, raw, cats)
        if name.lower() in {n.lower() for n in ctx.all_tools}:
            raise Fail(f"{name} is the name of a toolhead")
        if original:
            del hw[original]
        before = registry.render_cfg(registry.load(self.paths))
        hw[name] = item
        self._audit(ctx)
        if dry_run:
            return {"ok": True, "name": name, "warnings": warnings}
        registry.save(self.paths, ctx.reg)
        return {"ok": True, "name": name, "warnings": warnings, "renamed_from": original if original and original != name else "",
                "restart_needed": registry.render_cfg(ctx.reg) != before}

    def hardware_preview(self, raw):
        ctx, _ = self._ctx()
        cats = {c["id"] for c in lists.load(self.paths)["hw_categories"]}
        return {"ok": True, **extras.hardware_preview(ctx, raw, cats)}

    def hardware_remove(self, name):
        ctx, _ = self._ctx()
        if name not in ctx.reg["hardware"]:
            raise Fail(f"No system hardware named {name}")
        users = sorted(n for n, t in ctx.reg["tools"].items()
                       if name in t.get("also_on", []) or name in (t.get("power_pin"), t.get("enable_pin")))
        if users:
            raise Fail(f"{', '.join(users)} switch {name} on with the tool - change those tools first")
        del ctx.reg["hardware"][name]
        registry.save(self.paths, ctx.reg)
        return {"ok": True, "name": name, "restart_needed": True}

    # ---------------------------------------------------------------- admin lists
    def lists_get(self):
        lst = lists.load(self.paths)
        use = self._lists_in_use()
        return {"ok": True, **lst, "in_use": use, "builtin_kinds": sorted(lists.BUILTIN_KIND_IDS),
                "categories": [{"value": c, "label": l, "help": CATEGORY_HELP[c]} for c, l in CATEGORIES.items()],
                "behaviours": [{"value": b, "label": l} for b, l in BEHAVIOURS.items()],
                "category_behaviours": {c: list(v) for c, v in CATEGORY_BEHAVIOURS.items()},
                "limits": {k: list(v) for k, v in LIMITS.items()}}

    def _lists_in_use(self):
        reg = registry.load(self.paths)
        kinds, cats = {}, {}
        for n, t in reg["tools"].items():
            kinds.setdefault(t.get("kind", ""), []).append(n)
        for n, hw in reg.get("hardware", {}).items():
            cats.setdefault(hw.get("category", ""), []).append(n)
        return {"kinds": kinds, "hw_categories": cats}

    def lists_save(self, body):
        out = lists.save(self.paths, body, self._lists_in_use())
        return {"ok": True, **out}
