# Moving the Rhino to the OptiPlex 7050 Micro (design draft)

Oct 25 2026. **Draft for Mike's review. Nothing on the machine changes until he approves it.**
This replaces docs/install-ubuntu-server.md (the 3080 / Ubuntu plan), which stays as a reference.

- **What:** the 7050 Micro (i5-7500T, 8 GB, Mike's 2.5" SSD) runs Klipper, Moonraker, the Portal, Studio and
  PrusaSlicer on **Debian 12**. The Pi 3B keeps its SD card untouched and becomes the spare.
- **Accepted when:** the load test passes (§9): a long PrusaSlicer slice during a print, with no "Timer too close",
  no lost MCU, and no missed steps. Core pinning is a fix if it fails, not a substitute for the test
  (decisions.md, 2026-10-23).
- **Way back at any step:** shut the 7050 down, move the USB cables back, boot the Pi (§11).

Items marked **verify** come from earlier Gemini/Grok research or from memory, and haven't been checked on this hardware.

## 0. Before the 7050 arrives (on the Pi)

1. **Install Tool Manager 1.8.1** (Update in Studio). Backups from 1.8.1 on are named `rhino_studio_os-<date>.zip`.
2. **Back up now** (Settings › Host › Backups). Check that it says **complete** and that the GitHub copy says pushed. Then
   **Download** the zip to your PC. That file is the move: config, Moonraker database (history, Studio and Mainsail
   settings), photos, slice profiles and saved jobs.
3. **Why the backup is 133 MB:** run
   `unzip -l ~/rhino-backups/<newest>.zip | sort -k1 -n | tail -15` and send the result. If it's a bloated database
   or old photos, we trim it first (optional).
4. **The Pi's GPIO header:** look at the Pi and write down anything wired to its pins (relay, button, fan, LED,
   sensor). The 7050 has no GPIO, so anything there needs a new home first (the MCU board, or a USB relay). If the
   header is empty, there's nothing to do.
5. **Write down:** the Pi's IP address, klipper-backup's GitHub repo name, and a GitHub token that can push to it.
   `.env` holds the token and is deliberately not in the backup.
6. **Which board chip:** run `lsusb` on the Pi. If you see `1a86:7523` (CH340), §3's brltty step applies.

## 1. Hardware

- SSD in the caddy with the SATA ribbon. Use the **genuine Dell 65 W 19.5 V adapter (4.5 mm blue tip)**. **Verify:**
  with a weak or non-Dell adapter the 7050 may run its CPU at 800 MHz, which would wreck the load test. §9 checks
  the clock speed.
- First boot needs a keyboard and screen. After §2 everything is over SSH (PuTTY).

## 2. BIOS (F2 at power-on)

