"""
Stage 4c: Origin-destination commute classification
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
- Burden is then assigned per OD pair and aggregated as a count of car
  commuters (people), so no arbitrary per-SA2 share threshold is needed:
    no_charge                -- the OD pair does not cross the priced corridor
    pays_with_alternative    -- charged, residence SA2 has 45-min job access
                                at or above the Q75 viable-alternative bar
    pays_without_alternative -- charged, residence SA2 below that bar
- Outputs:
    outputs/od_pairs_classified.parquet  -- one row per OD pair, charged flags
    outputs/od_charged_by_scenario.csv   -- one row per residence SA2 x scenario
    outputs/od_classification.gpkg       -- SA2 polygons + per-scenario columns
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

DATA   = Path("data")
OUTPUT = Path("outputs")

COMMUTE_CSV = DATA / "2023-census-main-means-of-travel-to-work-by-statistical-area.csv"
SA2_EQUITY  = OUTPUT / "sa2_equity.gpkg"

if not COMMUTE_CSV.exists():
    raise FileNotFoundError(
        f"No commute OD table at {COMMUTE_CSV}.\n"
        "Download '2023 Census main means of travel to work by Statistical "
        "Area 2' (table 121988) from https://datafinder.stats.govt.nz/ and "
        "save the CSV there."
    )
if not (SA2_EQUITY.exists() and SA2_EQUITY.stat().st_size > 0):
    raise FileNotFoundError(f"No equity layer at {SA2_EQUITY}. Run stage4 first.")

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


# ── 4c.a  Load the equity layer and rebuild scenario footprints ──────────────
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
    print(f"  scenario {s}: {len(scenario_sets[s])} SA2s in footprint")

# Dissolved corridor footprint for the motorway scenarios (NZTM, metres).
corridor_poly = {}
for s in MOTORWAY_SCENARIOS:
    charged = sa2[sa2["SA22023_V1_00"].isin(scenario_sets[s])]
    corridor_poly[s] = charged.dissolve().geometry.iloc[0]

# SA2 centroid lookup (population-weighted lon/lat from stage 1), in NZTM.
_cent = gpd.GeoSeries(
    gpd.points_from_xy(sa2["lon"], sa2["lat"]), crs="EPSG:4326"
).to_crs(epsg=2193)
cx = dict(zip(sa2["SA22023_V1_00"], _cent.x))
cy = dict(zip(sa2["SA22023_V1_00"], _cent.y))

# Viable-alternative threshold: Q75 of 45-min job accessibility (as in stage 4).
VIABLE_ALT_THRESHOLD = sa2["access_45min"].quantile(0.75)
residence_has_alt = dict(
    zip(sa2["SA22023_V1_00"], sa2["access_45min"] >= VIABLE_ALT_THRESHOLD)
)
print(f"Viable-alternative threshold (Q75 of 45-min access): "
      f"{VIABLE_ALT_THRESHOLD:,.0f} jobs")

# ── 4c.b  Load the commute OD table ──────────────────────────────────────────
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

# ── 4c.c  Classify each OD pair as charged / not, per scenario ───────────────
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

# ── 4c.d  Per-OD-pair burden class ───────────────────────────────────────────
# Charged pairs split by whether the residence SA2 clears the viable-PT bar.
_res_alt = od[ORIGIN_COL].map(residence_has_alt).fillna(False).to_numpy()
for s in SCENARIOS:
    charged = od[f"charged_{s}"].to_numpy()
    od[f"burden_{s}"] = np.select(
        [~charged, charged & _res_alt, charged & ~_res_alt],
        BURDEN_CLASSES,
        default="no_charge",
    )

# ── 4c.e  Aggregate car commuters to the residence SA2 ───────────────────────
car_out = od.groupby(ORIGIN_COL)["car_commuters"].sum()
sa2["car_commuters_out"] = sa2["SA22023_V1_00"].map(car_out).fillna(0)

region_summary = []
ci_charged = {}
for s in SCENARIOS:
    # Car commuters per residence SA2 x burden class.
    piv = (
        od.pivot_table(index=ORIGIN_COL, columns=f"burden_{s}",
                       values="car_commuters", aggfunc="sum", fill_value=0)
        .reindex(columns=BURDEN_CLASSES, fill_value=0)
    )
    payer   = sa2["SA22023_V1_00"].map(piv["pays_with_alternative"]).fillna(0)
    trapped = sa2["SA22023_V1_00"].map(piv["pays_without_alternative"]).fillna(0)

    sa2[f"od_charged_commuters_{s}"] = (payer + trapped).round().astype(int)
    sa2[f"od_trapped_commuters_{s}"] = trapped.round().astype(int)
    share = (payer + trapped) / sa2["car_commuters_out"]
    sa2[f"od_charged_share_{s}"]     = share.fillna(0).round(4)

    # Per-SA2 label: the burden class carrying the most of the SA2's car
    # commuters. Ties favour the heavier class; SA2s with no car outflow are
    # 'no_charge'. This is threshold-free -- it reads off the OD flows directly.
    uncharged = sa2["car_commuters_out"] - payer - trapped
    stacked = np.column_stack([trapped.to_numpy(),
                               payer.to_numpy(),
                               uncharged.to_numpy()])
    label_order = ["pays_without_alternative", "pays_with_alternative", "no_charge"]
    sa2[f"od_burden_{s}"] = [label_order[i] for i in stacked.argmax(axis=1)]
    sa2.loc[sa2["car_commuters_out"] == 0, f"od_burden_{s}"] = "no_charge"

    charged_mask = sa2[f"od_burden_{s}"] != "no_charge"
    ci_charged[s] = concentration_index(
        sa2.loc[charged_mask, "access_45min"],
        sa2.loc[charged_mask, "NZDep2023"],
    )
    region_summary.append({
        "scenario": s,
        "car_commuters_total": int(car_out.sum()),
        "charged_commuters": int(piv["pays_with_alternative"].sum()
                                 + piv["pays_without_alternative"].sum()),
        "trapped_commuters": int(piv["pays_without_alternative"].sum()),
        "charged_pct": round(100 * (piv["pays_with_alternative"].sum()
                              + piv["pays_without_alternative"].sum())
                             / max(car_out.sum(), 1), 1),
        "n_sa2_charged_od": int(charged_mask.sum()),
        "n_sa2_charged_stage4": int((sa2[f"burden_{s}"] != "no_charge").sum()),
        "ci_charged_45min": ci_charged[s],
    })

# ── 4c.f  Report ─────────────────────────────────────────────────────────────
summary_df = pd.DataFrame(region_summary)
print("\nOD-based charge exposure by scenario:")
print(summary_df.to_string(index=False))
print("\n  charged_commuters    = car commuters whose OD pair crosses the "
      "priced corridor")
print("  trapped_commuters    = charged car commuters whose residence SA2 is "
      "below the viable-PT bar")
print("  n_sa2_charged_od     = SA2s whose dominant burden class is a charged "
      "class (vs n_sa2_charged_stage4, the stage-4 residence-membership count)")

# ── 4c.g  Write outputs ──────────────────────────────────────────────────────
od_out = od.rename(columns={ORIGIN_COL: "residence_sa2", DEST_COL: "workplace_sa2"})
od_cols = (
    ["residence_sa2", "workplace_sa2", "car_commuters", TOTAL_COL]
    + [f"charged_{s}" for s in SCENARIOS]
)
od_pairs_path = OUTPUT / "od_pairs_classified.parquet"
od_out[od_cols].to_parquet(od_pairs_path, index=False)
print(f"\n  {od_pairs_path.name}  ({len(od_out):,} OD pairs)")

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
od_csv_path = OUTPUT / "od_charged_by_scenario.csv"
pd.concat(long_rows, ignore_index=True).to_csv(od_csv_path, index=False)
summary_df.to_csv(OUTPUT / "od_classification_summary.csv", index=False)
print(f"  {od_csv_path.name}")
print(f"  od_classification_summary.csv")

od_gpkg_path = safe_to_gpkg(sa2, OUTPUT / "od_classification.gpkg")
print(f"  {od_gpkg_path.name}")

print("\nStage 4c complete.")
