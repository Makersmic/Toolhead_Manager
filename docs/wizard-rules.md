# Rules for Rhino wizards

Nov 23 2026. Set with Mike for every wizard built from here on (the connect and access wizard, the nozzle cleaning wizard, the update wizard,
the park spot wizard), and the older ones (Add a toolhead, Add hardware, the start wizards, tuning) when they are next touched.
The aim: a newcomer can follow the plain words, an expert can see and change exactly what is going to happen. Nothing is dumbed down and
nothing is hidden.

1. **One plain sentence per step, and a "What this does" under it.** The sentence says what the step is for. The folded "What this does"
   shows the real thing: the setting, the file, the command or the G-code. It is closed by default and always one click away.
2. **A wizard that writes G-code or config shows it, and lets you edit it** (Mike, Nov 23: "an advanced user may want to add or edit
   something"). The review step has the generated text in a box with **Edit**; **Reset to what the wizard wrote** puts it back.
   - Edited text is checked again by the Portal before it is kept, with the same rules as everywhere else: no line breaks in a value, no
     internal macros (leading `_`), none of the never-from-a-button commands (`M112`, `SAVE_CONFIG`, restarts, `FORCE_MOVE`,
     `SET_KINEMATIC_POSITION`, `SET_STEPPER_ENABLE`), numbers inside the machine's limits. A refused line is shown with the reason,
     and the text isn't saved.
   - An edited block is marked as edited. Running the wizard again says so, and asks whether to keep the edits or start again from the
     wizard's text. It never replaces edits without asking.
   - What an edit can't do: weaken a safety rule in `AGENTS.md` (`_TOOL_SAFE_OFF` on every end, cancel and swap path, interlocks,
     heater caps). Those lines aren't in the editable part.
3. **The result is an ordinary file** the person could have written by hand (a Portal-owned generated file, a Studio macro, a line in
   `moonraker.conf` through the existing safe editor). The wizard is a convenience, not a lock-in.
4. **Nothing can lock you out.** Network changes keep the Rhino's existing "switches back by itself unless you keep it" (2 minutes).
   Trust changes never remove the entry that lets this screen or the Portal in.
5. **Anything that moves the machine says so first,** runs a slow dry run before a real one where that makes sense, and says "keep a hand
   near Stop". Heat is never switched on by a wizard beyond the temperature the person typed and the heater's own limit.
6. **Read before write.** Every wizard starts with a read-only look at what is there now, shows it, and only then offers a change.
7. **One mascot pose per step** (`src/brand/mascot.ts`), as in the existing wizards. The pose never carries meaning alone.
8. **Each wizard has on-machine checks in `docs/testing.md`** with a pass condition and a *Stop if*.
