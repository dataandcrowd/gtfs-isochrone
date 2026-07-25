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

Classification rules follow the manuscript (section 3.3):
    CBD cordons (1a, 1c, 2c) -- workplace inside the cordon, residence outside.
    Motorways  (3b, 3c, 3e)  -- residence->workplace desire line intersects the
                                corridor polygon.

Buffer sensitivity
------------------
The stored motorway polygons are 2 km buffers of a centreline (layer names
scenario_3?_2km). For a buffer of a line, buffer(r).buffer(d) == buffer(r + d),
so re-buffering the stored polygon by (w - 2000) recovers the same corridor at
half-width w exactly, without needing to recover the centreline.

Input : data/scenarios/scenario_*.gpkg
        outputs/intermediate/od_pairs_classified.parquet   (for car_commuters, has_pt_alt)
        outputs/burden_by_sa2_final.gpkg      (access_45min, pop, NZDep2023)
Output: outputs/scenario_geometry_sensitivity.csv
        outputs/scenario_geometry_headline.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import attach_income, ci_population_weighted, equity_reading  # noqa: E402

DATA_SCEN = Path("data") / "scenarios"
OUTPUT    = Path("outputs")
BURDEN    = OUTPUT / "burden_by_sa2_final.gpkg"
SA2_PREPARED = Path("data") / "sa2" / "sa2_prepared.gpkg"
OD        = OUTPUT / "intermediate" / "od_pairs_classified.parquet"

CBD_SCENARIOS      = ["1a", "1c", "2c"]
MOTORWAY_SCENARIOS = ["3b", "3c", "3e"]
STORED_HALF_WIDTH  = 2000.0                      # metres, per the layer names
HALF_WIDTHS        = [250.0, 500.0, 1000.0, 2000.0, 3000.0]

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


def scenario_sa2_codes(s):
    """SA2 codes making up a CBD cordon, from the scenario file."""
    g = gpd.read_file(DATA_SCEN / f"scenario_{s}.gpkg")
    col = next(c for c in g.columns if c.startswith("SA22") and c.endswith("V1_00"))
    return set(g[col].astype(str))


def corridor_polygon(s, half_width):
    """Motorway corridor at an arbitrary half-width, from the stored 2 km buffer."""
    poly = gpd.read_file(DATA_SCEN / f"scenario_{s}.gpkg").to_crs(2193).geometry.union_all()
    delta = half_width - STORED_HALF_WIDTH
    return poly if delta == 0 else poly.buffer(delta)


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
        origins = sa2[sa2["k"].isin(by_res[by_res > 0].index)]
        row = {
            "scenario": s, "definition": label, "half_width_m": half_width,
            "charged_commuters": int(charged),
            "charged_pct_of_all": round(100 * charged / total_car, 1),
            "trapped_commuters": int(trapped),
            "trapped_pct": round(100 * trapped / max(charged, 1), 1),
            "n_charged_SA2": int(len(origins)),
        }
        for name, col in RANKS.items():
            ci = ci_population_weighted(origins["access_45min"], origins[col], origins["pop"])
            row[f"CI_{name}"] = ci
            row[f"reading_{name}"] = equity_reading(ci)
        return row

    rows = []

    # ── CBD cordons ─────────────────────────────────────────────────────────
    # 1a and 1c are single cordons: charged when the workplace is inside and
    # the residence outside.
    #
    # 2c is the "isthmus DOUBLE cordon" (see Figure 4): scenario_2c.gpkg holds
    # both rings — its inner 21 SA2s are exactly the 1c cordon, plus 38
    # outer-ring SA2s across Grey Lynn, Ponsonby, Mount Eden, Epsom and
    # Remuera. A commuter pays on crossing EITHER boundary, so a trip from the
    # outer ring into the city centre is charged even though both endpoints
    # sit inside the outer cordon. Treating 2c as one merged cordon would
    # wrongly class those trips as intra-cordon and drop them.
    inner_2c = scenario_sa2_codes("2c") & scenario_sa2_codes("1c")

    for s in CBD_SCENARIOS:
        codes = scenario_sa2_codes(s)
        mask = od["wrk"].isin(codes) & ~od["res"].isin(codes)
        if s == "2c":
            if inner_2c != scenario_sa2_codes("1c"):
                raise ValueError("2c does not contain the full 1c inner cordon")
            crosses_inner = od["wrk"].isin(inner_2c) & ~od["res"].isin(inner_2c)
            mask = mask | crosses_inner
            label = "double cordon (data/scenarios)"
        else:
            label = "cordon (data/scenarios)"
        rows.append(summarise(label, s, mask, np.nan))

    # ── Motorway corridors: sensitivity across half-widths ──────────────────
    for s in MOTORWAY_SCENARIOS:
        for w in HALF_WIDTHS:
            poly = corridor_polygon(s, w)
            if poly.is_empty:
                print(f"  {s} @ {w:,.0f} m: corridor empty, skipped")
                continue
            mask = pd.Series(lines.intersects(poly).to_numpy(), index=od.index)
            rows.append(summarise("motorway buffer (data/scenarios)", s, mask, w))

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT / "scenario_geometry_sensitivity.csv", index=False)

    show = ["scenario", "half_width_m", "charged_commuters", "charged_pct_of_all",
            "trapped_commuters", "trapped_pct", "CI_nzdep", "CI_income_eq", "n_charged_SA2"]
    print("\n── Scenario burden from authoritative geometry ──")
    print(out[show].to_string(index=False))

    headline = out[out["half_width_m"].isna() | (out["half_width_m"] == STORED_HALF_WIDTH)]
    headline.to_csv(OUTPUT / "scenario_geometry_headline.csv", index=False)
    print("\n── Headline (cordons + stored 2 km buffers) ──")
    print(headline[show].to_string(index=False))
    print(f"\nWritten: {OUTPUT/'scenario_geometry_sensitivity.csv'}")
    print(f"Written: {OUTPUT/'scenario_geometry_headline.csv'}")


if __name__ == "__main__":
    main()
