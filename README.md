<p align="center">
  <img src="manual/img/welcome.jpg" alt="Rhino Multi Motion System" width="100%">
</p>

<h1 align="center">Rhino Tool Manager</h1>

<p align="center">
  <b>One Klipper machine, five swappable toolheads - printing, laser, CNC and drag knife.</b><br>
  Safe tool swaps, a web portal for every tool, and maintenance tracking, all built on Klipper and Mainsail.
</p>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-1.3.5-2196f3">
  <img alt="Klipper" src="https://img.shields.io/badge/firmware-Klipper-b12f36">
  <img alt="Mainsail" src="https://img.shields.io/badge/UI-Mainsail-d51f26">
  <img alt="Python" src="https://img.shields.io/badge/portal-Python%20%2F%20Flask-3776ab">
  <img alt="OrcaSlicer" src="https://img.shields.io/badge/slicer-OrcaSlicer-009688">
</p>

## The toolheads

<table align="center"><tr><td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="rhino/portal/static/img/tools/blockone-dark.png"><img src="rhino/portal/static/img/tools/blockone-light.png" alt="blockone" height="150"></picture></td><td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="rhino/portal/static/img/tools/switchfly-dark.png"><img src="rhino/portal/static/img/tools/switchfly-light.png" alt="switchfly" height="150"></picture></td><td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="rhino/portal/static/img/tools/lightsaber-dark.png"><img src="rhino/portal/static/img/tools/lightsaber-light.png" alt="lightsaber" height="150"></picture></td><td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="rhino/portal/static/img/tools/hotjoe-dark.png"><img src="rhino/portal/static/img/tools/hotjoe-light.png" alt="hotjoe" height="150"></picture></td><td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="rhino/portal/static/img/tools/dragknife-dark.png"><img src="rhino/portal/static/img/tools/dragknife-light.png" alt="dragknife" height="150"></picture></td></tr><tr><td align="center"><b>BlockOne</b><br><sub>3D printing</sub></td><td align="center"><b>SwitchFly</b><br><sub>Dual-extrusion printing</sub></td><td align="center"><b>LightSaber</b><br><sub>80 W laser</sub></td><td align="center"><b>HotJoe</b><br><sub>CNC spindle</sub></td><td align="center"><b>DragKnife</b><br><sub>Drag knife</sub></td></tr></table>

Rhino Klipper config for BTT Octopus v1.1, plus a tool-management package: add your own toolheads
(hot wire, needle cutter, other powered or passive tools, new nozzle sizes) from a web portal
with drop-down menus, typed names and photos - or from the console. Each tool can bring its own
extra controls (relays, fans, servos, switches - set up by describing what they do) and macros,
and the portal tracks preventive maintenance for the machine and every tool.

## The portal

A dashboard on port 5000 that follows Mainsail's light or dark theme and colour.

![Dashboard](docs/images/dashboard-top.png)

<sub>Toolhead hours and jobs on the left, maintenance on the right. [Full dashboard](docs/images/dashboard.png).</sub>

<table>
<tr>
<td width="50%"><b>Tool library</b><br>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/library.png"><img src="docs/images/library-light.png" alt="Tool library"></picture></td>
<td width="50%"><b>Each tool's own page</b>: connector and pins, materials, macros<br>
<img src="docs/images/tool-page-light.png" alt="LightSaber tool page"></td>
</tr>
<tr>
<td><b>Pin map for every tool</b><br><img src="docs/images/tool-page.png" alt="BlockOne tool page"></td>
<td align="center"><b>Works on a phone</b><br><img src="docs/images/phone-dashboard.png" alt="Phone dashboard" width="260"></td>
</tr>
</table>

## Maintenance at a glance

<a href="docs/maintenance/"><img src="docs/maintenance/00-preview.png" alt="Due and upcoming maintenance" width="100%"></a>

<sub>A year of maintenance on the Rhino: what's due, what's on hold for parts and what's coming up.
<a href="docs/maintenance/">See the full maintenance showcase &rarr;</a></sub>

## What's in it

