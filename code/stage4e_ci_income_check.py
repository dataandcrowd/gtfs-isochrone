"""
Stage 4e: Robustness check — recompute the Concentration Index using 2023 Census
median household income as the ranking variable, instead of NZDep2023.

Motivation: the headline CI in Table 2 (outputs/equity_summary_final.csv) ranks
SA2s by NZDep2023, a composite multi-domain deprivation index. A reviewer may
ask whether the result is an artefact of that particular index. This script
repeats the identical CI calculation with a single-domain, directly monetary
ranking variable and reports the difference.

Ranking variable
----------------
VAR_4_225 from "2023 Census totals by topic for households by SA2":
    Subject pop: Households in occupied private dwellings, Year: 2023,
    Measure: Median, Var1: Total household income (Median ($))
Value -999 is Stats NZ's suppressed/not-available code and is treated as NaN.

Sign convention (kept identical to stage4d)
-------------------------------------------
The rank axis runs from LEAST to MOST disadvantaged, so that
    CI < 0  ==  accessibility concentrated in the less-disadvantaged SA2s
               (regressive on the access-to-jobs axis).
For NZDep2023 that is ascending NZDep (higher score = more deprived).
For income that is DESCENDING income (lower income = more disadvantaged), so we
rank on -median_income.

Input : outputs/burden_by_sa2_final.gpkg          (from stage 4c)
        data/income/statsnz-2023-census-...-GPKG.zip
Output: outputs/ci_income_vs_nzdep.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import (  # noqa: E402
    attach_income,
    ci_population_weighted,
    equity_reading,
)

OUTPUT    = Path("outputs")
BURDEN    = OUTPUT / "burden_by_sa2_final.gpkg"
SCENARIOS = ["1a", "1c", "2c", "3b", "3c", "3e"]


def main():
    if not (BURDEN.exists() and BURDEN.stat().st_size > 0):
        raise FileNotFoundError(f"No burden layer at {BURDEN}. Run stage 4c first.")

    sa2 = attach_income(gpd.read_file(BURDEN))

    n_missing = int(sa2["median_hh_income"].isna().sum())
    print(f"SA2s: {len(sa2)}, median income suppressed/missing: {n_missing}")
    if n_missing:
        miss = sa2.loc[sa2["median_hh_income"].isna(),
                       ["SA22026_V1_00_NAME", "pop"]]
        print(f"  suppressed SA2s hold {int(miss['pop'].sum())} residents "
              f"({100 * miss['pop'].sum() / sa2['pop'].sum():.2f}% of population):")
        for _, r in miss.iterrows():
            print(f"    - {r['SA22026_V1_00_NAME']} (pop {int(r['pop'])})")

    # The four ranking variables, all on a "higher = more disadvantaged" axis.
    RANKS = {
        "nzdep":         "NZDep2023",
        "income":        "income_disadv",
        "income_eq":     "income_equiv_sqrt_disadv",
        "income_percap": "income_equiv_percap_disadv",
    }
    DECILES = {
        "nzdep":         "NZDep_Decile",
        "income":        "income_decile",
        "income_eq":     "income_equiv_sqrt_decile",
        "income_percap": "income_equiv_percap_decile",
    }

    print(f"\nMean household size: {sa2['avg_hh_size'].min():.1f} to "
          f"{sa2['avg_hh_size'].max():.1f} usual residents "
          f"(median {sa2['avg_hh_size'].median():.1f})")

    # How far does each income variant agree with NZDep as a ranking?
    print("\nSpearman rho against NZDep2023 (higher = closer agreement):")
    for label, col in RANKS.items():
        if label == "nzdep":
            continue
        ok = sa2[col].notna() & sa2["NZDep2023"].notna()
        rho, pv = spearmanr(sa2.loc[ok, "NZDep2023"], sa2.loc[ok, col])
        print(f"  {label:14s} rho = {rho:.3f}  (p = {pv:.2g}, n = {ok.sum()})")
    print(f"  (NZDep2023 missing for {int(sa2['NZDep2023'].isna().sum())} SA2s)")

    # Restrict every CI to the SA2s where ALL ranking variables exist, so the
    # variants differ only by ranking and never by sample.
    complete = sa2[list(RANKS.values())].notna().all(axis=1)
    print(f"\nCommon complete-case sample: {int(complete.sum())} of {len(sa2)} SA2s")

    rows = []
    for s_ in SCENARIOS:
        chg = f"od_charged_commuters_{s_}"
        charged = sa2[(sa2[chg] > 0) & complete]

        row = {"scenario": s_, "n_charged_SA2": int((sa2[chg] > 0).sum())}
        for label, col in RANKS.items():
            ci = ci_population_weighted(
                charged["access_45min"], charged[col], charged["pop"]
            )
            row[f"CI_{label}"] = ci
            row[f"reading_{label}"] = equity_reading(ci)
        row["diff_income_minus_nzdep"]    = round(row["CI_income"] - row["CI_nzdep"], 4)
        row["diff_income_eq_minus_nzdep"] = round(row["CI_income_eq"] - row["CI_nzdep"], 4)
        rows.append(row)

    out = pd.DataFrame(rows)
    dest = OUTPUT / "ci_income_vs_nzdep.csv"
    out.to_csv(dest, index=False)

    print("\nCI on 45-min job accessibility over charged-origin SA2s "
          "(population-weighted; negative = regressive):")
    print(out.to_string(index=False))
    print(f"\nWritten: {dest}")

    # ── Decile-level check ───────────────────────────────────────────────────
    # Table 2 also reports the share of trapped commuters living in the least
    # (d1-3) and most (d8-10) deprived deciles. Rebuild those shares on each
    # decile scale. All are qcut over the Auckland SA2s only with 10 = most
    # disadvantaged, so they are directly comparable to NZDep_Decile.
    dec_rows = []
    for s_ in SCENARIOS:
        trp = f"od_trapped_commuters_{s_}"
        total = sa2[trp].sum()
        row = {"scenario": s_, "trapped_commuters": int(total)}
        for label, dcol in DECILES.items():
            dec_ = sa2[dcol]
            row[f"d1_3_pct_{label}"] = round(
                100 * sa2.loc[dec_.between(1, 3), trp].sum() / max(total, 1), 1)
            row[f"d8_10_pct_{label}"] = round(
                100 * sa2.loc[dec_.between(8, 10), trp].sum() / max(total, 1), 1)
        dec_rows.append(row)

    dec = pd.DataFrame(dec_rows)
    dec_dest = OUTPUT / "trapped_decile_income_vs_nzdep.csv"
    dec.to_csv(dec_dest, index=False)
    print("\nShare of trapped commuters in the most-disadvantaged deciles "
          "(d8-10, %), by ranking variable:")
    print(dec[["scenario"] + [f"d8_10_pct_{k}" for k in DECILES]].to_string(index=False))
    print(f"\nWritten: {dec_dest}")

    # Headline agreement statistics, each income variant against NZDep.
    print("\nAgreement with the NZDep-ranked Table 2:")
    for label in RANKS:
        if label == "nzdep":
            continue
        d = out[f"CI_{label}"] - out["CI_nzdep"]
        same_sign = int((np.sign(out[f"CI_{label}"]) == np.sign(out["CI_nzdep"])).sum())
        same_band = int((out[f"reading_{label}"] == out["reading_nzdep"]).sum())
        print(f"  {label:14s} mean|diff| = {d.abs().mean():.4f}, "
              f"max|diff| = {d.abs().max():.4f}, "
              f"sign {same_sign}/{len(out)}, band {same_band}/{len(out)}")


if __name__ == "__main__":
    main()
