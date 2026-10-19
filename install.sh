#!/usr/bin/env bash
# Rhino tool manager - installer.
#
#   bash ~/rhino-<version>/install.sh --dry-run    shows what it would do, changes nothing
#   bash ~/rhino-<version>/install.sh              installs
#
# Run it as your normal login (not with sudo); it asks for your password when it needs it.
# It stops at the first problem and tells you what to do. Undo with:  bash ~/rhino-<version>/uninstall.sh
#
#   install.sh --unattended    only for the Rhino updater (1.5.3): rhino-update runs it as root for the
#                              login in RHINO_USER, when Rhino Studio installs an uploaded zip. sudo is then a
#                              pass-through, and everything it writes in that login's folders is given back to it.
set -u

UNATTENDED=0
if [ "${1:-}" = "--unattended" ]; then
  [ "$(id -u)" = 0 ] && [ -n "${RHINO_USER:-}" ] && getent passwd "$RHINO_USER" >/dev/null \
    || { echo "--unattended is only for the Rhino updater (root, with RHINO_USER set)."; exit 1; }
  UNATTENDED=1
  USER="$RHINO_USER"; HOME="$(getent passwd "$USER" | cut -d: -f6)"; export USER HOME
  sudo() {
    case "${1:-}" in
      -v) return 0 ;;
      -n) shift; "$@" ;;
      -u) local u="$2"; shift 2; runuser -u "$u" -- "$@" ;;
      *) "$@" ;;
    esac
  }
  crontab() { command crontab -u "$USER" "$@"; }
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${RHINO_CONFIG_DIR:-$HOME/printer_data/config}"
STAMP="$(date +%Y-%m-%d-%H%M)"
BACKUP="$HOME/rhino-backup-$STAMP"
# A second install in the same minute must not copy into the first backup (cp -a would nest it inside)
n=1; while [ -e "$BACKUP" ]; do n=$((n+1)); BACKUP="$HOME/rhino-backup-$STAMP-$n"; done
LAST="$HOME/.rhino-last-backup"
SERVICE="${RHINO_SERVICE_FILE:-/etc/systemd/system/rhino-portal.service}"   # only dev/test_install.py sets this
MOONRAKER="${RHINO_MOONRAKER:-http://127.0.0.1:7125}"
# Rhino Studio, served by nginx (1.5.1). Only dev/test_install.py changes these.
NGX="${RHINO_NGINX_DIR:-/etc/nginx}"
NGINX_BIN="${RHINO_NGINX_BIN:-/usr/sbin/nginx}"
STUDIO_DIR="${RHINO_STUDIO_DIR:-$HOME/rhino-studio}"
STUDIO_PORT="${RHINO_STUDIO_PORT:-5001}"
# The updater (1.5.3): the Portal drops zips here; only dev/test_install.py changes these.
UPD="$(dirname "$CFG")/rhino_data/update"
UNITS="${RHINO_UNIT_DIR:-/etc/systemd/system}"
UPDATER_BIN="${RHINO_UPDATER_BIN:-/usr/local/sbin/rhino-update}"
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
# Unattended: whatever happens, files written in the login's folders go back to the login
give_back() { chown -R --no-dereference "$USER:$(id -g "$USER")" "$CFG" "$BACKUP" "$STUDIO_DIR" "$LAST" "$HOME/rhino-manager" "$UPD" 2>/dev/null; return 0; }
[ $UNATTENDED = 1 ] && trap give_back EXIT

# ------------------------------------------------------------------ checks before anything changes
say "Checking this Pi"
[ $UNATTENDED = 0 ] && [ "$(id -u)" = 0 ] && fail "Run this as your normal login, without sudo." "Example:  bash $SRC/install.sh"
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
    if crontab -l 2>/dev/null | grep -v '^[[:space:]]*#' | grep -q "rhino_portal"; then
      fail "An old copy of the portal, started from your crontab, is using port 5000." "$(printf '%s\n' \
        "Turn it off, then run this again:" \
        "  crontab -l | grep -n rhino_portal      (shows the line)" \
        "  crontab -e                             (put a # in front of that line, save)" \
        "  sudo ss -ltnp | grep :5000             (shows pid=NNN for each copy)" \
        "  kill NNN                               (for each pid it shows)")"
    fi
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
if [ $DRY = 0 ] && [ $UNATTENDED = 0 ]; then
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
      --exclude install.sh --exclude uninstall.sh --exclude rhino.sh --exclude VERSION --exclude /studio/
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
# Your positions are kept, but the travel limits in printer.cfg may have changed: say which numbers no longer fit.
if [ $had_positions = 1 ]; then
  python3 - "$SRC/printer.cfg" "$CFG/myrhino/positions.cfg" <<'PYEOF' 2>/dev/null || true
