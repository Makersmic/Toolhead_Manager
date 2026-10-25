# Rhino invariants (v1)

v1, Oct 25 2026. Checked against Studio `6158f74` and TM `e7033ab`. This file is the spec Phases 1–4 build against.

**How it works**
- Every invariant has an ID, a rule and a reason.
- Code that enforces one cites it in a comment (`// INV-A4`).
- Tests that prove it put the ID in the test name (`it('INV-A4: …')`).
- Phase 4 adds a check script for this (INV-B13). Nothing cites an ID yet.
- IDs are grouped by subject, not by phase; the Phase column gives the timing.

**Status key**
- ✅ enforced in code and covered by a test
- ⚠ enforced, but no test found (gap)
- ✎ the rule was changed in v1 to match the code
- ⏳ not built yet

## Part A: machine safety

| ID | Rule | Reason | Status / where |
|---|---|---|---|
| A1 | Nothing reaches Moonraker except through an allowlisted method: READ_ONLY_METHODS, ACTION_METHODS or CAMERA_METHODS. | Every other guarantee depends on this boundary. | ✅ `src/moonraker/client.ts` |
| A2 | G-code reaches the machine only as a `CheckedScript`, and only two functions make one. `approve(check(…))` covers everything typed or clicked. `fromPrompt()` covers Klipper prompt buttons, which pass as-is because Klipper's own macro wrote them (see A11). | A script that hasn't been checked can't be written at the call site. | ✎ ⚠ v0.1 said "the classifier is the only producer", which is false (`fromPrompt` is a second, deliberate one). No test asserts that only these two exist. |
| A3 | Every G-code line is classified. Anything that moves the machine, powers a tool, changes the recorded tool, restarts Klipper, starts a job or runs an `_internal` macro asks first and names what it does. | A line that slips through unclassified is an unguarded action. | ✅ `commands.ts`, `commands.test.ts` |
| A4 | Stops (M112, `printer.emergency_stop`) never ask. | A stop that asks can be delayed. | ✅ `machine.ts` → `client.emergencyStop()` |
| A5 | The mounted tool comes only from Klipper. The Rhino adapter reads `gcode_macro SWAP_TOOL.current_tool`; the toolchanger adapter reads `printer.toolchanger`. The UI never sets, guesses or keeps the mounted tool across a disconnect or a restart. | A remembered tool is a tool-swap hazard. | ✅ `src/tools/adapters/*`, `adapters.test.ts` |
| A6 | After a Klipper restart, the saved slot is shown as "last saved", never as mounted. | Until RESTORE_TOOL is answered, `current_tool` is 0. | ✅ |
| A7 | Portal writes are allowlisted by kind, and each kind maps to one fixed request (WRITE_ROUTES). Anything else is refused in the browser. | Same boundary as A1, applied to the Portal. | ✅ |
| A8 | The on-screen E-stop doesn't replace a physical E-stop or power switch. | The browser, network, host or Moonraker can all fail. | doc rule (README) |
| A9 | A camera picture can lag or freeze; it is not a safety device. | Same reason as A8. | doc rule (README) |
| A10 | The Dashboard is look-only: it has no buttons that act on the machine. When Klipper asks a question, the Dashboard shows a notice and the answer is given on Control. | The Dashboard is the always-on screen. | ⚠ Checked by reading the code: the only `@click`s are the chart/table toggles. No test. |
| A11 | A prompt button runs only its own command. `action:…` buttons are sent back as `RESPOND TYPE=command MSG="action:…"`. | A button that ran anything else would be an escalation path. | ✅ `fromPrompt`, `prompts.test.ts`. Rejects empty commands, commands over 300 characters, and commands with newlines. |
| A12 | Setting a temperature doesn't ask. Hotend range is 0–300 °C, bed 0–130 °C. The hotend can be set only when a confirmed print head (DEPOSITION) is mounted. Switching a heater off is always allowed. | The heater output stays wired to the tool connector whatever tool is mounted; that is a config fact. | ✅ `commands.ts:272`, `control.ts` `hotendSettable` |
| A13 | Start is blocked unless the mounted tool is confirmed and matches the file's `; rhino_toolhead`. A file with no toolhead gets a warning. Cancel and Resume ask; Pause doesn't. | Starting with the wrong tool is the most common slip. | ✅ `jobs.ts`, `jobs.test.ts` |
| A14 | Maintenance never blocks a job. Overdue care appears in the start confirmation and nowhere else. | Blocking on things that aren't safety issues trains people to override. | ⚠ `FileBrowser.vue` ("Nothing is blocked; it's your call"). No test. |
| A15 | Jogging is locked until unlocked. It locks again after 60 s idle, on leaving the screen, when the page is hidden (phone lock or app switch), and whenever `motionBlock` is set (Klipper not ready, job running, swap under way, tool change). Jogging needs a confirmed tool and homed axes, and refuses moves past the machine's travel. | Each item on the list is a way to lose attention. | ✅ `control.ts` (`UNLOCK_MS`, `visibilitychange`, `watch(motionBlock)`), `MotionPanel` unmount |
| A16 | One tap is one fixed step. There is no hold-to-move. | A lost touch or dropped Wi-Fi can't leave the machine moving. | ⚠ Checked by reading the code: no repeat or pointer-hold handlers in `src/control`. No test. |
| A17 | Toolchanger adapter: if the tool sensor disagrees with the selection, that is a stop, and Swap and Home are locked too. Tool-change commands from every family (T*, SELECT_TOOL, INITIALIZE_TOOLCHANGER, SET_DUAL_CARRIAGE…) ask first. | When the sensor disagrees, the machine's own state can't be trusted. | ✅ |
| A18 | Generated jobs call the existing macros (START_JOB, SWAP_TOOL, END_PRINT, *_JOB_SETUP) rather than raw tool-change or power G-code. | The macros carry the machine's own safety checks. | ✅ |
| A19 | Prepared files never heat, home, swap, restart, change work zeros, or switch a tool's power on. The laser rail comes on in `_LASER_START`. The spindle starts in `CNC_JOB_SETUP`. In drag-knife files, the plunges are the file's own and the starts belong to `DRAGKNIFE_JOB_SETUP`. | Run outside their wizard, these files can't fire anything. | ✅ |
| A20 | Every prepared file is read back line by line before it can be sent. A failed check blocks both Send and Download, for Kiri:Moto and PrusaSlicer output alike. | This checks what arrives back from the slicer. | ✅ `check.ts`; `prepare.ts:448/463` gate; `slicer.test.ts`, `upload.test.ts` |
| A21 | Bed mesh: making a mesh needs a confirmed print head. Nothing mesh-related runs during a job. The spindle never cuts with a mesh loaded (`_RHINO_MESH_OFF_FOR_CNC`, `_RHINO_MESH_CNC_CHECK`). Remove asks. Save asks, and lists pending items that aren't the mesh. | The probe, the job's moves and the spindle depth all depend on the mesh. | ✅ TM `myrhino/bed_mesh.cfg`, `dev/test_mesh.py`; Studio `stores/bedmesh.ts` |
| A22 | A job loads the saved mesh within 5 °C of its bed temperature (`variable_match_c 5`). Cold matches cold; otherwise the closest, then the newest; never an adaptive mesh. Nothing is probed per print. With no match, the file is held and you choose: Probe / Use closest / Print without / Cancel. Nothing probes before a button is pressed. | This was Mike's requirement: a prompt with a Cancel, like the PLA bed bypass. | ✅ TM `_RHINO_JOB_MESH`, `test_mesh.py` |
| A23 | RHINO_MESH_CALIBRATE refuses bad names, `adaptive-*` names, a bed temperature above heater_bed max_temp, and a soak over 60 min. | Each refusal closes off a mesh the machine shouldn't use. | ✅ `test_mesh.py` |
| A24 | SWAP_TOOL, RESTORE_TOOL and the job-setup prompts are answered in Studio's prompt UI, under A11. | The wizard is the tool-change procedure. | ✅ |
| A25 | The status strip shows the two cross-tool hazards in inverted ink, and they can only be switched off from there: a heater on or hot under a tool that doesn't have it, and a bed heating or still at ≥ 40 °C under a laser, spindle or knife job. | The per-tool readouts would otherwise hide both. | ⚠ `StatusStrip.vue`. No test. |
| A26 | Console commands go through the same `control.send()` check as everything else. This guards against slips, not against intent. | It is a full console by design. | ✅ `ConsolePanel.vue` → `control.send` |

