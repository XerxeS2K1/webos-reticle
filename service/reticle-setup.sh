#!/bin/sh
# Install (default) or remove ("remove") the start-at-boot hook, then start the daemon.
# The hook is a SYMLINK into the app directory, never a copy, so it cannot outlive the app.
# Safe to run twice. Needs root: the settings app runs it through the Homebrew Channel exec service.
DIR="$(dirname "$(realpath "$0")")"
HOOK=/var/lib/webosbrew/init.d/90-reticle
LOG=/var/lib/webosbrew/reticle-control.log
mkdir -p /var/lib/webosbrew/init.d 2>/dev/null
if [ "$1" = "remove" ]; then
  rm -f "$HOOK"
  for p in /proc/[0-9]*; do
    tr '\0' ' ' <"$p/cmdline" 2>/dev/null | grep -q "reticle-daemon-ru[n]" && kill "${p#/proc/}" 2>/dev/null
  done
  echo "$(date +%T) reticle-setup: removed boot hook, stopped daemon" >>"$LOG"
  exit 0
fi
if [ ! -f "$DIR/reticle-boot.sh" ]; then
  echo "$(date +%T) reticle-setup: reticle-boot.sh missing, nothing done" >>"$LOG"
  exit 1
fi
if [ "$(readlink "$HOOK" 2>/dev/null)" != "$DIR/reticle-boot.sh" ]; then
  ln -sfn "$DIR/reticle-boot.sh" "$HOOK"
  echo "$(date +%T) reticle-setup: boot hook linked" >>"$LOG"
fi
exec sh "$DIR/reticle-boot.sh"
