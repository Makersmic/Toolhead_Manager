# Moving the Rhino to the OptiPlex 7050 Micro

Oct 25 2026, **approved by Mike Oct 26** (answers at the end): NetworkManager on the 7050, hostname `rhino`, nothing on
the Pi's GPIO header, and the Pi is retired a month after the 7050 is accepted.
This replaces docs/install-ubuntu-server.md (the 3080 / Ubuntu plan), which stays as a reference.

- **What:** the 7050 Micro (i5-7500T, 8 GB, its own 128 GB M.2 SATA drive, on Wi-Fi) runs Klipper, Moonraker, the Portal, Studio and
  PrusaSlicer on **Debian 12**. The Pi 3B keeps its SD card untouched and becomes the spare.
- **Accepted when:** the load test passes (§9): a long PrusaSlicer slice during a print, with no "Timer too close",
  no lost MCU, and no missed steps. Core pinning is a fix if it fails, not a substitute for the test
  (decisions.md, 2026-10-23).
- **Way back at any step:** shut the 7050 down, move the USB cables back, boot the Pi (§11).

Items marked **verify** come from earlier Gemini/Grok research or from memory, and haven't been checked on this hardware.

**Done Nov 3 2026** up to §8's health check. What the real move changed is in **"The move, Nov 3"** near the end;
read it before doing this again.

## 0. Before the 7050 arrives (on the Pi)

1. **Install Tool Manager 1.9.9** (Update in Studio), then check **HW1** (a normal print runs as before). The
   7050 gets the same version, so the backup restores cleanly, and the Pi stays on 1.9.9 as the fallback.
2. **Back up now** (Settings › Host › Backups). Check that it says **complete** and that the GitHub copy says pushed. Then
   **Download** the zip to your PC. That file is the move: config, Moonraker database (history, Studio and Mainsail
   settings), photos, slice profiles and saved jobs.
3. **Size:** fixed in 1.8.2 (installer zips and the manual PDF are left out). Expect about 20 MB, not 133 MB.
   If it's still large, run `unzip -l ~/rhino-backups/<newest>.zip | sort -k1 -n | tail -15` and send the result.
4. **The Pi's GPIO header: empty** (Mike, Oct 26). Only the Octopus and the webcam are plugged in, both USB, so
   nothing needs a new home.
5. **Save klipper-backup's settings on your PC, and write down the Pi's IP address.** From the PC:
   ```
   scp pi@<the Pi's IP>:klipper-backup/.env klipper-backup.env
   chmod 600 klipper-backup.env
   ```
   This file holds the repo name, what gets backed up and how it pushes, and it may hold a GitHub token, so it's
   deliberately not in the backup. Don't share it, and delete it from the PC after §7.5.
6. **Which board chip:** run `lsusb` on the Pi. If you see `1a86:7523` (CH340), §3's brltty step applies.
7. **Health check:** `rhino.sh` option **7** (Tool Manager 1.9.5 or later). It changes nothing. It saves
   `~/rhino-health-mainsailos-<date>.json`; copy that to your PC with the backup zip, to compare with the 7050 in §8.

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
4. **Never sleep.** A desktop PC can suspend itself, and a sleeping host stops Klipper mid-job:
   ```
   sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
   ```
   The health check (§8) checks this.

## 4. Network: option A (Mike, Oct 26)

On a server install, Debian 12's network is run by **ifupdown** (`/etc/network/interfaces`), not NetworkManager. Studio's
Settings › Network and **Settings › Host › Name on the network** only change things on NetworkManager. Two options:

- **A (chosen):** hand the wired port to NetworkManager:
  1. Comment out the port's lines in `/etc/network/interfaces`, leaving only `lo`.
  2. `sudo systemctl restart NetworkManager`
  3. Reboot.

  After that, Studio can rename the Rhino and set a fixed address, with Keep/Undo. **Verify** on the box before relying on it.
- B (not chosen): leave ifupdown and set a fixed address in the router; Studio would show the network read-only.

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

1. Install **Tool Manager 1.9.9** (the same version as the Pi's backup): copy the zip over and run `rhino.sh` option 3 (the same as the first install on
   the Pi). This sets up the Portal, Studio at `http://rhinostudio.local` and the updater.