## Part B: durable state

| ID | Rule | Reason | Phase / status |
|---|---|---|---|
| B1 | Durable state lives in the config folder: `*.cfg`, `variables.cfg`, `variables.save`, and the Portal objects in `config/myrhino/` (`custom_tools.json` holding tools and hardware, `portal_lists.json`, `umbilical.json`, `maintenance/*`). From Phase 1 that adds `slice_profiles.json`. **The browser holds nothing durable.** | State outside it can be lost. | ✎ The file list is now exact (v0.1 named objects that don't exist as such). Breaks today: slice settings live in localStorage `rs.prepare.jobs`; fixed in Phase 1. |
| B2 | Objects added from Phase 1 on are versioned by the Portal. Each save makes a new revision, the last 5 are kept per object, and old ones are pruned on save (not by a background job). Objects older than Phase 1 are versioned by the backup's history. | Versioning makes restore and "what changed" answerable. | ✎ Option (a) taken. The rule as v0.1 wrote it is false today for tools, lists and maintenance. Phase 1. |
| B3 | Every durable object can be exported and imported as a file. | That is the way out if the host is lost. | ✅ whole store, 1.7.0: `rhino/backup.py`, `dev/test_backup.py` (download, upload checked file by file). Phase 1 adds profiles. |
| B4 | A backup is either complete or refused. It is never silently partial. | A partial backup that looks complete is worse than a failed one. | ✅ 1.7.0: `BackupService._create`, `dev/test_backup.py` ("INV-B4: …") |
| B5 | What the backup covers is the table in `docs/phase0-spine.md` § Backup inventory, and only there. Three items are **Phase 2 gates**: klipper-backup's `backupPaths`, whether `variables.save` is ignored by git, and whether PrusaSlicer has a saved profile on the Pi. | A copied inventory drifts. | ✅ 1.7.0: `backup.DOC_ROWS` / `INVENTORY`; `dev/test_backup.py` ("INV-B5: …") checks the table and the code agree. Gates answered Oct 25. |
| B6 | Slice profiles live only in `config/myrhino/slice_profiles.json`. The engine uses a profile; it doesn't own it. | The profile is the thing worth keeping. | ⏳ Phase 1 |
| B7 | A profile is engine-native: one engine's settings plus a shared header. Switching engines means choosing that engine's profile. There is no cross-engine translator. | Kiri and Prusa settings don't map one-to-one, and a translator would print differently without saying so. | ✅ Holds today: each job has its own `engine` field, the Kiri and Prusa paths are separate, and no translation code exists. Phase 1 keeps it that way. |
| B8 | The welcome-back summary never claims a backup or a state that isn't actually in the durable store. | It's the screen you trust after being away. | Partly ✅ 1.7.0: the Backups panel's GitHub line never says "pushed" unless the last push worked (`dev/test_backup.py`, `backup.test.ts`, "INV-B8: …"). The summary itself is Phase 3. |
| B9 | The summary shows, at minimum: jobs since you left, maintenance logged and overdue, the mounted tool, the last backup, the newest mesh's age, and next steps. | That is the minimum for it to be useful. | ⏳ Phase 3 |
| B10 | "Away" means time since the later of the last job's end and the last Studio visit. The Portal records visits. There is no toggle. | It can be worked out without anyone remembering to do something. | ⏳ Phase 3 |
| B11 | Parked features are listed in `docs/parked.md` with a reason each, and none is built without a new entry in `docs/decisions.md`. | That keeps them parked. | ✅ Created today |
| B12 | Every capability the README claims has a matching row in the "cannot do" table, or a reason why not. | A capability with no stated limit is an unstated risk. | ⏳ Phase 4 |
| B13 | Every invariant here is cited by at least one test, and every safety test cites an invariant. A check script enforces this. | An invariant with no test is only a hope. | ⏳ Phase 4 (0 citations today) |

## Part C: cross-cutting

| ID | Rule | Reason | Phase / status |
|---|---|---|---|
| C1 | A durable-state write that changes machine behaviour goes through the same confirm path as the matching machine action. | The durable-state layer mustn't become a way around the safety layer. | Verify now for tools and materials; Phase 1 for profiles |
| C2 | Part A applies whichever engine produced the G-code. If PrusaSlicer is made first-class, that means four things: (a) a Portal profile type, (b) the A20 check path, (c) the README safety section, (d) the job-setup flow. The 7050 load test decides whether it is. | This defines "first-class" before the decision, not by feel afterwards. | (b) ✅ already true (`prepare.ts:425/432`). Criteria recorded in decisions.md. |
| C3 | If the Portal is down, slow or inconsistent, that never blocks a safety action. Stop goes straight to Moonraker, and the macros are the fallback. | The Portal is a store, not an interlock. | ⚠ True by design (`emergencyStop` doesn't touch the Portal). Mock test (Portal down → Stop still works) belongs in Phase 4. |
| C4 | `docs/decisions.md` is the append-only record of why things were decided. Invariants cite decisions. | Durable decisions belong somewhere durable. | ✅ Created today, seeded from the Oct 23 handoff |

## Gaps to close in Phase 4

Add tests for A2 (only two producers), A10 (Dashboard has no machine actions), A14 (maintenance never blocks), A16 (no hold-to-move), A25 (cross-tool labels) and C3 (Portal down). Then add the B13 check script and cite IDs across the code.

## v0.1 → v1

- **A2:** now names both CheckedScript producers.
- **A10, A14, A16, A25, C3:** marked as test gaps.
- **A12, A15, A20, A26:** file locations added.
- **B1:** exact file list.
- **B2:** option (a).
- **B7:** confirmed against the code.
- **C2 (b):** confirmed.
- **B11, C4:** files created.
