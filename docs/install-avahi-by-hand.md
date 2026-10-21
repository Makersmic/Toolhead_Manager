# Installing avahi-utils by hand (for `rhinostudio.local`)

The Rhino install sets up `http://rhinostudio.local` with avahi-utils. On a Pi running Debian 11 "bullseye"
(MainsailOS / Raspberry Pi OS before bookworm) it can fail with:

```
Err:1 http://security.debian.org/debian-security bullseye-security/main arm64 avahi-utils arm64 0.8-5+deb11u3
  404  Not Found
```

Bullseye left Debian's long-term support on 31 August 2026. Your Pi's package lists still name that version, the
server no longer has the file, and an older avahi-utils won't install because avahi's packages must all be the same
version. `sudo apt update` doesn't change that. From 1.5.5 the install fetches the file from Debian's snapshot archive
by itself; these are the same steps by hand, if that didn't work.

1. Ask the snapshot archive for the file's id (change `arm64` below to `armhf` on 32-bit systems):

   ```
   curl -s "https://snapshot.debian.org/mr/binary/avahi-utils/0.8-5%2Bdeb11u3/binfiles"
   ```

   Take the `"hash"` next to `"architecture":"arm64"`.

2. Download it (put the hash at the end):

   ```
   curl -fL -o /tmp/avahi-utils.deb https://snapshot.debian.org/file/<hash>
   ```

3. Check it's the genuine file. These two must print the same code. The first comes from your Pi's own package
   lists, which apt has already checked against Debian's keys:

   ```
   apt-cache show avahi-utils=0.8-5+deb11u3 | grep SHA256
   sha256sum /tmp/avahi-utils.deb
   ```

   **If they differ, stop.** Don't install it.

4. Install it, then install the Rhino zip again (Studio: Settings › Software › Install from zip):

   ```
   sudo apt install /tmp/avahi-utils.deb
   ```

If `apt-cache policy avahi-utils` shows a different version than `0.8-5+deb11u3`, use that version in steps 1 and 3.

The long-term fix is moving the Pi to Debian 12 "bookworm", which has security support until June 2028.
