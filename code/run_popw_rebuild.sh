#!/usr/bin/env bash
# Population-weighted centroid rebuild pipeline
# Backs up existing outputs, then re-runs stage1→stage2→stage3→stage4→stage4b
# with SA1 population-weighted centroids.
#
# Usage:
#   cd /path/to/gtfs-isochrone
#   bash code/run_popw_rebuild.sh
#
# JVM memory (for r5py stage2): default 8G, override with R5PY_XMX env var
#   R5PY_XMX=12G bash code/run_popw_rebuild.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

export R5PY_XMX="${R5PY_XMX:-8G}"
export GTFS_SCRATCH="${GTFS_SCRATCH:-/tmp}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="outputs/_geomcentroid_${TIMESTAMP}"

echo "=============================================="
echo "  Population-weighted centroid rebuild"
echo "=============================================="
echo "Project root: $PROJECT_ROOT"
echo "R5PY_XMX:     $R5PY_XMX"
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────────────
CENSUS_ZIP="data/census/statsnz-2023-census-totals-by-topic-for-individuals-by-statistical-a-GPKG.zip"
SA1_FILES=(
    "$CENSUS_ZIP"
    "data/sa2/sa1-2023-clipped-generalised.gpkg"
    "data/sa2/statistical-area-1-2023-clipped-generalised.gpkg"
    "data/sa2/sa1_2023.gpkg"
)
SA1_FOUND=false
for f in "${SA1_FILES[@]}"; do
    if [ -f "$f" ]; then
        echo "SA1 geometry source: $f"
        SA1_FOUND=true
        break
    fi
done

if [ "$SA1_FOUND" = false ]; then
    echo "ERROR: SA1 geometry not found. Need one of:"
    echo "  - $CENSUS_ZIP"
    echo "  - data/sa2/sa1-2023-clipped-generalised.gpkg"
    echo "Download from: https://datafinder.stats.govt.nz/"
    exit 1
fi

if [ ! -f "data/deprivation/NZDep2023_SA1_withHigherGeo.xlsx" ]; then
    echo "ERROR: data/deprivation/NZDep2023_SA1_withHigherGeo.xlsx not found."
    exit 1
fi

# ── Backup existing outputs ────────────────────────────────────────────────
if [ -d "outputs" ] && [ "$(ls outputs/*.gpkg 2>/dev/null | wc -l)" -gt 0 ]; then
    echo ""
    echo "Backing up existing outputs → $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp outputs/*.gpkg "$BACKUP_DIR/" 2>/dev/null || true
    cp outputs/*.parquet "$BACKUP_DIR/" 2>/dev/null || true
    cp outputs/*.csv "$BACKUP_DIR/" 2>/dev/null || true
    echo "Backup complete."
fi

# ── Stage 1: Data prep (pop-weighted centroids) ───────────────────────────
echo ""
echo "── Stage 1: Data prep (pop-weighted centroids) ──"
python3 code/stage1_data_prep.py
echo "Stage 1 done."

# ── Stage 2: Routing (r5py travel time matrix) ───────────────────────────
echo ""
echo "── Stage 2: Routing (R5PY_XMX=${R5PY_XMX}) ──"
python3 code/stage2_routing.py
echo "Stage 2 done."

# ── Stage 3: Accessibility surface ────────────────────────────────────────
echo ""
echo "── Stage 3: Accessibility ──"
python3 code/stage3_accessibility.py
echo "Stage 3 done."

# ── Stage 4: Equity metrics ──────────────────────────────────────────────
echo ""
echo "── Stage 4: Equity ──"
python3 code/stage4_equity.py
echo "Stage 4 done."

# ── Stage 4b: Scenario boundaries ────────────────────────────────────────
echo ""
echo "── Stage 4b: Scenario boundaries ──"
python3 code/stage4b_scenario_boundaries.py
echo "Stage 4b done."

# ── Comparison: old vs new ───────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Comparing old (geometric) vs new (pop-weighted)"
echo "=============================================="

python3 - "$BACKUP_DIR" <<'PYEOF'
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

backup = Path(sys.argv[1])
old_path = backup / "sa2_final.gpkg"
new_path = Path("data/sa2/sa2_final.gpkg")

if not old_path.exists():
    old_path = backup / "sa2_equity.gpkg"
if not new_path.exists():
    new_path = Path("data/sa2/sa2_equity.gpkg")

if not old_path.exists() or not new_path.exists():
    print("Cannot compare: missing sa2_final.gpkg or sa2_equity.gpkg")
    sys.exit(0)

old = gpd.read_file(old_path)
new = gpd.read_file(new_path)

# Find common SA2 code column
code_col = next(c for c in old.columns if "SA2" in c.upper() and "V1" in c)

merged = old[[code_col]].merge(
    old.set_index(code_col)[["access_45min"]].rename(columns={"access_45min": "old_a45"}),
    left_on=code_col, right_index=True, how="left"
).merge(
    new.set_index(code_col)[["access_45min"]].rename(columns={"access_45min": "new_a45"}),
    left_on=code_col, right_index=True, how="left"
)

merged["delta"] = merged["new_a45"] - merged["old_a45"]

print("\n── access_45min change (new - old) ──")
print(merged["delta"].describe().to_string())
print(f"\n  SA2s with |change| > 1000 jobs: {(merged['delta'].abs() > 1000).sum()}")
print(f"  SA2s with |change| > 5000 jobs: {(merged['delta'].abs() > 5000).sum()}")

# Burden flip comparison per scenario
scenario_cols = [c for c in old.columns if c.startswith("burden_")]
if scenario_cols:
    print("\n── Burden classification flips per scenario ──")
    for col in scenario_cols:
        if col in new.columns:
            flips = (old[col].values != new[col].values).sum()
            print(f"  {col}: {flips} SA2s flipped")
else:
    print("\nNo burden columns found for flip comparison.")

PYEOF

echo ""
echo "=============================================="
echo "  Rebuild complete!"
echo "  Old outputs backed up to: $BACKUP_DIR"
echo "=============================================="
