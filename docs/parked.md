# Parked

Features decided against for now. They are kept here, not deleted. To un-park one, add a new entry to docs/decisions.md first (INV-B11).

The test for every feature: does it help the machine survive being left alone and be resumed safely?

| Item | Why it's parked |
|---|---|
| Timelapse | It's for videos and does nothing for a machine left alone. Mainsail or crowsnest can still do it alongside. |
| Spoolman | One user and a few spools; the materials table covers it. It would also add another service to keep running. |
| Job queue | One machine, and the tool swaps between jobs need a person anyway. |
| 3D mesh view | It's the main complaint about Mainsail's mesh page; the top-down map is clearer. |
| Mesh point editor | Klipper has no safe API for it. |
| Input shaper graphs | Run once at build time; the console output is enough. |
| Exhaustive UI tweak list | Tweaks get fixed when a page is touched for another reason, not kept as a backlog. |
| Moonraker [power] devices | Only worth doing if the 7050 setup adds a switched outlet. |
| Exclude object | Maybe later: it can save a long print, but it needs slicer labels. Revisit after slice profiles. |
| SliceBox as the recommended setup | It stays a community option. The 7050 all-in-one is the recommended setup. |
