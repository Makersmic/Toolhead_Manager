#!/usr/bin/env bash
# Rhino - Kiri:Moto slicer installer (PROTOTYPE). Normally run from the menu (rhino.sh, option 7).
#
#   bash install-kiri.sh --dry-run    shows what it would do, changes nothing
#   bash install-kiri.sh              installs (or updates) Kiri:Moto as a service on port 8090
#   bash install-kiri.sh --remove     stops and removes it, and turns the Slice tab off
#
# Run it as your normal login (not with sudo); it asks for your password once, for the service.
# What it puts where:
#   ~/rhino-kiri/app-<version>   Kiri:Moto (the previous version is kept for going back)
#   ~/rhino-kiri/app             points at the version in use
#   ~/rhino-kiri/node            Node.js 22 (only if this Pi does not already have Node 22 or newer)
#   /etc/systemd/system/rhino-kiri.service
#   ~/printer_data/config/myrhino/slicer.json   "enabled": true  (the portal's Slice tab)
set -u

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${RHINO_CONFIG_DIR:-$HOME/printer_data/config}"
KHOME="${RHINO_KIRI_HOME:-$HOME/rhino-kiri}"
SERVICE="${RHINO_KIRI_SERVICE_FILE:-/etc/systemd/system/rhino-kiri.service}"   # only the test changes these
MOONRAKER="${RHINO_MOONRAKER:-http://127.0.0.1:7125}"
PORT=8090
MODE=install
[ "${1:-}" = "--dry-run" ] && MODE=dry
[ "${1:-}" = "--remove" ] && MODE=remove
DRY=0; [ $MODE = dry ] && DRY=1

step=0
say()  { printf '\n\033[1m[%s] %s\033[0m\n' "$((step+=1))" "$*"; }
ok()   { printf '   \033[32mOK\033[0m   %s\n' "$*"; }
note() { printf '   note %s\n' "$*"; }
fail() { printf '\n\033[31mSTOPPED:\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '%s\n' "$2"; printf '\nNothing after this point was changed.\n'; exit 1; }
do_()  { if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
py()   { python3 -c "$1" 2>/dev/null; }

# slicer.json: set "enabled" (keeps any other settings already in the file)
slicer_enabled() {
  local f="$CFG/myrhino/slicer.json"
  if [ $DRY = 1 ]; then printf '   would set "enabled": %s in %s\n' "$1" "$f"; return 0; fi
  python3 - "$f" "$1" <<'EOF'
import json, os, sys
f, on = sys.argv[1], sys.argv[2] == "true"
d = {}
try:
    d = json.load(open(f))
    if not isinstance(d, dict): d = {}
except (OSError, ValueError):
    pass
d["enabled"] = on
d.setdefault("kiri_port", 8090)
os.makedirs(os.path.dirname(f), exist_ok=True)
json.dump(d, open(f + ".tmp", "w"), indent=2)
os.replace(f + ".tmp", f)
EOF
}

[ $DRY = 1 ] && printf '\033[1mDRY RUN - nothing will be changed.\033[0m\n'
[ "$(id -u)" = 0 ] && fail "Run this as your normal login, without sudo." "Example:  bash $SRC/install-kiri.sh"

# ------------------------------------------------------------------ remove
if [ $MODE = remove ]; then
  say "Removing Kiri:Moto"
  if [ -f "$SERVICE" ]; then
    sudo -v || fail "sudo did not accept the password."
    sudo systemctl disable --now rhino-kiri >/dev/null 2>&1
    sudo rm -f "$SERVICE" && sudo systemctl daemon-reload
    ok "service stopped and removed"
  else
    note "no rhino-kiri service was installed"
  fi
  [ -f "$CFG/myrhino/slicer.json" ] && { slicer_enabled false; ok "Slice tab turned off (myrhino/slicer.json)"; }
  rm -rf "$KHOME" && ok "removed $KHOME"
  printf '\n\033[1mKiri:Moto removed.\033[0m The portal works exactly as before.\n'
  exit 0
fi

# ------------------------------------------------------------------ checks before anything changes
say "Checking this Pi"
[ -f "$SRC/app/app.js" ] && [ -f "$SRC/VERSION" ] || fail "The Kiri:Moto files are not next to this script ($SRC)." "Unzip the whole rhino-kiri zip again."
VERSION="$(cat "$SRC/VERSION")"
ok "Kiri:Moto package $VERSION"
[ -f "$CFG/printer.cfg" ] || fail "No printer.cfg in $CFG." "Is this the Klipper Pi?"
[ -f "$CFG/rhino/slice/profiles.py" ] || fail "The Rhino Tool Manager on this Pi has no Slice tab yet." "Install the matching rhino-config zip first (menu option 3), then this one."
ok "Rhino Tool Manager with the Slice tab is installed"
command -v python3 >/dev/null || fail "python3 is missing." "sudo apt install python3"

case "$(uname -m)" in
  aarch64|arm64) ARCH=arm64 ;;
  armv7l)        ARCH=armv7l ;;
  x86_64)        ARCH=x64 ;;
  *) fail "This Pi's processor ($(uname -m)) has no Node.js 22 download." "Kiri:Moto needs Node.js 22. Ask for help." ;;
