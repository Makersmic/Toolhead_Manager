#!/bin/sh
# PROTOTYPE (developer use only - not run by rhino.sh yet).
# Builds the pinned Kiri:Moto with the Rhino patch and mod, ready to serve on port 8090:
#
#     sh dev/kiri_build.sh [build dir]       (default: ../kiri-build next to this repo)
#     node <build dir>/node_modules/@gridspace/app-server/app-server-run.js --single --port 8090
#
# Needs git and Node.js 22 or newer. Takes a few minutes and about 1 GB while building.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:-"$HERE/../kiri-build"}
. "$HERE/kiri/PINNED"

if [ ! -d "$DEST/.git" ]; then
  git clone "$repo" "$DEST"
fi
cd "$DEST"
git fetch --depth 1 origin "$commit"
git checkout -f "$commit"
git clean -fdx -e node_modules
for p in "$HERE"/kiri/patches/*.patch; do
  git apply "$p"
done
rm -rf mods/rhino && cp -r "$HERE/kiri/mods/rhino" mods/rhino

export ELECTRON_SKIP_BINARY_DOWNLOAD=1
npm i --no-audit --no-fund
npm run webpack-ext
npm run pack-prod
echo "Kiri:Moto $version built in $DEST"
