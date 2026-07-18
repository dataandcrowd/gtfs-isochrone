"""
Stage 4c: Origin-destination commute classification and OD-based equity
- Loads the 2023 Census journey-to-work table (SA2 of usual residence x
  SA2 of workplace, with the main-means-of-travel-to-work breakdown).
- Reconstructs each TOUC scenario's charged SA2 set from the burden_* columns
  written by stage 4, plus the dissolved corridor footprint for the motorway
  scenarios.
- Flags every commute OD pair as charged or not, per scenario:
    CBD scenarios (1a, 1c, 2c)
        charged when the workplace SA2 lies inside the cordon AND the
        residence SA2 lies outside it.
    Motorway scenarios (3b, 3c, 3e)
        charged when the straight residence->workplace desire line intersects
        the dissolved motorway-corridor footprint. This approximates "the
        peak-hour route crosses a priced motorway segment"; the exact test
        needs car route geometries, which the pipeline does not produce.
- A "viable public-transit alternative" is decided per OD pair, not by a
  residence-level proxy: the residence->workplace transit travel time is read
  from the stage-2 travel-time matrix. A charged commuter is a "trapped payer"
  when that trip has no transit option within VIABLE_PT_MINUTES.
- Burden is assigned per OD pair and aggregated as a count of car commuters:
    no_charge                -- the OD pair does not cross the priced corridor
    pays_with_alternative    -- charged, the trip is transit-feasible
    pays_without_alternative -- charged, the trip has no viable transit option
- Spatial autocorrelation diagnostics:
    Global Moran's I (queen contiguity) on access_45min and trapped commuters
    per scenario.
    Local Moran's I (LISA) identifies HH/HL/LH/LL clusters at p < 0.05.
- Outputs:
    outputs/od_pairs_classified.parquet  -- one row per OD pair
    outputs/od_charged_by_scenario.csv   -- one row per residence SA2 x scenario
    outputs/od_equity_summary.csv        -- per-scenario charge / trapped / CI
    outputs/od_burden_crosstab.csv       -- car commuters by NZDep decile
    outputs/od_morans_i.csv             -- global Moran's I results
    outputs/od_lisa_summary.csv         -- LISA cluster counts
    outputs/od_classification.gpkg       -- SA2 polygons + per-scenario columns
"""

import sys
from pathlib import Path

from functools import reduce

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from esda.moran import Moran, Moran_Local
from libpysal.weights import Queen

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

DATA        = Path("data")
DATA_CENSUS = DATA / "census"
OUTPUT      = Path("outputs")
DATA_SA2    = Path("data") / "sa2"

COMMUTE_CSV = DATA_CENSUS / "2023-census-main-means-of-travel-to-work-by-statistical-area.csv"
SA2_EQUITY  = DATA_SA2 / "sa2_equity.gpkg"
TT_PARQUET  = OUTPUT / "travel_time_matrix.parquet"

for _p, _hint in [
    (COMMUTE_CSV, "Download '2023 Census main means of travel to work by "
                  "Statistical Area 2' (table 121988) from "
                  "https://datafinder.stats.govt.nz/."),
    (SA2_EQUITY,  "Run stage4_equity.py first."),
    (TT_PARQUET,  "Run stage2_routing.py first."),
]:
    if not (_p.exists() and _p.stat().st_size > 0):
        raise FileNotFoundError(f"Missing input {_p}. {_hint}")

SCENARIOS          = ["1a", "1c", "2c", "3b", "3c", "3e"]
CBD_SCENARIOS      = {"1a", "1c", "2c"}
MOTORWAY_SCENARIOS = {"3b", "3c", "3e"}

BURDEN_CLASSES = ["no_charge", "pays_with_alternative", "pays_without_alternative"]

# Census journey-to-work column names (table 121988).
ORIGIN_COL = "SA22023_V1_00_usual_residence_address"
DEST_COL   = "SA22023_V1_00_workplace_address"
# Car-based travel modes (2023). A congestion charge falls on these trips;
# "passenger in a car" is included because the trip still occupies a charged
# vehicle, even though the passenger is not the fee payer.
CAR_COLS = [
    "2023_Drive_a_private_car_truck_or_van",
    "2023_Drive_a_company_car_truck_or_van",
    "2023_Passenger_in_a_car_truck_van_or_company_bus",
]
TOTAL_COL = "2023_Total_stated"

