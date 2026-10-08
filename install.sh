#!/usr/bin/env bash
# Rhino tool manager - installer.
#
#   bash ~/rhino-<version>/install.sh --dry-run    shows what it would do, changes nothing
#   bash ~/rhino-<version>/install.sh              installs
#
# Run it as your normal login (not with sudo); it asks for your password when it needs it.
# It stops at the first problem and tells you what to do. Undo with:  bash ~/rhino-<version>/uninstall.sh
set -u

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${RHINO_CONFIG_DIR:-$HOME/printer_data/config}"
STAMP="$(date +%Y-%m-%d-%H%M)"
BACKUP="$HOME/rhino-backup-$STAMP"
# A second install in the same minute must not copy into the first backup (cp -a would nest it inside)
n=1; while [ -e "$BACKUP" ]; do n=$((n+1)); BACKUP="$HOME/rhino-backup-$STAMP-$n"; done
LAST="$HOME/.rhino-last-backup"
SERVICE="${RHINO_SERVICE_FILE:-/etc/systemd/system/rhino-portal.service}"   # only dev/test_install.py sets this
MOONRAKER="${RHINO_MOONRAKER:-http://127.0.0.1:7125}"
MARK='#*# <---------------------- SAVE_CONFIG ---------------------->'
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

step=0
say()  { printf '\n\033[1m[%s] %s\033[0m\n' "$((step+=1))" "$*"; }
ok()   { printf '   \033[32mOK\033[0m   %s\n' "$*"; }
note() { printf '   note %s\n' "$*"; }
fail() { printf '\n\033[31mSTOPPED:\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '%s\n' "$2"; printf '\nNothing after this point was changed.\n'; exit 1; }
# do: run a command, or only show it in a dry run
do_() { if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
py()  { python3 -c "$1" 2>/dev/null; }

[ $DRY = 1 ] && printf '\033[1mDRY RUN - nothing will be changed.\033[0m\n'

# ------------------------------------------------------------------ checks before anything changes
say "Checking this Pi"
[ "$(id -u)" = 0 ] && fail "Run this as your normal login, without sudo." "Example:  bash $SRC/install.sh"
[ -f "$CFG/printer.cfg" ] || fail "No printer.cfg in $CFG." "Is this the Klipper Pi? Your config folder should be ~/printer_data/config."
ok "config folder: $CFG"
[ -f "$SRC/scripts/rhino_portal.py" ] && [ -d "$SRC/rhino" ] || fail "The new files are not next to this script ($SRC)." "Unzip the whole zip again (see the install guide, step 3)."
ok "new files: $SRC"
case "$SRC/" in "$CFG"/*) fail "This script is inside your config folder ($SRC)." "Unzip to a folder in your home instead (see the install guide, step 3)." ;; esac
command -v python3 >/dev/null || fail "python3 is missing." "sudo apt install python3"
ok "login: $USER (home $HOME)"

state=$(py "import json,urllib.request;print(json.load(urllib.request.urlopen('$MOONRAKER/printer/objects/query?print_stats',timeout=3))['result']['status']['print_stats']['state'])")
case "$state" in
  printing|paused) fail "A job is $state." "Finish or cancel it first - installing restarts the portal and you will restart Klipper." ;;
  "") note "could not ask Moonraker whether a job is running - make sure nothing is printing" ;;
  *) ok "no job running ($state)" ;;
esac

old_service=0
if [ -f "$SERVICE" ]; then
  old_service=1
  note "an existing rhino-portal service was found - it is saved in the backup and replaced"
fi
if py "import socket;s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',5000))"; then
  if [ $old_service = 1 ] && systemctl is-active --quiet rhino-portal 2>/dev/null; then
    ok "port 5000 is used by the old rhino-portal service (it is stopped before the new one starts)"
  else
    fail "Something else is using port 5000." "Find it with:  sudo ss -ltnp | grep :5000   - stop it, or ask for help, then run this again."
  fi
fi

# Zips up to 1.3.3 carried a .git folder of our own that the copy step put into your config folder. If your config
# folder is a git repository (a GitHub backup), that replaced its current branch. Only reported here - nothing is changed.
RHINO_GIT=ba3346dba51cdaa3f02fa67bd41725b2dec170ac
git_head() { local d="$1/.git" r; [ -f "$d/HEAD" ] || return 1; r=$(cat "$d/HEAD"); case "$r" in "ref: "*) cat "$d/${r#ref: }" 2>/dev/null || grep " ${r#ref: }$" "$d/packed-refs" 2>/dev/null | cut -d' ' -f1 ;; *) echo "$r" ;; esac; }
if [ "$(git_head "$CFG")" = "$RHINO_GIT" ]; then
  own=""
  for b in "$HOME"/rhino-backup-*; do h=$(git_head "$b") && [ "$h" != "$RHINO_GIT" ] && { own="$b"; break; }; done
  if [ -n "$own" ]; then
    printf '\n   \033[33mCHECK\033[0m your config folder'"'"'s git repository was overwritten by an earlier Rhino zip.\n'
    printf '         Your own one is in %s/.git. To put it back:\n' "$own"
    printf '         rm -rf %s/.git && cp -a %s/.git %s/\n' "$CFG" "$own" "$CFG"
  else
    printf '\n   \033[33mCHECK\033[0m %s/.git came from an earlier Rhino zip, not from you.\n' "$CFG"
    printf '         No backup has a git repository of your own, so you can delete it:  rm -rf %s/.git\n' "$CFG"
  fi
fi

for c in rsync unzip; do
  command -v $c >/dev/null || { note "$c is missing - it will be installed"; NEED_APT="${NEED_APT:-} $c"; }
done

# ------------------------------------------------------------------ sudo once, up front
if [ $DRY = 0 ]; then
  say "Your Pi password (needed to install packages and the service; typing is invisible)"
  sudo -v || fail "sudo did not accept the password."
  ok "sudo ready"
fi

# ------------------------------------------------------------------ backup
say "Backing up your config folder"
do_ cp -a "$CFG" "$BACKUP" || fail "Backup copy failed (is the SD card full?  df -h ~)."
do_ mkdir -p "$BACKUP/_rhino_install"
[ $old_service = 1 ] && do_ cp "$SERVICE" "$BACKUP/_rhino_install/old-rhino-portal.service"
[ $DRY = 0 ] && echo "$BACKUP" > "$LAST"
[ $DRY = 0 ] && ok "backup: $BACKUP"

# ------------------------------------------------------------------ helper programs
if [ -n "${NEED_APT:-}" ]; then
  say "Installing:${NEED_APT}"
  do_ sudo apt-get install -y ${NEED_APT} || fail "apt could not install${NEED_APT}." "Try:  sudo apt update   then run this again."
fi

# ------------------------------------------------------------------ copy
say "Copying the new files into your config folder"
had_positions=0; [ -f "$CFG/myrhino/positions.cfg" ] && had_positions=1
# Never copied: your saved state, git files, the test folder, zips and the installers themselves.
EXCL=(--exclude .git/ --exclude .gitignore --exclude variables.cfg --exclude variables.save --exclude dev/ --exclude '*.zip'
      --exclude install.sh --exclude uninstall.sh --exclude rhino.sh --exclude VERSION
      --exclude myrhino/custom_tools.cfg --exclude myrhino/maintenance_status.cfg --exclude myrhino/positions.cfg)
do_ rsync -a "${EXCL[@]}" "$SRC/" "$CFG/" || fail "Copy failed." "Your backup is in $BACKUP."
# Generated files and your positions: only put the starter copy in place if you do not have one yet.
for f in myrhino/custom_tools.cfg myrhino/maintenance_status.cfg myrhino/positions.cfg; do
  [ -f "$CFG/$f" ] || do_ cp "$SRC/$f" "$CFG/$f"
done
if [ $DRY = 0 ]; then
  [ -f "$CFG/scripts/rhino_portal.py" ] || fail "The copy did not arrive (scripts/rhino_portal.py missing)."
fi
[ $DRY = 0 ] && ok "files copied"
if [ $had_positions = 1 ]; then ok "your positions (myrhino/positions.cfg) kept as they are"
else note "myrhino/positions.cfg is new: the park, swap and prime-line positions are set there now"; fi
if grep -q "^variable_tool_swap_park_" "$CFG/variables.cfg" 2>/dev/null; then
  note "variables.cfg still has tool_swap_park_x/y/z - nothing reads them now (the swap spot is swap_x/swap_y"
  note "in myrhino/positions.cfg). You can delete those three lines."
fi

# ------------------------------------------------------------------ SAVE_CONFIG block
say "Keeping the settings Klipper saved at the bottom of printer.cfg (SAVE_CONFIG)"
if [ $DRY = 1 ]; then
  if grep -qF "$MARK" "$CFG/printer.cfg"; then note "your printer.cfg has a SAVE_CONFIG section - it would be carried over"
  else note "your printer.cfg has no SAVE_CONFIG section - nothing to carry over"; fi
elif grep -qF "$MARK" "$CFG/printer.cfg"; then
  ok "printer.cfg already has its SAVE_CONFIG section"
elif grep -qF "$MARK" "$BACKUP/printer.cfg"; then
  { echo; sed -n "/^#\*# <---------------------- SAVE_CONFIG/,\$p" "$BACKUP/printer.cfg"; } >> "$CFG/printer.cfg"
  n=$(grep -cF "$MARK" "$CFG/printer.cfg")
  [ "$n" = 1 ] || fail "SAVE_CONFIG section count is $n, expected 1." "Undo with:  bash $SRC/uninstall.sh"
  ok "SAVE_CONFIG section carried over"
else
  note "your old printer.cfg had no SAVE_CONFIG section - nothing to carry over"
fi

# ------------------------------------------------------------------ other logins
if [ "$HOME" != "/home/pi" ]; then
  say "Pointing /home/pi paths at $HOME"
  if [ $DRY = 1 ]; then
    printf '   would change /home/pi in: %s\n' "$(cd "$SRC" && grep -rl /home/pi --include='*.cfg' . | tr '\n' ' ')"
  else
    (cd "$CFG" && grep -rl /home/pi --include='*.cfg' . | xargs -r sed -i "s#/home/pi#$HOME#g")
    ok "paths updated"
  fi
fi

# ------------------------------------------------------------------ Python packages
say "Python packages for the portal"
if py "import flask"; then
  ok "Flask already installed"
else
  do_ sudo apt-get update -qq
  do_ sudo apt-get install -y python3-flask || fail "Flask did not install." "Check the internet connection, then run this again."
  [ $DRY = 1 ] || py "import flask" || fail "Flask installed but Python cannot find it."
  ok "Flask installed"
fi
if py "import waitress"; then
  ok "Waitress already installed"
elif [ $DRY = 1 ]; then
  printf '   would try: sudo apt-get install -y python3-waitress (optional)\n'
elif sudo apt-get install -y python3-waitress >/dev/null 2>&1 && py "import waitress"; then
  ok "Waitress installed"
else
  note "Waitress is not available on this Pi - fine, the portal uses Flask's own server"
fi

# ------------------------------------------------------------------ service
say "Starting the portal as a service (starts by itself at every boot)"
tmp="$(mktemp)"
sed "s#/home/pi#$HOME#g; s#^User=.*#User=$USER#" "$SRC/service/rhino-portal.service" > "$tmp"
if [ $old_service = 1 ]; then do_ sudo systemctl stop rhino-portal; fi
do_ sudo install -m 644 "$tmp" "$SERVICE"
rm -f "$tmp"
do_ sudo systemctl daemon-reload
do_ sudo systemctl enable --now rhino-portal
do_ sudo systemctl restart rhino-portal
if [ $DRY = 0 ]; then
  up=0
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if py "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5000/',timeout=2)"; then up=1; break; fi
  done
  [ $up = 1 ] || fail "The portal service did not answer on port 5000." "See why with:  journalctl -u rhino-portal -n 30 --no-pager"
  ok "portal answering on port 5000"
fi

# ------------------------------------------------------------------ done
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
url="http://${ip:-YOUR-PI-ADDRESS}:5000"
printf '\n\033[1m%s\033[0m\n' "$([ $DRY = 1 ] && echo 'Dry run finished - nothing was changed.' || echo 'Install finished.')"
[ $DRY = 1 ] && { echo "Run it for real with:  bash $SRC/install.sh"; exit 0; }
cat <<EOF

Portal:  $url
Backup:  $BACKUP   (undo: menu option 4, or  bash $SRC/uninstall.sh)

Next, in Mainsail:
  1. Mount a PRINT HEAD (BlockOne or SwitchFly) before you home or move Z.
  2. FIRMWARE_RESTART and wait for Ready. A red error box names the file and line - send it for help.
  3. Answer the "which toolhead is mounted?" question.
  4. CHECK_TOOLHEADS, then press Restart now when the console shows "rhino: OK".
EOF
