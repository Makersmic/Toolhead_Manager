# Macro builder (one-page design draft)

Oct 25 2026. **Draft for Mike's review. No code before the 7050 migration is accepted.**
This un-parks the visual macro builder (decisions.md, 2026-10-25) in a durable form.

## What it's for

Short routines you do by hand today, saved as a button: "park and cool down", "heat for PETG and purge",
"go to the laser's focus spot". They're built from a list of steps, without writing Klipper config.

Durability filter: your macros live on the Rhino and are in the backup, so they survive a cleared browser, a new
device and the 7050 move. They can't do anything the console wouldn't ask about first.

## Where they live

- **Store:** `config/myrhino/user_macros.json`. It follows the slice-profile pattern: schema version, validation on every
  save, atomic writes, a `rev` on every save (a stale one is refused), the last 5 revisions, and delete with undo for 30 days.
  It's in the config folder, so the backup and klipper-backup include it with no extra work.
- **A macro:** `{id, name, toolheads: [] (empty = any), steps: [...], notes, rev}`, with up to 30 steps.

## Steps (picked from a list, never free-form by default)

| Step | Fields | Becomes |
|---|---|---|
| Home | all / XY / Z | `G28` … |
| Move to | X, Y, Z (blank = stay), speed | `G90` + `G1`, checked against Klipper's travel limits when saved and again when run |
| Move by | dX, dY, dZ, speed | `G91` + `G1` + `G90` |
| Set temperature | hotend / bed, °, wait yes/no | `M104`/`M109`, `M140`/`M190` |
| Part fan | 0–100 % | `M106`/`M107` |
| Wait | seconds | `G4` |
| Run a macro | picked from Klipper's own macros (`_INTERNAL` ones hidden) | its name |
| Message | text | `RESPOND MSG=` |
| G-code line *(advanced, off unless turned on)* | one line | as typed, classified like the console |

**Left out on purpose:**
- Turning on a laser or spindle (that stays with the setup wizards).
- `M112`, `SAVE_CONFIG`, `FIRMWARE_RESTART`, `SET_KINEMATIC_POSITION`, `FORCE_MOVE`.
- Loops, conditions and variables.

## Running one (the safety gate)

- **Same check as the console.** A run builds the G-code, then sends it through `check()` → `approve()` in `src/control/commands.ts`.
  Anything the console asks about (motion, power, tool state, restart) is listed in one confirm dialog before anything
  is sent. Heat-only and message-only macros run without asking, like the console.
- **Heater rules still apply.** The store still refuses a hotend target unless a confirmed print head is mounted, and
  the bed limit is 130°.
- **When it can run:**
  - Not during a job.
  - Only when its toolhead is the one mounted and confirmed (an "any toolhead" macro still needs a confirmed tool).
  - Moves need the axes homed first, or a Home step before them.
- **Stopping a run:** Stop in the top bar stops it, as it does everything else. A run in progress shows in the console.

## Where you see them

- **Running them:** Control › Macros gets a **Your macros** group, showing the mounted tool's macros first, like today's groups.
- **Editing them:** **Settings › Macros** has the list and the editor:
  - steps as rows, each with ↑ ↓ to reorder and × to remove
  - **+ Add step**, which opens the step list
  - a read-only **G-code preview** underneath
  - **Save** and **Test run** (Test run goes through the same gate)
- **No drag-and-drop canvas.** A list reads the same on the phone.

## Portal

- **Routes:** `/api/user-macros`. It works the same way as slice profiles: list, get, create, save with rev, delete, history, revert, undelete, export, import.
- **Studio:** a reviewed `PORTAL_MACROS` allowlist.
- **Validation:** the Portal checks every step's fields and limits again on each save.
- **The Portal never runs a macro.** It only stores them, and running goes through Studio's console path.

## Tests

- **Off the machine:**
  - TM: validation, revisions, and the refused steps.
  - Studio: each step's G-code, the gate's classification of every step type, travel limits, and the tool and job rules.
- **On the machine:** MB1–MB8: build, run, edit on the phone, refused during a job, refused on the wrong tool, back up and restore.

## Questions for Mike

1. **Studio-only macros** (lean): they run from Studio's buttons, but Klipper doesn't know them, so `END_PRINT` or Mainsail can't call them.
   The alternative is the Portal writing them into a generated `user_macros.cfg` that Klipper loads. Anything could call them
   then, but every edit needs a Klipper restart, and generated Klipper config is what we've kept small on purpose.
2. Do you want the **advanced G-code line** step at all, or only the fixed steps?
3. Any routines you want built in as starting examples? List two or three you do by hand most.
