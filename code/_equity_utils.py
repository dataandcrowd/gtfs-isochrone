"""
Shared equity-metric helpers used by stage4d (Table 2) and stage4e (robustness).

Kept in one place so the NZDep-ranked and income-ranked versions of Table 2 are
guaranteed to be the same calculation with a different ranking variable, rather
than two copies that can drift apart.
"""

import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

INCOME_ZIP = Path("data") / "income" / (
    "statsnz-2023-census-totals-by-topic-for-households-by-statistical-ar-GPKG.zip"
)
INCOME_COL = "VAR_4_225"   # 2023 median total household income ($), households
HHSIZE_COL = "VAR_4_117"   # 2023 mean number of usual residents in household
SUPPRESSED = -999          # Stats NZ confidentialised / not-available code

# Equivalisation scales. Raw household income is not comparable across SA2s
# because household size varies (1.5 to 5.0 usual residents across Auckland),
# and large households cluster in South Auckland. Dividing by household size
# raised to ELASTICITY corrects for that:
#     0.0 = no correction        (raw household income)
#     0.5 = OECD square-root scale, moderate economies of scale  [default]
#     1.0 = strict per-capita, no economies of scale
# The modified-OECD scale is not usable here: it needs the adult/child split,
# and this table only publishes a mean household size per SA2.
EQUIV_ELASTICITY = {"sqrt": 0.5, "percap": 1.0}


def equity_reading(ci):
    """Magnitude band (manuscript Methods, after Vallejo-Torres et al. 2014).

    |CI| < 0.05 neutral, 0.05-0.10 mild, 0.10-0.20 moderate, > 0.20 strong.
    The direction follows the manuscript sign convention (see
    concentration_index): positive = concentrated among the less
    disadvantaged, negative = among the more disadvantaged. The bands describe
    one index and are not used to rank schemes.
    """
    if pd.isna(ci):
        return "n/a"
    a = abs(ci)
    band = ("Neutral" if a < 0.05 else
            "Mild" if a < 0.10 else
            "Moderate" if a < 0.20 else "Strong")
    if band == "Neutral":
        return band
    side = "less" if ci > 0 else "more"
    return f"{band}, towards {side} disadvantaged"


def concentration_index(values, disadvantage, weights):
    """Weighted Concentration Index, exactly as defined in the manuscript.

        CI = (2 / mu) * sum_i w_i (h_i - mu)(r_i - r_bar)

    w_i are the weights normalised to sum to one, mu the weighted mean of h,
    and r_i the fractional weighted rank of SA2 i with SA2s ordered from the
    MOST to the LEAST disadvantaged; tied scores share the mean rank of their
    group (Clarke & Van Ourti 2010).

    `disadvantage` must INCREASE with disadvantage (NZDep2023, or negated
    income). Sign: POSITIVE = h concentrated among the LESS disadvantaged,
    NEGATIVE = among the MORE disadvantaged. Baseline (h = access_45min,
    w = population, 497 SA2s) gives +0.040.

    FIX 2026-11-14: replaces ci_population_weighted, which ranked least -> most
    disadvantaged (opposite sign) and did not pool ties.
    """
    df = pd.DataFrame({"h": values, "d": disadvantage, "w": weights})
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    df = df[df["w"] > 0].sort_values("d", ascending=False, kind="mergesort")
    if len(df) < 2:
        return np.nan
    wn = df["w"] / df["w"].sum()
    end = wn.cumsum()
    start = end - wn
    r = (start.groupby(df["d"]).transform("min")
         + end.groupby(df["d"]).transform("max")) / 2
    mu = np.average(df["h"], weights=wn)
    if mu == 0:
        return np.nan
    cov = np.average((df["h"] - mu) * (r - np.average(r, weights=wn)), weights=wn)
    return round(2 * cov / mu, 4)


def scheme_cis(car, charged, trapped, disadvantage):
    """The three per-scheme CIs of the manuscript (RQ2), each weighted by its
    own denominator:
        CI_charged_share  h = charged / car commuters,   w = car commuters
        CI_trapped_share  h = trapped / charged,         w = charged
        CI_trapped_all    h = trapped / car commuters,   w = car commuters
    """
    car, charged, trapped = (pd.Series(x, dtype=float) for x in (car, charged, trapped))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "CI_charged_share": concentration_index(charged / car, disadvantage, car),
            "CI_trapped_share": concentration_index(trapped / charged, disadvantage, charged),
            "CI_trapped_all":   concentration_index(trapped / car, disadvantage, car),
        }


# Bivariate LISA quadrants (esda Moran_Local_BV.q) for x = trapped share and
# y = disadvantage of the neighbours (spatial lag).
BV_LABELS = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}
BV_DESCRIPTIONS = {
    "HH": "High trapped share, deprived neighbours",
    "HL": "High trapped share, affluent neighbours",
    "LH": "Low trapped share, deprived neighbours",
    "LL": "Low trapped share, affluent neighbours",
    "ns": "Not significant",
    "none": "No charged commuters",
}


