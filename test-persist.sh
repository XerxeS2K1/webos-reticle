#!/bin/sh
# Runs ON the TV. Persistence test for the reticle overlay.
set -u
L() { luna-send -n 1 -f "$1" "$2" >/dev/null 2>&1; }
call() { script -qc "luna-send -n 1 -f $1 '$2'" /dev/null; }
mark() { echo; echo "=== $* ==="; }

mark "installed appinfo"
grep -o '"version": *"[^"]*"\|"defaultWindowType": *"[^"]*"' /media/developer/apps/usr/palm/applications/org.hermes.reticle/appinfo.json

call luna://com.webos.applicationManager/getForegroundAppInfo '{}'

mark "launch reticle over current foreground"
call luna://com.webos.applicationManager/launch '{"id":"org.hermes.reticle"}'
sleep 4
grep "org.hermes.reticle" /var/log/messages | tail -2

mark "switch to HDMI 1"
call luna://com.webos.applicationManager/launch '{"id":"com.webos.app.hdmi1"}'
sleep 5
echo "-- reticle lines:"; grep "org.hermes.reticle" /var/log/messages | tail -2
echo "-- hdmi1 lines:"; grep "com.webos.app.hdmi1" /var/log/messages | tail -2

mark "switch back to HDMI 2"
call luna://com.webos.applicationManager/launch '{"id":"com.webos.app.hdmi2"}'
sleep 5
echo "-- reticle lines:"; grep "org.hermes.reticle" /var/log/messages | tail -2
echo "-- hdmi2 lines:"; grep "com.webos.app.hdmi2" /var/log/messages | tail -2
