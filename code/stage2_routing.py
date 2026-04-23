"""
Stage 2: r5py network build and travel time matrix
- Builds multimodal transport network (OSM + AT GTFS)
- Computes travel time matrix for all SA2 pairs
- Departure window: weekday 07:00-09:00
- Modes: TRANSIT (bus + rail + ferry) + WALK
- Outputs: travel_time_matrix.parquet
"""

import datetime
import os
import sys
from pathlib import Path

# JVM heap: configurable via R5PY_XMX env var (default 2500M for constrained
# sandbox; bump to 8G on a laptop with >=16 GB RAM).
_XMX = os.environ.get("R5PY_XMX", "2500M")
sys.argv += [f"-Xmx{_XMX}"]

import geopandas as gpd
import pandas as pd
import r5py

DATA   = Path("data")
OUTPUT = Path("outputs")

AKL_PBF  = DATA   / "auckland.osm.pbf"
# Prefer the cleaned feed (empty optional tables removed); R5's GTFS validator
# rejects tables that contain only a header row.
GTFS_ZIP = DATA / ("at_gtfs_clean.zip" if (DATA / "at_gtfs_clean.zip").exists() else "at_gtfs.zip")

SA2_PATH = OUTPUT / "sa2_prepared.gpkg"
if not (SA2_PATH.exists() and SA2_PATH.stat().st_size > 0):
    raise FileNotFoundError(
        f"No prepared SA2 file at {SA2_PATH}. Run stage1_data_prep.py first."
    )

# ── 2a. Load prepared SA2 centroids ─────────────────────────────────────────
sa2 = gpd.read_file(SA2_PATH)
sa2 = sa2.to_crs(epsg=4326)

# r5py expects a GeoDataFrame with an 'id' column and Point geometry
origins = gpd.GeoDataFrame(
    {"id": sa2["SA22023_V1_00"].values},
    geometry=gpd.points_from_xy(sa2["lon"], sa2["lat"]),
    crs="EPSG:4326"
)
print(f"Origins: {len(origins)} SA2 centroids")

# ── 2b. Build transport network ──────────────────────────────────────────────
# NOTE: First run takes 2-5 minutes; R5 writes a cached network to disk
print("Building transport network (OSM + GTFS)...")
print("This may take several minutes on first run.")

network = r5py.TransportNetwork(
    osm_pbf=str(AKL_PBF),
    gtfs=[str(GTFS_ZIP)]
)
print("Network built successfully.")

# ── 2c. Configure routing parameters ────────────────────────────────────────
# Departure: Tuesday 5 May 2026 (weekday, outside school holidays, inside the
# AT GTFS validity window 2026-04-15 to 2026-07-31).
# Departure time window: 07:00-09:00 (120 min) — R5 samples across this window
# and returns the median (p50) travel time across all departure minutes.

DEPARTURE_DATETIME = datetime.datetime(2026, 5, 5, 7, 0)
DEPARTURE_WINDOW   = datetime.timedelta(hours=2)
MAX_TRAVEL_TIME    = datetime.timedelta(minutes=60)
MAX_WALK_TIME      = datetime.timedelta(minutes=15)
WALK_SPEED_MS      = 1.2    # m/s (~4.3 km/h)

computer = r5py.TravelTimeMatrixComputer(
    network,
    origins=origins,
    destinations=origins,
    departure=DEPARTURE_DATETIME,
    departure_time_window=DEPARTURE_WINDOW,
    transport_modes=[
        r5py.TransportMode.TRANSIT,
        r5py.TransportMode.WALK,
    ],
    percentiles=[50],
    max_time=MAX_TRAVEL_TIME,
    max_time_walking=MAX_WALK_TIME,
    speed_walking=WALK_SPEED_MS * 3.6,   # r5py expects km/h
)

# ── 2d. Compute travel time matrix ───────────────────────────────────────────
print(f"Computing travel time matrix for {len(origins)} x {len(origins)} SA2 pairs...")
print("This is the main computation — expect 10-30 minutes for full Auckland.")

tt = computer.compute_travel_times()

# r5py emits either a single `travel_time` column (when percentiles == [50],
# which is the default) or `travel_time_p{:02d}` columns when multiple
# percentiles are requested. Normalise to `travel_time_p50` for the downstream
# accessibility stage.
if "travel_time_p50" not in tt.columns and "travel_time" in tt.columns:
    tt = tt.rename(columns={"travel_time": "travel_time_p50"})

print(f"Matrix shape: {tt.shape}")
print(f"Columns: {list(tt.columns)}")
print(f"Reachable pairs: {tt['travel_time_p50'].notna().sum():,} / {len(tt):,}")
print(f"Median travel time: {tt['travel_time_p50'].median():.1f} min")

# ── 2e. Save ─────────────────────────────────────────────────────────────────
# Use plain pandas writer: the travel-time matrix has no geometry column, so a
# normal parquet file (non-geo) is the natural format.
OUT = OUTPUT / "travel_time_matrix.parquet"
pd.DataFrame(tt).to_parquet(OUT, index=False)
print(f"\nStage 2 complete. Output saved: {OUT}")
print(tt.describe())
