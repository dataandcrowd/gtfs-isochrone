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
DATA         = Path("data");                DATA.mkdir(exist_ok=True)
DATA_SA2     = DATA / "sa2"
DATA_ROADS   = DATA / "roads"
DATA_DEP     = DATA / "deprivation"
DATA_CENSUS  = DATA / "census"
DATA_JOBS    = DATA / "jobs"
DATA_URBAN   = DATA / "urban_rural"
DATA_GTFS    = DATA / "gtfs"
DATA_OSM     = DATA / "osm"
DATA_AKL     = DATA / "auckland"
DATA_SCEN    = DATA / "scenarios"
for _d in (DATA_SA2, DATA_ROADS, DATA_DEP, DATA_CENSUS, DATA_JOBS,
            DATA_URBAN, DATA_GTFS, DATA_OSM, DATA_AKL, DATA_SCEN):
    _d.mkdir(parents=True, exist_ok=True)
OUTPUT = Path("outputs"); OUTPUT.mkdir(exist_ok=True)

# ── Auckland bounding box (WGS84) ────────────────────────────────────────────
# Bounds chosen to fully enclose the Auckland Council region as supplied in
# data/auckland_sa2.gpkg (whose own bounds are roughly 174.16..175.29 E,
# -37.29..-36.12 S). The earlier metro-only bbox (174.4..175.3, -37.1..-36.7)
# was too tight and dropped 74 SA2s in Rodney (north), Franklin (south), and
# the Hibiscus Coast.
AUCKLAND_BBOX = (174.0, -37.4, 175.4, -36.0)   # minx, miny, maxx, maxy

# ── 1a. Download NZ OSM PBF and clip to Auckland ─────────────────────────────
NZ_PBF  = DATA_OSM / "new-zealand-latest.osm.pbf"
AKL_PBF = DATA_OSM / "auckland.osm.pbf"

# Sidecar file recording which bbox the existing AKL_PBF was clipped with.
# Lets us re-clip only when AUCKLAND_BBOX has actually changed (re-clipping
# costs ~30 s on a 16 GB laptop).
BBOX_SIDECAR = DATA_OSM / "auckland.osm.pbf.bbox"
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
GTFS_ZIP = DATA_GTFS / "at_gtfs.zip"

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
    DATA_SA2 / "auckland_sa2.gpkg",
    DATA_SA2 / "statistical-area-2-2023-clipped-generalised.gpkg",
]
SA2_SOURCE = next((p for p in SA2_CANDIDATES if p.exists()), None)