import re, sys
cfg = open(sys.argv[1]).read()
sec = re.search(r"^\[stepper_z\]\s*$(.*?)(?=^\[)", cfg, re.M | re.S)
zmax = float(re.search(r"^position_max\s*:\s*([-\d.]+)", sec.group(1), re.M).group(1))
pos = dict(re.findall(r"^variable_(safe_z|zero_max_z)\s*:\s*([-\d.]+)", open(sys.argv[2]).read(), re.M))
for k, v in pos.items():
    if float(v) > zmax:
        print(f"   note myrhino/positions.cfg: {k} is {float(v):g}, past the bed's lowest point (Z{zmax:g} in printer.cfg).")
        print(f"        Change it to {zmax - 5:g} or less, then FIRMWARE_RESTART (RHINO_POSITIONS lists and checks them).")
PYEOF
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

# ------------------------------------------------------------------ network helper (1.4.8)
# Lets the Portal (and Rhino Studio, through it) change the Pi's name, address, Wi-Fi and power
# saving. One root-owned program, and one sudoers line that allows exactly that program: every
# change it makes switches back by itself after 2 minutes unless it is kept.
say "Network settings helper"
if [ "${RHINO_SKIP_NET:-0}" = 1 ]; then
  note "network helper skipped (RHINO_SKIP_NET=1)"
elif command -v nmcli >/dev/null 2>&1; then
  do_ sudo install -o root -g root -m 755 "$SRC/scripts/rhino_net_helper.py" /usr/local/sbin/rhino-net
  tmp="$(mktemp)"
  printf '# Rhino Tool Manager: the Portal may run the network helper (and nothing else) as root.\n%s ALL=(root) NOPASSWD: /usr/local/sbin/rhino-net\n' "$USER" > "$tmp"
  if [ $DRY = 1 ] || sudo visudo -cf "$tmp" >/dev/null; then
    do_ sudo install -o root -g root -m 440 "$tmp" /etc/sudoers.d/rhino-net
    ok "network helper installed"
  else
    note "sudoers check failed - network settings stay read-only in the portal"
  fi
  rm -f "$tmp"
else
  note "No NetworkManager (nmcli) on this Pi - network settings stay read-only in the portal"
fi

# ------------------------------------------------------------------ updater (1.5.3)
# Lets Rhino Studio install a release zip without SSH or Mainsail. One root-owned program, started only by
# systemd when the Portal drops a request file in its own folder: the Portal itself never gets sudo.
say "Updater (install a new zip from Rhino Studio)"
if [ "${RHINO_SKIP_UPDATER:-0}" = 1 ]; then
  note "updater skipped (RHINO_SKIP_UPDATER=1)"
else
  do_ mkdir -p "$UPD/incoming"
  [ $DRY = 0 ] && [ $UNATTENDED = 0 ] && chmod 755 "$UPD" "$UPD/incoming"
  do_ sudo install -o root -g root -m 755 "$SRC/scripts/rhino_update_helper.py" "$UPDATER_BIN"
  tmp="$(mktemp)"
  sed "s#@USER@#$USER#g; s#@DROP@#$UPD#g; s#@BIN@#$UPDATER_BIN#g; s#@MOONRAKER@#$MOONRAKER#g" "$SRC/service/rhino-update.service" > "$tmp"
  do_ sudo install -m 644 "$tmp" "$UNITS/rhino-update.service"
  sed "s#@DROP@#$UPD#g" "$SRC/service/rhino-update.path" > "$tmp"
  do_ sudo install -m 644 "$tmp" "$UNITS/rhino-update.path"
  rm -f "$tmp"
  do_ sudo systemctl daemon-reload
  do_ sudo systemctl enable --now rhino-update.path
  [ $DRY = 0 ] && ok "updater ready: Studio > Settings > Software > Install from zip"
fi

# ------------------------------------------------------------------ Rhino Studio (1.5.1)
# Studio's built files go to ~/rhino-studio, and nginx (already serving Mainsail) serves them on a port of their
# own, forwarding Moonraker, the cameras and /portal like the dev server on a PC does. Mainsail's site is not
# touched. Anything here that doesn't work is reported and skipped: it never stops the install, and nginx is
# only reloaded after "nginx -t" accepts the new site, so a problem can't take Mainsail down.
say "Rhino Studio (served by nginx on port $STUDIO_PORT)"
SITE="$NGX/sites-available/rhino-studio"
studio_url=""
studio_skip() { note "$1"; note "Rhino Studio is not served from this Pi - it still runs from a PC (npm run dev)."; }
if [ ! -f "$SRC/studio/index.html" ]; then
  studio_skip "this zip has no Studio in it"
elif [ ! -x "$NGINX_BIN" ] || [ ! -d "$NGX/sites-enabled" ]; then
  studio_skip "no nginx with a sites-enabled folder on this Pi"
elif ! printf '%s' "$STUDIO_PORT" | grep -Eq '^[0-9]{2,5}$'; then
  studio_skip "RHINO_STUDIO_PORT must be a port number"
