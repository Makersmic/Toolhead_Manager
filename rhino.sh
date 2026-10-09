#!/usr/bin/env bash
# Rhino tool manager - menu (in the style of KIAUH).
#   First time:  bash ~/rhino-<version>/rhino.sh
#   Afterwards:  bash ~/rhino-manager/rhino.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${RHINO_CONFIG_DIR:-$HOME/printer_data/config}"
MGR="$HOME/rhino-manager"
B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'
W=58

line()  { printf '%s\n' "$1$(printf '%*s' $W '' | tr ' ' "$2")$3"; }
row()   { local t="$1" plain; plain="$(printf '%s' "$t" | sed 's/\x1b\[[0-9;]*m//g')"; printf '| %s%*s |\n' "$t" $((W-2-${#plain})) ''; }
pause() { echo; read -r -p "Press Enter to return to the menu..." _; }
yes_no(){ local a; read -r -p "$1 [y/N] " a; [ "${a,,}" = y ] || [ "${a,,}" = yes ]; }

src_version()  { [ -f "$HERE/VERSION" ] && cat "$HERE/VERSION" || echo "?"; }
inst_version() { [ -f "$MGR/installed-version" ] && cat "$MGR/installed-version" || echo "not installed"; }
portal_state() {
  if systemctl is-active --quiet rhino-portal 2>/dev/null; then
    local ip; ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo "${G}running${N}  http://${ip:-YOUR-PI}:5000"
  elif [ -f /etc/systemd/system/rhino-portal.service ]; then echo "${R}stopped${N}"
  else echo "${Y}not installed${N}"; fi
}
is_package() { [ -f "$HERE/install.sh" ] && [ -d "$HERE/rhino" ]; }
KIRI="${RHINO_KIRI_HOME:-$HOME/rhino-kiri}"
kiri_state() {
  if systemctl is-active --quiet rhino-kiri 2>/dev/null; then
    echo "${G}running${N}  $(cat "$KIRI/installed-version" 2>/dev/null) (Slice tab)"
  elif [ -f /etc/systemd/system/rhino-kiri.service ]; then echo "${R}stopped${N}"
  else echo "${Y}not installed${N}"; fi
}

header() {
  clear 2>/dev/null || true
  line '/' '=' '\'
  row "${B}            ~~~~ [ Rhino Tool Manager ] ~~~~${N}"
  line '|' '-' '|'
  row "Installed version : $(inst_version)"
  is_package && row "This folder has   : $(src_version)   ($HERE)"
  row "Portal            : $(portal_state)"
  row "Kiri:Moto slicer  : $(kiri_state)"
  line '|' '-' '|'
}

menu() {
  header
  if is_package; then
    row "${C}1)${N} Preview the install       (changes nothing)"
    row "${C}2)${N} Install / update from this folder"
  else
    row "${C}1)${N} -"
    row "${C}2)${N} -"
  fi
  row "${C}3)${N} Install a new zip  (unpack, preview, install)"
  row "${C}4)${N} Undo an install            (pick a backup)"
  row "${C}5)${N} Portal status and recent log"
  row "${C}6)${N} Restart the portal"
  row "${C}7)${N} Kiri:Moto slicer           (prototype)"
  row ""
  row "${C}Q)${N} Quit"
  line '\' '=' '/'
}

do_preview() { bash "$HERE/install.sh" --dry-run; pause; }

do_install() {
  echo; echo "${B}Install version $(src_version) from $HERE${N}"
  echo "Your config folder is backed up first; option 4 undoes it."
  echo "Make sure nothing is printing."
  yes_no "Install now?" || return
  if bash "$HERE/install.sh"; then
    mkdir -p "$MGR"
    cp "$HERE/rhino.sh" "$HERE/install.sh" "$HERE/uninstall.sh" "$MGR/" 2>/dev/null
    src_version > "$MGR/installed-version"
    echo; echo "${G}This menu is now also at:  bash ~/rhino-manager/rhino.sh${N}"
  fi
  pause
}

do_new_zip() {
  echo; echo "${B}Zips in your config folder${N} (upload one in Mainsail: Machine > Upload)"
  local zips=() i=1 z
  for z in "$CFG"/rhino-config-*.zip; do [ -f "$z" ] && zips+=("$z"); done
  [ ${#zips[@]} = 0 ] && { echo "${Y}None found.${N} Upload rhino-config-<version>.zip in Mainsail first."; pause; return; }
  for z in "${zips[@]}"; do echo "  $i) $(basename "$z")"; i=$((i+1)); done
  local n; read -r -p "Which one (number, Enter to go back)? " n
  [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le ${#zips[@]} ] || return
  z="${zips[$((n-1))]}"
  local name; name="$(basename "$z" .zip)"; name="${name#rhino-config-}"
  local dest="$HOME/rhino-$name"
  command -v unzip >/dev/null || { echo "Installing unzip..."; sudo apt-get install -y unzip || { pause; return; }; }
  [ -d "$dest" ] && { echo "Replacing the earlier unpacked copy in $dest"; rm -rf "$dest"; }
  unzip -q -o "$z" -d "$dest" || { echo "${R}Could not unpack $z${N}"; pause; return; }
  echo "${G}Unpacked to $dest${N} - showing what installing it would do."
  sleep 1
  exec bash "$dest/rhino.sh" --after-unpack
}

do_undo() {
  echo; echo "${B}Backups${N} (the oldest is your setup from before the first install)"
  local bks=() i=1 b
  for b in "$HOME"/rhino-backup-*; do [ -d "$b" ] && bks+=("$b"); done
  [ ${#bks[@]} = 0 ] && { echo "No backups found."; pause; return; }
  for b in "${bks[@]}"; do echo "  $i) $(basename "$b")"; i=$((i+1)); done
  local n; read -r -p "Restore which one (number, Enter to go back)? " n
  [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le ${#bks[@]} ] || return
  b="${bks[$((n-1))]}"
  local un="$HERE/uninstall.sh"; [ -f "$un" ] || un="$MGR/uninstall.sh"
  echo; bash "$un" --dry-run "$b"
  echo; echo "Your config folder becomes exactly this backup. Anything changed since is kept aside in ~/rhino-undone-<time>."
  yes_no "Restore $(basename "$b")?" || return
  bash "$un" "$b" && rm -f "$MGR/installed-version"
  pause
}

do_kiri() {
  echo; echo "${B}Kiri:Moto slicer${N} (prototype) - the slicer in the portal's Slice tab"
  echo "Status: $(kiri_state)"
  echo; echo "  1) Install or update from a rhino-kiri zip  (upload it in Mainsail: Machine > Upload)"
  echo "  2) Remove it (the Slice tab is turned off; nothing else changes)"
  echo "  3) Status and recent log"
  local a; read -r -p "Choose (Enter to go back): " a
  case "$a" in
    1)
      local zips=() i=1 z n
      for z in "$CFG"/rhino-kiri-*.zip; do [ -f "$z" ] && zips+=("$z"); done
      [ ${#zips[@]} = 0 ] && { echo "${Y}None found.${N} Upload rhino-kiri-<version>.zip in Mainsail first."; pause; return; }
      for z in "${zips[@]}"; do echo "  $i) $(basename "$z")"; i=$((i+1)); done
      read -r -p "Which one (number, Enter to go back)? " n
      [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le ${#zips[@]} ] || return
      z="${zips[$((n-1))]}"
      local dest="$HOME/$(basename "$z" .zip)"
      command -v unzip >/dev/null || { echo "Installing unzip..."; sudo apt-get install -y unzip || { pause; return; }; }
      rm -rf "$dest"; unzip -q -o "$z" -d "$dest" || { echo "${R}Could not unpack $z${N}"; pause; return; }
      bash "$dest/install-kiri.sh" --dry-run || { pause; return; }
      echo; yes_no "Install Kiri:Moto now?" && bash "$dest/install-kiri.sh" && rm -rf "$dest"
      pause ;;
    2)
      local inst="$(ls -d "$HOME"/rhino-kiri-*/install-kiri.sh 2>/dev/null | head -n1)"
      [ -f "$CFG/kiri/install-kiri.sh" ] && inst="$CFG/kiri/install-kiri.sh"
      [ -n "$inst" ] || { echo "No Kiri:Moto installer found."; pause; return; }
      yes_no "Remove Kiri:Moto and turn the Slice tab off?" && bash "$inst" --remove
      pause ;;
    3)
      echo; systemctl status rhino-kiri --no-pager 2>/dev/null | head -n 5
      echo; journalctl -u rhino-kiri -n 15 --no-pager 2>/dev/null || echo "(no log)"
      pause ;;
  esac
}

do_status() {
  echo; systemctl status rhino-portal --no-pager 2>/dev/null | head -n 5
  echo; echo "${B}Last 15 log lines${N}"
  journalctl -u rhino-portal -n 15 --no-pager 2>/dev/null || echo "(no log)"
  pause
}

do_restart() {
  echo; sudo systemctl restart rhino-portal && sleep 2
  systemctl is-active --quiet rhino-portal && echo "${G}Portal restarted.${N}" || echo "${R}Portal did not start - see option 5.${N}"
  pause
}

[ "$(id -u)" = 0 ] && { echo "Run this as your normal login, without sudo."; exit 1; }
if [ "${1:-}" = "--after-unpack" ] && is_package; then
  # Straight on from option 3: preview this version, then offer to install it - so picking a zip
  # always ends in that version being installed (or a clear "not installed").
  bash "$HERE/install.sh" --dry-run && do_install
fi
while true; do
  menu
  read -r -p "Perform action: " choice
  case "${choice,,}" in
    1) is_package && do_preview ;;
    2) is_package && do_install ;;
    3) do_new_zip ;;
    4) do_undo ;;
    5) do_status ;;
    6) do_restart ;;
    7) do_kiri ;;
    q) echo "Bye."; exit 0 ;;
  esac
done
