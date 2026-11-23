# A Rhino host without Mainsail

Nov 22 2026. For building a Rhino host (a new PC, a spare, a rebuilt SD card) that **never has Mainsail on it**:
Klipper, Moonraker and Crowsnest from KIAUH, nginx for Studio, then the Rhino Tool Manager zip. Rhino Studio is the
only screen. About 90 minutes, most of it waiting on downloads.

**Status: written, not yet tried end to end.** The pieces are tested separately (the installer already runs with no
Mainsail site, and Studio needs nothing from Mainsail), but nobody has built a whole host this way. **Do it first on a
spare machine or a virtual machine. Don't use your running Rhino.** The working machine isn't touched by anything here,
which is also your way back.

The second half (Appendix) is the same end state reached from the running machine, by removing Mainsail. Don't start
it until the checks in `docs/testing.md` for the pause, resume and cancel change (OP1-OP7) have passed and the two-week spare period is over.

What you need: the Rhino Tool Manager zip (`rhino-config-<version>.zip`, from GitHub Releases) on your PC, a GitHub
token that can read `rhino-backup` if you are restoring a config, Ethernet to your router, and a PC to work from over SSH.

## Stop rules (for every step)

- **Stop** if any command in a step gives an error you don't understand. Don't carry on to the next step. Write down the
  step and the message.
- **Stop** if `sudo nginx -t` says anything but `syntax is ok` and `test is successful`.
- **Stop** if `systemctl is-active klipper moonraker` doesn't say `active` twice after step 2.
- **Never** plug the real machine's MCU boards into the new host while the old host is powered: only one host may talk
  to them. Do the whole install with the boards unplugged, and move them over at step 6.
- **Never** run the installer's option 3 twice with different zips without reading what it printed the first time.

## 1. The operating system

Follow `docs/install-ubuntu-server.md`, **sections 1 to 3 only** (BIOS, Ubuntu Server 24.04 LTS, base packages).
Use the server name `rhino`, so the machine is `http://rhino.local`. Install OpenSSH. Reboot once after the base packages.

If a Raspberry Pi: Raspberry Pi OS Lite (64-bit) with the same hostname, SSH on, and `sudo apt install -y git avahi-daemon avahi-utils flatpak`.

## 2. Klipper, Moonraker, Crowsnest (KIAUH)

```
cd ~ && git clone https://github.com/dw-0/kiauh.git
./kiauh/kiauh.sh
```

In KIAUH's **Install** menu choose **Klipper** (one instance) and **Moonraker**, and **Crowsnest** if you use cameras.
Then **Extensions**: **G-Code Shell Command** (`BACKUP_CFG` uses it). **Do not install Mainsail or Fluidd.** Quit KIAUH.

Check:

```
systemctl is-active klipper moonraker
curl -s http://localhost:7125/server/info | head -c 300
```

*Pass:* `active` twice, and a block of text that names Moonraker's version. (Klipper will say it can't start
without a printer.cfg: expected for now.)

