"""
Build scenario 3c as a true corridor: the union of a half-width buffer of the
state-highway centrelines (data/roads/sh_clipped_with_bridge.gpkg, EPSG:2193)
and the dissolved 1a city-centre cordon. REVIEW-FIX 2026-09 (author request,
2026-09-19). The previous stored polygon (a filled 2 km polygon, 111.4 km2) is
kept at data/scenarios/archive/scenario_3c_2km_filled.gpkg.

Writes data/scenarios/scenario_3c.gpkg (1,000 m) and, for the sensitivity,
data/scenarios/archive/scenario_3c_{500m,2000m}.gpkg.
"""
from pathlib import Path
import time
import geopandas as gpd
from shapely.ops import unary_union

ROADS = Path("data/roads/sh_clipped_with_bridge.gpkg")
SCEN = Path("data/scenarios")
WIDTHS = {500: SCEN / "archive" / "scenario_3c_500m.gpkg",
          1000: SCEN / "scenario_3c.gpkg",
          2000: SCEN / "archive" / "scenario_3c_2000m.gpkg"}

roads = gpd.read_file(ROADS).to_crs(2193)
lines = unary_union(roads.geometry).simplify(5.0)
print(f"centrelines: {roads.shape[0]} features, total length {lines.length / 1000:.1f} km")
cordon = gpd.read_file(SCEN / "scenario_1a.gpkg").to_crs(2193).geometry.union_all()
print(f"1a cordon area {cordon.area / 1e6:.2f} km2")
for w, out in WIDTHS.items():
    t0 = time.time()
    buf = lines.buffer(w, quad_segs=8)
    poly = unary_union([buf, cordon])
    g = gpd.GeoDataFrame({"scenario": ["3c"], "half_width_m": [w],
                          "definition": [f"SH centreline {w} m half-width plus 1a cordon"]},
                         geometry=[poly], crs=2193)
    if out.exists():
        out.unlink()          # GPKG would otherwise append a second layer
    g.to_file(out, layer=f"scenario_3c_{w}m", driver="GPKG")
    print(f"{w:>5} m: buffer {buf.area/1e6:.1f} km2, union with cordon {poly.area/1e6:.1f} km2 "
          f"-> {out}  ({time.time()-t0:.1f}s)")
