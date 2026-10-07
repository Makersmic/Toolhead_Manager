"""When is a maintenance task due? Pure functions: no files, no clock (callers pass `now`).

A task has one or more rules and is due when ANY of them is (whichever comes first):

    {"kind": "time",  "every": 3, "unit": "months", "lead": 14, "lead_unit": "days"}
    {"kind": "meter", "meter": "prod_h", "scope": "machine"|"tool", "every": 200, "lead": 20}
    {"kind": "date",  "on": "2026-12-01", "lead": 7}                      (one-off; lead in days)

"Event" rules ("after each tool swap", "after an emergency stop") are meter rules on a count meter
with every = 1 and event = True - the count going up is the event.

lead is the EARLY ALARM: how long before the due point the task moves to "due soon", so there is
time to plan and get parts. Missing lead -> 10 % of the interval.

time rules are counted from the last completion (anchor "completion") or sit on a fixed calendar
(anchor "calendar": first due on task["first_due"], then every interval after that).

task["paused"] = {"s": seconds, "meters": {"machine.prod_h": 3.5}} is time and use that did not count
because a custom status paused the task's clock; it moves every due point later by that much (and is
cleared when the task is next done).
"""
import calendar
import datetime

STATES = ("overdue", "due_soon", "ok", "done")          # most urgent first
UNITS = {"days": 1, "weeks": 7, "months": 30.4375}       # months: only for fractions/rates
DEFAULT_LEAD_FRACTION = 0.10


# ----------------------------------------------------------------------------- calendar helpers
def _dt(ts):
    return datetime.datetime.fromtimestamp(ts)


def add_interval(ts, n, unit):
    d = _dt(ts)
    if unit == "months":
        m = d.month - 1 + int(n)
        y, m = d.year + m // 12, m % 12 + 1
        day = min(d.day, calendar.monthrange(y, m)[1])
        return d.replace(year=y, month=m, day=day).timestamp()
    return ts + float(n) * UNITS[unit] * 86400


def day_start(datestr):
    """'2026-12-01' -> local midnight timestamp."""
    return datetime.datetime.strptime(datestr, "%Y-%m-%d").timestamp()


def fmt_date(ts):
    return _dt(ts).strftime("%d %b %Y").lstrip("0")


def fmt_span_days(days):
    days = abs(days)
    if days < 1:
        h = days * 24
        return "less than an hour" if h < 1 else f"{h:.0f} h"
    if days < 14:
        return f"{days:.0f} day" + ("" if round(days) == 1 else "s")
    if days < 60:
        return f"{days / 7:.0f} weeks"
    return f"{days / 30.4375:.0f} months"


def fmt_amount(v, unit, noun):
    """200 production hours / 1000 m of filament / 50 tool swaps."""
    num = f"{v:.1f}" if unit == "h" and abs(v) < 10 and v != int(v) else f"{v:.0f}"
    return f"{num} m {noun}" if unit == "m" else f"{num} {noun}"


def fmt_qty(v, unit):
    if unit == "h":
        return f"{v:.1f} h" if abs(v) < 10 else f"{v:.0f} h"
    if unit == "m":
        return f"{v:.0f} m" if abs(v) >= 10 else f"{v:.1f} m"
    return f"{v:.0f}"


# ----------------------------------------------------------------------------- one rule
def describe(rule, meter_defs):
    """Schedule in words: 'every 3 months', 'every 200 production hours', 'after each tool swap'."""
    k = rule["kind"]
    if k == "time":
        n, u = rule["every"], rule["unit"]
        return f"every {u[:-1]}" if n == 1 else f"every {n:g} {u}"
    if k == "date":
        return "once, on " + fmt_date(day_start(rule["on"]))
    md = meter_defs.get(meter_key(rule), {})
    if rule.get("event"):
        return md.get("event", "after each " + md.get("label", rule["meter"]).lower())
    return "every " + fmt_amount(rule["every"], md.get("unit", ""), md.get("noun", rule["meter"]))


