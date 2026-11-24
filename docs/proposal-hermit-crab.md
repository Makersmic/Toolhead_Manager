# Proposal: support for the BIQU Hermit Crab quick-change toolhead interface

> **PARKED Nov 23 2026 (Mike): stays a proposal. Build nothing around it yet; he wants to think more.** Revisit when he says.

Nov 23 2026. **For Mike's review: nothing is built.** Mike asked about "the BIQU Hermit Crab interchangeable toolhead interface" as something to tackle, after the idea of aiming at a community whose toolheads are swappable. Facts below come from BIQU's own wiki page
(https://global.bttwiki.com/Hermit%20Crab%202%20Series.html, read Nov 23) and retailer listings; **what the page does not say is listed explicitly**, and those gaps decide the design. I have not seen the hardware.

## What it is

A fixed plate plus several tool plates (3 come in a kit) for swapping print heads quickly, mounted on an MGN12 rail or 2020 V-slot profile. Two electronics versions:

| | Standard (V2) | CAN (V2) |
|---|---|---|
| Firmware | Klipper, Marlin, RRF | Klipper only |
| Board on the tool | no MCU: relies on the host board | RP2040 MCU, TMC2209 (UART), LIS2DW accelerometer, MAX31865, one NTC100K/PT100/PT1000 input |
| Link | wires to the host board | CAN (flashed over CAN, 1 Mbit) or USB-C |
| Outputs | heater HE0 3 A, fans, E0 | heater 6 A, fans FAN0 (4-pin) and FAN1/FAN2 (2-pin), E0 stepper, I2C, probe, RGB, STOP |

Klipper identifies a CAN board by a **canbus_uuid generated from the chip's own ID**, found with `canbus_query.py`; BIQU supplies a sample file (`sample-bigtreetech-hermit-crab-2-canbus.cfg`) to include.

## What the page does not say (these decide the design)

1. **How a swap works:** by hand, or from a dock. Not stated.
2. **What sits on the tool plate and what on the fixed plate**, and how the electrical link is made (cable, pogo pins). Not stated.
3. **What happens to the CAN ID when tools are swapped.** Each tool board has its own chip ID, so each has its own UUID. Not discussed.
4. **Any tool detection or tool-changer macros.** None on the page.

## The one thing that can break it: a board that is not there

Klipper reads every `[mcu]` in the config at start and **refuses to start if one is missing**. We hit the same rule with the USB accelerometer (1.9.50: remove it from the config before you unplug it). With one CAN board per tool plate, every swapped-out tool's board is missing. So the design must not list every tool's board at once. Possible ways (to be checked against the real hardware and Klipper's CAN behaviour, none verified):

- **A.** Only the **mounted** tool's board is in the config; swapping a tool rewrites the active `[mcu]` UUID and restarts Klipper. The Rhino already has a Portal-owned generated file and a restart-pending flow, so the Portal could keep a UUID per tool and write the mounted one. Cost: a Klipper restart on every swap (about 10 to 20 seconds), which is acceptable for hand swaps, not for in-print swaps.
- **B.** Give all tool boards the **same** CAN ID, so the config never changes. Not possible with a UUID derived from the chip (it can't be set by us), so I would not rely on it.
- **C.** Keep the **board on the fixed plate** and swap only passive parts (the standard version's design intent, as I read it: the plate carries the hotend and wires, the electronics stay put). Nothing to rewrite; this is just a different hardware profile.

Which of A or C applies depends on the answers to the questions above, which only the hardware answers.

## What Studio and the Tool Manager would need, if it fits

1. **A board entry** for the Hermit Crab (standard and CAN) in Add hardware > Boards, with its pins from BIQU's sample file (read from their GitHub, not guessed), so the pin picker and heater, fan, thermistor and accelerometer devices work on it.
2. **A tool template** "Hermit Crab tool" in the Add toolhead flow: print head category, its heater, thermistor, fans and extruder driver on that board, its own per-head tuned values (already per head).
3. **For way A:** a Portal-kept UUID per tool and a "this tool is now mounted" step that writes it into a generated file, offers the Klipper restart (never automatic), and refuses to start a job until Klipper is back and the mounted tool is confirmed. This would be a design of its own with a write-up before any macro or config change, per the rules.
4. **Per-tool accelerometer:** the CAN board has an onboard LIS2DW, so the input shaping wizard could measure each tool without a separate board: a real simplification, and worth doing if the board is present.

## Safety and durability

- Heater limits, the "tool off on every end, cancel and swap path" rule and the interlocks stay as they are for any new tool.
- A swap that leaves Klipper without the board it is configured for must **fail safe**: the Portal and Studio keep working while Klipper is down, say what is wrong, and offer the fix, as the accelerometer flow does.
- Nothing is proven without the hardware; the first version would be read-only (a board entry and a profile), tried on a real unit.

## Questions for Mike

1. **Do you have a Hermit Crab** (which version), or are you considering one? Hand swap or dock?
2. If you have one: can you photograph the tool plate and fixed plate, and **how many wires or contacts** join them?
3. Is it for **your own machine** (a fourth head type), or as the example of "swappable tool for the Voron-style audience"? That sets how general the profile must be.
4. OK to leave it as a proposal until the hardware answers the four gaps?
