"""Sending a sliced job to the Rhino (PROTOTYPE): the checks that must all pass first.

The portal refuses to send - and refuses to start - while anything here is wrong. The same checks
run when the file is sent and again when its setup is started, because the machine can change in
between (a tool swap, a job started from Mainsail).
"""
import re

STAMP = re.compile(r"^;\s*RHINO_TOOL=([A-Za-z0-9_\-]{1,40})\s*$")
BUSY = ("printing", "paused")

# The guided setup each tool type starts with. It asks the safety questions, sets the work zero
# and starts the file itself (LASER_JOB_SETUP FILE=...).
SETUP_MACRO = {"LASER": "LASER_JOB_SETUP"}


def read_stamp(text):
    """The tool a file was sliced for, from its '; RHINO_TOOL=<name>' line (looked for in the first 50 lines)."""
    for i, line in enumerate((text or "").splitlines()):
        if i >= 50:
            break
        m = STAMP.match(line.strip())
        if m:
            return m.group(1)
    return ""


def safe_name(tool, name):
    """'LightSaber-sign.gcode' from the tool and Kiri:Moto's file name: letters, digits, - and _ only, so it
    can go into a G-code command line and Mainsail's file list as it is."""
    base = re.sub(r"\.gcode$", "", str(name or ""), flags=re.I)
    base = re.sub(r"[^A-Za-z0-9_\-]+", "-", base).strip("-")[:50] or "job"
    return f"{tool}-{base}.gcode"


VALID_FILE = re.compile(r"^[A-Za-z0-9_\-]{1,40}-[A-Za-z0-9_\-]{1,50}\.gcode$")


def conflicts(stamp, status, mounted, profiles, restart_pending):
    """-> [text, ...]: every reason the file must not be sent / started now. Empty = all clear.

    stamp            tool name from the file ('' if none)
    status           Moonraker.status(): online, klippy, print_state
    mounted          name of the tool recorded as mounted ('' if none)
    profiles         {tool name: profile} the portal can slice for
    restart_pending  tool changes saved in the portal but not loaded by Klipper yet
    """
    out = []
    if not stamp:
        out.append("This file was not sliced with a Rhino profile (no RHINO_TOOL line), so the portal cannot tell "
                   "which tool it is for. Slice it again with a Rhino machine selected.")
    elif stamp not in profiles:
        out.append(f"This file is for {stamp}, which the portal has no Slice profile for.")
    if not status.get("online"):
        out.append("The printer is not reachable (Moonraker is not answering).")
    elif status.get("klippy") != "ready":
        out.append(f"Klipper is not ready (it says '{status.get('klippy')}'). Fix that in Mainsail first.")
    else:
        if status.get("print_state") in BUSY:
            out.append(f"A job is {status.get('print_state')}. Wait for it to finish or cancel it first.")
        if not mounted:
            out.append("No toolhead is recorded as mounted. Answer the 'which toolhead is mounted?' question in Mainsail.")
        elif stamp and mounted != stamp:
            out.append(f"This file is for {stamp}, but {mounted} is mounted. Swap to {stamp} first (SWAP_TOOL).")
    if restart_pending:
        out.append("Tool changes are saved but Klipper has not loaded them yet. Restart Klipper first (banner at the top).")
    return out