elif [ ! -f "$SITE" ] && py "import socket;s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',$STUDIO_PORT))"; then
  studio_skip "something else already uses port $STUDIO_PORT (see it with:  sudo ss -ltnp | grep :$STUDIO_PORT)"
else
  mport=$(sed -n '/^\[server\]/,/^\[/s/^port[[:space:]]*[:=][[:space:]]*\([0-9]*\).*/\1/p' "$CFG/moonraker.conf" 2>/dev/null | head -n1)
  mport="${mport:-7125}"
  sv="$(cat "$SRC/studio/VERSION" 2>/dev/null || echo '?')"
  # the files: the old copy is moved into the backup, so undo can put it back
  if [ -d "$STUDIO_DIR" ]; then do_ mv "$STUDIO_DIR" "$BACKUP/_rhino_install/old-rhino-studio"; fi
  do_ mkdir -p "$STUDIO_DIR"
  do_ rsync -a "$SRC/studio/" "$STUDIO_DIR/"
  # the site: the old one is kept in the backup too
  [ -f "$SITE" ] && do_ cp "$SITE" "$BACKUP/_rhino_install/old-rhino-studio.nginx"
  tmp="$(mktemp)"
  sed "s#@PORT@#$STUDIO_PORT#g; s#@ROOT@#$STUDIO_DIR#g; s#@MOONRAKER@#$mport#g" "$SRC/service/rhino-studio.nginx" > "$tmp"
  do_ sudo install -m 644 "$tmp" "$SITE"
  do_ sudo ln -sfn "$SITE" "$NGX/sites-enabled/rhino-studio"
  rm -f "$tmp"
  if [ $DRY = 1 ]; then
    printf '   would run: sudo %s -t   (and only then reload nginx)\n' "$NGINX_BIN"
  elif sudo "$NGINX_BIN" -t >/dev/null 2>&1; then
    sudo systemctl reload nginx
    ngx_user=$(sed -n 's/^[[:space:]]*user[[:space:]]\+\([^[:space:];]*\).*/\1/p' "$NGX/nginx.conf" 2>/dev/null | head -n1)
    if [ -n "$ngx_user" ] && ! sudo -u "$ngx_user" test -r "$STUDIO_DIR/index.html"; then
      note "nginx (user $ngx_user) can't read $STUDIO_DIR - your home folder isn't open to it."
      note "Mainsail in ~/mainsail usually needs the same; ask before changing folder permissions."
    fi
    studio_url=1
    if py "import urllib.request;b=urllib.request.urlopen('http://127.0.0.1:$STUDIO_PORT/',timeout=3).read();assert b'Rhino Studio' in b"; then
      ok "Rhino Studio $sv answering on port $STUDIO_PORT"
    else
      note "nginx took the new site, but Studio didn't answer on port $STUDIO_PORT yet."
      note "Check with:  curl -s http://127.0.0.1:$STUDIO_PORT/ | head -n 5     and  sudo tail /var/log/nginx/rhino-studio-error.log"
    fi
  else
    # nginx refused the site: take it out again so Mainsail keeps working, and say why
    why=$(sudo "$NGINX_BIN" -t 2>&1 | tail -n 3)
    sudo rm -f "$NGX/sites-enabled/rhino-studio" "$SITE"
    [ -f "$BACKUP/_rhino_install/old-rhino-studio.nginx" ] && sudo install -m 644 "$BACKUP/_rhino_install/old-rhino-studio.nginx" "$SITE" \
      && sudo ln -sfn "$SITE" "$NGX/sites-enabled/rhino-studio"
    studio_skip "nginx did not accept the Studio site, so it was taken out again (Mainsail is unchanged):"
    printf '%s\n' "$why" | sed 's/^/        /'
  fi
fi

# ------------------------------------------------------------------ done
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
url="http://${ip:-YOUR-PI-ADDRESS}:5000"
[ -n "$studio_url" ] && studio_url="http://${ip:-YOUR-PI-ADDRESS}:$STUDIO_PORT"
printf '\n\033[1m%s\033[0m\n' "$([ $DRY = 1 ] && echo 'Dry run finished - nothing was changed.' || echo 'Install finished.')"
[ $DRY = 1 ] && { echo "Run it for real with:  bash $SRC/install.sh"; exit 0; }
cat <<EOF

Portal:  $url
${studio_url:+Studio:  $studio_url   (on a phone or tablet too)
}Backup:  $BACKUP   (undo: menu option 4, or  bash $SRC/uninstall.sh)

Next, in Mainsail:
  1. Mount a PRINT HEAD (BlockOne or SwitchFly) before you home or move Z.
  2. FIRMWARE_RESTART and wait for Ready. A red error box names the file and line - send it for help.
  3. Answer the "which toolhead is mounted?" question.
  4. CHECK_TOOLHEADS, then press Restart now when the console shows "rhino: OK".
EOF
