#!/bin/bash
# Builds two IPKs (one package can only own one launch point on this TV, so the
# settings screen ships as its own package):
#   org.hermes.reticle_<ver>_all.ipk           overlay app + luna service
#   org.hermes.reticle.settings_<ver>_all.ipk  the on-TV settings screen
# Layout matches ares-package output (checked against the Homebrew Channel IPK):
#   usr/palm/applications/<id>/
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
Maintainer: Hermes <nobody@example.com>
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

# ---- package 1: overlay + service -----------------------------------------
M=$(mktemp -d)
mkdir -p "$M/usr/palm/applications/$BASE" "$M/usr/palm/services/$BASE.service" \
         "$M/usr/palm/packages/$BASE"
cp app/appinfo.json app/icon.png app/index.html app/settings.json app/luna.js app/designs.js app/design.js "$M/usr/palm/applications/$BASE/"
cp service/service.js service/package.json service/services.json "$M/usr/palm/services/$BASE.service/"
cat >"$M/usr/palm/packages/$BASE/packageinfo.json" <<EOF
{
  "id": "$BASE",
  "version": "$VER",
  "app": "$BASE",
  "services": ["$BASE.service"]
}
EOF
build_ipk "$BASE" "Reticle overlay for HDMI inputs" "$M"
rm -rf "$M"

# ---- package 2: settings screen -------------------------------------------
S=$(mktemp -d)
mkdir -p "$S/usr/palm/applications/$BASE.settings" "$S/usr/palm/packages/$BASE.settings"
cp settings/appinfo.json settings/index.html app/icon.png app/luna.js app/designs.js app/design.js "$S/usr/palm/applications/$BASE.settings/"
cat >"$S/usr/palm/packages/$BASE.settings/packageinfo.json" <<EOF
{
  "id": "$BASE.settings",
  "version": "$VER",
  "app": "$BASE.settings",
  "services": ["$BASE.service"]
}
EOF
build_ipk "$BASE.settings" "Reticle settings screen for the TV" "$S"
rm -rf "$S"
