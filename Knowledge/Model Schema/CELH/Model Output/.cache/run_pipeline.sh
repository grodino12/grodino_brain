#!/bin/bash
# Loop CELH iXBRL filings through extract -> reconcile -> validate
set -e

TICKER_ROOT="C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH"
SOURCES="C:/Users/rodin/Desktop/Brain/Sources/CELH"
OUT="$TICKER_ROOT/Model Output"
CACHE="$OUT/.cache"
LIB="C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json"

mkdir -p "$CACHE"

export PYTHONIOENCODING=utf-8
export PYTHONPATH="C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/financials-schema"

EXTRACT="C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py"
RECONCILE="C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py"
VALIDATE="C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py"

FAILED=()
NOVELS=()

for QDIR in "$SOURCES"/2023-Q1 "$SOURCES"/2023-Q2 "$SOURCES"/2023-Q3 "$SOURCES"/2023-FY \
            "$SOURCES"/2024-Q1 "$SOURCES"/2024-Q2 "$SOURCES"/2024-Q3 "$SOURCES"/2024-FY \
            "$SOURCES"/2025-Q1 "$SOURCES"/2025-Q2 "$SOURCES"/2025-Q3 "$SOURCES"/2025-FY ; do
  QLABEL=$(basename "$QDIR")
  HTM=$(ls "$QDIR"/filings/*.htm 2>/dev/null | head -1)
  if [ -z "$HTM" ]; then
    echo "[SKIP] $QLABEL: no .htm"
    continue
  fi
  # Slug for filenames: replace - with _
  SLUG=$(echo "$QLABEL" | tr '-' '_')
  RAW="$CACHE/raw_$SLUG.json"
  MAPPED="$CACHE/mapped_$SLUG.json"
  NOVELS_F="$CACHE/novels_$SLUG.json"
  VALIDATED="$OUT/validated_$SLUG.json"

  echo ""
  echo "===== $QLABEL ====="
  echo "[extract]"
  python "$EXTRACT" --ticker-root "$TICKER_ROOT" --source "$HTM" --out "$RAW" --library "$LIB" 2>&1 | tail -3 || { FAILED+=("$QLABEL: extract"); continue; }
  echo "[reconcile]"
  python "$RECONCILE" --ticker-root "$TICKER_ROOT" --in "$RAW" --out "$MAPPED" --novels-out "$NOVELS_F" 2>&1 | tail -5 || { FAILED+=("$QLABEL: reconcile"); continue; }
  if [ -f "$NOVELS_F" ]; then
    NCOUNT=$(python -c "import json; d=json.load(open(r'$NOVELS_F', encoding='utf-8')); print(len(d.get('novel_items', [])) if isinstance(d, dict) else 0)" 2>/dev/null || echo 0)
    if [ "$NCOUNT" != "0" ] && [ -n "$NCOUNT" ]; then
      NOVELS+=("$QLABEL: $NCOUNT novels")
    fi
  fi
  echo "[validate]"
  python "$VALIDATE" --ticker-root "$TICKER_ROOT" --in "$MAPPED" --out "$VALIDATED" 2>&1 | tail -3 || { FAILED+=("$QLABEL: validate"); continue; }
done

echo ""
echo "===== Summary ====="
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "FAILED stages:"
  printf '  %s\n' "${FAILED[@]}"
fi
if [ ${#NOVELS[@]} -gt 0 ]; then
  echo "NOVELS surfaced:"
  printf '  %s\n' "${NOVELS[@]}"
fi
if [ ${#FAILED[@]} -eq 0 ] && [ ${#NOVELS[@]} -eq 0 ]; then
  echo "All filings clean: 0 novels, 0 FAILs"
fi