if SA2_SOURCE is None:
    raise FileNotFoundError(
        "No SA2 GeoPackage found. Place one of:\n"
        "  - data/sa2/auckland_sa2.gpkg  (regional clip, preferred)\n"
        "  - data/sa2/statistical-area-2-2023-clipped-generalised.gpkg  (full NZ)\n"
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
NZDEP_CSV = DATA_DEP / "nzdep2023.csv"

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
EMP_CSV = DATA_JOBS / "employment_sa2.csv"

if EMP_CSV.exists():
    emp = pd.read_csv(EMP_CSV, dtype={"SA22023_V1_00": str})
    sa2 = sa2.merge(emp[["SA22023_V1_00", "jobs_count"]], on="SA22023_V1_00", how="left")
    sa2["jobs_count"] = sa2["jobs_count"].fillna(0)
    print(f"Employment data merged. Total jobs: {sa2['jobs_count'].sum():,.0f}")
else:
    print("WARNING: employment_sa2.csv not found. Using uniform job weights (1 per SA2).")
    sa2["jobs_count"] = 1

# ── 1f. Compute population-weighted SA2 centroids ────────────────────────────
# Use SA1-level 2023 Census usually resident population (VAR_2_37) to weight
# centroids within each SA2. SA1 geometry + population from the Stats NZ
# "2023 Census totals by topic" GPKG; SA1→SA2 mapping from NZDep xlsx.

SA1_CENSUS_ZIP = DATA_CENSUS / "statsnz-2023-census-totals-by-topic-for-individuals-by-statistical-a-GPKG.zip"
SA1_POP_XLSX = DATA_DEP / "NZDep2023_SA1_withHigherGeo.xlsx"

# Also accept pre-extracted or standalone SA1 boundary files
SA1_BOUNDARY_CANDIDATES = [
    DATA_SA2 / "sa1-2023-clipped-generalised.gpkg",
    DATA_SA2 / "statistical-area-1-2023-clipped-generalised.gpkg",
    DATA_SA2 / "sa1_2023.gpkg",
]
SA1_BOUNDARY = next((p for p in SA1_BOUNDARY_CANDIDATES if p.exists()), None)

_has_sa1_geo = SA1_CENSUS_ZIP.exists() or SA1_BOUNDARY is not None

if _has_sa1_geo and SA1_POP_XLSX.exists():
    print("Computing population-weighted centroids from SA1 boundaries + census population...")

    if SA1_CENSUS_ZIP.exists():
        import zipfile as _zf
        _zfile = _zf.ZipFile(SA1_CENSUS_ZIP)
        _gpkg_name = next(f for f in _zfile.namelist() if f.endswith(".gpkg"))
        _tmp_dir = tempfile.mkdtemp()
        _zfile.extract(_gpkg_name, _tmp_dir)
        _sa1_path = Path(_tmp_dir) / _gpkg_name
        # Read only SA1 code, geometry, and VAR_2_37 (population) to save memory
        sa1_geo = gpd.read_file(_sa1_path, columns=["SA12023_V1_00", "VAR_2_37"])
        _zfile.close()
        shutil.rmtree(_tmp_dir, ignore_errors=True)
        sa1_geo = sa1_geo.rename(columns={"SA12023_V1_00": "SA12023_code", "VAR_2_37": "pop"})
    else:
        sa1_geo = gpd.read_file(SA1_BOUNDARY)
        sa1_code_col = next(
            (c for c in sa1_geo.columns if "SA1" in c.upper() and "2023" in c), None
        )
        if sa1_code_col is None:
            raise KeyError(f"Cannot find SA1 code column in {SA1_BOUNDARY}. Cols: {list(sa1_geo.columns)}")
        sa1_geo = sa1_geo.rename(columns={sa1_code_col: "SA12023_code"})
        sa1_geo["pop"] = None  # will be filled from xlsx below

    sa1_geo["SA12023_code"] = sa1_geo["SA12023_code"].astype(str)

    # Ensure NZTM for accurate centroid computation
    if sa1_geo.crs is None or sa1_geo.crs.to_epsg() != 2193:
        sa1_geo = sa1_geo.to_crs(epsg=2193)
    sa1_geo["sa1_cx"] = sa1_geo.geometry.centroid.x
    sa1_geo["sa1_cy"] = sa1_geo.geometry.centroid.y

    # Load SA1→SA2 mapping from NZDep xlsx
    sa1_pop = pd.read_excel(SA1_POP_XLSX)
    sa1_pop["SA12023_code"] = sa1_pop["SA12023_code"].astype(str)
    sa1_pop["SA22023_code"] = sa1_pop["SA22023_code"].astype(str)

    # Merge geometry centroids with SA2 mapping
    sa1_merged = sa1_geo[["SA12023_code", "sa1_cx", "sa1_cy", "pop"]].merge(
        sa1_pop[["SA12023_code", "SA22023_code"]],
        on="SA12023_code",
        how="inner",
    )
    # If pop came from census GPKG (VAR_2_37), use it; otherwise fall back to xlsx
    if sa1_merged["pop"].isna().all():
        sa1_merged = sa1_merged.drop(columns=["pop"]).merge(
            sa1_pop[["SA12023_code", "URPopnSA1_2023"]].rename(columns={"URPopnSA1_2023": "pop"}),
            on="SA12023_code", how="left",
        )
    sa1_merged["pop"] = pd.to_numeric(sa1_merged["pop"], errors="coerce").fillna(0).clip(lower=0)

    # Compute population-weighted centroid per SA2 (in NZTM)
    def _popw_centroid(grp):
        w = grp["pop"].values
        total = w.sum()
        if total == 0:
            return pd.Series({"pw_cx": grp["sa1_cx"].mean(), "pw_cy": grp["sa1_cy"].mean()})
        return pd.Series({
            "pw_cx": (grp["sa1_cx"] * w).sum() / total,
            "pw_cy": (grp["sa1_cy"] * w).sum() / total,
        })

    pw_centroids = sa1_merged.groupby("SA22023_code", group_keys=False)[["sa1_cx", "sa1_cy", "pop"]].apply(_popw_centroid).reset_index()

    # Convert NZTM coords to WGS84
    pw_points = gpd.GeoDataFrame(
        pw_centroids,
        geometry=gpd.points_from_xy(pw_centroids["pw_cx"], pw_centroids["pw_cy"]),
        crs="EPSG:2193",
    ).to_crs(epsg=4326)
    pw_points["lon"] = pw_points.geometry.x
    pw_points["lat"] = pw_points.geometry.y

    # Join back to SA2 — match on SA2 code
    sa2["SA22023_V1_00_str"] = sa2["SA22023_V1_00"].astype(str)
    pw_lookup = pw_points.set_index("SA22023_code")[["lon", "lat"]]

    sa2 = sa2.to_crs(epsg=4326)
    # Geometric centroid for fallback + diagnostic (compute in projected CRS)
    _sa2_nztm = sa2.to_crs(epsg=2193)
    _geom_pts = _sa2_nztm.geometry.centroid
    _geom_pts_wgs = gpd.GeoSeries(_geom_pts, crs="EPSG:2193").to_crs(epsg=4326)
    sa2["geom_lon"] = _geom_pts_wgs.x.values
    sa2["geom_lat"] = _geom_pts_wgs.y.values

    sa2 = sa2.merge(
        pw_lookup, left_on="SA22023_V1_00_str", right_index=True, how="left"
    )
    # Fill missing pop-weighted centroids with geometric fallback
    n_missing = sa2["lon"].isna().sum()
    if n_missing > 0:
        print(f"  {n_missing} SA2s have no SA1 pop data — using geometric centroid as fallback")
        sa2["lon"] = sa2["lon"].fillna(sa2["geom_lon"])
        sa2["lat"] = sa2["lat"].fillna(sa2["geom_lat"])

    # Diagnostic: distance between geometric and pop-weighted centroids
    pw_nztm = gpd.GeoDataFrame(
        sa2[["SA22023_V1_00"]],
        geometry=gpd.points_from_xy(sa2["lon"], sa2["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=2193)
    geom_nztm = gpd.GeoDataFrame(
        sa2[["SA22023_V1_00"]],
        geometry=gpd.points_from_xy(sa2["geom_lon"], sa2["geom_lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=2193)
    dists = pw_nztm.geometry.distance(geom_nztm.geometry)
    print(f"  Pop-weighted vs geometric centroid distance (m):")
    print(f"    mean={dists.mean():.0f}, median={dists.median():.0f}, "
          f"max={dists.max():.0f}, p95={dists.quantile(0.95):.0f}")

    sa2 = sa2.drop(columns=["SA22023_V1_00_str", "geom_lon", "geom_lat"])
    print(f"  Population-weighted centroids assigned to {(~sa2['lon'].isna()).sum()} SA2s")

else:
    # Fallback: geometric centroid
    if not _has_sa1_geo:
        print("WARNING: SA1 geometry not found. Using geometric centroids.")
        print("  For population-weighted centroids, place one of:")
        print(f"    - {SA1_CENSUS_ZIP.name}  (Stats NZ 2023 Census by SA1, with geometry)")
        print(f"    - {SA1_BOUNDARY_CANDIDATES[0].name}  (SA1 boundaries only)")
        print("  Download from: https://datafinder.stats.govt.nz/")
    elif not SA1_POP_XLSX.exists():
        print(f"WARNING: {SA1_POP_XLSX.name} not found. Using geometric centroids.")

    sa2 = sa2.to_crs(epsg=4326)
    sa2["lon"] = sa2.geometry.centroid.x
    sa2["lat"] = sa2.geometry.centroid.y

# ── 1g. Save prepared SA2 layer ──────────────────────────────────────────────
OUT_GPKG = DATA_SA2 / "sa2_prepared.gpkg"
_drop_cols = [c for c in ["centroid_wgs84"] if c in sa2.columns]
_layer = sa2.drop(columns=_drop_cols)
safe_to_gpkg(_layer, OUT_GPKG)
print(f"\nStage 1 complete. Output saved: {OUT_GPKG}")
print(sa2[["SA22023_V1_00", "NZDep2023", "NZDep_Decile", "jobs_count",
           "lon", "lat", "pop_total"]].describe())
