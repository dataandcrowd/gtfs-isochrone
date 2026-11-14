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

Measures and sign convention (identical to stage4d / the manuscript)
--------------------------------------------------------------------
The baseline accessibility CI and the three per-scheme CIs (charged share,
trapped share of the charged, trapped share of all car commuters), each
weighted by its denominator. SA2s are ranked from MOST to LEAST disadvantaged,
so POSITIVE = concentrated among the less disadvantaged. Every ranking variable
is passed on a "higher = more disadvantaged" axis: NZDep2023 as is, income as
-median_income. (FIX 2026-11-14: previously the CI on accessibility over
charged-origin SA2s, with the opposite sign.)

Input : outputs/burden_by_sa2_final.gpkg          (from stage 4c)
        data/income/statsnz-2023-census-...-GPKG.zip
Output: outputs/sensitivity_analysis/3_deprivation_measure/
            ci_income_vs_nzdep.csv, trapped_decile_income_vs_nzdep.csv
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
    concentration_index,
    equity_reading,
    scheme_cis,
)

OUTPUT    = Path("outputs")
BURDEN    = OUTPUT / "burden_by_sa2_final.gpkg"
SENS      = OUTPUT / "sensitivity_analysis" / "3_deprivation_measure"
from _scenario_utils import SCENARIOS  # noqa: E402  (1a, 1c, 3c)


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

    # The manuscript's CIs (stage 4d / _equity_utils), one row per measure x
    # scheme plus the RQ1 baseline. Positive = concentrated among the less
    # disadvantaged.
    cc = sa2[complete]
    rows = []
    base = {"scenario": "baseline", "measure": "CI_baseline_access45"}
    for label, col in RANKS.items():
        ci = concentration_index(cc["access_45min"], cc[col], cc["pop"])
        base[f"CI_{label}"], base[f"reading_{label}"] = ci, equity_reading(ci)
    rows.append(base)
    for s_ in SCENARIOS:
        per_rank = {label: scheme_cis(cc["car_commuters_out"],
                                      cc[f"od_charged_commuters_{s_}"],
                                      cc[f"od_trapped_commuters_{s_}"], cc[col])
                    for label, col in RANKS.items()}
        for measure in ("CI_charged_share", "CI_trapped_share", "CI_trapped_all"):
            row = {"scenario": s_, "measure": measure}
            for label in RANKS:
                ci = per_rank[label][measure]
                row[f"CI_{label}"], row[f"reading_{label}"] = ci, equity_reading(ci)
            rows.append(row)

    out = pd.DataFrame(rows)
    out["diff_income_minus_nzdep"] = (out["CI_income"] - out["CI_nzdep"]).round(4)
    out["diff_income_eq_minus_nzdep"] = (out["CI_income_eq"] - out["CI_nzdep"]).round(4)
    SENS.mkdir(parents=True, exist_ok=True)
    dest = SENS / "ci_income_vs_nzdep.csv"
    out.to_csv(dest, index=False)

    print("\nManuscript CIs by ranking variable (complete-case sample; "
          "positive = concentrated among the less disadvantaged):")
    print(out[["scenario", "measure"] + [f"CI_{k}" for k in RANKS]].to_string(index=False))
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
    dec_dest = SENS / "trapped_decile_income_vs_nzdep.csv"
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
