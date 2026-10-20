#!/usr/bin/env bash
# Rhino tool manager - undo the last install.
#
#   bash ~/rhino-<version>/uninstall.sh --dry-run      shows what it would do
#   bash ~/rhino-<version>/uninstall.sh                puts back the backup made by install.sh
#   bash ~/rhino-<version>/uninstall.sh ~/rhino-backup-2026-10-03-1400    a specific backup
#
# Your config folder becomes exactly the backup again; anything saved in it after the
# install is lost (it is kept aside in ~/rhino-undone-<time> just in case).
set -u
CFG="${RHINO_CONFIG_DIR:-$HOME/printer_data/config}"
SERVICE="${RHINO_SERVICE_FILE:-/etc/systemd/system/rhino-portal.service}"   # only dev/test_install.py sets this
NGX="${RHINO_NGINX_DIR:-/etc/nginx}"; NGINX_BIN="${RHINO_NGINX_BIN:-/usr/sbin/nginx}"
STUDIO_DIR="${RHINO_STUDIO_DIR:-$HOME/rhino-studio}"
UNITS="${RHINO_UNIT_DIR:-/etc/systemd/system}"
DRY=0; B=""
for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1 || B="$a"; done
[ -z "$B" ] && [ -f "$HOME/.rhino-last-backup" ] && B="$(cat "$HOME/.rhino-last-backup")"
fail() { printf '\n\033[31mSTOPPED:\033[0m %s\nNothing was changed.\n' "$1"; exit 1; }
do_() { if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }

[ "$(id -u)" = 0 ] && fail "Run this as your normal login, without sudo."
[ -n "$B" ] && [ -f "$B/printer.cfg" ] || fail "No backup found. Give its folder:  bash uninstall.sh ~/rhino-backup-<date>"
echo "Restoring $B  ->  $CFG"
[ $DRY = 0 ] && { sudo -v || fail "sudo did not accept the password."; }

UNDONE="$HOME/rhino-undone-$(date +%Y-%m-%d-%H%M)"
n=1; while [ -e "$UNDONE" ]; do n=$((n+1)); UNDONE="$HOME/rhino-undone-$(date +%Y-%m-%d-%H%M)-$n"; done
do_ cp -a "$CFG" "$UNDONE"
do_ sudo systemctl disable --now rhino-portal
# 1.4.8+: the network helper and its sudoers line go too (reinstall puts them back)
if [ "${RHINO_SKIP_NET:-0}" = 0 ] && [ -e /usr/local/sbin/rhino-net -o -e /etc/sudoers.d/rhino-net ]; then
  do_ sudo rm -f /etc/sudoers.d/rhino-net /usr/local/sbin/rhino-net
fi
if [ -f "$B/_rhino_install/old-rhino-portal.service" ]; then
  echo "Putting back your previous portal service"
  do_ sudo install -m 644 "$B/_rhino_install/old-rhino-portal.service" "$SERVICE"
  do_ sudo systemctl daemon-reload
  do_ sudo systemctl enable --now rhino-portal
else
  do_ sudo rm -f "$SERVICE"
  do_ sudo systemctl daemon-reload
fi
do_ rsync -a --delete --exclude _rhino_install/ "$B/" "$CFG/"
# 1.5.1+: Rhino Studio on nginx - put back what was there before that install (or nothing)
SITE="$NGX/sites-available/rhino-studio"
if [ -f "$B/_rhino_install/old-rhino-studio.nginx" ] || [ -e "$SITE" ] || [ -d "$B/_rhino_install/old-rhino-studio" ] || [ -d "$STUDIO_DIR" ]; then
  echo "Putting Rhino Studio back as it was"
  if [ -f "$B/_rhino_install/old-rhino-studio.nginx" ]; then
    do_ sudo install -m 644 "$B/_rhino_install/old-rhino-studio.nginx" "$SITE"
    do_ sudo ln -sfn "$SITE" "$NGX/sites-enabled/rhino-studio"
  else
    do_ sudo rm -f "$NGX/sites-enabled/rhino-studio" "$SITE"
  fi
  if [ -d "$STUDIO_DIR" ]; then do_ mkdir -p "$UNDONE"; do_ mv "$STUDIO_DIR" "$UNDONE/rhino-studio"; fi
  if [ -d "$B/_rhino_install/old-rhino-studio" ]; then do_ cp -a "$B/_rhino_install/old-rhino-studio" "$STUDIO_DIR"; fi
  if [ $DRY = 1 ]; then echo "   would run: sudo $NGINX_BIN -t, then reload nginx"
  elif [ -x "$NGINX_BIN" ]; then
    if sudo "$NGINX_BIN" -t >/dev/null 2>&1; then sudo systemctl reload nginx
    else echo "nginx -t found a problem - not reloading nginx. See:  sudo nginx -t"; fi
  fi
fi
# 1.5.3+: Studio by name (rhinostudio.local) - its nginx site and its name service, as they were before that install
NSITE="$NGX/sites-available/rhino-studio-name"; NUNIT="$UNITS/rhino-studio-name.service"
if [ -f "$B/_rhino_install/old-rhino-studio-name.nginx" ] || [ -e "$NSITE" ]; then
  echo "Putting Rhino Studio's name site back as it was"
  if [ -f "$B/_rhino_install/old-rhino-studio-name.nginx" ]; then
    do_ sudo install -m 644 "$B/_rhino_install/old-rhino-studio-name.nginx" "$NSITE"
    do_ sudo ln -sfn "$NSITE" "$NGX/sites-enabled/rhino-studio-name"
  else
    do_ sudo rm -f "$NGX/sites-enabled/rhino-studio-name" "$NSITE"
  fi
  if [ $DRY = 1 ]; then echo "   would run: sudo $NGINX_BIN -t, then reload nginx"
  elif [ -x "$NGINX_BIN" ]; then
    if sudo "$NGINX_BIN" -t >/dev/null 2>&1; then sudo systemctl reload nginx
    else echo "nginx -t found a problem - not reloading nginx. See:  sudo nginx -t"; fi
  fi
fi
if [ -f "$B/_rhino_install/old-rhino-studio-name.service" ]; then
  do_ sudo install -m 644 "$B/_rhino_install/old-rhino-studio-name.service" "$NUNIT"
  do_ sudo systemctl daemon-reload
  do_ sudo systemctl restart rhino-studio-name
elif [ -f "$NUNIT" ]; then
  echo "Taking away the rhinostudio.local name"
  do_ sudo systemctl disable --now rhino-studio-name
  do_ sudo rm -f "$NUNIT"
  do_ sudo systemctl daemon-reload
fi
echo
[ $DRY = 1 ] && echo "Dry run finished - nothing was changed." || echo "Restored. In Mainsail run FIRMWARE_RESTART."