| | |
|---|---|
| 🔁 **Safe tool swaps** | `SWAP_TOOL` parks the bed at a safe height, homes X/Y only, and won't home Z with a laser, spindle or knife mounted |
| 🧾 **Job guard** | A sliced file says which tool it needs; the job stops if a different tool is mounted |
| 🌡️ **Print start** | Tool-and-material check, preheat, prime line and pressure advance before the file runs |
| 📏 **Paper-test Z** | `NOZZLE_HEIGHT_CALIBRATE` - a Mainsail button for setting nozzle height |
| 🎯 **Set Z zero by eye** | `SET_Z_ZERO` for the laser (at focus), spindle and drag knife - bed up/down, then SET |
| 🛠️ **Add your own tools** | Hot wire, needle cutter or any powered or passive tool, from the portal with photos |
| 🧰 **Maintenance** | Tasks by hours, jobs, swaps or calendar, for the machine and every tool, with a work log - [see it in action](docs/maintenance/) |
| 🖨️ **OrcaSlicer profiles** | BlockOne printer, process, PLA and PETG in `slicer/orca/` |
| 📦 **Menu installer** | KIAUH-style menu: preview, install, update from a zip, undo from a backup |
| 📘 **User manual** | `manual/Rhino-User-Manual.pdf` - install, every tool, wiring and maintenance |

## Quick start

You need a Klipper/Mainsail Pi with the Rhino config, and a print head (BlockOne or SwitchFly) mounted.

1. Upload `rhino-config-<version>.zip` in Mainsail (**Machine** > **Upload**).
2. On the Pi, open the menu:
   ```
   cd ~/printer_data/config
   unzip -o rhino-config-<version>.zip -d ~/rhino-<version>
   bash ~/rhino-<version>/rhino.sh
   ```
   (After the first install the menu is always at `bash ~/rhino-manager/rhino.sh`.)
3. Choose **3) Install a new zip**, read the preview, confirm. It backs up your config folder first and keeps your
   saved settings, then starts the portal on port 5000.
4. In Mainsail: `FIRMWARE_RESTART`, answer "which toolhead is mounted?", then `CHECK_TOOLHEADS`.

Undo with menu option **4**. The full walkthrough is the *Install and first start* chapter of the manual.

## Using it

| To... | Do this | Manual chapter |
|---|---|---|
| Change tools | `SWAP_TOOL` (Mainsail button) | Swapping tools |
| Print | Slice with the Orca profiles in `slicer/orca/`, print from Mainsail | Running a job |
| Laser, CNC or drag knife | `LASER_JOB_SETUP` / `CNC_JOB_SETUP` / `DRAGKNIFE_JOB_SETUP FILE=<name>.gcode` | Running a job |
| Set Z zero for a non-print tool | `SET_Z_ZERO` - move the bed, then SET | Running a job |
| Set nozzle height | `NOZZLE_HEIGHT_CALIBRATE` (paper test) | Running a job |
| Add a tool | Portal > **Add a tool** (or `ADD_TOOLHEAD`) | The Tool Manager portal |
| Track maintenance | Portal > **Maintenance** ([showcase](docs/maintenance/)) | Maintenance tracking |

## Documentation

- [**User manual**](manual/Rhino-User-Manual.pdf) - install, every tool, the portal, maintenance, troubleshooting
- [**Maintenance showcase**](docs/maintenance/) - the maintenance screens after a year of use
- [**Testing**](docs/testing.md) - how it's tested, and the on-machine checks for each release
- [**Developer notes**](docs/developer.md) - running it without the printer, where things are in the code
- [**Changes**](CHANGES.md) - what changed in each version
- The machine itself (CAD, wiring, build notes): [Rhino-3d-Printer](https://github.com/Makersmic/Rhino-3d-Printer)

## Security

The portal has no login: anyone who can reach port 5000 can add or remove tools (it can't run G-code or restart
mid-print). Keep it on your own network or reach it through Tailscale or an SSH tunnel. Other websites can't drive
it: per-start token, same-origin check and a strict Content-Security-Policy.
