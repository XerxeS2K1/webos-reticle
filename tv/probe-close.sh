#!/bin/sh
# Probe ways to close the overlay app from a root shell. -n 1: close replies once.
try() {
  echo "== $1"
  timeout 6 script -qc "luna-send -n 1 -f $1 '$2'" /dev/null | tr -d '\r' | head -8
  sleep 1
}
try luna://com.webos.applicationManager/close '{"id":"org.hermes.reticle"}'
try luna://com.webos.applicationManager/close '{"appId":"org.hermes.reticle"}'
try luna://com.webos.service.applicationManager/close '{"id":"org.hermes.reticle"}'
echo "== running?"
luna-send -n 1 -f luna://com.webos.applicationManager/listApps '{}' >/dev/null 2>&1
grep "org.hermes.reticle" /var/log/messages | tail -2
