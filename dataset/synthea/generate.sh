#!/usr/bin/env bash
# Reproducibly generate the Synthea cohorts used by the backend.
#
# Requires Java 17+ and the official Synthea release jar:
#   https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
#
# Profiles:
#   adults  Synthea adults aged 40-90, all standard modules, no filtering (fast; the default cohort).
#   nsclc   Only living patients with active non-small cell lung cancer (keep_nsclc.json). Uses the
#           local override in modules/ (lung cancer lifetime risk x4, see its remarks). Slow, because
#           Synthea's lung cancer is highly lethal and most simulated patients die before the reference date.
#
# Usage: dataset/synthea/generate.sh <adults|nsclc> [population] [seed]
# Then:  python dataset/synthea/build_cohort.py <output dir>/csv backend/data/synthea_<profile>.json
set -euo pipefail

PROFILE="${1:-adults}"
POPULATION="${2:-1000}"
SEED="${3:-20261017}"
REFERENCE_DATE="20261001"   # fixed simulation end date keeps ages and "recent" windows reproducible
STATE="Massachusetts"
HERE="$(cd "$(dirname "$0")" && pwd)"
JAR="${SYNTHEA_JAR:-$HOME/tools/synthea/synthea-with-dependencies.jar}"
JAVA="${JAVA:-$(command -v java || echo "$HOME/tools/jdk/bin/java")}"
OUT="${SYNTHEA_OUT:-$HOME/synthea-out/${PROFILE}-p${POPULATION}-s${SEED}}"

case "$PROFILE" in
  adults) EXTRA=() ;;
  nsclc)  EXTRA=(-k "$HERE/keep_nsclc.json" -d "$HERE/modules") ;;
  *) echo "unknown profile: $PROFILE" >&2; exit 2 ;;
esac

rm -rf "$OUT" && mkdir -p "$OUT"
"$JAVA" -Xmx4g -jar "$JAR" \
  -p "$POPULATION" -s "$SEED" -cs "$SEED" -r "$REFERENCE_DATE" -a 40-90 \
  "${EXTRA[@]}" \
  --exporter.baseDirectory="$OUT" \
  --exporter.csv.export=true \
  --exporter.fhir.export=false \
  --exporter.hospital.fhir.export=false \
  --exporter.practitioner.fhir.export=false \
  --exporter.metadata.export=true \
  "$STATE"
echo "Synthea CSV written to $OUT/csv"
