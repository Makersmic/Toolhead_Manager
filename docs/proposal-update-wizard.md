# Proposal: updating the Rhino safely (a wizard)

Nov 23 2026. **For Mike's review: nothing is built.** Follows `docs/wizard-rules.md`. For people after Mike: an update is the moment a
machine left alone is most likely to be broken by hand, and today it is several separate places.

## Why

Today an update is: Settings > Software (the Tool Manager release, from GitHub or a zip), Settings > Host (Back up now), the Rhino menu on
the host (`rhino.sh` option 7 to check, option 4 to undo). Nothing says "back up first", "no job running", "this release changes Klipper
macros, so keep a hand near Stop", or "if it looks wrong, here is how to go back". Undo exists, but only over SSH.

## The wizard (five steps)

1. **Before.** Read only: the installed and the newest release; whether a job is running (updates are refused then); free disk space; the
   age of the last backup; and **what the release changes**, in plain words, with a clear flag when it changes **Klipper macros** or
   the Portal's service file ("keep a hand near Stop afterwards; here are the checks"). Source: the release's notes (see open question 2).
2. **Back up.** Runs the existing Back up now and waits for it, showing the result. It doesn't go on if the backup failed.
3. **Install.** The existing install (`update-github`, or an uploaded zip), through the root-owned updater, as today. Shows progress
   and says what to expect: the Portal restarts and Studio reconnects by itself; Klipper restarts only if the release needs it.
4. **Check.** Studio reconnects; runs the Health check page's check; shows before and after side by side (version, Fix/Look counts, Klipper
   Ready); lists the on-machine checks for macro changes taken from `docs/testing.md`'s section for that release (see open question 3).
5. **If something is wrong.** Plain steps to go back: what Undo does and how to start it (today: `rhino.sh` option 4 on the host over
   SSH, with the command written out in the "What this does" box). See "Undo from Studio" below.

Writes no G-code, so the edit rule has nothing to apply to here; the "What this does" boxes show the real commands and files.

## What it needs

- **Reads:** `GET /api/update/preflight` (new, read only: job state, free space on the config and home disks, last backup age, installed and
  latest version, the notes text). Everything else exists: `backup-now`, `update-github`, `update-upload`, `update-install`, `GET /api/health`
  and the health run.
- **Studio:** `src/views/UpdateWizardView.vue`; plain logic in `src/update/` (the before/after comparison, the macro-change flag) with tests.
  Entry points: a "Update the Rhino" button on Settings > Software, replacing today's bare Update for the Tool Manager row.
- **Klipper, Moonraker, OS packages** (the rest of the Software page) stay as they are, with one warning added to the Klipper row: a Klipper
  update can need the **boards' firmware** to be flashed again, and a mismatch makes Klipper refuse to start. The wizard doesn't flash
  boards. (Out of scope; the warning is the cheap part.)

## Undo from Studio (optional second stage)

Going back is the step most worth making easy and the most dangerous to get wrong. Proposed as its own stage, built only if Mike wants it:
the updater (root-owned, started by a request file like an install) gains an "undo the last install" request that runs what
`uninstall.sh` and `rhino.sh` option 4 do today, then restarts the Portal. Risks: it changes the root-owned updater, the one piece the
Portal can't hold itself to (the Portal only drops a request file), and an undo during a job must be refused. Its own write-up and
tests would come first.

## What can go wrong

- **An install that hangs or fails half-way.** The existing updater has a 45-minute limit and keeps a backup of the config first; the
  wizard reads the updater's status file and says which stage it stopped at. Never a second install while one runs (the Portal already
  refuses).
- **The Portal restarts, so Studio loses it for a moment.** The wizard says so first, then waits and reconnects. It can't tell a
  restart from a hang, so after 2 minutes it points to the Health check and the host.
- **A job starts during the wizard.** The install step re-checks the job state right before it starts.
- **A release with a macro change goes unchecked.** The flag in step 1 and the list in step 4 are there for that; the wizard can't run the
  machine checks for the person, and says so.

## Open questions for Mike

1. Should step 5 only explain Undo (the SSH command), or do you want Undo from Studio (the second stage)? Proposed: explain first.
2. **Release notes:** the wizard needs the change list for the newest release before downloading it. Today the Portal reads GitHub's
   release record, not `CHANGES.md`. Proposed: the release workflow puts that release's `CHANGES.md` entry in the release notes, and
   the notes start with a line "Klipper macros change: yes/no" the wizard can read. (That changes the release workflow, which is yours to
   approve.)
3. Pull the on-machine checks for a release from `docs/testing.md` into the wizard, or only link to the document? Proposed: only link
   at first; reading headings out of a markdown file is fragile.
4. Do you want the wizard to refuse an update when the last backup is older than a day, or only warn? Proposed: it makes the backup itself
   in step 2, so the age only matters for a skipped step: warn only.

## Tests and checks

Unit tests for the comparison and the flags; Portal test for the preflight route; headless run against the mock, light and dark, desktop,
phone and 760 px, one screenshot round. On the machine (new section in `docs/testing.md`): UW1 a full update from one release to the
next on a spare host first; UW2 a job running blocks it with a clear message; UW3 the check step's before and after match the Health check
page; UW4 pulling the network cable mid-install leaves a machine that comes back (the existing updater's behaviour, now with a wizard
watching). Each with a pass condition and a *Stop if*.
