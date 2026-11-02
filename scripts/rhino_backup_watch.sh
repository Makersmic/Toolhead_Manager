#!/usr/bin/env bash
# Rhino Tool Manager: pushes the config to GitHub after it changes, once the changes have settled.
#
# It replaces klipper-backup's utils/filewatch.sh (GPL-3.0, Staubgeborener/klipper-backup; the watch list below is
# built the same way). That script runs one whole backup per file event, in turn, so an update touching hundreds of
# files queued hours of backups and commits. This one waits for a quiet spell and runs one.
#
#   - changes in a burst become one backup, QUIET seconds after the last of them
#   - a steady stream of changes still gets a backup every MAX_WAIT seconds
#   - while a job prints or is paused, nothing runs; what changed is backed up when the job is over (the old
#     script dropped those changes until the next one)
#   - rsync's temporary files (.printer.cfg.Ab3dEf) aren't changes
#   - the Care meters (myrhino/maintenance/meters.json) save about every 5 minutes, so they don't start a backup of
#     their own; they're still in the folder, so they go up with the next backup something else starts
#
# Run by klipper-backup-filewatch.service as your login, through the override install.sh adds. It never touches
# klipper-backup's own files, and uninstall.sh takes the override away again.
set -u
KB="${RHINO_KB_DIR:-$HOME/klipper-backup}"
QUIET="${RHINO_WATCH_QUIET:-60}"
MAX_WAIT="${RHINO_WATCH_MAX:-900}"
JOB_POLL="${RHINO_WATCH_JOB_POLL:-60}"
MOONRAKER="${RHINO_MOONRAKER:-http://localhost:7125}"
# rsync's temporary names are a dot, the file's name, a dot and six random characters
EXCLUDE='\.swp|\.tmp|printer-[0-9]*_[0-9]*\.cfg|\.bak|\.bkp|/\.[^/]+\.[A-Za-z0-9]{6}$|/myrhino/maintenance/meters\.json$'

if [ ! -f "$KB/.env" ]; then
  echo "rhino_backup_watch: $KB/.env is missing, so there's nothing to watch. Set up klipper-backup first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$KB/.env"

watchlist=()
for path in "${backupPaths[@]}"; do
  for file in $HOME/$path; do
    [ -h "$file" ] && continue
    watchlist+=("$(dirname "$file")")
  done
done
mapfile -t watchlist < <(printf '%s\n' "${watchlist[@]}" | sort -u)

job_running() {
  curl -s -m 5 "$MOONRAKER/printer/objects/query?print_stats" </dev/null | grep -qE '"state": *"(printing|paused)"'
}

count=0
last_file=""
first=0
last=0

run_backup() {
  echo "rhino_backup_watch: backing up $count change(s), latest $last_file"
  # stdin from /dev/null: anything that reads it would otherwise eat the waiting file events
  bash "$KB/script.sh" --commit_message "$count changes, latest $last_file - $(date +'%x %X')" </dev/null 2>&1 | tail -n 3
  count=0
}

inotifywait -mrP -e close_write -e move -e delete --exclude "$EXCLUDE" "${watchlist[@]}" |
{
  while :; do
    if [ "$count" = 0 ]; then
      IFS=' ' read -r dir event file || exit 1
    else
      left=$(( QUIET - (SECONDS - last) ))
      over=$(( MAX_WAIT - (SECONDS - first) ))
      [ "$over" -lt "$left" ] && left=$over
      if [ "$left" -le 0 ]; then
        if job_running; then
          left=$JOB_POLL
        else
          run_backup
          continue
        fi
      fi
      IFS=' ' read -r -t "$left" dir event file
      rc=$?
      if [ "$rc" -gt 128 ]; then continue; fi
      if [ "$rc" -ne 0 ]; then
        # inotifywait stopped: save what's waiting if that's safe, and let systemd start this again
        job_running || run_backup
        exit 1
      fi
    fi
    [ "$count" = 0 ] && first=$SECONDS
    last=$SECONDS
    count=$(( count + 1 ))
    last_file="${file:-$(basename "$dir")}"
    : "$event"
  done
}
