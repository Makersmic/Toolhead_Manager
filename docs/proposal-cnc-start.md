# Proposal: start CNC jobs from Studio's start wizard (`CNC_JOB_SETUP FROM=STUDIO`)

Nov 11 2026. **Applied Nov 11 2026 (Mike: "apply and ship 1.9.27").** The laser and drag knife got the same in 1.9.25
(`docs/proposal-studio-start.md`); Mike: "work on the wizard" for the spindle. Script: `dev/proposal_cnc_start.py`;
simulator tests: `dev/test_cnc_start.py` (they test a patched copy until it's applied).

## What changes, in one line

`CNC_JOB_SETUP FROM=STUDIO` runs the same checks, then starts the job straight away, because Studio's wizard has just
walked through the checklist, both zeros and the warm-up on screen. Three helpers get `QUIET=1` so Studio can run
each step on its own. Without `FROM=STUDIO` / `QUIET=1` nothing changes.

## Studio's steps, and what each sends

| Step | Sends | Asks first? |
|---|---|---|
| Check | nothing: the prompt's four lines, ticked | — |
| X/Y zero | the jog panel (padlock), then `_CNC_SAVE_XY QUIET=1` at the head's position | yes |
| Z zero | `SET_Z_ZERO` (Klipper's own window over the page) | yes |
| Frame (offered) | the outline 5 mm above the stock, spindle off, in work coordinates | yes |
| Warm-up | `SET_GCODE_VARIABLE MACRO=CNC_JOB_SETUP VARIABLE=duty VALUE=…` then `_CNC_WARMUP QUIET=1`; ±5 % with `_CNC_ADJUST_SPEED … QUIET=1`; Stop with `_CNC_ABORT` | yes |
| Start | `CNC_JOB_SETUP FILE=… FROM=STUDIO` | yes (a job) |

## What runs, in order

### `CNC_JOB_SETUP FILE=<f> FROM=STUDIO`

| # | Line | Same as today? |
|---|---|---|
| 1 | Refuse if a job is printing or paused; refuse unless the HotJoe is mounted | yes |
| 2 | **New:** refuse unless `SET_Z_ZERO`'s zero is for the HotJoe (cleared by a swap or restart) | new |
| 3 | **New:** refuse unless the spindle is running: relay on and throttle above 0.31 | new |
| 4 | `_RHINO_INTERLOCKS`, `_RHINO_HOOKS SLOT=before_start`, record the file | yes |
| 5 | **Skipped with FROM=STUDIO:** the prompt chain | Studio did it |
| 6 | `_CNC_START`: the bed-mesh check, then `_START_JOB_FILE` | yes, unchanged |

### The helpers

- `_CNC_SAVE_XY QUIET=1`: the same save and G54, then stops (today it goes on to the Z window).
- `_CNC_WARMUP QUIET=1`: refused without the HotJoe's Z zero; **then `_RHINO_INTERLOCKS`** (the lid), then the same
  lift, relay and ramp, without the Ready prompt. The prompt chain checks the lid in `CNC_JOB_SETUP` before the
  warm-up; Studio's order puts the warm-up first, so the check moves with it.
- `_CNC_ADJUST_SPEED QUIET=1`: the same ±5 % (0.3 to 1.0), without the Ready prompt.
- `variable_studio_start: 1` on `CNC_JOB_SETUP`: Studio uses its wizard only on a config that has this.

## What can go wrong

| Risk | What stops it |
|---|---|
| A job starts on a stopped spindle (the bit snaps or the stock moves) | `FROM=STUDIO` refuses unless the relay is on and the throttle is above the ESC's stop |
| The spindle starts with the lid open | `_CNC_WARMUP QUIET=1` runs `_RHINO_INTERLOCKS` before the relay |
| A zero from before a swap or restart | The zeroed flag (1.9.25) is per tool and cleared by every swap and restart |
| The spindle is left running if the wizard is closed | Same as the prompt chain today. The wizard has a Stop the spindle button, Control shows it running, and the idle timeout and `_TOOL_SAFE_OFF` paths are unchanged |
| Hand-typed `CNC_JOB_SETUP … FROM=STUDIO` | Studio's console asks before any `*_JOB_SETUP` line (1.9.25); the zero, spindle and lid checks still apply |
| Mainsail prompt users | Nothing changes without `FROM=STUDIO` / `QUIET=1`; the simulator compares the windows line for line |

## How it's applied and tested

- `python3 dev/proposal_cnc_start.py` prints the diff; `--apply` writes it (refused a second time).
- `dev/test_cnc_start.py`: refusals before the zero and with the spindle off; quiet X/Y zero, warm-up (lid first) and
  ±5 %; the start; a swap clears it; the prompt chain unchanged. Lint and the full macro suite pass on the patched copy.
- On the machine (`docs/testing.md`, CW1-CW4), on scrap, with the bit in and glasses on.

## Question for Mike

1. OK to apply? (Same pattern as the laser and knife; the two new refusals are the spindle running and the lid before
   the warm-up.)
