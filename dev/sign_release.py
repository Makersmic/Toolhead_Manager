#!/usr/bin/env python3
"""Release signing (1.9.29): make a key pair, or sign a release zip.

    python3 dev/sign_release.py --new-key
        Prints a new ed25519 key pair: the seed goes in the GitHub Actions secret RHINO_SIGNING_KEY (and a private
        copy you keep), the public key goes in PUBLIC_KEYS in scripts/rhino_update_helper.py.

    RHINO_SIGNING_KEY=<base64 seed> python3 dev/sign_release.py rhino-config-1.9.29.zip
        Writes rhino-config-1.9.29.zip.sig (base64 ed25519 signature of the whole file), then checks it with the
        updater's own verify and the public key in the helper (so a key that isn't in PUBLIC_KEYS fails here, not on
        a user's machine). The release workflow runs this; a missing secret stops the release.

The maths lives in scripts/rhino_update_helper.py (standard library only), so what signs is what verifies.
"""
import argparse
import base64
import importlib.util
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rhino_update_helper", os.path.join(HERE, "..", "scripts", "rhino_update_helper.py"))
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip", nargs="?", help="rhino-config-<version>.zip to sign")
    ap.add_argument("--new-key", action="store_true", help="print a new key pair and exit")
    a = ap.parse_args()
    if a.new_key:
        seed = secrets.token_bytes(32)
        print("RHINO_SIGNING_KEY (secret seed, base64):", base64.b64encode(seed).decode())
        print("PUBLIC_KEYS entry (base64):             ", base64.b64encode(H.ed25519_public(seed)).decode())
        return 0
    if not a.zip:
        ap.error("give the zip to sign, or --new-key")
    try:
        seed = base64.b64decode(os.environ["RHINO_SIGNING_KEY"].strip(), validate=True)
        if len(seed) != 32:
            raise ValueError
    except (KeyError, ValueError):
        print("RHINO_SIGNING_KEY must be set to the base64 32-byte seed (dev/sign_release.py --new-key makes one).", file=sys.stderr)
        return 1
    sig = H.ed25519_sign(seed, path=a.zip)
    out = a.zip + ".sig"
    with open(out, "w") as f:
        f.write(base64.b64encode(sig).decode() + "  " + os.path.basename(a.zip) + "\n")
    try:
        H.check_signature(a.zip, out)
    except ValueError as e:
        os.unlink(out)
        print(f"Signed, but the updater would refuse it: {e}", file=sys.stderr)
        print("Is this key's public half in PUBLIC_KEYS in scripts/rhino_update_helper.py?", file=sys.stderr)
        return 1
    print(f"Signed: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
