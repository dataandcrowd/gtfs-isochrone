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
    """Signed-magnitude banding, matches paper Section 3.3."""
    if pd.isna(ci):
        return "n/a"
    a = abs(ci)
    band = ("neutral" if a < 0.05 else
            "mild"    if a < 0.10 else
            "moderate" if a < 0.20 else "strong")
    if band == "neutral":
        return "Neutral"
    adverb = {"mild": "Mildly", "moderate": "Moderately", "strong": "Strongly"}[band]
    direction = "regressive" if ci < 0 else "pro-poor"
    return f"{adverb} {direction}"


def ci_population_weighted(values, disadvantage, weights):
    """Population-weighted Concentration Index.

    CI = (2 / mu) * weighted Cov(values, fractional weighted disadvantage rank).

    `disadvantage` must INCREASE with disadvantage (ascending NZDep2023, or
    negated median income). NEGATIVE CI then means the value is concentrated in
    the less-disadvantaged SA2s — regressive on the access-to-jobs axis.
    """
    df = pd.DataFrame({"y": values, "r": disadvantage, "w": weights}).dropna()
    df = df[df["w"] > 0].sort_values("r")
    if len(df) < 2:
        return np.nan
    wn = df["w"] / df["w"].sum()
    rf = wn.cumsum() - 0.5 * wn                       # weighted fractional rank (midpoint)
    mu = np.average(df["y"], weights=df["w"])
    if mu == 0:
        return np.nan
    rbar = np.average(rf, weights=df["w"])
    cov = np.average((df["y"] - mu) * (rf - rbar), weights=df["w"])
    return round(2 * cov / mu, 4)


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
