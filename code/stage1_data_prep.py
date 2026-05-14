"""
Stage 1: Data download and preparation
- Downloads Auckland OSM PBF and clips to bbox
- Downloads AT GTFS feed
- Loads SA2 boundaries + NZDep 2023 + employment data
- Outputs: auckland.osm.pbf, at_gtfs.zip, sa2_prepared.gpkg
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

# Shared helper that writes GeoPackage via a scratch path + shutil.copy2 to
# work around SQLite lock issues on FUSE-mounted sandboxes.
sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import SCRATCH_ROOT, safe_to_gpkg  # noqa: E402

# ── Directory setup ──────────────────────────────────────────────────────────
DATA   = Path("data");   DATA.mkdir(exist_ok=True)
OUTPUT = Path("outputs"); OUTPUT.mkdir(exist_ok=True)

# ── Auckland bounding box (WGS84) ────────────────────────────────────────────
# Bounds chosen to fully enclose the Auckland Council region as supplied in
# data/auckland_sa2.gpkg (whose own bounds are roughly 174.16..175.29 E,
# -37.29..-36.12 S). The earlier metro-only bbox (174.4..175.3, -37.1..-36.7)
# was too tight and dropped 74 SA2s in Rodney (north), Franklin (south), and
# the Hibiscus Coast.
AUCKLAND_BBOX = (174.0, -37.4, 175.4, -36.0)   # minx, miny, maxx, maxy

# ── 1a. Download NZ OSM PBF and clip to Auckland ─────────────────────────────
NZ_PBF  = DATA / "new-zealand-latest.osm.pbf"
AKL_PBF = DATA / "auckland.osm.pbf"

# Sidecar file recording which bbox the existing AKL_PBF was clipped with.
# Lets us re-clip only when AUCKLAND_BBOX has actually changed (re-clipping
# costs ~30 s on a 16 GB laptop).
BBOX_SIDECAR = DATA / "auckland.osm.pbf.bbox"
_current_bbox = ",".join(str(c) for c in AUCKLAND_BBOX)
_existing_bbox = BBOX_SIDECAR.read_text().strip() if BBOX_SIDECAR.exists() else None
_pbf_needs_clip = (
    not AKL_PBF.exists()
    or AKL_PBF.stat().st_size == 0
    or _existing_bbox != _current_bbox
)

if _pbf_needs_clip:
    if not NZ_PBF.exists():
        print("Downloading NZ OSM PBF (~800 MB)...")
        url = "https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf"
        r = requests.get(url, stream=True, timeout=600)
        with open(NZ_PBF, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete.")

    print(f"Clipping NZ PBF to Auckland bbox {_current_bbox} with osmium...")
    # Write to scratch first, then shutil.copy2 over the FUSE mount target.
    # osmium cannot overwrite a file the FUSE layer refuses to unlink.
    with tempfile.NamedTemporaryFile(
        suffix=".osm.pbf", dir=SCRATCH_ROOT, delete=False,
    ) as tmp:
        scratch_pbf = Path(tmp.name)
    scratch_pbf.unlink()
    subprocess.run([
        "osmium", "extract",
        "--bbox", _current_bbox,
        str(NZ_PBF),
        "-o", str(scratch_pbf),
        "--overwrite",
    ], check=True)
    shutil.copy2(scratch_pbf, AKL_PBF)
    try:
        scratch_pbf.unlink()
    except OSError:
        pass
    BBOX_SIDECAR.write_text(_current_bbox)
    print(f"Clipped PBF saved: {AKL_PBF} ({AKL_PBF.stat().st_size / 1e6:.1f} MB)")
else:
    print(f"OSM PBF already covers bbox {_current_bbox}: {AKL_PBF}")

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

# Reproject to WGS84 for r5py compatibility downstream. We do NOT apply the
# AUCKLAND_BBOX as a hard clip on the SA2 layer here because the supplied
# auckland_sa2.gpkg is already a regional clip drawn from the Auckland Council
# boundary; intersecting with the looser numeric bbox would silently drop
# legitimate SA2s along the curved edge of the region (notably the offshore
# islands and the long Rodney coastline). Stage 2 is responsible for ensuring
# the OSM extent covers all SA2s used as origins.
sa2 = sa2.to_crs(epsg=4326)
print(f"SA2 retained from {SA2_SOURCE.name}: {len(sa2)} units")

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

# ── 1f. Compute SA2 centroids ────────────────────────────────────────────────
# Two centroid definitions are computed and stored:
#   - centroid_geom : polygon geometric centroid (legacy, retained for diagnostics)
#   - lon / lat     : population-weighted SA2 centroid, used as the r5py origin
#                     point downstream. Weighted by SA1 usually resident count
#                     (Stats NZ 2023 Census). This is the more defensible origin
#                     for an equity analysis, since 'Aucklanders complain about
#                     poor PT' is a per-resident claim, not a per-polygon claim.
# Provenance:
#   - SA1 polygon geometry + SA1 population: Stats NZ '2023 Census totals by
#     topic for individuals by SA1' GPKG (VAR_2_37 = total usually resident
#     population count, 2023). See data/2023_census_totals_by_topic_for_individuals_by_sa1_part_2_lookup_table.csv
#     for the column dictionary.
#   - SA1 -> SA2 mapping: data/NZDep2023_SA1.xlsx, columns SA12023_code and
#     SA22023_code.
# Where total SA1 population in an SA2 is zero (empty census units, e.g. some
# offshore islands), we fall back to the polygon geometric centroid so r5py
# still gets a valid origin point.

sa2 = sa2.to_crs(epsg=4326)
sa2["centroid_geom"] = sa2.geometry.centroid

SA1_GPKG = DATA / "statsnz-2023-census-totals-by-topic-for-individuals-by-statistical-a-GPKG.zip"
SA1_LOOKUP = DATA / "NZDep2023_SA1.xlsx"

import zipfile, tempfile, shutil

def _load_sa1_layer() -> gpd.GeoDataFrame:
    """Load SA1 polygons + 2023 usually resident population (VAR_2_37) from
    the Stats NZ GPKG bundle. The bundle is a zip in data/; we extract to a
    temporary directory rather than unpacking into the repo."""
    if not SA1_GPKG.exists():
        raise FileNotFoundError(
            f"SA1 GPKG bundle not found at {SA1_GPKG}. Download from Stats NZ "
            "DataFinder: '2023 Census totals by topic for individuals by SA1' "
            "(GPKG format), and place the .zip in data/."
        )
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(SA1_GPKG) as zf:
            # find the *.gpkg member
            gpkg_member = next(n for n in zf.namelist() if n.endswith(".gpkg"))
            zf.extract(gpkg_member, td)
            gpkg_path = Path(td) / gpkg_member
            sa1 = gpd.read_file(
                str(gpkg_path),
                columns=["SA12023_V1_00", "VAR_2_37", "geometry"],
            )
    sa1 = sa1.rename(columns={"SA12023_V1_00": "SA1_code",
                              "VAR_2_37":      "pop_2023"})
    sa1["SA1_code"] = sa1["SA1_code"].astype(str)
    sa1["pop_2023"] = pd.to_numeric(sa1["pop_2023"], errors="coerce").fillna(0)
    return sa1

sa1 = _load_sa1_layer()

# SA1 -> SA2 mapping
m = pd.read_excel(SA1_LOOKUP)
m = m.rename(columns={"SA12023_code": "SA1_code",
                      "SA22023_code": "SA22023_V1_00"})
m["SA1_code"]      = m["SA1_code"].astype(str)
m["SA22023_V1_00"] = m["SA22023_V1_00"].astype(str)
sa1 = sa1.merge(m[["SA1_code", "SA22023_V1_00"]], on="SA1_code", how="left")

# Restrict to Auckland SA1s by membership in the Auckland SA2 set
sa1_akl = sa1[sa1["SA22023_V1_00"].isin(sa2["SA22023_V1_00"])].copy()
print(f"SA1 features in Auckland: {len(sa1_akl):,} "
      f"(total SA1 pop {int(sa1_akl['pop_2023'].sum()):,})")

# Compute SA1 centroids in projected metres so x/y averaging is correct,
# then back-project the weighted mean to WGS84.
sa1_akl_m = sa1_akl.to_crs(epsg=2193).copy()
sa1_akl_m["cx_m"] = sa1_akl_m.geometry.centroid.x
sa1_akl_m["cy_m"] = sa1_akl_m.geometry.centroid.y

# Population-weighted SA2 centroid (in NZTM2000 metres). Where total
# population in an SA2 is zero, the groupby yields NaN; we resolve below.
def _weighted_mean(g):
    w = g["pop_2023"]
    if w.sum() <= 0:
        return pd.Series({"pwx_m": float("nan"), "pwy_m": float("nan"),
                          "pop_total": 0.0})
    return pd.Series({
        "pwx_m": (w * g["cx_m"]).sum() / w.sum(),
        "pwy_m": (w * g["cy_m"]).sum() / w.sum(),
        "pop_total": float(w.sum()),
    })
pw = (sa1_akl_m.groupby("SA22023_V1_00", group_keys=False)
              .apply(_weighted_mean)
              .reset_index())

# Back-project the metric pop-weighted point to WGS84 lon/lat.
pw_gpd = gpd.GeoDataFrame(
    pw,
    geometry=gpd.points_from_xy(pw["pwx_m"], pw["pwy_m"]),
    crs="EPSG:2193",
).to_crs(4326)
pw["pw_lon"] = pw_gpd.geometry.x
pw["pw_lat"] = pw_gpd.geometry.y

sa2 = sa2.merge(pw[["SA22023_V1_00", "pw_lon", "pw_lat", "pop_total"]],
                on="SA22023_V1_00", how="left")

# Geometric centroid as fallback (for SA2s where pop = 0)
fallback_mask = sa2["pw_lon"].isna() | sa2["pw_lat"].isna() | (sa2["pop_total"].fillna(0) <= 0)
sa2.loc[fallback_mask, "pw_lon"] = sa2.loc[fallback_mask, "centroid_geom"].x
sa2.loc[fallback_mask, "pw_lat"] = sa2.loc[fallback_mask, "centroid_geom"].y
n_fb = int(fallback_mask.sum())
if n_fb:
    print(f"  {n_fb} SA2s had zero SA1 population; fell back to geometric centroid.")

# Final origin coordinates for r5py
sa2["lon"] = sa2["pw_lon"]
sa2["lat"] = sa2["pw_lat"]

# Diagnostic: distance between geometric and pop-weighted centroid
_diag = gpd.GeoDataFrame(
    sa2[["SA22023_V1_00"]].copy(),
    geometry=sa2["centroid_geom"],
    crs="EPSG:4326",
).to_crs(2193)
_diag["pw_x"], _diag["pw_y"] = (
    gpd.GeoDataFrame(geometry=gpd.points_from_xy(sa2["lon"], sa2["lat"]),
                     crs="EPSG:4326").to_crs(2193).geometry.x.values,
    gpd.GeoDataFrame(geometry=gpd.points_from_xy(sa2["lon"], sa2["lat"]),
                     crs="EPSG:4326").to_crs(2193).geometry.y.values,
)
_diag["dist_m"] = ((_diag.geometry.x - _diag["pw_x"])**2 +
                   (_diag.geometry.y - _diag["pw_y"])**2) ** 0.5
print("Centroid shift (m) between geometric and pop-weighted origins:")
print(_diag["dist_m"].describe().round(1).to_string())

# ── 1g. Save prepared SA2 layer ──────────────────────────────────────────────
OUT_GPKG = OUTPUT / "sa2_prepared.gpkg"
_layer = sa2.drop(columns=["centroid_geom"])
safe_to_gpkg(_layer, OUT_GPKG)
print(f"\nStage 1 complete. Output saved: {OUT_GPKG}")
print(sa2[["SA22023_V1_00", "NZDep2023", "NZDep_Decile", "jobs_count",
           "lon", "lat", "pop_total"]].describe())
