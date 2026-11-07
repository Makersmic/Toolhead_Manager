# A Clonezilla image of the 7050's SSD

A one-time copy of the whole SSD, taken after the 7050 was accepted (decisions.md, 2026-11-07). Recovery after a dead
SSD is then: **restore this image to a new SSD, then restore the newest backup zip.** The image holds Debian, Klipper,
Moonraker, Mainsail, Tool Manager and PrusaSlicer exactly as they were. The backup zip holds everything since.

Clonezilla only **reads** the SSD when it saves an image. The one way to lose data is to choose *restore* where you
meant *save*, or to write the Clonezilla USB stick onto the wrong drive. Both steps have a *Stop if*.

## What you need

- A USB stick of 1 GB or more for Clonezilla. It gets wiped.
- A USB drive for the image, with more free space than the 7050 uses. Check over SSH: `df -h /` and look at **Used**.
  ext4, exFAT or NTFS all work. Use one that won't be wiped for something else.
- The keyboard and screen on the 7050, as for the first install.
- 30-60 minutes. The Rhino can't run during it.

## 1. Before (machine on)

1. Studio: **Back up now**, and wait for it to say pushed to GitHub. *Stop if* it fails: fix the backup first.
2. Note the version (Settings › Software, 1.9.10) and today's date. They go in the image's name.
3. Over SSH: `df -h /`. Write down **Used**. *Stop if* the image drive has less free space than that.
4. Turn the Rhino's 24 V supply off, then on the 7050: `sudo poweroff`.

## 2. Make the Clonezilla stick (on the PC)

1. Download Clonezilla Live **stable, amd64, ISO** from clonezilla.org. Check its SHA256 against the page's.
2. Plug the stick in and find it with `lsblk`. It's the one whose size matches the stick and that appeared when you
   plugged it in, for example `/dev/sdb`. **Stop if** you're not sure which one it is. Ask before going on.
3. Write it (replace `sdX` with the stick, the whole device, not a `sdX1` partition):
   ```
   sudo dd if=clonezilla-live-*-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
   ```
   balenaEtcher does the same with a picker, if you'd rather not type the device.

## 3. Save the image (on the 7050)

1. Plug in the Clonezilla stick and the image drive. The Octopus and webcam can stay plugged in.
2. Power on and press **F12** for the boot menu. Pick the Clonezilla stick (UEFI).
   - **Watch the screen at power-on** for an AC adapter warning that waits for F1. Write down what it says (move log,
     Nov 6: still to check). Press F1 if it asks.
   - If Secure Boot refuses the stick: F2 › Secure Boot › off, boot it, and turn Secure Boot back on in step 5.
3. Clonezilla: **Clonezilla live (Default settings)**, your language and keyboard, then **Start Clonezilla**.
4. Choose these, in order:
   - **device-image** (disk to image file)
   - **local_dev**. It asks you to plug in the drive: it already is, so press Enter. Pick the **image drive**'s partition. *Stop if* the only
     choices are the SSD's partitions: the image drive wasn't found. Never pick the SSD here.
   - Pick the top folder of the drive (or a folder on it), then **Done**.
   - **Beginner**
   - **savedisk**. **Stop if** you're on a screen that says *restoredisk*. Go back. Restore overwrites the SSD.
   - Name: `rhino-7050-1.9.10-2026-11-DD` (today's date).
   - Source disk: the **SSD** (the internal drive, its size matches the 7050's SSD, usually `sda`). *Stop if* there's
     more than one choice and you can't tell which is the SSD. The image drive and stick are USB.
   - Compression: the default (`-z1p`).
   - File system check: **skip** (the default). The SSD's file system is fine, and the check can be slow.
   - **Yes, check the saved image** after saving.
   - Encrypt: **no** (a passphrase you've forgotten in two years makes the image useless).
   - When done: **poweroff**.
5. Confirm with **y** where it asks. Wait. At the end it should say the image was checked and is restorable.
   **Stop if** it reports an error while saving or checking. The SSD wasn't changed, so the 7050 is fine; tell me the
   message.

## 4. After

1. Unplug the stick and the image drive. If you turned Secure Boot off, turn it back on (F2).
2. Turn the 24 V supply on and power the 7050 on. It should boot normally (it boots from the SSD).
3. Studio opens, Klipper is Ready, Settings › Software says 1.9.10.
4. On the PC, plug in the image drive and check the folder `rhino-7050-1.9.10-...` is there with files in it.
5. Label the drive: *Rhino 7050 image, date, 1.9.10*. Keep it away from the machine (a fire or power surge that kills
   the 7050 shouldn't take the image too).
6. Tell me: the image name, its size, and what the power-on screen said about the adapter. I'll add them to the
   move log.

## Rollback

Saving an image changes nothing on the SSD, so there's nothing to undo on the 7050.

- **The 7050 boots Clonezilla again, or nothing, after.** The stick is still plugged in, or the boot order changed:
  unplug it, or press F12 and pick the SSD (*Debian*). In F2, put the SSD first in the boot order.
- **It stops at a warning screen that waits for F1.** That's the adapter warning: press F1 to boot. Then we decide
  whether to set the BIOS to continue on warnings, so it comes back alone after a power cut.
- **Secure Boot was turned off and Debian won't boot after turning it back on.** Turn it off again, boot, and tell me.
  (Debian 12 boots with it on, so this shouldn't happen.)
- **The wrong stick got written with `dd`.** Stop. Don't write anything else to that drive. Tell me what was on it.

## Using the image: recovery after a dead SSD

Only when the SSD has failed or the system can't be repaired. This **overwrites** the target disk.

1. Fit the new SSD (same size or bigger). Boot the Clonezilla stick as in step 3.
2. **device-image**, **local_dev**, the image drive, **Beginner**, **restoredisk**, the image, the target: the new SSD.
   Clonezilla asks twice before writing. Read the disk names before each yes.
3. Boot the 7050. It's now as it was on the image's date.
4. Restore the newest backup zip with `rhino.sh`, as in migrate-7050.md §7 (the same version on both: install the
   version the zip was made with first, if it's newer than the image's).
5. Run the health check (option 7) and the §8 first checks.
