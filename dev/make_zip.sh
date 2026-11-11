#!/bin/sh
# Build the release zip: rhino-config-<VERSION>.zip next to this repo.
#
#   sh dev/make_zip.sh ../rhino-studio      with Rhino Studio built into studio/ (served by the Pi's nginx)
#   sh dev/make_zip.sh                      without Studio (the installer then skips that step)
#
# studio/ is made here and never committed (.gitignore). Same exclusions as every release zip.
set -eu
cd "$(dirname "$0")/.."
VER="$(cat VERSION)"
OUT="$(cd .. && pwd)/rhino-config-$VER.zip"
rm -rf studio
if [ -n "${1:-}" ]; then
  ( cd "$1" && npm run build >/dev/null )
  cp -a "$1/dist" studio
  node -p "require('$(cd "$1" && pwd)/package.json').version" > studio/VERSION
  echo "Studio $(cat studio/VERSION) built into studio/"
  # Help (docs/phase-help.md): the manual's web pages, served with Studio so they work with no internet
  cp -a manual/web studio/help
fi
# The camera sound's go2rtc (1.9.21, docs/install-mic.md): RHINO_GO2RTC=1 (the release) puts the pinned build inside,
# checked against the checksum in scripts/rhino_mic.sh, with its MIT licence. Never committed (.gitignore).
rm -rf vendor
if [ "${RHINO_GO2RTC:-}" = 1 ]; then
  GVER="$(sed -n 's/^VER=//p' scripts/rhino_mic.sh)"
  GSHA="$(sed -n 's/^SHA=\([0-9a-f]\{64\}\)$/\1/p' scripts/rhino_mic.sh)"
  mkdir -p vendor/go2rtc
  curl -fsSL -o vendor/go2rtc/go2rtc_linux_amd64 "https://github.com/AlexxIT/go2rtc/releases/download/v$GVER/go2rtc_linux_amd64"
  echo "$GSHA  vendor/go2rtc/go2rtc_linux_amd64" | sha256sum -c - || { echo "go2rtc $GVER isn't the pinned file: release stopped"; exit 1; }
  curl -fsSL -o vendor/go2rtc/LICENSE "https://raw.githubusercontent.com/AlexxIT/go2rtc/v$GVER/LICENSE"
  grep -q "MIT License" vendor/go2rtc/LICENSE || { echo "go2rtc's licence isn't MIT any more: check before shipping it"; exit 1; }
  printf 'go2rtc %s by Alexey Khit (github.com/AlexxIT/go2rtc), MIT licence (LICENSE here). Used unchanged as its own\nprogram for the camera sound (docs/install-mic.md); install.sh copies it to ~/rhino-mic.\n' "$GVER" > vendor/go2rtc/README
  echo "go2rtc $GVER inside (checksum matches)"
fi
rm -f "$OUT"
zip -qr "$OUT" . -x '.git/*' '.github/*' '*__pycache__*' '*node_modules*' 'manual/*' 'docs/*' '*.zip' 'package*.json'
echo "$OUT"
