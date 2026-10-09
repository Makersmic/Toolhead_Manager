"""Klipper's questions (the pop-ups Mainsail shows) for the portal (PROTOTYPE).

Rhino's guided macros ask through Klipper's prompt messages: RESPOND TYPE=command MSG="action:prompt_..."
Klipper prints them as '// action:prompt_begin <title>', '// action:prompt_text ...', '// action:prompt_button
<label>|<command>|<colour>', '// action:prompt_show', '// action:prompt_end'. Moonraker keeps the recent lines
in its G-code store, which is what the portal reads - the same lines Mainsail draws its pop-up from, so both
always show the same question.

The portal never lets the page send a command: the page says which button (by number) of which question
(by its id); the portal reads the question again, checks it is still the one showing, and runs that button's
own command.
"""
import re

PREFIX = "// action:"
COLORS = ("primary", "secondary", "info", "warning", "error", "success")


def _button(body):
    bits = body.split("|")
    label = bits[0].strip()
    cmd = bits[1].strip() if len(bits) > 1 and bits[1].strip() else label
    color = bits[2].strip() if len(bits) > 2 and bits[2].strip() in COLORS else "secondary"
    return {"label": label, "command": cmd, "color": color}


def current(entries):
    """The question showing now, or None.

    entries: Moonraker G-code store, oldest first: [{"message": str, "time": float, "type": str}, ...].
    -> {"id": str, "title": str, "items": [{"text": str} | {"group": [button, ...]}], "footer": [button, ...],
        "buttons": [button, ...]}   (buttons = every button in order, footer last - what press() numbers)
    """
    building, shown = None, None
    for n, e in enumerate(entries or []):
        if not isinstance(e, dict) or e.get("type") == "command":
            continue          # lines typed in the console are not Klipper's output
        for raw in str(e.get("message", "")).splitlines():
            line = raw.strip()
            if not line.startswith(PREFIX):
                continue
            a = line[len(PREFIX):]
            if a.startswith("prompt_begin"):
                building = {"id": f"{e.get('time', 0)}-{n}", "title": a[len("prompt_begin"):].strip(),
                            "items": [], "footer": [], "_group": None}
                shown = None
            elif building is None:
                if a.startswith("prompt_end"):
                    shown = None
                continue
            elif a.startswith("prompt_text"):
                building["items"].append({"text": a[len("prompt_text"):].strip()})
            elif a.startswith("prompt_button_group_start"):
                building["_group"] = []
                building["items"].append({"group": building["_group"]})
            elif a.startswith("prompt_button_group_end"):
                building["_group"] = None
            elif a.startswith("prompt_footer_button"):
                building["footer"].append(_button(a[len("prompt_footer_button"):].strip()))
            elif a.startswith("prompt_button"):
                b = _button(a[len("prompt_button"):].strip())
                if building["_group"] is not None:
                    building["_group"].append(b)
                else:
                    building["items"].append({"group": [b]})
            elif a.startswith("prompt_show"):
                shown = building
            elif a.startswith("prompt_end"):
                building, shown = None, None
    if not shown:
        return None
    out = {k: v for k, v in shown.items() if k != "_group"}
    out["buttons"] = [b for it in out["items"] for b in it.get("group", [])] + list(out["footer"])
    return out


SAFE_COMMAND = re.compile(r"^[^\n\r]{1,300}$")


def button(prompt, number):
    """The button with this number (0-based, footer last) of the question, or None."""
    if not prompt or not isinstance(number, int) or not 0 <= number < len(prompt["buttons"]):
        return None
    b = prompt["buttons"][number]
    return b if SAFE_COMMAND.match(b["command"]) else None
