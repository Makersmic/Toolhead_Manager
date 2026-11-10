#!/usr/bin/env bash
# The camera's microphone for Rhino Studio, sound only (docs/install-mic.md, Mike Nov 9 2026).
#
#   bash ~/printer_data/config/scripts/rhino_mic.sh install --dry-run   say every step, change nothing
#   bash ~/printer_data/config/scripts/rhino_mic.sh install             ffmpeg, go2rtc (pinned, checksum checked), the service
#   bash ~/printer_data/config/scripts/rhino_mic.sh status              is it there and running, does it see the microphone
#   bash ~/printer_data/config/scripts/rhino_mic.sh remove              the service and go2rtc go; ffmpeg stays (see the doc)
#
# Since 1.9.21 install.sh runs "install" by itself when a USB camera with a microphone is plugged in, using the go2rtc
# that comes inside the release zip (RHINO_MIC_BIN), so nothing is downloaded then.
#
# Nothing here touches Klipper, Moonraker, crowsnest or the config folder. It stops before changing anything if a job
# is running, the camera's microphone isn't there, or the download isn't exactly the pinned go2rtc.
# go2rtc: https://github.com/AlexxIT/go2rtc (MIT), run as its own program; nothing of it is copied into this repo.
set -uo pipefail

VER=1.9.15
SHA=20b46c6910734cb05ecefb234066f36868ff19b42ba1418a7a32e13a3e035712
SHA="${RHINO_MIC_TEST_SHA:-$SHA}"        # dev/test_mic.py only: its fake download can't match the real file
URL="${RHINO_MIC_URL:-https://github.com/AlexxIT/go2rtc/releases/download/v$VER/go2rtc_linux_amd64}"
ROOT="${RHINO_MIC_ROOT:-}"               # tests: a stand-in for / (proc, etc)
BUNDLED="${RHINO_MIC_BIN:-}"             # install.sh: the go2rtc inside the release zip
MICUSER="${RHINO_MIC_USER:-$(id -un)}"   # install.sh --unattended runs this as root for the login
CARD="${RHINO_MIC_CARD:-C920}"
MOON="${RHINO_MOONRAKER:-http://127.0.0.1:7125}"
API="http://127.0.0.1:1984"
CFG="$(cd "$(dirname "$0")/.." && pwd)"  # the config folder: scripts/..
DIR="$HOME/rhino-mic"
UNIT="${RHINO_UNIT_DIR:-$ROOT/etc/systemd/system}/rhino-mic.service"
SITE="${RHINO_NGINX_DIR:-$ROOT/etc/nginx}/sites-available/rhino-studio"
DEVICE="plughw:CARD=$CARD,DEV=0"
WAIT="${RHINO_MIC_WAIT:-20}"             # half-seconds to wait for go2rtc to answer

ACTION="${1:-}"
DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
n=0
say()  { printf '\n[%s] %s\n' "$((n+=1))" "$*"; }
ok()   { printf '   OK   %s\n' "$*"; }
note() { printf '   note %s\n' "$*"; }
stop() { printf '\nSTOPPED: %s\n' "$1"; [ -n "${2:-}" ] && printf '   %s\n' "$2"; printf 'Nothing more was changed.\n'; exit 1; }
do_()  { if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }

have_card() { grep -Eq "\[$CARD +\]" "$ROOT/proc/asound/cards" 2>/dev/null; }
job_state() { curl -s --max-time 5 "$MOON/printer/objects/query?print_stats=state" 2>/dev/null | grep -Eo '"state": *"[a-z]+"' | grep -Eo '[a-z]+"$' | tr -d '"'; }
# Read the whole answer first: with pipefail, grep -q stopping early can make the writer fail (SIGPIPE) and the
# check fail with it (1.9.21 on the 7050: "no Opus encoder" from Debian's ffmpeg, which has one)
api_up()    { local a; a="$(curl -sf --max-time 2 "$API/api/streams" 2>/dev/null)" && grep -q '"mic"' <<<"$a"; }
has_opus()  { local e; e="$(ffmpeg -hide_banner -encoders 2>/dev/null)"; grep -q libopus <<<"$e"; }

