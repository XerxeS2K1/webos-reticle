#!/bin/sh
# Runs ON the TV. Does getForegroundAppInfo support a subscription?
set -u
rm -f /tmp/fgsub.log
( script -qc "luna-send -i -n -1 -f luna://com.webos.applicationManager/getForegroundAppInfo '{\"subscribe\":true}'" /tmp/fgsub.log >/dev/null 2>&1 ) &
SUBPID=$!
sleep 3
echo "--- switching to hdmi1"
script -qc "luna-send -n 1 -f luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi1\"}'" /dev/null >/dev/null
sleep 4
echo "--- switching to hdmi2"
script -qc "luna-send -n 1 -f luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\"}'" /dev/null >/dev/null
sleep 4
kill $SUBPID 2>/dev/null
pkill -f "[l]una-send -i -n -1" 2>/dev/null
echo "--- subscription log"
cat /tmp/fgsub.log 2>/dev/null | tr -d '\r' | head -60