esac
ok "processor: $(uname -m)"

state=$(py "import json,urllib.request;print(json.load(urllib.request.urlopen('$MOONRAKER/printer/objects/query?print_stats',timeout=3))['result']['status']['print_stats']['state'])")
case "$state" in
  printing|paused) fail "A job is $state." "Finish or cancel it first." ;;
  "") note "could not ask Moonraker whether a job is running - make sure nothing is printing" ;;
  *) ok "no job running ($state)" ;;
esac

old_service=0; [ -f "$SERVICE" ] && old_service=1
if py "import socket;s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',$PORT))"; then
  if [ $old_service = 1 ]; then ok "port $PORT is used by the installed Kiri:Moto (it is replaced)"
  else fail "Something else is using port $PORT." "Find it with:  sudo ss -ltnp | grep :$PORT"; fi
else
  ok "port $PORT is free"
fi

need_mb=$(( $(du -sm "$SRC/app" | cut -f1) + 120 ))
free_mb=$(df -Pm "$HOME" | awk 'NR==2 {print $4}')
[ "${free_mb:-0}" -ge "$need_mb" ] || fail "Not enough free space: $free_mb MB free, about $need_mb MB needed." "Free some space (old backups: ls -d ~/rhino-backup-*)."
ok "free space: $free_mb MB (about $need_mb MB needed)"

# Node.js: use this Pi's own if it is new enough, otherwise our own copy
. "$SRC/NODE"
node_version="${RHINO_NODE_VERSION:-$node_version}"
node_mirror="${RHINO_NODE_MIRROR:-$node_mirror}"
NODE=""
if command -v node >/dev/null && [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -ge 22 ]; then
  NODE="$(command -v node)"; ok "Node.js $(node --version) already on this Pi"
elif [ -x "$KHOME/node/bin/node" ] && [ "$("$KHOME/node/bin/node" -p 'process.versions.node.split(".")[0]')" -ge 22 ]; then
  NODE="$KHOME/node/bin/node"; ok "Node.js $("$NODE" --version) already installed for Kiri:Moto"
else
  note "Node.js 22 is needed: v$node_version ($ARCH) will be downloaded from $node_mirror and checked"
fi

[ $DRY = 0 ] && { say "Your Pi password (needed for the service; typing is invisible)"; sudo -v || fail "sudo did not accept the password."; ok "sudo ready"; }

# ------------------------------------------------------------------ Node.js
if [ -z "$NODE" ]; then
  say "Downloading Node.js v$node_version"
  tarball="node-v$node_version-linux-$ARCH.tar.xz"
  if [ $DRY = 1 ]; then
    printf '   would download %s/v%s/%s and check it against SHASUMS256.txt\n' "$node_mirror" "$node_version" "$tarball"
  else
    tmpd="$(mktemp -d)"
    curl -fsSL -o "$tmpd/$tarball" "$node_mirror/v$node_version/$tarball" || fail "Could not download Node.js." "Check the Pi's internet connection, then run this again."
    curl -fsSL -o "$tmpd/SHASUMS256.txt" "$node_mirror/v$node_version/SHASUMS256.txt" || fail "Could not download Node.js's checksum list."
    want="$(awk -v f="$tarball" '$2 == f {print $1}' "$tmpd/SHASUMS256.txt")"
    have="$(sha256sum "$tmpd/$tarball" | cut -d' ' -f1)"
    [ -n "$want" ] && [ "$want" = "$have" ] || fail "The Node.js download did not match its checksum." "Run this again; if it keeps failing, ask for help."
    ok "download checked (sha256)"
    mkdir -p "$KHOME" && rm -rf "$KHOME/node.new" && mkdir -p "$KHOME/node.new"
    tar -xJf "$tmpd/$tarball" -C "$KHOME/node.new" --strip-components=1 || fail "Could not unpack Node.js."
    rm -rf "$KHOME/node" && mv "$KHOME/node.new" "$KHOME/node" && rm -rf "$tmpd"
    NODE="$KHOME/node/bin/node"
    ok "Node.js $("$NODE" --version) in $KHOME/node"
  fi