# Stats NZ confidentiality code: -999 means the count is suppressed, not zero.
SUPPRESSED = -999

# A commute has a "viable PT alternative" when it can be made by transit in at
# most this many minutes (peak 07:00-09:00 median, from the stage-2 matrix).
# Trips unreachable within the matrix's 60-minute ceiling never qualify.
VIABLE_PT_MINUTES = 45


def concentration_index(values, deprivation):
    """CI = (2 / mu) * Cov(values, fractional NZDep rank). Matches stage 4."""
    df = pd.DataFrame({"y": values, "rank": deprivation}).dropna()
    if len(df) < 2:
        return np.nan
    n = len(df)
    df["r_frac"] = df["rank"].rank(method="average") / n
    mu = df["y"].mean()
    if mu == 0:
        return np.nan
    cov = np.cov(df["y"], df["r_frac"], bias=True)[0, 1]
    return round(2 * cov / mu, 4)


# -- 4c.a  Load the equity layer and rebuild scenario footprints --------------
sa2 = safe_read_gpkg(SA2_EQUITY)
sa2["SA22023_V1_00"] = sa2["SA22023_V1_00"].astype(str)
sa2 = sa2.to_crs(epsg=2193)
valid_codes = set(sa2["SA22023_V1_00"])
print(f"Auckland SA2 units: {len(sa2)}")

# Charged SA2 set per scenario = SA2s that stage 4 did not label 'no_charge'.
scenario_sets = {}
for s in SCENARIOS:
    col = f"burden_{s}"
    if col not in sa2.columns:
        raise KeyError(f"{SA2_EQUITY.name} has no '{col}' column. Re-run stage4.")
    scenario_sets[s] = set(sa2.loc[sa2[col] != "no_charge", "SA22023_V1_00"])

# Dissolved corridor footprint for the motorway scenarios (NZTM, metres).
corridor_poly = {}
for s in MOTORWAY_SCENARIOS:
    charged = sa2[sa2["SA22023_V1_00"].isin(scenario_sets[s])]
    corridor_poly[s] = reduce(lambda a, b: a.union(b), charged.geometry)

# SA2 centroid lookup (population-weighted lon/lat from stage 1), in NZTM.
_cent = gpd.GeoSeries(
    gpd.points_from_xy(sa2["lon"], sa2["lat"]), crs="EPSG:4326"
).to_crs(epsg=2193)
cx = dict(zip(sa2["SA22023_V1_00"], _cent.x))
cy = dict(zip(sa2["SA22023_V1_00"], _cent.y))

# -- 4c.b  Load the stage-2 transit travel-time matrix ------------------------
tt = pd.read_parquet(TT_PARQUET)
if "travel_time_p50" not in tt.columns and "travel_time" in tt.columns:
    tt = tt.rename(columns={"travel_time": "travel_time_p50"})
tt["from_id"] = tt["from_id"].astype(str)
tt["to_id"]   = tt["to_id"].astype(str)
tt_lookup = tt.set_index(["from_id", "to_id"])["travel_time_p50"]
print(f"Travel-time matrix: {len(tt):,} OD pairs, "
      f"{tt['travel_time_p50'].notna().sum():,} transit-reachable within 60 min")

# -- 4c.c  Load the commute OD table ------------------------------------------
od = pd.read_csv(
    COMMUTE_CSV,
    encoding="utf-8-sig",
    dtype={ORIGIN_COL: str, DEST_COL: str},
)
print(f"\nCommute OD rows (nationwide): {len(od):,}")

# Suppressed cells (-999) are unknown small counts, not zeros: treat as 0.
for col in CAR_COLS + [TOTAL_COL]:
    od[col] = pd.to_numeric(od[col], errors="coerce")
    od.loc[od[col] == SUPPRESSED, col] = 0
    od[col] = od[col].fillna(0).clip(lower=0)

od["car_commuters"] = od[CAR_COLS].sum(axis=1)