Look at `~/printer_data/config/moonraker.conf`. *Pass:* it has an `[authorization]` section with a `trusted_clients` list
(KIAUH's default has one). The installer adds your network to it if it's missing.

## 3. nginx

```
sudo apt install -y nginx
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
chmod o+x ~
```

- Ubuntu's nginx starts with a welcome page on port 80. The Rhino's Studio site takes port 80 itself, and two sites can't both be the default one, so the welcome page has to go. Since 1.9.45 the installer switches it off itself, but only when it is nginx's own welcome site (a link `sites-enabled/default` with `root /var/www/html;`); it leaves the file in `sites-available`, and Undo (`rhino.sh` option 4) switches it back on. The `rm` above does the same by hand and is harmless if you have done it. If the installer later says nginx refused the change and mentions a duplicate `default_server`, look in `/etc/nginx/sites-enabled/` for what else listens on port 80 (a site that isn't nginx's own welcome page is never touched).
- `chmod o+x ~` lets nginx pass through your home folder to `~/rhino-studio` (it doesn't let anyone list it). Without it
  Studio shows "403 Forbidden".

*Pass:* `nginx -t` says `syntax is ok` and `test is successful`.

## 4. Your config

**Fresh machine, no config yet:** `touch ~/printer_data/config/printer.cfg`. The zip brings the whole config (it is the
Rhino's); you will fill in your boards' serial IDs at step 6.

**Restoring the Rhino's config from `rhino-backup`:** follow `docs/install-ubuntu-server.md`, **section 6**. Keep this
host's own `moonraker.conf`. Skip anything in the copied files about Mainsail: `mainsail.cfg` and any `[update_manager mainsail]`
sections aren't needed, and an old `printer.cfg` that still says `[include mainsail.cfg]` is rewritten by the install in step 5.

## 5. The Rhino Tool Manager

There is no Mainsail to upload the zip with, so copy it over SSH. From your PC:

```
scp rhino-config-<version>.zip <username>@rhino.local:~/printer_data/config/
```

On the host:

```
cd ~/printer_data/config
unzip -o rhino-config-<version>.zip -d ~/rhino-<version>
bash ~/rhino-<version>/rhino.sh
```

Choose **3) Install a new zip**, read the preview, confirm. It asks for your password once (for nginx).

What you should see in the output:

- *"no Mainsail site in /etc/nginx/sites-enabled - Studio takes the bare address on its own"*: **expected here**.
- *"http://rhino.local opens Rhino Studio"*: this is the line you want.
- *"No NetworkManager (nmcli)"* on Ubuntu Server: expected (it uses netplan). Network settings stay read-only in Studio.
- *"nginx (user www-data) can't read ~/rhino-studio"*: run `chmod o+x ~`, then run option 3 again.

**Stop** if it says Studio is not served, or nginx refused the change. Read what it printed and go back to step 3.

## 6. First start

1. Plug in the MCU boards (host powered down first). `ls /dev/serial/by-id/` should show the names your `printer.cfg`'s `[mcu]` `serial:` lines use.
2. `sudo systemctl restart klipper`. Open `http://rhino.local` on your PC: **Rhino Studio opens**, not a welcome page.
3. In Studio, Control, send `FIRMWARE_RESTART`, answer "which toolhead is mounted?" (it appears in Studio), run `CHECK_TOOLHEADS`.
4. Run the health check: `bash ~/rhino-<version>/rhino.sh`, option **7**. It should pass; it will say
   `pause_resume.cfg is there (the Rhino's own pause, resume and cancel)`.  Anything it marks to fix, fix before going on.

## Checks (also in `docs/testing.md`)

Do these in order. Hand near Stop for anything that moves.

- **MF1 No Mainsail anywhere.** `systemctl is-active klipper moonraker nginx` prints `active` three times, and `ls -d ~/mainsail ~/mainsail-config` says "No such file". *Stop if* Mainsail turns out to be installed.
- **MF2 Studio is the front door.** From the PC, `curl -s http://rhino.local | grep -c "Rhino Studio"` prints 1 or more. *Stop if* it shows nginx's welcome page, a 403, or nothing.
- **MF3 Studio works.** Studio shows Connected, the mounted tool, and (with Crowsnest) the cameras. Open Settings > Software: no Mainsail row, nothing marked broken.
- **MF4 A job's moves.** Home, pause and resume a short print, then cancel one (checks OP2 and OP3). *Stop if* anything moves where it didn't before.
- **MF5 Install twice.** Run option 3 with the same zip again. *Pass:* it finishes with the same "http://rhino.local opens Rhino Studio" line and no errors; Studio still opens. *Stop if* it errors or nginx refuses.
- **MF6 Power cut.** `sudo reboot`. After about two minutes Studio is Connected and Klipper is Ready, with nothing done by hand.
- **MF7 Health check.** Option 7 of `rhino.sh`: nothing marked to fix.

## If something's wrong

| What you see | Do this |
|---|---|
| `http://rhino.local` shows nginx's welcome page | `sudo rm -f /etc/nginx/sites-enabled/default`, `sudo nginx -t`, `sudo systemctl reload nginx` (the installer does this itself from 1.9.45; this is for a host installed with an older release) |
| Studio shows 403 Forbidden | `chmod o+x ~`, reload the page |
| The installer says nginx refused the change | `sudo nginx -t` shows why; usually a second site on port 80. Fix that, then run option 3 again: it is safe to repeat |
| `rhino.local` doesn't open at all | `systemctl status avahi-daemon`; use the host's IP address instead. Some Android phones never resolve `.local` |
| Klipper: "Unable to connect" to the MCU | `ls /dev/serial/by-id/`; `sudo apt remove -y brltty` if installed; `groups` should list `dialout` (log out and in) |
| Klipper won't start and the log says a section is defined twice, or a file is missing | `head -3 ~/printer_data/config/printer.cfg`: exactly one pause/resume include, and the file it names must be there |
| Studio is Connected but no cameras | Crowsnest isn't installed or `crowsnest.conf` names the wrong device (`ls /dev/v4l/by-id/`) |

## Going back

You built this on a spare, so the working Rhino is exactly as it was: power the spare down, plug the MCU boards back
into the old host, boot it. To undo only the Tool Manager on the spare: `bash ~/rhino-<version>/rhino.sh`, option **4)
Undo**. It puts back what the install changed: the config folder and the nginx sites.
To put Mainsail on the spare after all (not tried): KIAUH's Install menu, **Mainsail**, then run option 3 again, which is
meant to move Mainsail to port 8090 and keep Studio on the bare address. KIAUH's own nginx site may clash with Studio's
on port 80 until then, so run `sudo nginx -t` and expect to fix that by hand.

---

## Appendix: removing Mainsail from the running machine (later)

Not before: the pause, resume and cancel change is installed and OP1-OP7 have passed, and the two-week spare period is
over. Mainsail then comes off in these separate steps, each with its own OK from Mike. **Take a backup first** (Studio,
Settings > Host > Backups, and confirm it finished).

1. **KIAUH > Remove > Mainsail**, and `mainsail-config` if it offers. **Answer No if it offers to remove nginx**: Studio is served by it.
   *Pass:* `http://rhino.local` still opens Studio and `systemctl is-active nginx` says `active`. *Stop if* Studio doesn't open: run option 4 (Undo) of `rhino.sh`.
2. Take `[update_manager mainsail]` and `[update_manager mainsail-config]` (and `[update_manager client mainsail]` if it's there) out of `moonraker.conf`, then restart Moonraker.
   *Pass:* Studio's Settings > Software lists Klipper and Moonraker only, and Moonraker's log has no update-manager warning about Mainsail.
3. **Retire the installer's Mainsail step** (the nginx part that moves Mainsail to port 8090). A code change with its own tests, in a release of its own.
4. **Update the manual and the skills** so nothing says Mainsail is part of the Rhino.

*Stop if* at any point Studio can't reach Moonraker: Mainsail was never between them, so that means Moonraker or nginx
was touched. Undo, then look at `journalctl -u moonraker -n 50` and `sudo nginx -t`.
