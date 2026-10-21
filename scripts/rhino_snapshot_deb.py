#!/usr/bin/env python3
"""Fetch a package that has vanished from Debian's servers, from snapshot.debian.org, and check it (1.5.5).

  rhino_snapshot_deb.py PACKAGE OUT_DIR      -> prints the path of the checked .deb, exit 0
                                                  (exit 1 with a reason on stderr otherwise)

Why: Debian 11 "bullseye" left LTS on 31 Aug 2026. The Pi's package lists can still name a version (avahi-utils
0.8-5+deb11u3) that security.debian.org no longer serves, so apt gets "404 Not Found" and, because avahi's packages
depend on each other at the exact version, an older one won't do either. snapshot.debian.org keeps every file Debian
ever published.

Safety: the version and the expected SHA256 come from this Pi's own package lists (apt-cache), which apt has already
checked against Debian's signing keys. The file is only accepted if its SHA256 matches that, so the snapshot server is
only trusted to deliver bytes, never to say what they should be. Nothing is installed here; install.sh does that with
apt-get, which still checks dependencies.
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("RHINO_SNAPSHOT_URL", "https://snapshot.debian.org").rstrip("/")


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout


def candidate(pkg):
    for line in sh("apt-cache", "policy", pkg).splitlines():
        if line.strip().startswith("Candidate:"):
            v = line.split(":", 1)[1].strip()
            return None if v in ("", "(none)") else v
    return None


def expected_sha256(pkg, ver):
    for line in sh("apt-cache", "show", f"{pkg}={ver}").splitlines():
        if line.startswith("SHA256:"):
            return line.split(":", 1)[1].strip().lower()
    return None


def get(url, limit=200 * 1024 * 1024):
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("too big")
    return data


def main():
    if len(sys.argv) != 3:
        print(__doc__.split("\n")[2].strip(), file=sys.stderr)
        return 2
    pkg, out_dir = sys.argv[1], sys.argv[2]
    ver = candidate(pkg)
    if not ver:
        print(f"apt doesn't know a version of {pkg}", file=sys.stderr)
        return 1
    want = expected_sha256(pkg, ver)
    if not want or len(want) != 64:
        print(f"no SHA256 for {pkg} {ver} in this Pi's package lists", file=sys.stderr)
        return 1
    arch = sh("dpkg", "--print-architecture").strip()
    try:
        info = json.loads(get(f"{BASE}/mr/binary/{urllib.parse.quote(pkg)}/{urllib.parse.quote(ver)}/binfiles"))
        hashes = [b["hash"] for b in info.get("result", []) if b.get("architecture") in (arch, "all")]
    except Exception as e:                                   # noqa: BLE001 - any failure means "couldn't"
        print(f"snapshot.debian.org didn't answer for {pkg} {ver} ({e.__class__.__name__})", file=sys.stderr)
        return 1
    for h in hashes:
        if not all(c in "0123456789abcdef" for c in h.lower()):
            continue
        try:
            data = get(f"{BASE}/file/{h}")
        except Exception:                                    # noqa: BLE001
            continue
        if hashlib.sha256(data).hexdigest() != want:
            continue                                         # not the file the signed lists describe: never used
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{pkg}_{ver.replace(':', '%3a')}_{arch}.deb")
        with open(path, "wb") as f:
            f.write(data)
        print(path)
        return 0
    print(f"snapshot.debian.org has no file for {pkg} {ver} ({arch}) matching this Pi's package lists", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
