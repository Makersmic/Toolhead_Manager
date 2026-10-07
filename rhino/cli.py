"""Command line: what Klipper's RUN_SHELL_COMMAND (and you, over SSH) call.

    python3 -m rhino [--config-dir DIR] add|edit|remove|rename|list|check|pins KEY=VALUE ...

Keys are case-insensitive. Output lines start with "rhino:" so they are easy to spot in the
Mainsail console; exit status is 0 on success and 1 on any refusal (nothing is changed on refusal).
"""
import sys

from . import pending
from .errors import Fail
from .paths import resolve
from .service import RESTART_NOTE, ToolService

ALIASES = {"feed": "feed_rate", "zoff": "z_offset", "pin": "new_pin", "enable": "enable_pin",
           "delmaterial": "del_material", "newname": "new_name", "cycle_time": "cycle"}
USAGE = "usage: python3 -m rhino [--config-dir DIR] add|edit|remove|rename|list|check|pins|pm-status KEY=VALUE ..."


def parse_kv(args):
    out = {}
    for a in args:
        if "=" not in a:
            raise Fail(f"bad argument {a!r} (expected KEY=VALUE)")
        k, v = a.split("=", 1)
        k = k.strip().lower()
        out[ALIASES.get(k, k)] = v
    return out


def _say(msg):
    print("rhino: " + msg)


def run(argv):
    config_dir = None
    if argv[:1] == ["--config-dir"] and len(argv) >= 2:
        config_dir, argv = argv[1], argv[2:]
    if not argv:
        raise Fail(USAGE)
    cmd, f = argv[0], parse_kv(argv[1:])
    svc = ToolService(resolve(config_dir))
    name = f.pop("name", "")
    if cmd == "add":
        r = svc.add({**f, "name": name})
        pending.mark(svc.paths, f"added {r['name']} (console)")
        _say(f"OK added {r['name']} (slot {r['slot']}, {r['type']}). {RESTART_NOTE}")
        [_say("note: " + w) for w in r["warnings"]]
    elif cmd == "edit":
        r = svc.edit(name, f)
        pending.mark(svc.paths, f"edited {name} (console)")
        _say(f"OK updated {name}: {', '.join(r['changes'])}. {RESTART_NOTE}")
    elif cmd == "rename":
        r = svc.rename(name, f.get("new_name", ""))
        pending.mark(svc.paths, f"renamed {name} to {r['name']} (console)")
        _say(f"OK renamed {name} to {r['name']}. {RESTART_NOTE}")
    elif cmd == "remove":
        svc.remove(name)
        pending.mark(svc.paths, f"removed {name} (console)")
        _say(f"OK removed {name}. {RESTART_NOTE}")
    elif cmd == "check":
        r = svc.check()
        _say(f"OK registry valid ({r['tools']} user-added tools); custom_tools.cfg regenerated.")
        [_say("warning: include missing from printer.cfg: " + m) for m in r["missing_includes"]]
    elif cmd == "list":
        for t in svc.list_tools():
            tag = "built-in" if t["builtin"] else "custom"
            _say(f"slot {t['slot']}: {t['name']} [{t['type']}, {tag}] materials={','.join(t['materials'])}")
        _say("OK")
    elif cmd == "pm-status":
        from .maint import MaintService
        for line in MaintService(svc.paths, svc).console_lines():
            _say(line)
    elif cmd == "pins":
        for p in svc.pin_report()["pins"]:
            _say(f"{p['pin']}: {p['state']}" + (f" ({p['owner']})" if p["owner"] else ""))
        _say("OK")
    else:
        raise Fail(USAGE)


def main(argv=None):
    try:
        run(list(sys.argv[1:] if argv is None else argv))
    except Fail as e:
        _say(f"ERROR {e} - nothing was changed.")
        return 1
    except Exception as e:  # never leave a traceback and a half-written file in the console
        _say(f"ERROR unexpected {type(e).__name__}: {e} - nothing was changed.")
        return 1
    return 0