install_mic() {
  say "Checking first (nothing changes here)"
  [ "$(uname -m)" = "x86_64" ] || stop "This host isn't x86-64 ($(uname -m))." "The pinned go2rtc is the linux_amd64 build for the 7050."
  case "$(job_state)" in
    printing|paused) stop "A job is running." "Install the microphone when the Rhino is idle: ffmpeg's install keeps the host busy for a minute." ;;
    "") note "Moonraker didn't answer, so no job can be running" ;;
    *) ok "no job running" ;;
  esac
  have_card || stop "The camera's microphone ($CARD) isn't there." "cat /proc/asound/cards lists: $(grep -Eo '\[[^]]+\]' "$ROOT/proc/asound/cards" 2>/dev/null | tr -d '[]' | tr -s ' ' | tr '\n' ' ')"
  ok "the camera's microphone: $DEVICE"
  [ -f "$CFG/service/rhino-mic.service" ] && [ -f "$CFG/service/rhino-mic.yaml" ] || stop "The service files aren't in $CFG/service." "Install Tool Manager 1.9.20 or later first."
  if grep -qs "/mic/webrtc" "$SITE"; then ok "Studio's site passes /mic/webrtc to the microphone"
  else note "Studio's site has no /mic route yet: install Tool Manager 1.9.20 or later, or Studio can't reach the sound"; fi

  say "ffmpeg (Debian's package): reads the microphone and encodes the sound"
  if command -v ffmpeg >/dev/null 2>&1; then ok "already installed"
  else do_ sudo apt-get install -y --no-install-recommends ffmpeg || stop "ffmpeg didn't install." "Try: sudo apt-get update, then run this again."
  fi
  if [ $DRY = 0 ]; then has_opus || stop "This ffmpeg has no Opus encoder (libopus)." "Browsers need Opus for WebRTC sound."; ok "ffmpeg has the Opus encoder"; fi

  say "go2rtc $VER: passes the sound to the browser"
  if [ -x "$DIR/go2rtc" ] && [ "$(sha256sum "$DIR/go2rtc" | cut -d' ' -f1)" = "$SHA" ]; then ok "go2rtc $VER already in $DIR"
  elif [ -n "$BUNDLED" ] && [ -f "$BUNDLED" ]; then
    [ "$(sha256sum "$BUNDLED" | cut -d' ' -f1)" = "$SHA" ] || stop "The go2rtc in the release isn't the pinned $VER." "The zip may be damaged: download it again."
    if [ $DRY = 1 ]; then note "would use the go2rtc $VER inside the release (checksum matches)"
    else mkdir -p "$DIR" && install -m 755 "$BUNDLED" "$DIR/go2rtc" && ok "go2rtc $VER from the release, checksum matches"; fi
  elif [ $DRY = 1 ]; then printf '   would download %s\n   and keep it only if its sha256 is %s\n' "$URL" "$SHA"
  else
    tmp="$(mktemp)"
    curl -fsSL --max-time 120 -o "$tmp" "$URL" || { rm -f "$tmp"; stop "The download failed." "$URL"; }
    got="$(sha256sum "$tmp" | cut -d' ' -f1)"
    [ "$got" = "$SHA" ] || { rm -f "$tmp"; stop "The download isn't the pinned go2rtc $VER (sha256 $got)." "Expected $SHA. Nothing was kept."; }
    mkdir -p "$DIR" && install -m 755 "$tmp" "$DIR/go2rtc" && rm -f "$tmp"
    ok "go2rtc $VER in $DIR, checksum matches"
  fi

  say "Its settings: the microphone, this host only, no outside servers"
  conf="$(sed "s#@DEVICE@#$DEVICE#g" "$CFG/service/rhino-mic.yaml")"
  if [ $DRY = 1 ]; then note "would write $DIR/go2rtc.yaml"
  else
    mkdir -p "$DIR"
    [ -f "$DIR/go2rtc.yaml" ] && [ "$(cat "$DIR/go2rtc.yaml")" != "$conf" ] && cp "$DIR/go2rtc.yaml" "$DIR/go2rtc.yaml.bak" && note "the old settings kept as go2rtc.yaml.bak"
    printf '%s\n' "$conf" > "$DIR/go2rtc.yaml"
    ok "$DIR/go2rtc.yaml"
  fi

  say "The rhino-mic service: starts at boot, low priority"
  unit="$(sed "s#@USER@#$MICUSER#g; s#@DIR@#$DIR#g" "$CFG/service/rhino-mic.service")"
  if [ $DRY = 1 ]; then note "would write $UNIT and start rhino-mic"
  else
    tmpu="$(mktemp)"; printf '%s\n' "$unit" > "$tmpu"
    sudo install -m 644 "$tmpu" "$UNIT" && rm -f "$tmpu" || stop "Couldn't write $UNIT."
    [ "$(id -u)" = 0 ] && [ "$MICUSER" != root ] && chown -R "$MICUSER": "$DIR"   # the login's own folder stays its own
    sudo systemctl daemon-reload && sudo systemctl enable rhino-mic >/dev/null 2>&1 && sudo systemctl restart rhino-mic || stop "rhino-mic didn't start." "journalctl -u rhino-mic -n 30"
    i=0; until api_up; do i=$((i+1)); [ $i -ge "$WAIT" ] && stop "go2rtc started but doesn't answer on this host." "journalctl -u rhino-mic -n 30; undo with: bash $0 remove"; sleep 0.5; done
    ok "running, and go2rtc lists the mic stream"
  fi

  if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    note "a firewall (ufw) is on: allow the sound with  sudo ufw allow 8555  (TCP and UDP)"
  fi
  printf '\n%s\n' "$([ $DRY = 1 ] && echo 'Dry run finished: nothing changed.' || echo 'Microphone installed.')"
  printf 'Next, in Rhino Studio: Settings > Cameras > Sound, tick "Play the camera'"'"'s microphone on the Dashboard",\nthen tap Sound on the Dashboard. Undo with:  bash %s remove\n' "$0"
}

