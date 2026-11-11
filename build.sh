#!/bin/bash
# Builds ONE IPK containing the overlay app, the settings app and the luna service:
#   org.hermes.reticle_<ver>_all.ipk
# Layout matches ares-package output (checked against the Homebrew Channel IPK):
#   usr/palm/applications/<id>/          main app: settings + web UI (package id, so it gets the luna role)
#   usr/palm/applications/<id>.overlay/  the transparent overlay, hidden from the launcher
#   usr/palm/services/<id>.service/
#   usr/palm/packages/<id>/packageinfo.json
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

BASE=org.hermes.reticle
VER=$(python3 -c "import json;print(json.load(open('app/appinfo.json'))['version'])")

# keep every appinfo on the package version
python3 - "$VER" <<'PY'
import json, pathlib, sys
ver = sys.argv[1]
for p in (pathlib.Path("app/appinfo.json"), pathlib.Path("settings/appinfo.json")):
    d = json.loads(p.read_text())
    d["version"] = ver
    p.write_text(json.dumps(d, indent=2) + "\n")
PY

# build_ipk <package-id> <description> <staging dir with usr/...>
build_ipk() {
  local ID="$1" DESC="$2" DATA="$3"
  local W OUT
  W=$(mktemp -d)
  mkdir -p "$W/control"
  cat >"$W/control/control" <<EOF
Package: $ID
Version: $VER
Section: misc
Priority: optional
Architecture: all
Installed-Size: 0
Maintainer: XerxeS2K1 <180217047+XerxeS2K1@users.noreply.github.com>
Description: $DESC
webOS-Package-Format-Version: 2
webOS-Packager-Version: x.y.x
EOF
  ( cd "$W/control" && tar czf "$W/control.tar.gz" control )
  ( cd "$DATA" && tar czf "$W/data.tar.gz" usr )
  printf '2.0\n' >"$W/debian-binary"
  OUT="${ID}_${VER}_all.ipk"
  rm -f "$ROOT/$OUT"
  ( cd "$W" && ar rc "$ROOT/$OUT" debian-binary control.tar.gz data.tar.gz )
  rm -rf "$W"
  echo "built: $ROOT/$OUT"
  sha256sum "$OUT"
}

# ---- the package -----------------------------------------------------------
M=$(mktemp -d)
mkdir -p "$M/usr/palm/applications/$BASE.overlay" "$M/usr/palm/applications/$BASE" \
         "$M/usr/palm/services/$BASE.service" "$M/usr/palm/packages/$BASE"
cp app/appinfo.json app/icon.png app/largeIcon.png app/index.html app/settings.json app/luna.js app/designs.js app/design.js "$M/usr/palm/applications/$BASE.overlay/"
cp settings/appinfo.json settings/index.html app/icon.png app/largeIcon.png app/luna.js app/designs.js app/design.js "$M/usr/palm/applications/$BASE/"
cp service/service.js service/package.json service/services.json service/daemon.js service/web.html service/crosshairs.png service/reticle-boot.sh service/reticle-setup.sh "$M/usr/palm/services/$BASE.service/"
chmod +x "$M"/usr/palm/services/$BASE.service/*.sh
cat >"$M/usr/palm/packages/$BASE/packageinfo.json" <<EOF
{
  "id": "$BASE",
  "version": "$VER",
  "app": "$BASE",
  "services": ["$BASE.service"]
}
EOF
build_ipk "$BASE" "Crosshair overlay for HDMI inputs, with on-TV settings" "$M"
rm -rf "$M"