def evaluate(rule, task, now, meter_value, meter_rate, meter_defs):
    """meter_defs: {"machine.prod_h": {label, unit, noun, event}, "tool.mounts": {...}}

    -> {state, fraction, due_ts|None, due_value|None, remaining, unit, text, eta_ts, summary}

    meter_value(rule) -> current reading of the rule's meter (None if unknown)
    meter_rate(rule)  -> average use per day (None if not enough history)
    fraction is how much of the interval is used (1.0 = due), so rules can be compared."""
    last = task.get("last") or {}
    start = task.get("start") or {"at": task.get("created", now), "meters": {}}
    paused = task.get("paused") or {}
    md0 = meter_defs.get(meter_key(rule), {}) if rule["kind"] == "meter" else {}
    out = {"summary": describe(rule, meter_defs), "due_ts": None, "due_value": None, "eta_ts": None, "unit": "",
           "noun": md0.get("noun", ""), "kind": rule["kind"], "event": bool(rule.get("event"))}
    k = rule["kind"]

    if k == "date":
        due = day_start(rule["on"])
        if last.get("at") and last["at"] >= (task.get("created") or 0):
            return {**out, "state": "done", "fraction": 0.0, "remaining": 0, "text": "done " + fmt_date(last["at"]),
                    "due_ts": due}
        lead = float(rule.get("lead", 7)) * 86400
        return {**out, **_by_time(now, due, lead, max(due - (task.get("created") or now), 86400))}

    if k == "time":
        n, unit = float(rule["every"]), rule["unit"]
        if task.get("anchor") == "calendar" and task.get("first_due"):
            due = day_start(task["first_due"])
            done_at = last.get("at")
            guard = 0
            while done_at and due <= done_at and guard < 10000:
                due = add_interval(due, n, unit)
                guard += 1
        else:
            base = last.get("at") or start.get("at") or now
            due = add_interval(base, n, unit)
        due += float(paused.get("s") or 0)
        period = n * UNITS[unit] * 86400
        lead = _lead_seconds(rule, period)
        return {**out, **_by_time(now, due, lead, period)}

    # meter
    md = meter_defs.get(meter_key(rule), {})
    unit = md.get("unit", "")
    cur = meter_value(rule)
    if cur is None:
        return {**out, "state": "ok", "fraction": 0.0, "remaining": None, "unit": unit,
                "text": "no reading yet for this meter"}
    key = meter_key(rule)
    base = (last.get("meters") or {}).get(key)
    if base is None:
        base = (start.get("meters") or {}).get(key, cur)
    base += float((paused.get("meters") or {}).get(key) or 0)
    every = float(rule["every"])
    due_value = base + every
    remaining = due_value - cur
    lead = float(rule["lead"]) if rule.get("lead") not in (None, "") else every * DEFAULT_LEAD_FRACTION
    rate = meter_rate(rule)
    eta = now + remaining / rate * 86400 if rate and rate > 0 and remaining > 0 else None
    fraction = (cur - base) / every if every else 1.0
    if rule.get("event"):
        state = "overdue" if remaining <= 0 else "ok"
        n_since = cur - base
        text = (f"{md.get('label', rule['meter'])}: {n_since:.0f} since last done" if remaining <= 0
                else "not needed until the next one")
    elif remaining <= 0:
        state, text = "overdue", f"{fmt_qty(-remaining, unit)} over (due at {fmt_qty(due_value, unit)})"
    else:
        state = "due_soon" if remaining <= lead else "ok"
        text = f"{fmt_qty(remaining, unit)} left (due at {fmt_qty(due_value, unit)})"
        if eta:
            text += f", about {fmt_span_days((eta - now) / 86400)} at your usual rate"
    return {**out, "state": state, "fraction": fraction, "remaining": remaining, "unit": unit, "due_value": due_value,
            "eta_ts": eta, "text": text, "lead": lead}


def _lead_seconds(rule, period):
    if rule.get("lead") in (None, ""):
        return period * DEFAULT_LEAD_FRACTION
    return float(rule["lead"]) * UNITS[rule.get("lead_unit") or "days"] * 86400


def _by_time(now, due, lead, period):
    left = due - now
    days = left / 86400
    if left <= 0:
        state, text = "overdue", f"overdue by {fmt_span_days(days)} (was due {fmt_date(due)})"
    else:
        state = "due_soon" if left <= lead else "ok"
        text = f"due {fmt_date(due)}, in {fmt_span_days(days)}"
    return {"state": state, "fraction": 1.0 - left / period if period else 1.0, "remaining": days, "unit": "days",
            "due_ts": due, "eta_ts": due, "text": text, "lead": lead / 86400}


def meter_key(rule):
    """Key under which a completion snapshot stores this rule's reading: 'machine.prod_h' / 'tool.prod_h'."""
    return ("tool." if rule.get("scope") == "tool" else "machine.") + rule["meter"]


# ----------------------------------------------------------------------------- whole task
def task_status(task, now, meter_value, meter_rate, meter_defs):
    """Combine the rules: the most urgent state wins; 'next' is the rule closest to due."""
    rules = [evaluate(r, task, now, meter_value, meter_rate, meter_defs) for r in task.get("rules", [])]
    if not rules:
        return {"state": "ok", "rules": [], "next": None, "fraction": 0.0, "snoozed": False}
    order = {s: i for i, s in enumerate(STATES)}
    live = [r for r in rules if r["state"] != "done"] or rules
    worst = min(live, key=lambda r: (order[r["state"]], -r["fraction"]))
    state = worst["state"]
    snoozed = bool(task.get("snooze_until") and now < task["snooze_until"] and state in ("overdue", "due_soon"))
    etas = [r["eta_ts"] for r in live if r.get("eta_ts")]
    return {"state": state, "rules": rules, "next": worst, "fraction": max(r["fraction"] for r in live),
            "snoozed": snoozed, "eta_ts": min(etas) if etas else None}
