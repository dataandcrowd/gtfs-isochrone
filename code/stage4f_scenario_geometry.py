"""
Stage 4f: Reclassify scenario burden from the AUTHORITATIVE scenario geometry
in data/scenarios/, with a buffer-width sensitivity analysis for the motorway
corridors.

Why this exists
---------------
stage4_equity.py defines each scenario from a hand-written list of SA2 names,
and stage4c dissolves those whole SA2 polygons into the "corridor". data/
scenarios/ already holds the real scenario geometry (and is read by nothing in
the pipeline), so the two disagree substantially:

    scenario   data/scenarios/            hardcoded SA2 lists
    1a         16 SA2s,   4.25 km2        15 SA2s
    1c         21 SA2s,   8.22 km2        27 SA2s   (+6)
    2c         59 SA2s,  41.78 km2       158 SA2s   (+99)
    3b         2 km buffer, 108.2 km2    171 SA2s, 263.4 km2
    3c         2 km buffer, 111.4 km2    186 SA2s, 267.5 km2
    3e         2 km buffer,  72.7 km2     22 SA2s,  28.5 km2

(Historical: since 2026-11-14 stage 4c also classifies from data/scenarios/
via _scenario_utils, so stage 4c and this stage agree. Only the manuscript
scenarios 1a, 1c and 3c are analysed; 2c, 3b and 3e were dropped.)

Classification rules follow the manuscript (section 3.3):
    Cordons (1a, 1c) -- workplace inside the cordon, residence outside.
    Corridor (3c)    -- residence->workplace desire line intersects the
                        corridor polygon.

Buffer sensitivity
------------------
3c is a buffer of the state-highway centrelines plus the 1a cordon, built at
each half-width separately by build_scenario_3c.py (500 m and 2,000 m in
data/scenarios/archive/, 1,000 m headline in data/scenarios/). Widths whose
file has not been built are skipped.

Input : data/scenarios/scenario_*.gpkg
        outputs/intermediate/od_pairs_classified.parquet   (for car_commuters, has_pt_alt)
        outputs/burden_by_sa2_final.gpkg      (access_45min, pop, NZDep2023)
Output: outputs/sensitivity_analysis/2_corridor_width/
            scenario_geometry_sensitivity.csv
            scenario_geometry_headline.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import attach_income, concentration_index, equity_reading  # noqa: E402
# FIX 2026-11-14: scenario definitions now come from _scenario_utils (shared
# with stage 4c). Only 1a, 1c and 3c are analysed; the 3c corridor widths are
# the separately built 500 / 1000 / 2000 m buffers (build_scenario_3c.py), not
# re-buffers of a stored 2 km polygon. The 1000 m row is the headline.
from _scenario_utils import (  # noqa: E402
    CBD_SCENARIOS, MOTORWAY_SCENARIOS, STORED_HALF_WIDTH, CORRIDOR_FILES,
    scenario_sa2_codes, corridor_polygon,
)

OUTPUT    = Path("outputs")
BURDEN    = OUTPUT / "burden_by_sa2_final.gpkg"
SENS      = OUTPUT / "sensitivity_analysis" / "2_corridor_width"
SA2_PREPARED = Path("data") / "sa2" / "sa2_prepared.gpkg"
OD        = OUTPUT / "intermediate" / "od_pairs_classified.parquet"

HALF_WIDTHS = sorted(CORRIDOR_FILES)

RANKS = {
    "nzdep":     "NZDep2023",
    "income_eq": "income_equiv_sqrt_disadv",
}


def load_sa2():
    sa2 = attach_income(gpd.read_file(BURDEN))
    sa2["k"] = sa2["SA22023_V1_00"].astype(str)
    # The burden layer carries no coordinates; take the population-weighted
    # centroids from the prepared layer that stage 1 wrote.
    prep = gpd.read_file(SA2_PREPARED, columns=["SA22023_V1_00", "lon", "lat"],
                         ignore_geometry=True)
    prep["k"] = prep["SA22023_V1_00"].astype(str)
    sa2 = sa2.merge(prep[["k", "lon", "lat"]], on="k", how="left")
    if sa2["lon"].isna().any():
        raise ValueError(f"{int(sa2['lon'].isna().sum())} SA2s have no centroid")
    return sa2


def main():
    sa2 = load_sa2()
    od = pd.read_parquet(OD)

    # Desire lines between population-weighted centroids, in NZTM.
    cen = gpd.GeoSeries(gpd.points_from_xy(sa2["lon"], sa2["lat"]),
                        crs=4326).to_crs(2193)
    cx = dict(zip(sa2["k"], cen.x))
    cy = dict(zip(sa2["k"], cen.y))
    od["res"] = od["residence_sa2"].astype(str)
    od["wrk"] = od["workplace_sa2"].astype(str)
    ok = od["res"].isin(cx) & od["wrk"].isin(cx)
    od = od[ok].copy()
    lines = gpd.GeoSeries([
        LineString([(cx[a], cy[a]), (cx[b], cy[b])])
        for a, b in zip(od["res"], od["wrk"])
    ], crs=2193)

    total_car = od["car_commuters"].sum()
    print(f"OD pairs: {len(od):,}   car commuters: {int(total_car):,}")

    def summarise(label, s, charged_mask, half_width):
        ch = od.loc[charged_mask]
        charged = ch["car_commuters"].sum()
        trapped = ch.loc[~ch["has_pt_alt"], "car_commuters"].sum()
        by_res = ch.groupby("res")["car_commuters"].sum()
        tr_res = (ch.loc[~ch["has_pt_alt"]].groupby("res")["car_commuters"].sum()
                  .reindex(by_res.index, fill_value=0))
        row = {
            "scenario": s, "definition": label, "half_width_m": half_width,
            "charged_commuters": int(charged),
            "charged_pct_of_all": round(100 * charged / total_car, 1),
            "trapped_commuters": int(trapped),
            "trapped_pct": round(100 * trapped / max(charged, 1), 1),
            "n_charged_SA2": int((by_res > 0).sum()),
        }
        # Manuscript CI of the trapped share (h = trapped / charged, w = charged);
        # positive = concentrated among the less disadvantaged.
        idx = sa2.set_index("k")
        for name, col in RANKS.items():
            with np.errstate(divide="ignore", invalid="ignore"):
                ci = concentration_index(tr_res / by_res,
                                         idx[col].reindex(by_res.index), by_res)
            row[f"CI_{name}"] = ci
            row[f"reading_{name}"] = equity_reading(ci)
        return row

    rows = []

    # ── CBD cordons: workplace inside, residence outside ─────────────────────
    for s in CBD_SCENARIOS:
        codes = scenario_sa2_codes(s)
        mask = od["wrk"].isin(codes) & ~od["res"].isin(codes)
        rows.append(summarise("cordon (data/scenarios)", s, mask, np.nan))

    # ── Motorway corridors: sensitivity across half-widths ──────────────────
    for s in MOTORWAY_SCENARIOS:
        for w in HALF_WIDTHS:
            if not CORRIDOR_FILES[w].exists():
                print(f"  {s} @ {w:,.0f} m: {CORRIDOR_FILES[w]} not built "
                      f"(run build_scenario_3c.py), skipped")
                continue
            poly = corridor_polygon(s, w)
            if poly.is_empty:
                print(f"  {s} @ {w:,.0f} m: corridor empty, skipped")
                continue
            mask = pd.Series(lines.intersects(poly).to_numpy(), index=od.index)
            rows.append(summarise("corridor buffer + 1a cordon (data/scenarios)", s, mask, w))

    out = pd.DataFrame(rows)
    SENS.mkdir(parents=True, exist_ok=True)
    out.to_csv(SENS / "scenario_geometry_sensitivity.csv", index=False)

    show = ["scenario", "half_width_m", "charged_commuters", "charged_pct_of_all",
            "trapped_commuters", "trapped_pct", "CI_nzdep", "CI_income_eq", "n_charged_SA2"]
    print("\n── Scenario burden from authoritative geometry ──")
    print(out[show].to_string(index=False))

    headline = out[out["half_width_m"].isna() | (out["half_width_m"] == STORED_HALF_WIDTH)]
    headline.to_csv(SENS / "scenario_geometry_headline.csv", index=False)
    print(f"\n── Headline (cordons + {STORED_HALF_WIDTH:,.0f} m corridor) ──")
    print(headline[show].to_string(index=False))
    print(f"\nWritten: {SENS/'scenario_geometry_sensitivity.csv'}")
    print(f"Written: {SENS/'scenario_geometry_headline.csv'}")


if __name__ == "__main__":
    main()