2. Studio › Settings › Host › Backups › **Add a backup from another Rhino…**, then pick the zip from step 0.2. It's
   checked before it's listed.
3. **Restore… › Everything** (check **B5**). It shows what it will change first, asks you to type the machine's
   name, and backs up the 7050's fresh state before writing.
   - It refuses if the backup's `[mcu] serial:` boards aren't connected. That's a good thing after a move: plug the board in first.
   - It leaves the program files as installed (1.9.9).
   - **Verify:** `moonraker.conf` comes back from the Pi. With user `pi`, the paths match. Check `[authorization]`
     `trusted_clients` still covers your network.
4. `FIRMWARE_RESTART`, answer "which toolhead is mounted?", then `CHECK_TOOLHEADS`.
5. **klipper-backup.** The Pi must stay off: only one host should push to the backup repo.
   1. Get it, without installing yet:
      ```
      cd ~ && git clone https://github.com/Staubgeborener/klipper-backup.git
      ```
   2. From the PC, put the settings from step 0.5 in place, then delete the PC's copy once this step works:
      ```
      scp klipper-backup.env pi@rhino.local:klipper-backup/.env
      ```
   3. Give the 7050 its own key. This pushes over SSH, the same way the Pi does, and an SSH key doesn't expire:
      ```
      chmod 600 ~/klipper-backup/.env
      ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C rhino-7050
      cat ~/.ssh/id_ed25519.pub
      ```
      On GitHub, open the backup repo › Settings › Deploy keys › **Add deploy key**, paste that line, and tick **Allow
      write access**. Then run `ssh -T git@github.com` and answer `yes`. *Stop if:* it doesn't say you've successfully
      authenticated. Pushes would fail.
   4. Run `~/klipper-backup/install.sh`. Answer **no** to reconfiguring the `.env`, and **yes** to the filewatch
      service. **Verify:** the installer's questions on this version.
   5. **Run `rhino.sh` option 3 again with the same zip.** This adds Rhino's backup watcher. Step 1 couldn't, because
      klipper-backup wasn't there yet. Without this step the 7050 keeps klipper-backup's own watcher, which runs one
      whole backup per file event. It's the same install as an update and keeps your config.
   6. Check it: `systemctl cat klipper-backup-filewatch` ends with the `rhino.conf` override, and
      `pgrep -af rhino_backup_watch` shows it running. *Stop if:* either is missing. Don't carry on with the old watcher.
   7. **Back up now.** The GitHub copy should say pushed.
6. **PrusaSlicer:** Settings › Software › PrusaSlicer › Install. Expect 10–20 minutes the first time. Then run checks P1–P9.

## 8. First checks (a short list, not the whole testing.md)

- [ ] **Health check** (`rhino.sh` option 7): no FAIL, apart from one known false alarm up to 1.9.9: "No VERSION in
      the config folder", with `tool manager ?` in the facts. Settings › Software shows the real version. Copy the Pi's
      report from §0.7 into `~` and let option 7 compare them: the **boards** line should be the same Octopus, connected.
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

- **Until the load test passes, don't update Tool Manager on the 7050.** The way back (§11) restores a 7050 backup on
  the Pi, and a restore wants the same version on both (1.9.9).
- **Once it's accepted:** make a **one-time Clonezilla image of the 7050's SSD** (boot Clonezilla Live from a USB stick,
  device-image, save to a USB drive or the PC, and check it). Recovery is then the image plus the newest backup zip.
- The Pi's SD card stays as it is, frozen at 1.9.9, for a month after acceptance, then it's retired (Mike, Oct 26).
  Releases after that target the 7050 (x86) only.
- I add 7050 notes to the manual's install chapter (it's being rewritten anyway).
- decisions.md records the result.

## 11. Way back

Shut the 7050 down, move the USB cables back, and boot the Pi. Its SD card is unchanged. Anything made on the 7050 in
the meantime (new profiles, history) comes back with a backup from the 7050 restored on the Pi (both on 1.9.9).

After the Pi is retired, the way back is the Clonezilla image (§10) restored onto the SSD, then the newest backup zip.

## The move, Nov 3

What happened on the real hardware, and what to do differently next time. Where this disagrees with the steps above,
this wins.

