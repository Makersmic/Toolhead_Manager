#!/usr/bin/env python3
"""Tiny Klipper gcode_macro simulator, enough to exercise Rhino's macros.

Mirrors the Klipper behaviours that matter for these macros:
  * Jinja delimiters  {% %}  and  { }  (Klipper's Environment)
  * the WHOLE template renders first, then the resulting lines execute
    (so action_raise_error in a template aborts before any command runs, and a
    macro cannot see its own SAVE_VARIABLE/SET_GCODE_VARIABLE results)
  * variable_* options are literal_eval'd and visible as bare names + via
    printer["gcode_macro X"].name
  * SAVE_VARIABLE / SET_GCODE_VARIABLE use literal_eval
  * printer["..."] returns a COPY of an object's status dict
"""
import ast, configparser, glob, os, re, shlex, copy
import jinja2

class KlipperError(Exception):
    pass

class Status(dict):
    """printer object: missing objects raise KeyError like Klipper's wrapper."""
    def __init__(self, sim):
        super().__init__()
        self.sim = sim
    def __getitem__(self, key):
        key = str(key).strip()
        if key.startswith("gcode_macro "):
            name = key[len("gcode_macro "):].strip().upper()
            if name not in self.sim.macros:
                raise KeyError(key)
            return dict(self.sim.macro_vars[name])
        if key == "save_variables":
            return {"variables": dict(self.sim.save_vars)}
        if key == "configfile":
            settings = copy.deepcopy(self.sim.config_sections)
            settings.setdefault("pause_resume", {}).setdefault("recover_velocity", 50.0)
            settings.setdefault("idle_timeout", {}).setdefault("timeout", 600.0)
            return {"config": self.sim.config_sections, "settings": settings}
        if key.startswith("output_pin "):
            name = key[len("output_pin "):].strip()
            if name not in self.sim.pins:
                raise KeyError(key)
            return {"value": self.sim.pins[name]}
        if key in self.sim.objects:
            return copy.deepcopy(self.sim.objects[key])
        raise KeyError(key)
    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

