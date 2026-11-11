#!/bin/sh
# Runs ON the TV. Serves /tmp over http (loopback) and installs both IPKs with
# Homebrew Channel's installer, then prints the installed versions.
set -u
cd /tmp || exit 1
pkill -f "[p]ython3 -m http.server 8099" 2>/dev/null
nohup python3 -m http.server 8099 --bind 127.0.0.1 >/tmp/httpd.log 2>&1 &
sleep 2

install_one() {
  f="$1"
  HASH=$(sha256sum "$f" | cut -d' ' -f1)
  echo "== installing $(basename "$f") hash=$HASH"
  timeout 30 script -qc "luna-send -n 2 -f luna://org.webosbrew.hbchannel.service/install '{\"ipkUrl\":\"http://127.0.0.1:8099/$(basename "$f")\",\"ipkHash\":\"$HASH\"}'" /dev/null \
    | tr -d '\r' | grep -E 'statusText|finished|errorText'
  sleep 2
}

install_one /tmp/reticle.ipk
install_one /tmp/reticle-settings.ipk

echo "== on-disk versions:"
grep -o '"version": *"[^"]*"' /media/developer/apps/usr/palm/applications/org.hermes.reticle/appinfo.json
grep -o '"version": *"[^"]*"' /media/developer/apps/usr/palm/applications/org.hermes.reticle.settings/appinfo.json
pkill -f "[p]ython3 -m http.server 8099" 2>/dev/null
rm -f /tmp/reticle.ipk /tmp/reticle-settings.ipk
echo "== done"