# Restrict to intra-Auckland commutes: both endpoints must be Auckland SA2s
# (the cordons are in Auckland, and the motorway test needs both centroids).
n_before = len(od)
od = od[od[ORIGIN_COL].isin(valid_codes) & od[DEST_COL].isin(valid_codes)].copy()
print(f"Intra-Auckland OD pairs: {len(od):,} (dropped {n_before - len(od):,})")
print(f"Auckland car commuters (intra-region): {od['car_commuters'].sum():,.0f}")

# -- 4c.d  Per-OD-pair transit feasibility ------------------------------------
od["transit_time"] = pd.MultiIndex.from_arrays(
    [od[ORIGIN_COL], od[DEST_COL]]
).map(tt_lookup)
od["has_pt_alt"] = od["transit_time"].notna() & (
    od["transit_time"] <= VIABLE_PT_MINUTES
)
print(f"\nViable-PT-alternative threshold: {VIABLE_PT_MINUTES} min transit.")
for thr in (30, 45, 60):
    feasible = od.loc[od["transit_time"].notna() & (od["transit_time"] <= thr),
                      "car_commuters"].sum()
    print(f"  car commuters with a transit option <= {thr} min: "
          f"{100 * feasible / max(od['car_commuters'].sum(), 1):.1f}%")

# -- 4c.e  Classify each OD pair, then assign burden --------------------------
# CBD: workplace inside the cordon, residence outside it.
for s in CBD_SCENARIOS:
    cset = scenario_sets[s]
    od[f"charged_{s}"] = od[DEST_COL].isin(cset) & ~od[ORIGIN_COL].isin(cset)

# Motorway: the residence->workplace desire line intersects the corridor.
_o = np.column_stack([od[ORIGIN_COL].map(cx).to_numpy(),
                      od[ORIGIN_COL].map(cy).to_numpy()])
_d = np.column_stack([od[DEST_COL].map(cx).to_numpy(),
                      od[DEST_COL].map(cy).to_numpy()])
desire_lines = gpd.GeoSeries(
    shapely.linestrings(np.stack([_o, _d], axis=1)), crs="EPSG:2193"
)
for s in MOTORWAY_SCENARIOS:
    od[f"charged_{s}"] = desire_lines.intersects(corridor_poly[s]).to_numpy()

# Burden: charged trips split by whether the trip itself is transit-feasible.
_has_alt = od["has_pt_alt"].to_numpy()
for s in SCENARIOS:
    charged = od[f"charged_{s}"].to_numpy()
    od[f"burden_{s}"] = np.select(
        [~charged, charged & _has_alt, charged & ~_has_alt],
        BURDEN_CLASSES,
        default="no_charge",
    )

# -- 4c.f  Aggregate car commuters to the residence SA2 -----------------------
car_out = od.groupby(ORIGIN_COL)["car_commuters"].sum()
sa2["car_commuters_out"] = sa2["SA22023_V1_00"].map(car_out).fillna(0)