class Sim:
    def __init__(self, root):
        self.root = root
        self.macros = {}         # NAME -> {'gcode':..., 'description':...}
        self.macro_vars = {}     # NAME -> {var: value}
        self.delayed = {}        # NAME -> gcode
        self.config_sections = {}
        self.save_vars = {}
        self.objects = {
            "print_stats": {"state": "standby", "total_duration": 0.0},
            "pause_resume": {"is_paused": False},
            "toolhead": {"homed_axes": "xyz", "axis_maximum": {"x": 576.0, "y": 406.0, "z": 400.0}, "axis_minimum": {"x": 0.0, "y": 0.0, "z": -10.0},
                         "position": {"x": 100.0, "y": 50.0, "z": 20.0, "e": 0.0},
                         "extruder": "extruder"},
            "homed_axes": "xyz",
            "extruder": {"temperature": 25.0, "target": 0.0, "min_extrude_temp": 170.0, "can_extrude": False},
            "idle_timeout": {"state": "Ready"},
            "heater_bed": {"temperature": 25.0, "target": 0.0},
            "gcode_move": {"gcode_position": {"x": 0.0, "y": 0.0, "z": 0.0},
                           "homing_origin": {"x": 0.0, "y": 0.0, "z": 0.0},
                           "absolute_coordinates": True, "absolute_extrude": True},
            "gcode": {"script_counter": 0},
        }
        self.log = []            # (kind, text) in execution order
        self.pins = {}
        self.prompt = None       # last shown prompt: {'title','text':[], 'buttons':[(label,cmd,color)], 'footer':[]}
        self._prompt_building = None
        self.jenv = jinja2.Environment('{%', '%}', '{', '}', extensions=['jinja2.ext.do'])
        self.printer = Status(self)
        self.depth = 0
        self.raise_on_error = True

    # ---------------- config loading ----------------
    def load(self, main="printer.cfg"):
        parts = []
        self._read(os.path.join(self.root, main), parts, set())
        cp = configparser.RawConfigParser(strict=False, inline_comment_prefixes=(";", "#"))
        cp.optionxform = str
        for src, text in parts:
            cp.read_string(text, source=src)
        for s in cp.sections():
            d = dict(cp.items(s))
            self.config_sections[s] = d
            if s.startswith("gcode_macro "):
                name = s[len("gcode_macro "):].strip().upper()
                self.macros[name] = d
                vars_ = {}
                for k, v in d.items():
                    if k.startswith("variable_"):
                        vars_[k[len("variable_"):]] = ast.literal_eval(v.strip())
                self.macro_vars[name] = vars_
            elif s.startswith("delayed_gcode "):
                self.delayed[s[len("delayed_gcode "):].strip().upper()] = d.get("gcode", "")
            elif s.startswith("output_pin "):
                self.pins[s[len("output_pin "):].strip()] = float(d.get("value", 0) or 0)
        # rename_existing: old command stays callable as the renamed name
        for name, d in list(self.macros.items()):
            if "rename_existing" in d:
                self.macros[d["rename_existing"].strip().upper()] = {"gcode": ""}
                self.macro_vars[d["rename_existing"].strip().upper()] = {}
        # stub mainsail.cfg essentials
        for n in ("PAUSE", "RESUME", "PAUSE_BASE", "RESUME_BASE", "CLEAR_PAUSE",
                  "CANCEL_PRINT_BASE", "SDCARD_PRINT_FILE", "TURN_OFF_HEATERS"):
            self.macros.setdefault(n, {"gcode": ""})
            self.macro_vars.setdefault(n, {})
        return self

    def _read(self, path, parts, seen):
        if path in seen:
            return
        seen.add(path)
        base = os.path.dirname(path)
        cur = []
        for line in open(path, encoding="utf-8").read().splitlines():
            m = re.match(r"\[include\s+(.+?)\]\s*$", line)
            if m:
                targets = sorted(glob.glob(os.path.join(base, m.group(1))))
                if not targets and m.group(1).strip() == "mainsail.cfg":
                    fx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mainsail.cfg")
                    targets = [fx] if os.path.exists(fx) else []
                for t in targets:
                    self._read(t, parts, seen)
                continue
            cur.append(line)
        parts.append((path, "\n".join(cur)))

    # ---------------- execution ----------------
    def _context(self, name, params, rawparams):
        ctx = {
            "printer": self.printer,
            "params": params,
            "rawparams": rawparams,
            "action_raise_error": self._raise,
            "action_respond_info": lambda m: self.log.append(("info", m)) or "",
            "action_respond_error": lambda m: self.log.append(("error", m)) or "",
            "action_emergency_stop": lambda m="": self.log.append(("ESTOP", m)) or "",
        }
        ctx.update(self.macro_vars.get(name, {}))
        return ctx

    def _raise(self, msg):
        raise KlipperError(msg)

    def render(self, name, gcode, params=None, rawparams=""):
        ctx = self._context(name, params or {}, rawparams)
        tmpl = self.jenv.from_string(gcode)
        return tmpl.render(**ctx)

    def run_macro(self, name, params=None, rawparams=""):
        name = name.upper()
        params = {k.upper(): v for k, v in (params or {}).items()}
        if name not in self.macros:
            raise KlipperError(f"Unknown command: {name}")
        self.depth += 1
        if self.depth > 40:
            raise KlipperError("macro recursion too deep (possible loop)")
        try:
            text = self.render(name, self.macros[name].get("gcode", ""), params, rawparams)
            for line in text.splitlines():
                self.run_line(line)
        finally:
            self.depth -= 1

    def run_script(self, script):
        for line in script.strip().splitlines():
            self.run_line(line)

    def run_line(self, line):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            return
        line = re.split(r"\s;", line, 1)[0].strip()   # trailing ; comment
        parts = shlex.split(line, posix=True)
        cmd = parts[0].upper()
        rest = line[len(parts[0]):].strip()
        params = {}
        for tok in parts[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                params[k.upper()] = v
            else:
                params[tok[0].upper()] = tok[1:]
        self.log.append(("cmd", line))
        extra = getattr(self, "extra_cmds", {})
        if cmd in extra:
            return extra[cmd](params, rest)
        h = getattr(self, "cmd_" + cmd, None)
        if h:
            return h(params, rest)
        if cmd in self.macros:
            return self.run_macro(cmd, params, rest)
        if re.fullmatch(r"G\d+|M\d+", cmd):
            return  # hardware/motion, ignored
        known_noops = {"SET_VELOCITY_LIMIT", "SET_TMC_CURRENT",
                       "SET_STEPPER_ENABLE", "TEMPERATURE_WAIT", "SAVE_GCODE_STATE",
                       "RESTORE_GCODE_STATE", "RESTART", "FIRMWARE_RESTART",
                       "Z_TILT_ADJUST", "SET_PRESSURE_ADVANCE", "SET_IDLE_TIMEOUT"}
        if cmd in known_noops:
            return
        raise KlipperError(f"Unknown command: {cmd}")

    # ---------------- builtin commands ----------------
    def cmd_RESPOND(self, p, rest):
        msg = p.get("MSG", "")
        typ = p.get("TYPE", "echo")
        if typ == "command" and msg.startswith("action:"):
            self._action(msg[len("action:"):])
        else:
            self.log.append((typ, msg))

    def _action(self, a):
        if a.startswith("prompt_begin"):
            self._prompt_building = {"title": a[len("prompt_begin"):].strip(), "text": [],
                                     "buttons": [], "footer": []}
        elif a.startswith("prompt_text"):
            self._prompt_building["text"].append(a[len("prompt_text"):].strip())
        elif a.startswith("prompt_button_group"):
            pass
        elif a.startswith("prompt_button"):
            body = a[len("prompt_button"):].strip()
            bits = body.split("|")
            self._prompt_building["buttons"].append(
                (bits[0], bits[1] if len(bits) > 1 else "", bits[2] if len(bits) > 2 else "primary"))
        elif a.startswith("prompt_footer_button"):
            body = a[len("prompt_footer_button"):].strip()
            bits = body.split("|")
            self._prompt_building["footer"].append(
                (bits[0], bits[1] if len(bits) > 1 else "", bits[2] if len(bits) > 2 else "primary"))
        elif a.startswith("prompt_show"):
            self.prompt = self._prompt_building
        elif a.startswith("prompt_end"):
            self.prompt = None
            self._prompt_building = None
        elif a.startswith("prompt_input"):
            raise KlipperError("action:prompt_input is not implemented by Mainsail")
        else:
            self.log.append(("action", a))

    def cmd_RUN_SHELL_COMMAND(self, p, rest):
        if p.get("CMD") not in {s.split(" ", 1)[1] for s in self.config_sections if s.startswith("gcode_shell_command ")}:
            raise KlipperError(f"Unknown gcode_shell_command {p.get('CMD')}")
        self.shell_calls = getattr(self, "shell_calls", [])
        self.shell_calls.append((p["CMD"], p.get("PARAMS", "")))

    def cmd_SET_GCODE_OFFSET(self, p, rest):
        self.offsets = getattr(self, "offsets", {"X": 0.0, "Y": 0.0, "Z": 0.0})
        for ax in "XYZ":
            if ax in p:
                self.offsets[ax] = float(p[ax])
        if p.get("MOVE") == "1":
            self.moved = True

    def cmd_PAUSE_BASE(self, p, rest):
        self.objects["print_stats"]["state"] = "paused"
        self.objects["pause_resume"]["is_paused"] = True

    def cmd_RESUME_BASE(self, p, rest):
        self.objects["print_stats"]["state"] = "printing"
        self.objects["pause_resume"]["is_paused"] = False

    def cmd_CANCEL_PRINT_BASE(self, p, rest):
        self.objects["print_stats"]["state"] = "cancelled"
        self.objects["pause_resume"]["is_paused"] = False

    def cmd_SAVE_VARIABLE(self, p, rest):
        self.save_vars[p["VARIABLE"].lower()] = ast.literal_eval(p["VALUE"])

    def cmd_SET_GCODE_VARIABLE(self, p, rest):
        m = p["MACRO"].upper()
        if m not in self.macro_vars:
            raise KlipperError(f"Unknown gcode_macro '{m}'")
        self.macro_vars[m][p["VARIABLE"].lower()] = ast.literal_eval(p["VALUE"])

    def cmd_SET_PIN(self, p, rest):
        pin = p["PIN"]
        if pin not in self.pins:
            raise KlipperError(f"pin {pin} not configured")
        v = float(p["VALUE"])
        cfg = self.config_sections.get("output_pin " + pin, {})
        if str(cfg.get("pwm", "False")).lower() not in ("true", "1") and v not in (0.0, 1.0):
            raise KlipperError(f"Invalid pin value {v} for digital pin {pin}")
        self.pins[pin] = v

    def cmd_SET_FAN_SPEED(self, p, rest):
        name = p["FAN"]
        if "fan_generic " + name not in self.config_sections:
            raise KlipperError(f"Unknown fan {name}")
        self.fans = getattr(self, "fans", {})
        self.fans[name] = float(p.get("SPEED", 0))

    def cmd_SET_SERVO(self, p, rest):
        name = p["SERVO"]
        if "servo " + name not in self.config_sections:
            raise KlipperError(f"Unknown servo {name}")
        self.servos = getattr(self, "servos", {})
        self.servos[name] = ("width", float(p["WIDTH"])) if "WIDTH" in p else ("angle", float(p.get("ANGLE", 0)))

    def cmd_UPDATE_DELAYED_GCODE(self, p, rest):
        self.log.append(("delayed", p["ID"].upper(), p.get("DURATION")))
        self.pending_delayed = getattr(self, "pending_delayed", {})
        self.pending_delayed[p["ID"].upper()] = float(p.get("DURATION", 0))

    def fire_delayed(self, name):
        name = name.upper()
        self.run_delayed_body(name)

    def run_delayed_body(self, name):
        text = self.render(name, self.delayed[name])
        for line in text.splitlines():
            self.run_line(line)

    # ---------------- helpers for tests ----------------
    def press(self, label_contains):
        """Simulate clicking a button in the currently shown prompt."""
        if not self.prompt:
            raise AssertionError("no prompt shown")
        for lab, cmd, _ in self.prompt["buttons"] + self.prompt["footer"]:
            if label_contains.lower() in lab.lower():
                self.run_script(cmd)
                return lab
        labs = [b[0] for b in self.prompt["buttons"] + self.prompt["footer"]]
        raise AssertionError(f"no button containing {label_contains!r}; have {labs}")

    def buttons(self):
        return [b[0] for b in (self.prompt or {}).get("buttons", [])] + \
               [b[0] for b in (self.prompt or {}).get("footer", [])]

    def errors(self):
        return [m for k, *m in self.log if k == "error"]
