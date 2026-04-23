"""
Stage 1: Data download and preparation
- Downloads Auckland OSM PBF and clips to bbox
- Downloads AT GTFS feed
- Loads SA2 boundaries + NZDep 2023 + employment data
- Outputs: auckland.osm.pbf, at_gtfs.zip, sa2_prepared.gpkg
"""

import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

# Shared helper that writes GeoPackage via a scratch path + shutil.copy2 to
# work around SQLite lock issues on FUSE-mounted sandboxes.
sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_to_gpkg  # noqa: E402

# ── Directory setup ──────────────────────────────────────────────────────────
DATA   = Path("data");   DATA.mkdir(exist_ok=True)
OUTPUT = Path("outputs"); OUTPUT.mkdir(exist_ok=True)

# ── Auckland bounding box (WGS84) ────────────────────────────────────────────
AUCKLAND_BBOX = (174.4, -37.1, 175.3, -36.7)   # minx, miny, maxx, maxy

# ── 1a. Download NZ OSM PBF and clip to Auckland ─────────────────────────────
NZ_PBF  = DATA / "new-zealand-latest.osm.pbf"
AKL_PBF = DATA / "auckland.osm.pbf"

if not AKL_PBF.exists():
    if not NZ_PBF.exists():
        print("Downloading NZ OSM PBF (~800 MB)...")
        url = "https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf"
        r = requests.get(url, stream=True, timeout=600)
        with open(NZ_PBF, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete.")

    print("Clipping to Auckland bbox with osmium...")
    bbox_str = ",".join(str(c) for c in AUCKLAND_BBOX)
    subprocess.run([
        "osmium", "extract",
        "--bbox", bbox_str,
        str(NZ_PBF),
        "-o", str(AKL_PBF),
        "--overwrite"
    ], check=True)
    print(f"Clipped PBF saved: {AKL_PBF} ({AKL_PBF.stat().st_size / 1e6:.1f} MB)")
else:
    print(f"OSM PBF already exists: {AKL_PBF}")

# ── 1b. Download AT GTFS ─────────────────────────────────────────────────────
GTFS_ZIP = DATA / "at_gtfs.zip"

if not GTFS_ZIP.exists():
    print("Downloading AT GTFS feed...")
    r = requests.get("https://gtfs.at.govt.nz/gtfs.zip", timeout=120)
    with open(GTFS_ZIP, "wb") as f:
        f.write(r.content)
    print(f"GTFS saved: {GTFS_ZIP} ({GTFS_ZIP.stat().st_size / 1e6:.1f} MB)")
else:
    print(f"GTFS already exists: {GTFS_ZIP}")

# ── 1c. Load SA2 boundaries ──────────────────────────────────────────────────
# Prefer the Auckland-region SA2 GeoPackage provided by the user.
# Fallback: the full NZ Stats NZ SA2 layer (SA22023 or SA22026 codes).
SA2_CANDIDATES = [
    DATA / "auckland_sa2.gpkg",
    DATA / "statistical-area-2-2023-clipped-generalised.gpkg",
]
SA2_SOURCE = next((p for p in SA2_CANDIDATES if p.exists()), None)

if SA2_SOURCE is None:
    raise FileNotFoundError(
        "No SA2 GeoPackage found. Place one of:\n"
        "  - data/auckland_sa2.gpkg  (regional clip, preferred)\n"
        "  - data/statistical-area-2-2023-clipped-generalised.gpkg  (full NZ)\n"
        "Download either from https://datafinder.stats.govt.nz/"
    )

sa2 = gpd.read_file(SA2_SOURCE)
print(f"SA2 loaded from {SA2_SOURCE.name}: {len(sa2)} units, CRS={sa2.crs}")

# Standardise SA2 ID column name. Accept either 2023 or 2026 boundary variants;
# the 6-digit codes are almost always identical between the two snapshots.
if "SA22023_V1_00" not in sa2.columns:
    candidate = [c for c in sa2.columns if "SA2" in c.upper()
                 and any(y in c for y in ("2023", "2026"))]
    if candidate:
        sa2 = sa2.rename(columns={candidate[0]: "SA22023_V1_00"})
    else:
        raise KeyError(f"Could not find SA2 code column. Available: {list(sa2.columns)}")

# Reproject and clip to the Auckland bbox. If the file is already an Auckland
# clip (like auckland_sa2.gpkg) the intersect test is a no-op.
sa2 = sa2.to_crs(epsg=4326)
akl_bbox_geom = box(*AUCKLAND_BBOX)
sa2 = sa2[sa2.geometry.intersects(akl_bbox_geom)].copy()
print(f"SA2 after Auckland clip: {len(sa2)} units")

# ── 1d. Load NZDep 2023 ──────────────────────────────────────────────────────
# NZDep 2023 — download from:
# https://www.otago.ac.nz/wellington/departments/publichealth/research/hirp/otago020194.html
NZDEP_CSV = DATA / "nzdep2023.csv"

if not NZDEP_CSV.exists():
    raise FileNotFoundError(
        "Please download NZDep 2023 CSV from the University of Otago Wellington\n"
        f"and save to: {NZDEP_CSV}"
    )

nzdep = pd.read_csv(NZDEP_CSV, dtype={"SA22023_V1_00": str})
required_cols = {"SA22023_V1_00", "NZDep2023"}
if not required_cols.issubset(nzdep.columns):
    print(f"Available columns: {list(nzdep.columns)}")
    raise ValueError(f"NZDep CSV missing expected columns: {required_cols - set(nzdep.columns)}")

sa2 = sa2.merge(
    nzdep[["SA22023_V1_00", "NZDep2023"]],
    on="SA22023_V1_00",
    how="left"
)
sa2["NZDep_Decile"] = pd.qcut(sa2["NZDep2023"], q=10, labels=range(1, 11)).astype("Int64")
print(f"NZDep merged: {sa2['NZDep2023'].notna().sum()} / {len(sa2)} SA2s have deprivation scores")

# ── 1e. Load employment data ─────────────────────────────────────────────────
# Stats NZ Business Demography or Census employment by SA2
# Download from: https://www.stats.govt.nz/tools/2018-census-place-of-work-auckland
EMP_CSV = DATA / "employment_sa2.csv"

if EMP_CSV.exists():
    emp = pd.read_csv(EMP_CSV, dtype={"SA22023_V1_00": str})
    sa2 = sa2.merge(emp[["SA22023_V1_00", "jobs_count"]], on="SA22023_V1_00", how="left")
    sa2["jobs_count"] = sa2["jobs_count"].fillna(0)
    print(f"Employment data merged. Total jobs: {sa2['jobs_count'].sum():,.0f}")
else:
    print("WARNING: employment_sa2.csv not found. Using uniform job weights (1 per SA2).")
    sa2["jobs_count"] = 1

# ── 1f. Compute SA2 centroids (stay in WGS84) ────────────────────────────────
sa2 = sa2.to_crs(epsg=4326)
sa2["centroid_wgs84"] = sa2.geometry.centroid
sa2["lon"] = sa2["centroid_wgs84"].x
sa2["lat"]  = sa2["centroid_wgs84"].y

# ── 1g. Save prepared SA2 layer ──────────────────────────────────────────────
OUT_GPKG = OUTPUT / "sa2_prepared.gpkg"
_layer   = sa2.drop(columns=["centroid_wgs84"])
safe_to_gpkg(_layer, OUT_GPKG)
print(f"\nStage 1 complete. Output saved: {OUT_GPKG}")
print(sa2[["SA22023_V1_00", "NZDep2023", "NZDep_Decile", "jobs_count", "lon", "lat"]].describe())