equity_rows, crosstab_rows = [], []
for s in SCENARIOS:
    piv = (
        od.pivot_table(index=ORIGIN_COL, columns=f"burden_{s}",
                       values="car_commuters", aggfunc="sum", fill_value=0)
        .reindex(columns=BURDEN_CLASSES, fill_value=0)
    )
    payer   = sa2["SA22023_V1_00"].map(piv["pays_with_alternative"]).fillna(0)
    trapped = sa2["SA22023_V1_00"].map(piv["pays_without_alternative"]).fillna(0)

    sa2[f"od_charged_commuters_{s}"] = (payer + trapped).round().astype(int)
    sa2[f"od_trapped_commuters_{s}"] = trapped.round().astype(int)
    sa2[f"od_charged_share_{s}"] = (
        ((payer + trapped) / sa2["car_commuters_out"]).fillna(0).round(4)
    )

    # Per-SA2 label: the burden class carrying the most of the SA2's car
    # commuters. Threshold-free; SA2s with no car outflow are 'no_charge'.
    uncharged = sa2["car_commuters_out"] - payer - trapped
    stacked = np.column_stack([trapped.to_numpy(), payer.to_numpy(),
                               uncharged.to_numpy()])
    label_order = ["pays_without_alternative", "pays_with_alternative", "no_charge"]
    sa2[f"od_burden_{s}"] = [label_order[i] for i in stacked.argmax(axis=1)]
    sa2.loc[sa2["car_commuters_out"] == 0, f"od_burden_{s}"] = "no_charge"

    # Burden x NZDep decile crosstab (car commuters).
    by_dec = sa2.groupby("NZDep_Decile").agg(
        charged_commuters=(f"od_charged_commuters_{s}", "sum"),
        trapped_commuters=(f"od_trapped_commuters_{s}", "sum"),
    )
    for dec, row in by_dec.iterrows():
        crosstab_rows.append({
            "scenario": s, "NZDep_Decile": int(dec),
            "charged_commuters": int(row["charged_commuters"]),
            "trapped_commuters": int(row["trapped_commuters"]),
        })

    charged_tot = int(payer.sum() + trapped.sum())
    trapped_tot = int(trapped.sum())
    deprived_trapped = int(
        sa2.loc[sa2["NZDep_Decile"].isin([8, 9, 10]),
                f"od_trapped_commuters_{s}"].sum()
    )
    equity_rows.append({
        "scenario": s,
        "car_commuters_total": int(car_out.sum()),
        "charged_commuters": charged_tot,
        "charged_pct": round(100 * charged_tot / max(car_out.sum(), 1), 1),
        "with_alternative_commuters": charged_tot - trapped_tot,
        "trapped_commuters": trapped_tot,
        "trapped_pct_of_charged": round(100 * trapped_tot / max(charged_tot, 1), 1),
        "trapped_deprived_share": round(
            100 * deprived_trapped / max(trapped_tot, 1), 1),
        "CI_charged": concentration_index(
            sa2[f"od_charged_commuters_{s}"], sa2["NZDep2023"]),
        "CI_trapped": concentration_index(
            sa2[f"od_trapped_commuters_{s}"], sa2["NZDep2023"]),
    })

equity_df = pd.DataFrame(equity_rows)
crosstab_df = pd.DataFrame(crosstab_rows)

# -- 4c.g  Report — answers to the two scenario research questions ------------
print("\n" + "=" * 78)
print("Q2  Who is charged, and do they have a viable PT alternative?")
print("=" * 78)
print(equity_df[["scenario", "charged_commuters", "charged_pct",
                 "with_alternative_commuters", "trapped_commuters",
                 "trapped_pct_of_charged"]].to_string(index=False))

print("\n" + "=" * 78)
print("Q3  Which scenario concentrates the trapped-payer burden on "
      "deprived areas?")
print("=" * 78)
print(equity_df[["scenario", "trapped_commuters", "trapped_deprived_share",
                 "CI_trapped"]].to_string(index=False))
print("\n  trapped_deprived_share = % of trapped payers living in NZDep "
      "deciles 8-10")
print("  CI_trapped > 0 => trapped-payer burden concentrated in MORE deprived "
      "SA2s (regressive)")
_worst = equity_df.loc[equity_df["CI_trapped"].idxmax()]
print(f"  most regressive: scenario {_worst['scenario']} "
      f"(CI_trapped = {_worst['CI_trapped']})")

# -- 4c.h  Global Moran's I ---------------------------------------------------
w = Queen.from_dataframe(sa2, use_index=False)
w.transform = "R"
print(f"\nQueen contiguity weights: {w.n} SA2s, {w.n_components} component(s), "
      f"{w.islands} island(s)")

morans_rows = []

mi_access = Moran(sa2["access_45min"].fillna(0).to_numpy(), w)
morans_rows.append({
    "variable": "access_45min", "scenario": "-",
    "morans_I": round(mi_access.I, 4), "p_value": round(mi_access.p_sim, 4),
})
print(f"\nGlobal Moran's I  access_45min: {mi_access.I:.4f}  (p={mi_access.p_sim:.4f})")

print(f"\n{'scenario':>10}  {'Moran I':>8}  {'p':>6}")
for s in SCENARIOS:
    col = f"od_trapped_commuters_{s}"
    mi = Moran(sa2[col].fillna(0).to_numpy(), w)
    morans_rows.append({
        "variable": "od_trapped_commuters", "scenario": s,
        "morans_I": round(mi.I, 4), "p_value": round(mi.p_sim, 4),
    })
    print(f"{s:>10}  {mi.I:>8.4f}  {mi.p_sim:>6.4f}")

morans_df = pd.DataFrame(morans_rows)

