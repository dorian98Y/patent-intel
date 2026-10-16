#!/usr/bin/env bash
# patent-intel one-shot workflow: dedupe -> fetch -> verify -> summarize
# Usage: ./cli/run_workflow.sh <list.csv|list.txt> [number_column] [CHINESE|ENGLISH] [--family]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
IN="${1:?usage: run_workflow.sh <list.csv|txt> [number_column] [lang] [--family]}"
COL="${2:-number}"; LANG_="${3:-ENGLISH}"; FAM="${4:-}"
OUT="${GP_OUT:-$HERE/runs/$(date +%Y%m%d_%H%M%S)}"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$OUT"
echo "== patent-intel workflow start $(date '+%F %T') =="
echo "-- 1/4 dedupe ------------------------------------------------"
$PY -u -m patent_intel.dedupe --in "$IN" --col "$COL" --out "$OUT/1_dedup.csv" --report "$OUT/1_merge_log.csv" $FAM
echo "-- 2/4 bulk fetch --------------------------------------------"
$PY -u -m patent_intel.gp resolve "$OUT/1_dedup.csv" --col number --lang "$LANG_" -o "$OUT/2_meta.csv"
echo "-- 3/4 verify ------------------------------------------------"
$PY -u -m patent_intel.verify --ref "$IN" --col "$COL" --lang "$LANG_" --out "$OUT/3_mismatch.csv"
echo "-- 4/4 summarize ---------------------------------------------"
$PY - "$OUT" "$IN" <<'PY'
import csv, os, sys
out, inp = sys.argv[1], sys.argv[2]
def n(p):
    try: return sum(1 for _ in open(p, encoding="utf-8-sig")) - 1
    except Exception: return 0
den, meta, mm = n(f"{out}/1_dedup.csv"), n(f"{out}/2_meta.csv"), n(f"{out}/3_mismatch.csv")
src = {}
try:
    for r in csv.DictReader(open(f"{out}/2_meta.csv", encoding="utf-8-sig")):
        src[r.get("来源", r.get("source", ""))] = src.get(r.get("来源", r.get("source", "")), 0) + 1
except Exception: pass
lines = [f"input: {inp}", f"deduplicated: {den}", f"fetched: {meta} (sources {src})",
         f"mismatches: {mm} (see 3_mismatch.csv)", f"merges/suspected: see 1_merge_log.csv", f"output dir: {out}"]
open(f"{out}/0_summary.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
PY
echo "== patent-intel workflow end $(date '+%F %T') =="
