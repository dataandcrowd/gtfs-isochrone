"""
Stage 4d: Regenerate outputs/equity_summary_final.csv (the source of Table 2).

Provenance note (A1): this table was previously produced by an uncommitted step,
so the column CI_charged_pw appeared nowhere in code/. This script commits that
step. The CI, decile-share, commuter-count and trapped-% columns reproduce the
existing equity_summary_final.csv exactly. moran_I reproduces to within ~0.003
(new vs committed: 1a 0.483/0.486, 1c 0.512/0.514, 2c 0.508/0.510,
3b 0.549/0.553, 3c 0.534/0.538, 3e 0.582/0.584) — a data-vintage difference
between gpkg snapshots. At two decimals 4 of 6 match; 1a (0.48 vs 0.49) and
3c (0.53 vs 0.54) differ by one in the last place. If regenerated on the current
gpkg, update the reported Moran's I range accordingly (new values span 0.48 to
0.58, vs 0.49 to 0.58 in the committed CSV).

The reported Concentration Index (column CI_charged_pw) is:
    population-weighted CI of 45-minute job ACCESSIBILITY (access_45min),
    computed over the residence SA2s that send >= 1 charged commuter,
    SA2s ranked by NZDep2023.
Sign convention: NEGATIVE = regressive on the access-to-jobs axis (accessibility
lower in more-deprived charged SA2s). This is the OPPOSITE convention from the
count-based CI_trapped diagnostic in stage4c (positive = regressive).

Input : outputs/burden_by_sa2_final.gpkg  (from stage 4c)
Output: outputs/equity_summary_final.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from esda.moran import Moran
from libpysal.weights import Queen

OUTPUT   = Path("outputs")
BURDEN   = OUTPUT / "burden_by_sa2_final.gpkg"
SCENARIOS = ["1a", "1c", "2c", "3b", "3c", "3e"]

# CI banding (matches paper Section 3.3): signed magnitude bands.
def equity_reading(ci):
    a = abs(ci)
    band = ("neutral" if a < 0.05 else
            "mild"    if a < 0.10 else
            "moderate" if a < 0.20 else "strong")
    if band == "neutral":
        return "Neutral"
    adverb = {"mild": "Mildly", "moderate": "Moderately", "strong": "Strongly"}[band]
    direction = "regressive" if ci < 0 else "pro-poor"
    return f"{adverb} {direction}"


def ci_population_weighted(values, deprivation, weights):
    """Population-weighted Concentration Index.

    CI = (2 / mu) * weighted Cov(values, fractional weighted NZDep rank).
    NEGATIVE = accessibility concentrated in less-deprived SA2s (regressive).
    """
    df = pd.DataFrame({"y": values, "r": deprivation, "w": weights}).dropna()
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


def main():
    if not (BURDEN.exists() and BURDEN.stat().st_size > 0):
        raise FileNotFoundError(f"No burden layer at {BURDEN}. Run stage 4c first.")
    sa2 = gpd.read_file(BURDEN)

    # Global Moran's I on the trapped-payer count (queen contiguity), per scenario.
    w = Queen.from_dataframe(sa2, use_index=False)
    w.transform = "r"

    rows = []
    for s in SCENARIOS:
        chg = f"od_charged_commuters_{s}"
        trp = f"od_trapped_commuters_{s}"
        charged_sa2 = sa2[sa2[chg] > 0]

        ci = ci_population_weighted(
            charged_sa2["access_45min"], charged_sa2["NZDep2023"], charged_sa2["pop"]
        )
        charged = int(sa2[chg].sum())
        trapped = int(sa2[trp].sum())
        dec = sa2["NZDep_Decile"]
        d13  = round(100 * sa2.loc[dec.between(1, 3), trp].sum() / max(trapped, 1), 1)
        d810 = round(100 * sa2.loc[dec.between(8, 10), trp].sum() / max(trapped, 1), 1)

        mi = Moran(sa2[trp].fillna(0).to_numpy(), w, permutations=999)

        rows.append({
            "scenario": s,
            "charged_commuters": charged,
            "trapped_commuters": trapped,
            "trapped_pct": round(100 * trapped / max(charged, 1), 1),
            "d1_3_pct": d13,
            "d8_10_pct": d810,
            "CI_charged_pw": ci,
            "equity_reading": equity_reading(ci),
            "moran_I": round(mi.I, 3),
            "moran_p": round(mi.p_sim, 3),
            "n_charged_SA2": int((sa2[chg] > 0).sum()),
        })

    out = pd.DataFrame(rows)
    dest = OUTPUT / "equity_summary_final.csv"
    out.to_csv(dest, index=False)
    print(out.to_string(index=False))
    print(f"\nWritten: {dest}")


if __name__ == "__main__":
    main()