# -- 4c.i  Local Moran's I (LISA) --------------------------------------------
lisa_counts = {}

lm_access = Moran_Local(sa2["access_45min"].fillna(0).to_numpy(), w, seed=42)
sig = lm_access.p_sim < 0.05
labels = np.full(len(sa2), "ns", dtype=object)
labels[(lm_access.q == 1) & sig] = "HH"
labels[(lm_access.q == 2) & sig] = "LH"
labels[(lm_access.q == 3) & sig] = "LL"
labels[(lm_access.q == 4) & sig] = "HL"
sa2["lisa_access45"] = labels
lisa_counts["access_45min"] = pd.Series(labels).value_counts().to_dict()

for s in SCENARIOS:
    col = f"od_trapped_commuters_{s}"
    lm = Moran_Local(sa2[col].fillna(0).to_numpy(), w, seed=42)
    sig = lm.p_sim < 0.05
    labels = np.full(len(sa2), "ns", dtype=object)
    labels[(lm.q == 1) & sig] = "HH"
    labels[(lm.q == 2) & sig] = "LH"
    labels[(lm.q == 3) & sig] = "LL"
    labels[(lm.q == 4) & sig] = "HL"
    sa2[f"lisa_trapped_{s}"] = labels
    lisa_counts[s] = pd.Series(labels).value_counts().to_dict()

lisa_df = pd.DataFrame(lisa_counts).T.reindex(columns=["HH", "HL", "LH", "LL", "ns"]).fillna(0).astype(int)
lisa_df.index.name = "variable_or_scenario"

print("\n" + "=" * 78)
print("LISA cluster counts (p < 0.05)")
print("=" * 78)
print(lisa_df.to_string())

for s in SCENARIOS:
    hh_sa2 = sa2[sa2[f"lisa_trapped_{s}"] == "HH"].nlargest(
        8, f"od_trapped_commuters_{s}"
    )
    if len(hh_sa2) > 0:
        print(f"\nTrapped-payer hotspots (scenario {s}, HH, top {len(hh_sa2)}):")
        for _, row in hh_sa2.iterrows():
            print(f"  {row['SA22026_V1_00_NAME']:40s}  {int(row[f'od_trapped_commuters_{s}']):>6,}")

# -- 4c.j  Write outputs ------------------------------------------------------
od_out = od.rename(columns={ORIGIN_COL: "residence_sa2", DEST_COL: "workplace_sa2"})
od_cols = (
    ["residence_sa2", "workplace_sa2", "car_commuters", TOTAL_COL,
     "transit_time", "has_pt_alt"]
    + [f"charged_{s}" for s in SCENARIOS]
)
od_out[od_cols].to_parquet(OUTPUT / "od_pairs_classified.parquet", index=False)

long_rows = []
for s in SCENARIOS:
    long_rows.append(pd.DataFrame({
        "residence_sa2": sa2["SA22023_V1_00"],
        "NZDep_Decile": sa2["NZDep_Decile"],
        "scenario": s,
        "car_commuters_out": sa2["car_commuters_out"],
        "od_charged_commuters": sa2[f"od_charged_commuters_{s}"],
        "od_trapped_commuters": sa2[f"od_trapped_commuters_{s}"],
        "od_charged_share": sa2[f"od_charged_share_{s}"],
        "od_burden": sa2[f"od_burden_{s}"],
    }))
pd.concat(long_rows, ignore_index=True).to_csv(
    OUTPUT / "od_charged_by_scenario.csv", index=False)
equity_df.to_csv(OUTPUT / "od_equity_summary.csv", index=False)
crosstab_df.to_csv(OUTPUT / "od_burden_crosstab.csv", index=False)
morans_df.to_csv(OUTPUT / "od_morans_i.csv", index=False)
lisa_df.to_csv(OUTPUT / "od_lisa_summary.csv")
od_gpkg_path = safe_to_gpkg(sa2, OUTPUT / "od_classification.gpkg")

print("\nOutputs written:")
for name in ("od_pairs_classified.parquet", "od_charged_by_scenario.csv",
             "od_equity_summary.csv", "od_burden_crosstab.csv",
             "od_morans_i.csv", "od_lisa_summary.csv"):
    print(f"  {name}")
print(f"  {od_gpkg_path.name}")
print("\nStage 4c complete.")