**Hardware and BIOS (§1, §2)**
- The 7050 came with a **128 GB M.2 SATA** drive (SanDisk SD8SN8U), used instead of the 2.5" SSD. The BIOS lists it as
  "SATA". Check a used drive before trusting it: `sudo apt install smartmontools`, `sudo smartctl -H -A /dev/sda`
  (PASSED, 0 reallocated), then `sudo smartctl -t short /dev/sda` and `-l selftest` after 2 minutes. This one passed
  with 91 % life left, 20,204 hours, and 272 unexpected power losses from its office life.
- **Wi-Fi** (`wlp2s0`, internal card) instead of wired, Mike's choice. Klipper talks to the board over USB, so a Wi-Fi drop
  doesn't stop a job. Power saving is off (§4 below).

**Debian installer (§3)**
- **Leave the root password blank.** Debian then locks root, installs `sudo` and puts the user in the sudo group. With a
  root password set, `sudo` isn't installed and the plan's `su -` line needs that password. The first step after boot is
  then only `sudo usermod -aG dialout pi`.
- **Username:** the installer proposes one from the full name (`mike`). Erase it and type **`pi`**.
- **Software selection:** move with the arrows and toggle with **space**. Enter accepts the list as it is, which installs
  GNOME and leaves SSH out. If that happens, reinstall rather than remove a desktop.
- Partitioning: Guided, entire disk, no LVM or encryption (encryption would wait for a passphrase after a power cut).
  "Force UEFI installation?" Yes.
- **"No bootable devices" after the install**, with a `debian` entry already first in the BIOS boot list: the entry was
  stale and remaking it didn't help. Fix from the installer stick: Advanced options › Rescue mode › root on `/dev/sda2`
  (mount `/boot/efi` when asked) › Execute a shell, then:
  ```
  grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable
  update-grub
  ```
  This puts the loader at the default UEFI path, so the 7050 boots with no boot entry at all, which also survives a BIOS
  update or a dead CMOS battery. **Do it on every install**, even when it boots fine.
- Add `smartmontools` to §3's install line.