status_mic() {
  say "The camera's microphone"
  have_card && ok "$CARD is there ($DEVICE)" || note "$CARD isn't in /proc/asound/cards"
  command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg installed" || note "ffmpeg not installed"
  if [ -x "$DIR/go2rtc" ]; then
    [ "$(sha256sum "$DIR/go2rtc" | cut -d' ' -f1)" = "$SHA" ] && ok "go2rtc $VER in $DIR" || note "go2rtc in $DIR isn't the pinned $VER"
  else note "go2rtc isn't installed"; fi
  [ -f "$UNIT" ] && ok "service file there" || note "no rhino-mic service"
  st="$(systemctl is-active rhino-mic 2>/dev/null)"; [ "$st" = "active" ] && ok "rhino-mic running" || note "rhino-mic is ${st:-not there}"
  api_up && ok "go2rtc answers and lists the mic stream" || note "go2rtc doesn't answer on this host"
}

remove_mic() {
  say "Removing the microphone service (ffmpeg stays)"
  if [ -f "$UNIT" ]; then
    sudo systemctl disable --now rhino-mic >/dev/null 2>&1
    sudo rm -f "$UNIT" && sudo systemctl daemon-reload
    ok "rhino-mic stopped and removed"
  else ok "no rhino-mic service"; fi
  if [ -d "$DIR" ]; then rm -rf "$DIR" && ok "$DIR removed"; else ok "no $DIR"; fi
  printf '\nRemoved. Studio now says the microphone service isn'"'"'t running; untick Sound in Settings > Cameras.\n'
  printf 'ffmpeg is still installed (it does nothing on its own). To remove it too:  sudo apt-get remove ffmpeg\n'
}

case "$ACTION" in
  install) install_mic ;;
  status) status_mic ;;
  remove) remove_mic ;;
  *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
