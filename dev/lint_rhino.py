#!/usr/bin/env python3
"""Static lint for the Rhino Klipper config tree (no Klipper needed).

Checks:
  * [include] resolution (globs ok) and duplicate sections across files
  * Jinja syntax of every [gcode_macro]/[delayed_gcode] body
  * commands called from macros that nothing defines
  * SET_PIN PIN=<x> targets that have no [output_pin x]
  * RUN_SHELL_COMMAND CMD=<x> targets that have no [gcode_shell_command x]
  * action:prompt_* verbs Mainsail does not implement
"""
import configparser, glob, os, re, sys
from collections import defaultdict
import jinja2

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "printer.cfg")

# What mainsail.cfg (mainsail-crew/mainsail-config) provides, plus Klipper core.
STUB_MACROS = {"PAUSE", "RESUME", "CANCEL_PRINT", "PAUSE_BASE", "RESUME_BASE",
               "CANCEL_PRINT_BASE", "CLEAR_PAUSE", "SET_PAUSE_NEXT_LAYER",
               "SET_PAUSE_AT_LAYER", "SDCARD_PRINT_FILE", "TURN_OFF_HEATERS"}
KLIPPER_CMDS = set("""
G0 G1 G2 G3 G4 G20 G21 G28 G90 G91 G92 M82 M83 M84 M104 M105 M106 M107 M109 M112 M114
M115 M117 M118 M140 M141 M190 M220 M221 M204 M400 SET_GCODE_OFFSET SET_KINEMATIC_POSITION SET_VELOCITY_LIMIT
SET_PIN SET_TMC_CURRENT SET_STEPPER_ENABLE TEMPERATURE_WAIT SAVE_GCODE_STATE
RESTORE_GCODE_STATE SAVE_VARIABLE RESPOND RESTART FIRMWARE_RESTART Z_TILT_ADJUST SET_IDLE_TIMEOUT
SET_GCODE_VARIABLE UPDATE_DELAYED_GCODE SET_PRESSURE_ADVANCE SET_HEATER_TEMPERATURE
RUN_SHELL_COMMAND G90 G91 M73 EMERGENCY_STOP SET_LED SET_FAN_SPEED SET_SERVO M112
""".split())
# Jinja-tag-only / non-command first tokens
IGNORE_FIRST = {"{%", "{#", "{"}

def read_with_includes(path, seen=None, out=None, origin=None):
    out = out if out is not None else []
    seen = seen if seen is not None else set()
    if path in seen:
        return out
    seen.add(path)
    base = os.path.dirname(path)
    cur = []
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"\[include\s+(.+?)\](?:\s*[#;].*)?$", line)
        if m:
            inc = m.group(1)
            targets = sorted(glob.glob(os.path.join(base, inc)))
            if not targets and "mainsail" not in inc and "klipper-toolchanger" not in inc:
                out.append(("MISSING_INCLUDE", inc, path))
            for t in targets:
                read_with_includes(t, seen, out)
            continue
        cur.append(line)
    out.append(("FILE", path, "\n".join(cur)))
    return out

def parse_files(parts):
    sections = defaultdict(list)  # section -> [(file, {opt: val})]
    for kind, a, b in parts:
        if kind != "FILE":
            continue
        cp = configparser.RawConfigParser(strict=False,
                                          inline_comment_prefixes=(";", "#"))
        cp.optionxform = str
        try:
            cp.read_string(b, source=a)
        except configparser.Error as e:
            print(f"PARSE ERROR {a}: {e}")
            continue
        for s in cp.sections():
            sections[s].append((a, dict(cp.items(s))))
    return sections

def merged(sections):
    m = {}
    for s, lst in sections.items():
        d = {}
        for _, opts in lst:
            d.update(opts)
        m[s] = d
    return m

