#!/usr/bin/env bash
# Symbolische Gegenprobe der deal-Contracts mit CrossHair.
#
# Nur die Module, deren Funktionen ausschliesslich mit primitiven Typen
# arbeiten. CrossHair fuehrt den Code mit symbolischen Platzhaltern aus;
# sobald einer davon in Pydantic oder polars landet, wird er dort als
# ungueltiger Typ abgewiesen und CrossHair meldet einen Fehler, der keiner
# ist. Die uebrigen Contracts decken pytest und `deal lint` ab.
set -euo pipefail

MODULES=(
  src/analysis/metrics.py
  src/analysis/workout.py
  src/validation/ranges.py
  src/validation/recovery.py
  src/intervals/comparison.py
  src/suggestion/interval_choice.py
)

status=0
for module in "${MODULES[@]}"; do
  echo "== $module"
  PYTHONPATH=src uv run crosshair check "$module" \
    --analysis_kind=deal --per_condition_timeout=8 || status=1
done

if [ "$status" -eq 0 ]; then
  echo "Kein Gegenbeispiel gefunden."
fi
exit "$status"
