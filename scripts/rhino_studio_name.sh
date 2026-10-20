#!/usr/bin/env bash
# Rhino Tool Manager 1.5.3: announces <name>.local (default rhinostudio.local) for this host's address on the
# local network, through avahi, so Rhino Studio opens at http://rhinostudio.local with no port.
#
#   bash rhino_studio_name.sh rhinostudio
#
# Run by rhino-studio-name.service as your login (no root). It only asks avahi-daemon to answer one more name;
# it changes nothing on the host, and stopping the service takes the name away again. If DHCP gives the host a
# new address, the name follows it within 30 seconds. The host's own name.local is not touched.
set -u
NAME="${1:-rhinostudio}.local"
POLL="${RHINO_NAME_POLL:-30}"   # seconds between address checks (only tests change it)

addr() {
  # the address the host uses to reach the network (the one a phone on the same Wi-Fi can reach)
  local a
  a=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n1)
  [ -n "$a" ] || a=$(hostname -I 2>/dev/null | awk '{print $1}')
  printf '%s' "$a"
}

pid=""; cur=""
stop_() { [ -n "$pid" ] && kill "$pid" 2>/dev/null; [ -n "$pid" ] && wait "$pid" 2>/dev/null; pid=""; }
trap 'stop_; exit 0' TERM INT

while :; do
  a=$(addr)
  # avahi-publish ends by itself on a name clash or when avahi-daemon restarts: start it again
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null; pid=""
  fi
  if [ "$a" != "$cur" ] || [ -z "$pid" ]; then
    stop_
    cur="$a"
    if [ -n "$a" ]; then
      echo "announcing $NAME at $a"
      # -R: no reverse entry, so the address keeps the host's own name when looked up the other way
      avahi-publish -a -R "$NAME" "$a" &
      pid=$!
    else
      echo "no network address yet - waiting"
    fi
  fi
  sleep "$POLL" &
  wait $!
done
