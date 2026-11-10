# Installing the camera's microphone (Rhino Studio sound)

Mike, Nov 9 2026: hear the machine on the Dashboard. Sound only: the picture stays on crowsnest's MJPEG, so if the
sound ever stops, the cameras don't. Nothing here touches Klipper, Moonraker, crowsnest or the config folder.

**What gets installed on the 7050**

| Piece | What it is | Where |
|---|---|---|
| ffmpeg | Debian 12's package: reads the C920's microphone and encodes the sound (Opus) | `apt` |
| go2rtc 1.9.15 | One program (MIT licence, github.com/AlexxIT/go2rtc), pinned and checksum-checked: passes the sound to the browser over WebRTC | `~/rhino-mic/go2rtc` |
| its settings | API and RTSP on this host only, no outside servers, the C920 by name (`plughw:CARD=C920,DEV=0`) | `~/rhino-mic/go2rtc.yaml` |
| `rhino-mic` service | starts go2rtc at boot; low priority (`Nice=10`), at most half a core and 256 MB | `/etc/systemd/system/rhino-mic.service` |

ffmpeg runs only while someone listens; go2rtc idles otherwise. Studio asks for the sound at `/mic/webrtc` on its
own site (nginx, Tool Manager 1.9.20), which passes only that one request, only from the home network. The sound
then goes straight to the browser on **port 8555** (TCP and UDP). Anyone who can open Studio on the network can listen
while the Dashboard's Sound is on.

## Since 1.9.21: the install does it

Installing Tool Manager 1.9.21 or later (Studio's Update, Install from zip, or the menu) sets the sound up by itself
when a USB camera with a microphone is plugged in, using the go2rtc that comes inside the release zip (checked against
the pinned checksum when the release is built, and again on the Rhino). The install shows a **Camera sound** step:

- *the rhino-mic service is running*: done. Turn it on in Studio: Settings › Cameras › Sound (step 5 below).
- *sound skipped: …*: the install still finished; the reason is on that line and the whole log is named under it
  (`~/rhino-backup-<date>/_rhino_install/mic.log`). The usual one is ffmpeg needing the internet the first time.
- *no USB camera with a microphone found*: plug the camera in and install again.

Undo (menu option 4) takes the sound service away again if that install added it. The steps below still work by hand,
for example to check it (`status`) or remove it on its own.

## By hand: before you start

- Tool Manager **1.9.20 or later** installed (it brings the script, the service files and Studio's `/mic` route).
  Check in Studio: Settings › Software.
- **No job running**, and you can spare a few minutes: ffmpeg's install keeps the host busy for about a minute.
- The C920 plugged in: `cat /proc/asound/cards` shows a line with `[C920 ...]`.

## Steps

1. **Log in:** `ssh pi@rhino.local`
2. **Preview** (changes nothing):
   ```
   bash ~/printer_data/config/scripts/rhino_mic.sh install --dry-run
   ```
   It ends with *Dry run finished: nothing changed.* **Stop if** it says STOPPED: do what it says, or send me the output.
3. **Install:**
   ```
   bash ~/printer_data/config/scripts/rhino_mic.sh install
   ```
   It asks for your password once. Each stage ends in OK, and the last line is *Microphone installed.*
   **Stop if** it says STOPPED. It changes nothing more after that line. In particular:
   - *The download isn't the pinned go2rtc*: don't fetch it another way. Send me the output; GitHub may have replaced
     the file, and the checksum in the script has to be checked again first.
   - *go2rtc started but doesn't answer*: run `journalctl -u rhino-mic -n 30`, send me the output, then undo (below).
4. **Check it:** `bash ~/printer_data/config/scripts/rhino_mic.sh status` shows five OK lines.
5. **In Studio:** Settings › Cameras › Sound: tick *Play the camera's microphone on the Dashboard*. Press **Sound off**
   there to try it (it becomes *Sound on*). Then the Dashboard shows a Sound button beside the camera's name.

## If there's no sound

- Studio says *The microphone service isn't running*: step 4's status says which part is missing.
- *Sound on* but silent: turn the volume slider up, and check the computer's own volume. Then try another browser.
- It connects, then nothing on a phone or another PC: a firewall between them is blocking port 8555. The 7050 has no
  firewall by default; the script says if `ufw` is on.

## Undo (rollback)

```
bash ~/printer_data/config/scripts/rhino_mic.sh remove
```
Stops and removes the `rhino-mic` service and `~/rhino-mic`. Studio then says the service isn't running: untick
Sound in Settings › Cameras. ffmpeg stays (it does nothing on its own); to remove it too: `sudo apt-get remove ffmpeg`.
Undoing the Tool Manager install that added it (menu option 4) removes it too; one installed by hand stays until
you run the line above.

## Checks (Tool Manager docs/testing.md)

MIC1-MIC4.
