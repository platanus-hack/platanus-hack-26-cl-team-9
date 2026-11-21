#!/usr/bin/env bash
# Builds data/processed/chile.geojson: continental Chile by region, light enough for deck.gl.
# Source: github.com/fcortes/Chile-GeoJSON (Regional.geojson, derived from BCN vector maps, no license file).
# Simplified on purpose (about 3k vertices, 60 KB). Not for measuring. Raise 5% to 20% for more detail.
set -euo pipefail
cd "$(dirname "$0")/.."

RAW=raw/Regional.geojson
[ -f "$RAW" ] || curl -fsSL -o "$RAW" https://raw.githubusercontent.com/fcortes/Chile-GeoJSON/master/Regional.geojson

# filter drops "Zona sin demarcar" (codregion 0); clip drops Easter Island and Juan Fernandez (west of lon -77).
npx -y mapshaper@0.8.6 "$RAW" \
  -filter 'codregion > 0' \
  -clip bbox=-77,-57,-65,-17 \
  -filter-fields codregion,Region \
  -simplify visvalingam 5% keep-shapes \
  -o precision=0.001 format=geojson force processed/chile.geojson
