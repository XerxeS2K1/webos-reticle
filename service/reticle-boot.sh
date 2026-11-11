#!/bin/sh
# Starts (or restarts) the reticle daemon, detached. Safe to run any number of
# times. Called at TV start from /var/lib/webosbrew/init.d (a symlink to this
# file) and by the settings app on first run / after an update.
# run-parts waits for this script, so it must return quickly.
DIR="$(dirname "$(realpath "$0")")"
LOG=/var/lib/webosbrew/reticle-control.log
mkdir -p /var/lib/webosbrew 2>/dev/null

if [ ! -f "$DIR/daemon.js" ] || [ ! -x /usr/bin/node ]; then
  echo "$(date +%T) reticle-boot: daemon.js or node missing, not starting" >>"$LOG"
  exit 0
fi

# stop any running copy (by command line, not by pidfile: pidfiles go stale)
for p in /proc/[0-9]*; do
  pid="${p#/proc/}"
  if tr '\0' ' ' <"$p/cmdline" 2>/dev/null | grep -q "reticle-daemon-ru[n]"; then
    [ "$pid" != "$$" ] && kill "$pid" 2>/dev/null
  fi
done
sleep 1
# the argument below only tags the process so it can be found again
nohup /usr/bin/node "$DIR/daemon.js" reticle-daemon-run >/dev/null 2>&1 &
exit 0
