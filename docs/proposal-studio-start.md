# Proposal: start laser and drag knife jobs from Studio's start wizard (`FROM=STUDIO`)

Nov 10 2026. **Approved, not applied yet.** Design: `docs/phase-tool-wizards.md` (start wizards). Mike
(Nov 10): build the laser and knife tuning tests now, write this proposal for the start wizard. CNC follows the same
pattern later, in its own proposal.

## What changes, in one line

`LASER_JOB_SETUP` and `DRAGKNIFE_JOB_SETUP` take an optional `FROM=STUDIO`. With it, they run the same checks, then go
straight to their start step instead of showing the Mainsail prompt chain, because Studio's start wizard has just walked
through the same steps on screen. Without it, nothing changes.

## Why

Studio's start wizard shows the bed, the job's outline, the jog panel and a frame check (trace the outline with the
tool off). The prompt chain can't show any of that. Today Studio can only hand over to the prompts, so the same checklist
is answered twice and the frame check has nowhere to live.

## What runs, in order

### `LASER_JOB_SETUP FILE=<f> FROM=STUDIO`

| # | Line | Same as today? |
|---|---|---|
| 1 | Refuse if a job is printing or paused | yes |
| 2 | **New:** refuse unless `SET_Z_ZERO` was completed for LightSaber since the last tool change or Klipper restart | new |
| 3 | `_RHINO_INTERLOCKS` (refuses with the lid open) | yes |
| 4 | `_RHINO_HOOKS SLOT=before_start` | yes |
| 5 | Record the file for `_START_JOB_FILE` | yes |
| 6 | `SET_GCODE_OFFSET X=0 Y=0` (laser files use machine X/Y) | yes |
| 7 | **Skipped with FROM=STUDIO:** the checklist prompt, `_LASER_FOCUS`, `_LASER_TEST_FIRE`'s prompt, `_LASER_READY` | Studio did these |
| 8 | `_LASER_START`: refuses unless LightSaber is the mounted tool, starts the file, then `ACTIVATE_LASER` only after the file has loaded | yes, unchanged |

Studio's wizard before that call: checklist (the same five lines as the prompt), stock placement, `SET_Z_ZERO` (its own
prompt, shown inside the wizard), the frame (plain moves at the zero + 5 mm, laser off, sent through the console check
so they confirm), and the test fire (`_LASER_TEST_FIRE QUIET=1`: the same pulse, no prompt after it).

### `DRAGKNIFE_JOB_SETUP FILE=<f> FROM=STUDIO`

| # | Line | Same as today? |
|---|---|---|
| 1 | Refuse if a job is printing or paused; refuse unless DragKnife is mounted | yes |
| 2 | **New:** refuse unless `SET_Z_ZERO` was completed for DragKnife since the last tool change or restart | new |
| 3 | `_RHINO_INTERLOCKS`, `_RHINO_HOOKS SLOT=before_start`, record the file | yes |
| 4 | The G54 lines from `_DK_SAVE_Z` (X/Y work zero = machine origin), as today | yes, moved into a shared macro |
| 5 | **Skipped with FROM=STUDIO:** the checklist prompt, `_DK_TEST_CUT`'s prompts, `_DK_READY` | Studio did these |
| 6 | `_DK_START` (`_START_JOB_FILE`) | yes |

Studio's test cut step runs `_DK_TEST_CUT QUIET=1`: the same 10 mm line at the same depth, no prompt after it.

### The "zeroed" flag (the only new state)

- `SET_Z_ZERO` gets `variable_zeroed: ''`. Its SET button's macro writes the mounted tool's name there.
- `SWAP_TOOL` clears it at the start of every swap (one line). A Klipper restart clears it on its own: macro variables
  reset on restart, which is what we want, because the bed may have moved.
- `FROM=STUDIO` refuses unless `zeroed` equals the mounted tool. Without `FROM=STUDIO`, the flag is not read, so the
  prompt chain behaves exactly as today.

## What can go wrong

| Risk | What stops it |
|---|---|
| Someone types `LASER_JOB_SETUP FROM=STUDIO` by hand and skips the checklist | Studio's console check confirms every `*_JOB_SETUP` line (a job start). The zero flag and interlocks still apply; `_LASER_START` still refuses the wrong tool. The checklist is the operator's own; a hand-typed line was already able to skip it with `_LASER_START`. |
| A zero from a different stock or a different tool | The flag is per tool and cleared by every swap and restart. A new sheet of stock on the same tool isn't detected: the wizard always runs Zero before Start, and the frame check shows a wrong height before anything cuts. |
| The refusal lines abort before switching something off | `action_raise_error` aborts the whole macro before any line runs (AGENTS.md). The refusals are at the very top, before anything is switched on, so there is nothing to switch off. |
| `QUIET=1` test fire leaves the rails on | `_LASER_TEST_FIRE` ends with `SET_LASER_POWER POWER=0.0` and `DEACTIVATE_LASER` before its prompt; `QUIET=1` only skips the prompt lines after them. |
| Duplicate macro definitions | The edits change existing macros in place; no new `[gcode_macro]` with an existing name. |
| Mainsail prompt users | Nothing changes without `FROM=STUDIO`. |

## How it's applied and tested

- `dev/proposal_studio_start.py --apply`: anchored edits to `guided/laser_workflow.cfg`, `guided/dragknife_workflow.cfg`
  and `toolchanger.cfg` (SET_Z_ZERO, SWAP_TOOL), refusing a second run, like `dev/proposal_macro_hooks.py`. A test
  checks its anchors.
- Simulator tests: FROM=STUDIO refused before a zero; accepted after; refused again after a swap; the laser's rails come
  on only after the file loads; without FROM=STUDIO the prompt chain is unchanged (prompt text compared).
- On the machine (`docs/testing.md`, new SW1-SW4): each with a pass condition and a *Stop if*, on scrap stock, with
  the laser at test power.

## Mike's answers (Nov 10 2026)

1. The `zeroed` flag on `SET_Z_ZERO` and the clearing line in `SWAP_TOOL`: yes.
2. The frame check: offered, not required.
3. The start wizard's checklist: the same lines as the prompts, word for word.

Next: `dev/proposal_studio_start.py --apply` with its anchor test, the simulator tests, SW1-SW4, then Studio's start
wizard.