- **System Configuration › SATA Operation: AHCI** (Debian can't see the disk in RAID mode).
- **Power Management › AC Recovery: Power On**, so the Rhino comes back on its own after a power cut.
- **Power Management › Deep Sleep: Disabled**, and USB wake/power left on. **Verify** the menu names on the 7050.
- Secure Boot can stay on. Debian 12 boots with it.

## 3. Debian 12

1. Write the Debian 12 netinst image to a USB stick (Rufus or balenaEtcher) and boot from it (F12).
2. In the installer:
   - hostname **`rhino`**
   - user **`pi`**, which keeps every `/home/pi` path in the config and backup the same
   - the whole SSD
   - software: untick the desktop and **tick "SSH server" and "standard system utilities"**
3. After the first boot (as `pi`, using `su -` for root where needed):
   ```
   su - -c "apt update && apt install -y sudo && usermod -aG sudo,dialout pi"     # log out and in once
   sudo apt full-upgrade -y
   sudo timedatectl set-timezone America/Chicago
   sudo apt install -y git rsync unzip avahi-daemon avahi-utils flatpak network-manager
   ```
   - `dialout` lets Klipper open the board's serial port.
   - `avahi-daemon` makes `rhino.local` and `rhinostudio.local` work.
   - `flatpak` is for PrusaSlicer (check P0).
   - **CH340 board only:** `sudo apt remove -y brltty`. It grabs CH340 serial ports. **Verify** whether it's installed at all on netinst.

## 4. Network (decide with Mike)

On a server install, Debian 12's network is run by **ifupdown** (`/etc/network/interfaces`), not NetworkManager. Studio's
Settings › Network and **Settings › Host › Name on the network** only change things on NetworkManager. Two options:

- **A (lean):** hand the wired port to NetworkManager:
  1. Comment out the port's lines in `/etc/network/interfaces`, leaving only `lo`.
  2. `sudo systemctl restart NetworkManager`
  3. Reboot.

  After that, Studio can rename the Rhino and set a fixed address, with Keep/Undo. **Verify** on the box before relying on it.
- **B:** leave ifupdown and set a fixed address in your router. Studio shows the network read-only, like the Pi does today.

## 5. Klipper, Moonraker, Mainsail (KIAUH)

```
cd ~ && git clone https://github.com/dw-0/kiauh.git && ./kiauh/kiauh.sh
```

Install:
- Klipper (one instance), Moonraker, and Mainsail (kept as a back door; Studio is the everyday screen)
- Crowsnest, if you use cameras
- Extensions › G-Code Shell Command, which `BACKUP_CFG` uses

If `http://rhino.local` shows **403**, run `chmod o+x ~`.

## 6. Move the machine

1. On the Pi, `sudo shutdown now`. Only one host may talk to the boards.
2. Move the board's and cameras' USB cables to the 7050.
3. On the 7050, `ls /dev/serial/by-id/`. The names match the `[mcu] serial:` lines (they're the board's own ID).

## 7. Tool Manager, then the restore

1. Install **Tool Manager 1.8.1**: copy the zip over and run `rhino.sh` option 3 (the same as the first install on
   the Pi). This sets up the Portal, Studio at `http://rhinostudio.local` and the updater.
2. Studio › Settings › Host › Backups › **Add a backup from another Rhino…**, then pick the zip from step 0.2. It's
   checked before it's listed.
3. **Restore… › Everything** (check **B5**). It shows what it will change first, asks you to type the machine's
   name, and backs up the 7050's fresh state before writing.
   - It refuses if the backup's `[mcu] serial:` boards aren't connected. That's a good thing after a move: plug the board in first.
   - It leaves the program files as installed (1.8.1).
   - **Verify:** `moonraker.conf` comes back from the Pi. With user `pi`, the paths match. Check `[authorization]`
     `trusted_clients` still covers your network.
4. `FIRMWARE_RESTART`, answer "which toolhead is mounted?", then `CHECK_TOOLHEADS`.
5. **klipper-backup:**
   ```
   cd ~ && git clone https://github.com/Staubgeborener/klipper-backup.git && ./klipper-backup/install.sh
   ```
   Use the same repo and token as step 0.5. Then **Back up now**. The GitHub copy should say pushed.
6. **PrusaSlicer:** Settings › Software › PrusaSlicer › Install. Expect 10–20 minutes the first time. Then run checks P1–P9.

## 8. First checks (a short list, not the whole testing.md)

- [ ] Studio opens at `http://rhinostudio.local` from the PC and the phone.
- [ ] Settings › Slice profiles shows your profiles. Job history and Care are as they were.
- [ ] Home all, swap tools once each way, and a bed mesh (BM checks).
- [ ] A short print with BlockOne.
- [ ] Back up now works on the new host, with the GitHub copy pushed.

## 9. Load test (the acceptance)

1. **Clock:** run `grep MHz /proc/cpuinfo` while running `yes > /dev/null` on all 4 cores for 30 s. It should be well over
   2 GHz. At 800 MHz, check the adapter (§1).
2. **The test:** start a print of 2 hours or more with BlockOne. Twenty minutes in, slice a large model with PrusaSlicer
   in Studio (fine layers, tree supports), twice in a row.
3. **Pass if all of these hold:**
   - The print finishes clean: no layer shift, no stall.
   - Mainsail's "System load" stays sane.
   - `grep -i -E "timer too close|lost communication|shutdown" ~/printer_data/logs/klippy.log` finds nothing new.
4. **If it fails:** first `usbcore.autosuspend=-1` (only if the MCU dropped), then pin Klipper to a core
   (`CPUAffinity=` in the klipper service), then test again.
5. **Then decide:** PrusaSlicer on the Rhino is first-class or out (decisions.md, 2026-10-23).

## 10. Afterwards

- The Pi's SD card stays as it is for a month, as the spare.
- I add 7050 notes to the manual's install chapter (it's being rewritten anyway).
- decisions.md records the result.

## 11. Way back

Shut the 7050 down, move the USB cables back, and boot the Pi. Its SD card is unchanged. Anything made on the 7050 in
the meantime (new profiles, history) comes back with a backup from the 7050 restored on the Pi.

## Questions for Mike

1. **Network:** option A (NetworkManager, so Studio can rename and set the address) or B (router, read-only)? **Lean: A.**
2. Hostname **`rhino`** on the 7050, or keep **`mainsailos`** so bookmarks still work? **Lean: `rhino`.**
   `rhinostudio.local` works either way.
3. Anything on the Pi's GPIO header (step 0.4)?
