"""
Stage 3: Accessibility surface and spatial join
- Computes cumulative opportunity accessibility (A_i) at 30 and 45 min thresholds
- Joins accessibility scores back to SA2 polygons
- Overlays with NZDep 2023 deciles
- Outputs: sa2_accessibility.gpkg
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

OUTPUT = Path("outputs")

SA2_PATH = OUTPUT / "sa2_prepared.gpkg"
if not (SA2_PATH.exists() and SA2_PATH.stat().st_size > 0):
    raise FileNotFoundError(f"No prepared SA2 file at {SA2_PATH}. Run stage1 first.")
TT_PARQUET = OUTPUT / "travel_time_matrix.parquet"

# ── 3a. Load data ─────────────────────────────────────────────────────────────
sa2 = safe_read_gpkg(SA2_PATH)
tt  = pd.read_parquet(TT_PARQUET)

# Ensure the travel-time column name matches downstream expectations.
if "travel_time_p50" not in tt.columns and "travel_time" in tt.columns:
    tt = tt.rename(columns={"travel_time": "travel_time_p50"})

# Harmonise ID types: stage 1 writes SA2 codes as strings, but r5py round-trips
# them through the RegionalTask and may return them as integers. Compare as str.
sa2["SA22023_V1_00"] = sa2["SA22023_V1_00"].astype(str)
tt["from_id"] = tt["from_id"].astype(str)
tt["to_id"]   = tt["to_id"].astype(str)

print(f"SA2 units: {len(sa2)}")
print(f"Travel time matrix rows: {len(tt):,}")

# Job opportunities at each destination SA2
jobs = sa2.set_index("SA22023_V1_00")["jobs_count"].fillna(0)

# ── 3b. Cumulative opportunity accessibility function ─────────────────────────
def compute_accessibility(tt_df, jobs_series, threshold_min):
    """
    A_i = sum_j O_j  where travel_time(i,j) <= threshold_min
    
    Parameters
    ----------
    tt_df        : DataFrame with columns [from_id, to_id, travel_time_p50]
    jobs_series  : Series indexed by SA2 ID with job counts
    threshold_min: integer, time threshold in minutes

    Returns
    -------
    DataFrame with columns [SA22023_V1_00, access_{threshold_min}min]
    """
    within = tt_df[tt_df["travel_time_p50"] <= threshold_min].copy()
    within["jobs"] = within["to_id"].map(jobs_series).fillna(0)

    acc = (
        within
        .groupby("from_id")["jobs"]
        .sum()
        .reset_index()
        .rename(columns={
            "from_id": "SA22023_V1_00",
            "jobs": f"access_{threshold_min}min"
        })
    )
    return acc

# ── 3c. Compute accessibility at two thresholds ───────────────────────────────
print("Computing accessibility at 30-min threshold...")
acc_30 = compute_accessibility(tt, jobs, threshold_min=30)

print("Computing accessibility at 45-min threshold...")
acc_45 = compute_accessibility(tt, jobs, threshold_min=45)

# Merge back to SA2
sa2 = sa2.merge(acc_30, on="SA22023_V1_00", how="left")
sa2 = sa2.merge(acc_45, on="SA22023_V1_00", how="left")

# SA2s with no reachable destinations within threshold = 0 (not NaN)
sa2["access_30min"] = sa2["access_30min"].fillna(0)
sa2["access_45min"] = sa2["access_45min"].fillna(0)

# ── 3d. Normalise accessibility (0-1) for mapping ────────────────────────────
for col in ["access_30min", "access_45min"]:
    max_val = sa2[col].max()
    sa2[f"{col}_norm"] = (sa2[col] / max_val).round(4) if max_val > 0 else 0.0

# ── 3e. Accessibility decile (within-Auckland quintile ranking) ───────────────
# qcut with duplicates='drop' may collapse identical bin edges (lots of zero-
# accessibility SA2s in outer Rodney / Franklin), so label count must match
# the number of bins actually returned. Compute bins first and label after.
_decile = pd.qcut(sa2["access_45min"], q=10, duplicates="drop")
_n_bins = _decile.cat.categories.size
sa2["access_45min_decile"] = pd.qcut(
    sa2["access_45min"],
    q=10,
    labels=range(1, _n_bins + 1),
    duplicates="drop",
).astype("Int64")

# ── 3f. Summary statistics by NZDep decile ───────────────────────────────────
print("\nAccessibility (45 min) by NZDep decile:")
summary = (
    sa2.groupby("NZDep_Decile")["access_45min"]
    .agg(["mean", "median", "std", "count"])
    .round(0)
)
print(summary.to_string())

# Flag high-accessibility SA2s (top quartile) as "viable alternative" candidates
Q75 = sa2["access_30min"].quantile(0.75)
sa2["has_viable_alt"] = sa2["access_30min"] >= Q75
print(f"\nViable alternative threshold (Q75, 30 min): {Q75:,.0f} jobs")
print(f"SA2s above threshold: {sa2['has_viable_alt'].sum()} / {len(sa2)}")

# ── 3g. Save ──────────────────────────────────────────────────────────────────
OUT = OUTPUT / "sa2_accessibility.gpkg"
safe_to_gpkg(sa2, OUT)
print(f"\nStage 3 complete. Output saved: {OUT}")
print(sa2[["SA22023_V1_00", "NZDep2023", "access_30min", "access_45min", "has_viable_alt"]].describe())
