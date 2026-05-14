#!/usr/bin/env bash
# Rebuild the accessibility + equity outputs using POPULATION-WEIGHTED SA2
# centroids as r5py origins. Intended to be run on Hyesop's laptop where r5py,
# Java, and ~8 GB JVM heap are available.
#
# Usage (from the gtfs-isochrone repo root):
#   bash code/run_popw_rebuild.sh
#
# Inputs (all already in data/):
#   - data/statsnz-2023-census-totals-by-topic-for-individuals-by-statistical-a-GPKG.zip
#   - data/NZDep2023_SA1.xlsx
#   - data/auckland.osm.pbf
#   - data/at_gtfs_clean.zip
#   - data/auckland_sa2.gpkg, data/employment_sa2.csv, data/nzdep2023.csv
#
# Outputs after the run:
#   - outputs/sa2_prepared.gpkg               (with pw lon/lat)
#   - outputs/travel_time_matrix.parquet      (new, from pw centroids)
#   - outputs/sa2_accessibility.gpkg          (new access_30min / access_45min)
#   - outputs/sa2_equity.gpkg                 (new burden + CI)
#   - outputs/sa2_final.gpkg                  (joined for visualisation)
#
# The previous geometric-centroid run is backed up to outputs/_geomcentroid/
# before anything is overwritten.

set -euo pipefail

cd "$(dirname "$0")/.."   # run from repo root

BACKUP_DIR="outputs/_geomcentroid"
mkdir -p "$BACKUP_DIR"

echo "==> Backing up geometric-centroid run to $BACKUP_DIR/ ..."
for f in sa2_prepared.gpkg travel_time_matrix.parquet \
         sa2_accessibility.gpkg sa2_accessibility_newjobs.gpkg \
         sa2_equity.gpkg sa2_equity_v2.gpkg sa2_final.gpkg \
         scenario_boundaries.gpkg scenario_boundaries_summary.csv \
         burden_crosstab.csv equity_summary.csv; do
  if [ -f "outputs/$f" ]; then
    cp -p "outputs/$f" "$BACKUP_DIR/$f"
    echo "    backed up outputs/$f"
  fi
done

export R5PY_XMX="${R5PY_XMX:-8G}"   # bump if your laptop has the RAM
echo "==> JVM heap set to R5PY_XMX=$R5PY_XMX"

echo "==> Stage 1 (population-weighted centroids)"
python3 code/stage1_data_prep.py

echo "==> Stage 2 (r5py travel-time matrix from pop-weighted origins)"
python3 code/stage2_routing.py

echo "==> Stage 3 (accessibility recomputation)"
python3 code/stage3_accessibility.py

echo "==> Stage 4 (equity recomputation)"
python3 code/stage4_equity.py

echo "==> Stage 4b (scenario boundaries with new burden classifications)"
python3 code/stage4b_scenario_boundaries.py

echo
echo "==> Quick comparison: how many SA2s flipped the burden classification?"
python3 - <<'PY'
import geopandas as gpd
old = gpd.read_file("outputs/_geomcentroid/sa2_final.gpkg")
new = gpd.read_file("outputs/sa2_final.gpkg")
old = old[["SA22023_V1_00","access_45min","burden_1a","burden_1c","burden_2c",
           "burden_3b","burden_3c","burden_3e"]].rename(
    columns={c: c+"_old" for c in ["access_45min","burden_1a","burden_1c",
                                    "burden_2c","burden_3b","burden_3c","burden_3e"]})
old["SA22023_V1_00"] = old["SA22023_V1_00"].astype(str)
new["SA22023_V1_00"] = new["SA22023_V1_00"].astype(str)
j = new.merge(old, on="SA22023_V1_00", how="left")
print()
print("Access_45min change (new - old):")
print((j["access_45min"] - j["access_45min_old"]).describe().round(0))
print()
for sc in ["1a","1c","2c","3b","3c","3e"]:
    flipped = (j[f"burden_{sc}"] != j[f"burden_{sc}_old"]).sum()
    old_no_alt = (j[f"burden_{sc}_old"] == "pays_without_alternative").sum()
    new_no_alt = (j[f"burden_{sc}"] == "pays_without_alternative").sum()
    print(f"  {sc}: flipped {flipped:>3} SA2s | no-alt {old_no_alt} -> {new_no_alt}")
PY

echo
echo "Done. Geometric-centroid backups in outputs/_geomcentroid/."
echo "If the new numbers look right, send me back the contents of outputs/_geomcentroid/sa2_final.gpkg"
echo "and outputs/sa2_final.gpkg and I'll regenerate the slides and tables."
