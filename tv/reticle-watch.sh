#!/bin/sh
# reticle-watch.sh — keeps the Reticle overlay up over the console input.
# webOS hides an overlay window whenever a new app (including an HDMI input)
# launches, so the overlay has to be relaunched after the input appears.
# Target inputs come from /var/lib/webosbrew/reticle-inputs.conf (one app id per
# line); defaults to HDMI 1.
#
# Runs as root on the TV. Start:  nohup /media/developer/reticle-watch.sh &
# Boot persistence: symlink/copy into /var/lib/webosbrew/init.d/

CONF=/var/lib/webosbrew/reticle-inputs.conf
APP=org.hermes.reticle
LOG=/tmp/reticle-watch.log

[ -f "$CONF" ] || { mkdir -p "$(dirname "$CONF")"; echo "com.webos.app.hdmi1" >"$CONF"; }

log() { echo "$(date -u +%H:%M:%S) $*" >>"$LOG"; }

fg_app() {
  # luna-send drops its reply when stdout is not a tty, so go through script(1)
  script -qc "luna-send -n 1 -f luna://com.webos.applicationManager/getForegroundAppInfo '{}'" /dev/null 2>/dev/null \
    | sed -n 's/.*"appId": *"\([^"]*\)".*/\1/p' | head -1
}

launch_reticle() {
  log "launching $APP (over $1)"
  script -qc "luna-send -n 1 -f luna://com.webos.applicationManager/launch '{\"id\":\"$APP\"}'" /dev/null >/dev/null 2>&1
}

is_target() {
  grep -qxF "$1" "$CONF" 2>/dev/null
}

log "started, targets: $(tr '\n' ' ' <"$CONF")"
last=""
while :; do
  cur=$(fg_app)
  if [ -n "$cur" ] && [ "$cur" != "$last" ]; then
    log "foreground -> $cur"
    if is_target "$cur"; then
      # the input's own window settles a moment after SAM reports it
      sleep 2
      [ "$(fg_app)" = "$cur" ] && launch_reticle "$cur"
    fi
    last="$cur"
  fi
  sleep 1
done