**Network (§4, Wi-Fi version, at the 7050's keyboard)**
```
sudo cp /etc/network/interfaces /root/interfaces.installer
printf 'source /etc/network/interfaces.d/*\n\nauto lo\niface lo inet loopback\n' | sudo tee /etc/network/interfaces
printf '[connection]\nwifi.powersave = 2\n' | sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf
sudo reboot
nmcli device                                            # the wl... line must say disconnected, not unmanaged
sudo nmcli --ask device wifi connect "<network name>"   # --ask keeps the passphrase out of the shell history
sudo reboot                                             # then PuTTY in without touching the keyboard
sudo rm /root/interfaces.installer                      # it holds the passphrase in plain text
```
The address changed from .133 to **192.168.1.132** when NetworkManager took over. Reserve it in the Google Home app.

**KIAUH (§5)**
- **Say yes to KIAUH's example `printer.cfg`.** `install.sh` refuses without a `printer.cfg` ("No printer.cfg in ..."), and
  so does the restore's safety backup. The restore replaces it.
- Crowsnest and G-Code Shell Command installed fine. Klipper came out two commits newer than the Pi's
  (`v0.13.0-820-g0cee841e` vs `-818-g020d25e7`) and loaded the restored config. Pin the real-Klipper CI step to the
  7050's version.

**Before the Pi goes off (end of §0 / start of §6)**
- With the PC that held `~/rhino-safety` out of action, copy straight from the Pi to the 7050 while both are on:
  ```
  scp pi@192.168.1.225:klipper-backup/.env ~/klipper-backup.env && chmod 600 ~/klipper-backup.env
  scp 'pi@192.168.1.225:rhino-health-mainsailos-*.json' ~/
  ```
  The token then never touches a USB stick or the laptop. In §7.5.2 it's
  `mv ~/klipper-backup.env ~/klipper-backup/.env && chmod 600 ~/klipper-backup/.env`.
- Take the backup zip **after** the last Pi print, so it holds the newest history.

**Move and Tool Manager (§6, §7)**
- **Switch the Rhino's 24 V supply on.** With it off, the Octopus doesn't appear in `lsusb` or `/dev/serial/by-id/` at
  all, and `dmesg` shows nothing when it's plugged in.
- Tool Manager straight onto the 7050, checked against the release's `.sha256`:
  ```
  cd ~/printer_data/config && wget https://github.com/Makersmic/Toolhead_Manager/releases/download/v1.9.9/rhino-config-1.9.9.zip
  unzip -o rhino-config-1.9.9.zip -d ~/rhino-1.9.9 && bash ~/rhino-1.9.9/rhino.sh     # option 3
  ```
- Before the restore, the Portal log warns `job_hooks.cfg not rewritten ... cannot find [gcode_macro VARIABLES]`. That's
  KIAUH's example config; it's gone after the restore and a Portal restart (menu 6).
- The restore (Everything) went through first time, including the board check.

**klipper-backup (§7.5)**
- This version's installer asks, in order: proceed **y**; reconfigure the .env **n**; add to Moonraker's update manager **n**
  (asked only if `moonraker.conf` lacks it, so no keeps it as on the Pi); filewatch **y**; on-boot service **n**; cron every
  4 hours **n** (it would run during jobs).
- `pgrep -af rhino_backup_watch` shows **two** lines: the watcher and its helper (`ps -o pid,ppid,cmd` shows one is the
  other's child). Two lines with PPID 1 would be two watchers.
- **The first Back up now failed to push:** "untracked working tree files would be overwritten by merge". An earlier run had
  started a new history in `~/config_backup` without pulling GitHub's (one parentless commit). Fix:
  `mv ~/config_backup ~/config_backup.broken-<date>`, then Back up now. Next time, **rename any existing
  `~/config_backup` before the first Back up now**. Check: `git -C ~/config_backup log --oneline -3` shows the new commit on
  top of the Pi's, with `origin/main` beside it, and `ls-tree HEAD printer_data/` shows `040000 tree`.

**Health check (§8):** 21 pass, plus the known VERSION false alarm. Compared with the Pi's report: same Octopus, connected.
The `boards` line lists the same `[mcu]` twice on both machines, which is a counting bug in the check, not two boards.

**Found on the way**
- **`BACKUP_CFG` during a job stalls the print.** Seen on the Pi Nov 3: `RUN_SHELL_COMMAND` holds Klipper's G-code queue
  until the backup ends (`timeout: 240.`), so the head stops on the part. **Don't run it during a job** until it refuses
  there. The fix is a macro change and goes to review first. The Portal's automatic backups already wait for the job.
- Health check fixes for the next release: the VERSION false alarm, and the doubled boards line.

Still open after Nov 3: the rest of §8 (data, motion, a short print with BW4), PrusaSlicer (§7.6), the load test (§9).

**Nov 6:** back on with a second adapter of the same non-Dell model used since the move. Clock under load on all
4 cores: **2800 MHz** (§9.1 passes; no 800 MHz throttle). Still to check: whether the BIOS shows an adapter warning
at power-on that waits for F1, which would block AC Recovery after a power cut.

**Nov 7, §8 and §9:** health check passes (only the known VERSION false alarm); boards match the Pi's report, Octopus
connected. Studio on PC and phone, profiles and history there. Home, bed mesh (saved), swaps both ways, extruder after
a resoldered stepper wire. Mike moved the X/Y endstop physically after a laser-head crash during homing; homing and
swaps checked again after. **Load test passed:** a BlockOne print with all four cores loaded (`nice -n 10 yes`, 10 min,
20 min in) in place of the PrusaSlicer slices: no layer shift or stall, no visible change in the part, and the
`timer too close|lost communication|shutdown` count in klippy.log stayed at 41. **The 7050 is accepted.**
PrusaSlicer on the Rhino isn't decided yet: on the 7050 it fails with a custom G-code template error (cause being
found), so its half of §9 waits for that fix.

## Mike's answers (Oct 26)

1. **Network:** A, NetworkManager on the 7050 (§4).
2. **Hostname:** `rhino` (§3). `rhinostudio.local` works too; bookmarks to `mainsailos.local` need updating.
3. **Pi GPIO header:** nothing on it; only the Octopus and the webcam, both USB (§0.4).
4. **Pi retirement:** yes. Fallback during the move, frozen at 1.9.9, retired a month after acceptance; a one-time
   Clonezilla image of the 7050 SSD (§10).