def trapped_share_spatial(sa2, charged, trapped, disadvantage,
                          permutations=999, alpha=0.05, seed=42):
    """Spatial statistics of the trapped share, as in the manuscript Methods.

    * Global Moran's I of the trapped share (trapped / charged), queen
      contiguity, row-standardised, `permutations` permutations.
    * Bivariate local Moran (Anselin et al.): x = each SA2's trapped share,
      spatial lag of y = mean disadvantage (NZDep2023) of its neighbours.
      Significant SA2s (p < alpha) are labelled HH / HL / LH / LL.

    The trapped share is undefined where an SA2 sends no charged commuter, so
    both statistics use the SA2s with >= 1 charged commuter and a disadvantage
    score; SA2s left with no neighbour inside that subset are dropped too
    (an island has no spatial lag). Excluded SA2s are labelled 'none'.

    Returns (summary dict, labels Series aligned to sa2.index).
    """
    from esda.moran import Moran, Moran_Local_BV
    from libpysal.weights import Queen, w_subset

    sa2 = sa2.reset_index(drop=True)
    ch = np.asarray(charged, dtype=float)
    tr = np.asarray(trapped, dtype=float)
    dep = np.asarray(disadvantage, dtype=float)
    w_full = Queen.from_dataframe(sa2, use_index=False, silence_warnings=True)

    keep = [i for i in range(len(sa2)) if ch[i] > 0 and not np.isnan(dep[i])]
    dropped_islands = 0
    while True:
        ws = w_subset(w_full, keep, silence_warnings=True)
        islands = set(ws.islands)
        if not islands:
            break
        dropped_islands += len(islands)
        keep = [i for i in keep if i not in islands]
    ws.transform = "r"

    x = tr[keep] / ch[keep]
    y = dep[keep]
    np.random.seed(seed)
    mi = Moran(x, ws, permutations=permutations)
    bv = Moran_Local_BV(x, y, ws, permutations=permutations, seed=seed)

    labels = np.full(len(sa2), "none", dtype=object)
    sub = np.full(len(keep), "ns", dtype=object)
    sig = bv.p_sim < alpha
    for q, lab in BV_LABELS.items():
        sub[(bv.q == q) & sig] = lab
    labels[keep] = sub

    summary = {
        "moran_I": round(float(mi.I), 3),
        "moran_p": round(float(mi.p_sim), 3),
        "n_moran": len(keep),
        "n_islands_dropped": dropped_islands,
    }
    for lab in ("HH", "HL", "LH", "LL"):
        summary[f"n_{lab}"] = int((labels == lab).sum())
    return summary, pd.Series(labels)


def load_median_income():
    """Median household income and mean household size per SA2.

    Read from the Stats NZ GPKG inside the zip. Returns a DataFrame with
    SA22023_V1_00 (str), median_hh_income and avg_hh_size (float, NaN where
    Stats NZ suppressed the cell).
    """
    if not INCOME_ZIP.exists():
        raise FileNotFoundError(f"No census income archive at {INCOME_ZIP}")
    with zipfile.ZipFile(INCOME_ZIP) as zf:
        inner = [n for n in zf.namelist() if n.endswith(".gpkg")]
    if not inner:
        raise FileNotFoundError(f"No .gpkg inside {INCOME_ZIP.name}")

    # GDAL reads straight out of the archive via its /vsizip/ handler.
    inc = gpd.read_file(
        f"/vsizip/{INCOME_ZIP}/{inner[0]}",
        columns=["SA22023_V1_00", INCOME_COL, HHSIZE_COL],
        ignore_geometry=True,
    ).rename(columns={INCOME_COL: "median_hh_income",
                      HHSIZE_COL: "avg_hh_size"})

    inc["SA22023_V1_00"] = inc["SA22023_V1_00"].astype(str)
    for c in ("median_hh_income", "avg_hh_size"):
        inc[c] = inc[c].replace(SUPPRESSED, np.nan)
    # A zero or negative household size would blow up the equivalisation.
    inc.loc[inc["avg_hh_size"] <= 0, "avg_hh_size"] = np.nan
    return inc


def attach_income(sa2):
    """Join median income onto an SA2 layer and derive the disadvantage columns.

    Adds:
        median_hh_income   — $ per household, NaN where Stats NZ suppressed it
        avg_hh_size        — mean usual residents per household
        income_equiv_sqrt  — $ equivalised on the square-root scale
        income_equiv_percap— $ equivalised strictly per capita
        <base>_disadv      — negated income, so higher = more disadvantaged
                             (same direction as NZDep2023)
        <base>_decile      — 1..10 with 10 = LOWEST income, matching the
                             NZDep_Decile convention (10 = most deprived).
                             Like NZDep_Decile (stage1 line ~176) these are qcut
                             over the Auckland SA2s only, not national deciles,
                             so all the decile scales are directly comparable.
    for <base> in income, income_equiv_sqrt, income_equiv_percap.
    """
    sa2 = sa2.copy()
    sa2["SA22023_V1_00"] = sa2["SA22023_V1_00"].astype(str)

    n_before = len(sa2)
    sa2 = sa2.merge(load_median_income(), on="SA22023_V1_00", how="left")
    if len(sa2) != n_before:
        raise ValueError("income join changed row count — duplicate SA2 codes?")

    for name, elasticity in EQUIV_ELASTICITY.items():
        sa2[f"income_equiv_{name}"] = (
            sa2["median_hh_income"] / sa2["avg_hh_size"] ** elasticity
        )

    for base in ("income", "income_equiv_sqrt", "income_equiv_percap"):
        src = "median_hh_income" if base == "income" else base
        sa2[f"{base}_disadv"] = -sa2[src]
        sa2[f"{base}_decile"] = pd.qcut(
            sa2[f"{base}_disadv"], 10, labels=range(1, 11)
        ).astype(float)
    return sa2
