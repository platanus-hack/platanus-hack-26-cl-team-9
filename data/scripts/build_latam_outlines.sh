#!/usr/bin/env bash
# Builds data/processed/latam/outlines.geojson: country outlines of the regional context layer.
# Source: geoBoundaries gbOpen ADM0 (wmgeolab). The licence differs by country (Creative Commons
# Attribution 2.5 for Argentina; read `boundaryLicense` in the API). GADM is not used: it forbids redistribution.
# Usage: data/scripts/build_latam_outlines.sh [ISO3...]   (default ARG BRA PER BOL)
set -euo pipefail
cd "$(dirname "$0")/.."

COUNTRIES=("$@")
[ ${#COUNTRIES[@]} -gt 0 ] || COUNTRIES=(ARG BRA PER BOL)
mkdir -p raw/geoboundaries processed/latam

for iso in "${COUNTRIES[@]}"; do
  RAW=raw/geoboundaries/$iso-ADM0.geojson
  if [ ! -f "$RAW" ]; then
    url=$(curl -fsSL "https://www.geoboundaries.org/api/current/gbOpen/$iso/ADM0/" \
      | python3 -c 'import sys, json; print(json.load(sys.stdin)["simplifiedGeometryGeoJSON"])')
    curl -fsSL -o "$RAW" "$url"
  fi
done

# one file per country, tagged with its ISO3, then merged and simplified (about 8% of the vertices).
files=()
for iso in "${COUNTRIES[@]}"; do
  files+=("raw/geoboundaries/$iso-ADM0.geojson")
done
npx -y mapshaper@0.8.6 -i "${files[@]}" combine-files \
  -merge-layers \
  -filter-fields shapeGroup \
  -simplify visvalingam 8% keep-shapes \
  -o precision=0.01 format=geojson force processed/latam/outlines.geojson
