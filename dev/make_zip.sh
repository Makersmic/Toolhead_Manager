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
fi
rm -f "$OUT"
zip -qr "$OUT" . -x '.git/*' '.github/*' '*__pycache__*' '*node_modules*' 'manual/*' 'docs/*' '*.zip' 'package*.json'
echo "$OUT"
