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
SERVICE=/etc/systemd/system/rhino-portal.service
DRY=0; B=""
for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1 || B="$a"; done
[ -z "$B" ] && [ -f "$HOME/.rhino-last-backup" ] && B="$(cat "$HOME/.rhino-last-backup")"
fail() { printf '\n\033[31mSTOPPED:\033[0m %s\nNothing was changed.\n' "$1"; exit 1; }
do_() { if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }

[ "$(id -u)" = 0 ] && fail "Run this as your normal login, without sudo."
[ -n "$B" ] && [ -f "$B/printer.cfg" ] || fail "No backup found. Give its folder:  bash uninstall.sh ~/rhino-backup-<date>"
echo "Restoring $B  ->  $CFG"
[ $DRY = 0 ] && { sudo -v || fail "sudo did not accept the password."; }

do_ cp -a "$CFG" "$HOME/rhino-undone-$(date +%Y-%m-%d-%H%M)"
do_ sudo systemctl disable --now rhino-portal
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
echo
[ $DRY = 1 ] && echo "Dry run finished - nothing was changed." || echo "Restored. In Mainsail run FIRMWARE_RESTART."