def main():
    parts = read_with_includes(MAIN)
    problems = 0
    for kind, a, b in parts:
        if kind == "MISSING_INCLUDE":
            print(f"[MISSING INCLUDE] {b}: {a}")
            problems += 1
    sections = parse_files(parts)
    cfg = merged(sections)

    print("== duplicate sections (merged by Klipper; later file wins per option) ==")
    for s, lst in sorted(sections.items()):
        if len(lst) > 1:
            files = [os.path.relpath(f, ROOT) for f, _ in lst]
            dup_opts = defaultdict(int)
            for _, o in lst:
                for k in o:
                    dup_opts[k] += 1
            clash = [k for k, v in dup_opts.items() if v > 1]
            print(f"  [{s}] in {files}; overridden options: {clash}")

    macros = {s[len("gcode_macro "):].strip().upper(): cfg[s]
              for s in cfg if s.startswith("gcode_macro ")}
    delayed = {s[len("delayed_gcode "):].strip().upper() for s in cfg if s.startswith("delayed_gcode ")}
    shell = {s[len("gcode_shell_command "):].strip() for s in cfg if s.startswith("gcode_shell_command ")}
    pins = {s[len("output_pin "):].strip().upper() for s in cfg if s.startswith("output_pin ")}
    renamed = {v["rename_existing"].strip().upper() for v in macros.values() if "rename_existing" in v}
    defined = set(macros) | STUB_MACROS | KLIPPER_CMDS | renamed

    env = jinja2.Environment('{%', '%}', '{', '}', extensions=['jinja2.ext.do'])  # Klipper's delimiters
    print("== Jinja syntax ==")
    bodies = {}
    for s, d in cfg.items():
        if s.startswith("gcode_macro ") or s.startswith("delayed_gcode "):
            body = d.get("gcode", "")
            bodies[s] = body
            try:
                env.parse(body)
            except jinja2.TemplateSyntaxError as e:
                print(f"  [{s}] line {e.lineno}: {e.message}")
                problems += 1

    print("== undefined commands / pins / shell commands / prompt verbs ==")
    for s, body in sorted(bodies.items()):
        depth_expr = 0
        for ln in body.splitlines():
            t = ln.strip()
            if "tc.run_shell_command" in t:
                print(f"  [{s}] uses tc.run_shell_command (not a Klipper Jinja API)")
                problems += 1
            if not t or t.startswith("#") or t.startswith(";"):
                continue
            if t.startswith("{%") or t.startswith("{#"):
                continue
            if t.startswith("{"):
                continue
            tok = re.split(r"[\s;]", t, maxsplit=1)[0].upper()
            if re.fullmatch(r"[A-Z_][A-Z0-9_]*", tok) and tok not in defined:
                if not re.fullmatch(r"G\d+|M\d+", tok):
                    print(f"  [{s}] calls undefined command: {tok}")
                    problems += 1
            m = re.search(r"\bSET_PIN\s+PIN=([A-Za-z0-9_{}]+)", t)
            if m and "{" not in m.group(1) and m.group(1).upper() not in pins:
                print(f"  [{s}] SET_PIN on undefined pin: {m.group(1)}")
                problems += 1
            m = re.search(r"\bRUN_SHELL_COMMAND\s+CMD=([A-Za-z0-9_]+)", t)
            if m and m.group(1) not in shell:
                print(f"  [{s}] RUN_SHELL_COMMAND undefined shell cmd: {m.group(1)}")
                problems += 1
            for v in re.findall(r"action:(prompt_[a-z_]+)", t):
                if v not in {"prompt_begin", "prompt_text", "prompt_button",
                             "prompt_button_group_start", "prompt_button_group_end",
                             "prompt_footer_button", "prompt_show", "prompt_end"}:
                    print(f"  [{s}] unsupported prompt verb: {v}")
                    problems += 1

    print("== options Klipper does not accept in a section ==")
    allowed = {"delayed_gcode ": {"gcode", "initial_duration"},
               "gcode_macro ": {"gcode", "description", "rename_existing"}}
    for s, d in sorted(cfg.items()):
        for prefix, ok in allowed.items():
            if s.startswith(prefix):
                for k in d:
                    if k not in ok and not (prefix == "gcode_macro " and k.startswith("variable_")):
                        print(f"  [{s}] option '{k}' is not valid in this section")
                        problems += 1

    print("== options Klipper refuses at start-up ==")
    allowed = {"delayed_gcode ": {"gcode", "initial_duration"},
               "gcode_macro ": {"gcode", "description", "rename_existing"}}
    for s, d in sorted(cfg.items()):
        for prefix, okset in allowed.items():
            if s.startswith(prefix):
                for k in d:
                    if k not in okset and not (prefix == "gcode_macro " and k.startswith("variable_")):
                        print(f"  [{s}] option '{k}' is not valid in this section")
                        problems += 1
        # Software PWM (pwm: true without hardware_pwm) only allows a shutdown value of 0 or 1.
        if s.startswith("output_pin ") and str(d.get("pwm", "false")).strip().lower() in ("true", "1") \
                and str(d.get("hardware_pwm", "false")).strip().lower() not in ("true", "1"):
            try:
                sv = float(str(d.get("shutdown_value", "0")).split()[0]) / float(str(d.get("scale", "1")).split()[0])
            except ValueError:
                sv = 0.0
            if sv not in (0.0, 1.0):
                print(f"  [{s}] shutdown_value must be 0 or 1 on soft PWM (is {d.get('shutdown_value')})")
                problems += 1

    print(f"\nTotal problems flagged: {problems}")
    return problems

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
