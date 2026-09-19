"""
Shared scenario-geometry helpers.

REVIEW-FIX 2026-09: stage 4c used to build its charged sets from the
hardcoded SA2 name lists in stage4_equity.py, while stage 4f read the
authoritative geometry in data/scenarios/. The two disagreed. The functions
below were lifted from stage4f_scenario_geometry.py so that both stages use
one definition:

    cordons (1a, 1c)   charged when the workplace SA2 is inside the cordon
                       and the residence SA2 is outside it
    motorway (3c)      charged when the straight desire line between the
                       population-weighted residence and workplace centroids
                       intersects the corridor polygon: a 1 km half-width
                       buffer of the state-highway centrelines plus the 1a
                       city-centre cordon (built by build_scenario_3c.py,
                       2026-09-19; the earlier filled 2 km polygon is in
                       data/scenarios/archive/)

Only scenarios 1a, 1c and 3c are analysed.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

DATA_SCEN = Path("data") / "scenarios"

SCENARIOS          = ["1a", "1c", "3c"]
CBD_SCENARIOS      = ["1a", "1c"]
MOTORWAY_SCENARIOS = ["3c"]
STORED_HALF_WIDTH  = 1000.0                      # metres (2026-09-19: 1 km corridor)
# True line-buffer variants for the sensitivity, all built the same way.
CORRIDOR_FILES = {
    500.0:  DATA_SCEN / "archive" / "scenario_3c_500m.gpkg",
    1000.0: DATA_SCEN / "scenario_3c.gpkg",
    2000.0: DATA_SCEN / "archive" / "scenario_3c_2000m.gpkg",
}


def scenario_sa2_codes(s):
    """SA2 codes making up a CBD cordon, from the scenario file."""
    g = gpd.read_file(DATA_SCEN / f"scenario_{s}.gpkg")
    col = next(c for c in g.columns if c.startswith("SA22") and c.endswith("V1_00"))
    return set(g[col].astype(str))


def corridor_polygon(s, half_width=STORED_HALF_WIDTH):
    """Motorway corridor polygon at a given half-width.

    2026-09-19: each half-width is a separately built buffer of the centrelines
    plus the 1a cordon (CORRIDOR_FILES), not an erosion or dilation of one
    stored polygon. Only the built widths are available.
    """
    if s != "3c":
        raise ValueError(f"no corridor file for scenario {s}")
    try:
        path = CORRIDOR_FILES[float(half_width)]
    except KeyError:
        raise ValueError(f"no corridor built at half-width {half_width} m; "
                         f"available: {sorted(CORRIDOR_FILES)}")
    return gpd.read_file(path).to_crs(2193).geometry.union_all()


def desire_lines(res_codes, wrk_codes, cx, cy):
    """Straight residence -> workplace lines in NZTM from centroid lookups."""
    o = np.column_stack([pd.Series(res_codes).map(cx).to_numpy(),
                         pd.Series(res_codes).map(cy).to_numpy()])
    d = np.column_stack([pd.Series(wrk_codes).map(cx).to_numpy(),
                         pd.Series(wrk_codes).map(cy).to_numpy()])
    return gpd.GeoSeries(shapely.linestrings(np.stack([o, d], axis=1)), crs="EPSG:2193")


def charged_mask(s, res_codes, wrk_codes, lines=None, half_width=STORED_HALF_WIDTH):
    """Boolean numpy array: is each OD pair charged under scenario `s`?"""
    res = pd.Series(res_codes).astype(str)
    wrk = pd.Series(wrk_codes).astype(str)
    if s in CBD_SCENARIOS:
        codes = scenario_sa2_codes(s)
        return (wrk.isin(codes) & ~res.isin(codes)).to_numpy()
    if s in MOTORWAY_SCENARIOS:
        if lines is None:
            raise ValueError("motorway scenarios need the desire lines")
        return lines.intersects(corridor_polygon(s, half_width)).to_numpy()
    raise ValueError(f"unknown scenario {s}")
