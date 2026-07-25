#!/usr/bin/env bash
# ==========================================================================
#  Auckland congestion-charging equity analysis — full pipeline
#
#  Runs every stage in order, from raw data to the tables and figures used in
#  the manuscript. See code/HOW_TO_RUN.txt for setup and options.
#
#  Usage:
#     bash code/run_all.sh                  # everything
#     bash code/run_all.sh --skip-routing   # reuse the existing travel-time matrix
#     bash code/run_all.sh --skip-validation# skip the driving-route validation
#     bash code/run_all.sh --tables-only    # skip both long routing steps
# ==========================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_ROUTING=0
SKIP_VALIDATION=0
for arg in "$@"; do
    case "$arg" in
        --skip-routing)    SKIP_ROUTING=1 ;;
        --skip-validation) SKIP_VALIDATION=1 ;;
        --tables-only)     SKIP_ROUTING=1; SKIP_VALIDATION=1 ;;
        -h|--help)         sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
    esac
done

# ── Environment ───────────────────────────────────────────────────────────
# The project venv pins a working shapely/numpy/r5py combination. The system
# Python has shapely 2.0.4 against numpy 2.x, where union_all() and dissolve()
# raise TypeError, which breaks stage 4b.
if [ -x ".venv/bin/python3" ]; then
    export PATH="$PROJECT_ROOT/.venv/bin:$PATH"
else
    echo "ERROR: .venv not found. See code/HOW_TO_RUN.txt (section 1)."
    exit 1
fi
export R5PY_XMX="${R5PY_XMX:-12G}"
# _io_utils stages GeoPackage writes through this directory.
export GTFS_SCRATCH="${GTFS_SCRATCH:-/tmp}"

echo "=========================================================="
echo "  Auckland ToU charging — equity pipeline"
echo "=========================================================="
python3 - <<'PY'
import geopandas, shapely, r5py, pandas, numpy, sys
print(f"python {sys.version.split()[0]}  geopandas {geopandas.__version__}  "
      f"shapely {shapely.__version__}  r5py {r5py.__version__}")
print(f"pandas {pandas.__version__}  numpy {numpy.__version__}")
PY
echo "R5PY_XMX=$R5PY_XMX  GTFS_SCRATCH=$GTFS_SCRATCH"
echo ""

# ── Pre-flight: required inputs ───────────────────────────────────────────
REQUIRED=(
    "data/sa2/auckland_sa2.gpkg"
    "data/urban_rural/urban-rural.gpkg"
    "data/deprivation/NZDep2023_SA1_withHigherGeo.xlsx"
    "data/census/statsnz-2023-census-totals-by-topic-for-individuals-by-statistical-a-GPKG.zip"
    "data/income/statsnz-2023-census-totals-by-topic-for-households-by-statistical-ar-GPKG.zip"
    "data/osm/auckland.osm.pbf"
    "data/gtfs/at_gtfs.zip"
    "data/scenarios/scenario_1a.gpkg"
)
missing=0
for f in "${REQUIRED[@]}"; do
    [ -f "$f" ] || { echo "MISSING: $f"; missing=1; }
done
if [ "$missing" -eq 1 ]; then
    echo ""
    echo "Required input data is missing. See code/HOW_TO_RUN.txt (section 2)."
    exit 1
fi
mkdir -p outputs/intermediate outputs/figures

run() {   # run <label> <script> [args...]
    echo ""
    echo "---- $1 ----"
    local t0=$SECONDS
    shift
    python3 "$@"
    echo "     done in $((SECONDS - t0))s"
}

# ── Stage 1-3: data prep, routing, accessibility ──────────────────────────
run "Stage 1  Data prep (504 urban SA2s, pop-weighted centroids)" \
    code/stage1_data_prep.py

if [ "$SKIP_ROUTING" -eq 0 ]; then
    run "Stage 2  Travel-time matrix (r5py, SLOW: 10-30 min)" \
        code/stage2_routing.py
else
    echo ""
    echo "---- Stage 2  SKIPPED, reusing outputs/intermediate/travel_time_matrix.parquet ----"
    [ -f outputs/intermediate/travel_time_matrix.parquet ] || {
        echo "ERROR: no existing travel-time matrix to reuse."; exit 1; }
fi

run "Stage 3  Accessibility surface"          code/stage3_accessibility.py

# ── Stage 4: equity, scenarios, classification ────────────────────────────
run "Stage 4   Equity metrics"                code/stage4_equity.py
run "Stage 4b  Scenario boundary maps"        code/stage4b_scenario_boundaries.py
run "Stage 4c  OD classification + burden layer" code/stage4c_od_classification.py

for rank in nzdep income income_eq income_percap; do
    run "Stage 4d  Table 2 (rank=$rank)" \
        code/stage4d_equity_summary_final.py --rank "$rank"
done

run "Stage 4e  Income robustness comparison"  code/stage4e_ci_income_check.py
run "Stage 4f  Scenario geometry + buffer sensitivity" \
    code/stage4f_scenario_geometry.py

if [ "$SKIP_VALIDATION" -eq 0 ]; then
    run "Stage 4g  Driving-route validation (SLOW: 20-40 min)" \
        code/stage4g_route_motorway_share.py -n 0
else
    echo ""
    echo "---- Stage 4g  SKIPPED (driving-route validation) ----"
fi

# ── Figures ───────────────────────────────────────────────────────────────
# A figure failure should not discard a completed analysis, so these are
# reported but do not abort the run.
echo ""
echo "---- Figures ----"
FIG_FAILED=()
for f in _plot_fig_4_1.py _plot_fig_4_2a_bars.py _plot_fig_4_2b_lisa_maps.py \
         _plot_appendix_maps.py _plot_fig_method_classification.py \
         concept_fig_access45.py; do
    [ -f "code/$f" ] || continue
    if python3 "code/$f" > /dev/null 2>&1; then
        echo "  ok      $f"
    else
        echo "  FAILED  $f"
        FIG_FAILED+=("$f")
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=========================================================="
echo "  Pipeline complete in $((SECONDS / 60))m $((SECONDS % 60))s"
echo "=========================================================="
echo "Manuscript tables  -> outputs/*.csv"
echo "Manuscript figures -> outputs/figures/"
echo "Intermediates      -> outputs/intermediate/"
if [ "${#FIG_FAILED[@]}" -gt 0 ]; then
    echo ""
    echo "WARNING: these figure scripts failed: ${FIG_FAILED[*]}"
    echo "The analysis outputs above are unaffected."
fi
