# Moving the Rhino to Ubuntu Server (Dell OptiPlex 3080)

From the Pi 3B to an x86 PC running Ubuntu Server 24.04 LTS: Klipper, Moonraker and Mainsail through KIAUH, your
config back from the `rhino-backup` GitHub repo, then the Rhino Tool Manager zip, PrusaSlicer and Rhino Studio.
About an hour, most of it waiting on downloads. Keep the Pi's SD card as it is until the last step passes: it's your
way back.

What you need: a USB stick (4 GB+), a keyboard and screen for the OptiPlex for the first boot only, Ethernet to
your router, and a GitHub token that can read `rhino-backup` (GitHub > Settings > Developer settings > Personal
access tokens; read access to that repo's contents is enough).

## 1. BIOS (F2 at power-on)

- **Storage > SATA/NVMe operation: AHCI** (Dell often ships "RAID On"; Ubuntu's installer then can't see the drive).
  Only change this on a disk you're about to wipe.
- **Power Management > AC Recovery: Power On**, so the Rhino comes back by itself after a power cut.
- Secure Boot can stay on.

## 2. Install Ubuntu Server

1. Download **Ubuntu Server 24.04 LTS** (ubuntu.com/download/server) and write it to the stick with balenaEtcher or
   Rufus. Boot the OptiPlex from it (F12, pick the USB stick).
2. In the installer:
   - **Ubuntu Server** (not "minimized"). Network: the Ethernet port, DHCP is fine.
   - Storage: use the entire disk.
   - Profile: **server name `rhino`** (Mainsail will be at `http://rhino.local`). Username: anything; `pi` saves the
     installer rewriting `/home/pi` paths, but any name works.
   - **Install OpenSSH server: yes.** No snaps.
3. Reboot, pull the stick. From now on you can work over SSH from your PC: `ssh <username>@rhino.local` (or use the
   address the OptiPlex shows on its login screen until step 3 is done).

## 3. Base packages

```
sudo apt update && sudo apt full-upgrade -y
sudo timedatectl set-timezone America/Chicago
sudo apt install -y git avahi-daemon avahi-utils flatpak
```

- `avahi-daemon` makes `rhino.local` (and later `rhinostudio.local`) work. Ubuntu Server doesn't ship it.
- `flatpak` is check **P0**: the Portal never uses sudo, so this is the one hand step PrusaSlicer needs.
- If `dpkg -l brltty` shows it installed, remove it (`sudo apt remove -y brltty`): it grabs CH340 USB-serial
  boards, and Klipper then can't find the MCU.
- `sudo reboot` once now.

## 4. Klipper, Moonraker, Mainsail (KIAUH)

```
cd ~ && git clone https://github.com/dw-0/kiauh.git
./kiauh/kiauh.sh
```

In KIAUH's **Install** menu: **Klipper** (one instance), **Moonraker**, **Mainsail** (port 80), and **Crowsnest** if
you use cameras. Then **Extensions**: **G-Code Shell Command** (`BACKUP_CFG` uses it). Quit KIAUH.

Open `http://rhino.local` on your PC. Mainsail shows; Klipper will complain about a missing printer.cfg. That's
expected. If you get **403 Forbidden** instead, nginx can't read your home folder (Ubuntu makes it private):
`chmod o+x ~` (lets nginx pass through it, not list it), then reload the page.

## 5. Move the machine over

1. On the Pi: `sudo shutdown now`. Only one host may talk to the MCU boards.
2. Move the USB cables for the MCU boards (and cameras) from the Pi to the OptiPlex.
3. `ls /dev/serial/by-id/` on the OptiPlex: the names should be the same ones your printer.cfg's `[mcu]`
   `serial:` lines use (they're the boards' own IDs, not the host's).

## 6. Your config back from rhino-backup

```
sudo systemctl stop klipper
git clone https://github.com/Makersmic/rhino-backup ~/rhino-backup-repo
```

Username: `Makersmic`; password: the token. Then find the folder in it that holds printer.cfg:

```
find ~/rhino-backup-repo -name printer.cfg -not -path '*/.git/*'
```

Copy that folder's contents in, **keeping Ubuntu's own moonraker.conf** (the old one has the Pi's paths):

```
cp ~/printer_data/config/moonraker.conf ~/moonraker.conf.ubuntu
rsync -a --exclude .git --exclude moonraker.conf <the folder find printed>/ ~/printer_data/config/
diff <the folder find printed>/moonraker.conf ~/printer_data/config/moonraker.conf
```

`diff` shows what the Pi's moonraker.conf had that the new one doesn't. Copy over only the extra sections you still
want (an `[update_manager ...]`, `[timelapse]`, ...), not paths or `[server]`. In `[authorization]`, keep
`cors_domains` with `*.local` and `trusted_clients` with your network range (KIAUH's defaults have both).

Cameras: if `crowsnest.conf` names devices, check them against `ls /dev/v4l/by-id/`.

Then `sudo systemctl start klipper` and reload Mainsail. Klipper may report a /home/pi path; the next step fixes those.

**BACKUP_CFG** on the new host: install klipper-backup and point it at the same `rhino-backup` repo:

```
cd ~ && git clone https://github.com/Staubgeborener/klipper-backup.git && ./klipper-backup/install.sh
```

## 7. Rhino Tool Manager (1.5.2 now, 1.5.3 when it's out)

Same as on the Pi:

1. Mainsail > **Machine** > upload `rhino-config-<version>.zip`.
2. Over SSH:
   ```
   cd ~/printer_data/config
   unzip -o rhino-config-<version>.zip -d ~/rhino-<version>
   bash ~/rhino-<version>/rhino.sh
   ```
3. **3) Install a new zip**, read the preview, confirm. Ubuntu asks for your password once. The install rewrites
   `/home/pi` paths to your home, starts the Portal (port 5000) and serves Studio at `http://rhino.local:5001`.

Notes you may see, and what they mean here:

- *"No NetworkManager (nmcli) on this Pi"*: expected on Ubuntu Server (it uses netplan). Network settings stay
  read-only in the Portal and Studio; set a fixed address in your router instead.
- *"nginx (user www-data) can't read ~/rhino-studio"*: run the `chmod o+x ~` from step 4, then install again.

Then in Mainsail: `FIRMWARE_RESTART`, answer "which toolhead is mounted?", `CHECK_TOOLHEADS`. Run checks **A-I**
in `docs/testing.md` that matter to you (at least homing, a swap and a short print).

## 8. PrusaSlicer on the host

Studio (`http://rhino.local:5001`) > **Settings > Software > PrusaSlicer > Install**. The first install downloads a
few hundred MB from Flathub; allow 10-20 minutes. Then run **P1-P9** in `docs/testing.md`. The OptiPlex has the
memory to slice during a print (4 GB+), which the Pi never did.

## 9. Tool Manager 1.5.3 (once, by hand)

1.5.3 sets up the updater, so install it with menu option 3 like step 7. From then on, updates go in from Studio
(Settings > Software > Install from zip), no Mainsail or SSH needed. 1.5.3 also adds `http://rhinostudio.local`.
Checks **U1-U6** and **S8-S12**.

## If something's wrong

| What you see | Do this |
|---|---|
| Mainsail shows 403 Forbidden | `chmod o+x ~`, reload |
| Klipper: "Unable to connect" to the MCU | `ls /dev/serial/by-id/`; remove brltty if installed; `groups` should list `dialout` (log out and in after KIAUH) |
| `rhino.local` doesn't open | `systemctl status avahi-daemon`; use the address instead. Some Android phones never resolve `.local` |
| PrusaSlicer row says Flatpak is missing | `sudo apt install flatpak` (step 3) |
| Want the Pi back | Shut the OptiPlex down, move the USB cables back, boot the Pi: its SD card is unchanged |