fi
[ $DRY = 1 ] && [ -z "$NODE" ] && NODE="$KHOME/node/bin/node"

# ------------------------------------------------------------------ Kiri:Moto files
say "Copying Kiri:Moto $VERSION"
dest="$KHOME/app-$VERSION"
prev=""; [ -L "$KHOME/app" ] && prev="$(readlink "$KHOME/app")"
if [ $DRY = 1 ]; then
  printf '   would copy %s to %s and point %s at it\n' "$SRC/app" "$dest" "$KHOME/app"
else
  mkdir -p "$KHOME" && rm -rf "$dest.new"
  cp -a "$SRC/app" "$dest.new" || fail "Copy failed (is the SD card full?  df -h ~)."
  rm -rf "$dest" && mv "$dest.new" "$dest"
  ln -sfn "$dest" "$KHOME/app.new" && mv -T "$KHOME/app.new" "$KHOME/app"
  ok "files in $dest"
  # keep the version in use and the one before it (for going back); remove older ones
  for d in "$KHOME"/app-*; do
    [ -d "$d" ] || continue
    [ "$d" = "$dest" ] || [ "$d" = "$prev" ] || { rm -rf "$d"; note "removed old $(basename "$d")"; }
  done
fi

# ------------------------------------------------------------------ service
say "Starting Kiri:Moto as a service on port $PORT (starts by itself at every boot)"
unit="$(mktemp)"
cat > "$unit" <<EOF
# Kiri:Moto slicer for the Rhino Tool Manager's Slice tab (installed by install-kiri.sh)
[Unit]
Description=Kiri:Moto slicer for the Rhino Tool Manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$KHOME/app
ExecStart=$NODE $KHOME/app/node_modules/@gridspace/app-server/app-server-run.js --single --port $PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=$KHOME

[Install]
WantedBy=multi-user.target
EOF
[ $old_service = 1 ] && do_ sudo systemctl stop rhino-kiri
do_ sudo install -m 644 "$unit" "$SERVICE"
rm -f "$unit"
do_ sudo systemctl daemon-reload
do_ sudo systemctl enable --now rhino-kiri
do_ sudo systemctl restart rhino-kiri
if [ $DRY = 0 ]; then
  up=0
  for i in $(seq 1 90); do       # a Pi takes a while to get Kiri:Moto going the first time
    sleep 1
    if py "import urllib.request;urllib.request.urlopen('http://127.0.0.1:$PORT/kiri/',timeout=2)"; then up=1; break; fi
  done
  [ $up = 1 ] || fail "Kiri:Moto did not answer on port $PORT." "See why with:  journalctl -u rhino-kiri -n 30 --no-pager"
  ok "Kiri:Moto answering on port $PORT"
fi

# ------------------------------------------------------------------ Slice tab
say "Turning on the portal's Slice tab"
slicer_enabled true
[ $DRY = 0 ] && ok "myrhino/slicer.json: enabled (the portal picks it up on the next page load)"
[ $DRY = 0 ] && echo "$VERSION" > "$KHOME/installed-version"

ip=$(hostname -I 2>/dev/null | awk '{print $1}')
printf '\n\033[1m%s\033[0m\n' "$([ $DRY = 1 ] && echo 'Dry run finished - nothing was changed.' || echo 'Kiri:Moto installed.')"
[ $DRY = 1 ] && exit 0
cat <<EOF

Open the portal (http://${ip:-YOUR-PI}:5000) and click Slice in the sidebar.
The first time it opens, Kiri:Moto shows its Help window once - close it.
Remove it again with the menu (option 7, then Remove).
EOF
