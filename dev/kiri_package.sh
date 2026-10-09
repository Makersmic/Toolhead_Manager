#!/bin/sh
# PROTOTYPE (developer use only). Turns a Kiri:Moto build from dev/kiri_build.sh into the zip the
# Rhino menu installs (rhino.sh -> "Kiri:Moto slicer"): only what the server and the browser use,
# links replaced by real files, no build tools, no native parts - the same zip works on any Pi.
#
#     sh dev/kiri_package.sh <build dir> [output dir]      -> rhino-kiri-<version>-<rev>.zip
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
SRC=$(cd "$1" && pwd)
OUT=$(cd "${2:-$HERE/..}" && pwd)
. "$HERE/kiri/PINNED"
REV=$(cat "$HERE/kiri/PACKAGE_REV")
NAME="rhino-kiri-$version-$REV"
STAGE=$(mktemp -d)
APP="$STAGE/app"
mkdir -p "$APP"

# the app itself; cp -L turns Kiri's links into node_modules into real files
cp "$SRC/app.js" "$SRC/package.json" "$SRC/license.md" "$APP/"
for d in conf src web alt; do cp -RL "$SRC/$d" "$APP/$d"; done
mkdir -p "$APP/mods"
for m in bambu proxy; do cp -RL "$SRC/mods/$m" "$APP/mods/$m"; done
cp -R "$HERE/kiri/mods/rhino" "$APP/mods/rhino"        # always the Rhino mod from this repo
rm -f "$APP"/web/boot/bundle-*.bin          # offline-install bundle: needs HTTPS, not used here (26 MB)

# server-side packages: the ones the server loads (traced), and everything they depend on
mkdir -p "$APP/node_modules"
node "$HERE/dev/kiri_deps.js" "$SRC" | while read -r pkg; do
  mkdir -p "$APP/node_modules/$(dirname "$pkg")"
  cp -RL "$SRC/node_modules/$pkg" "$APP/node_modules/$pkg"
done
if find "$APP" -name "*.node" | grep -q .; then echo "native module found - the zip would not be portable" >&2; exit 1; fi

cp "$HERE/kiri/PINNED" "$STAGE/PINNED"
echo "$version-$REV" > "$STAGE/VERSION"
cp "$HERE/kiri/install-kiri.sh" "$STAGE/install-kiri.sh"
cp "$HERE/kiri/NODE" "$STAGE/NODE"
rm -f "$OUT/$NAME.zip"
(cd "$STAGE" && zip -qr "$OUT/$NAME.zip" .)
rm -rf "$STAGE"
echo "$OUT/$NAME.zip ($(du -h "$OUT/$NAME.zip" | cut -f1))"
