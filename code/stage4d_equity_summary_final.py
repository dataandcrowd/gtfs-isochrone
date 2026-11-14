"""
Stage 4d: Regenerate outputs/equity_summary_final.csv (the source of Table 2).

FIX 2026-11-14: rebuilt to the measures defined in the manuscript Methods
(Nov 10 draft). The earlier CI_charged_pw (accessibility over charged-origin
SA2s, opposite sign) and the Moran's I on the trapped COUNT are gone.

Columns (one row per scheme, 1a / 1c / 3c):
    charged / trapped counts and %                  RQ2 headline numbers
    charged_rate_d1_3 / _d8_10                      % of the group's car commuters charged
    trapped_rate_d1_3 / _d8_10                      % of the group's charged who are trapped
    d1_3_pct / d8_10_pct                            % of all trapped living in the group
    CI_charged_share   h = charged / car commuters, w = car commuters
    CI_trapped_share   h = trapped / charged,       w = charged
    CI_trapped_all     h = trapped / car commuters, w = car commuters
    CI_baseline_access45  RQ1, h = access_45min, w = population (same every row)
    moran_I / moran_p  global Moran's I of the trapped share (queen, 999 perms)
    n_HH .. n_LL       bivariate local Moran clusters, trapped share x
                       neighbours' disadvantage, p < 0.05
CI sign (manuscript): SA2s ranked most -> least disadvantaged, so POSITIVE =
concentrated among the less disadvantaged, NEGATIVE = among the more
disadvantaged. Bands: <0.05 neutral, 0.05-0.10 mild, 0.10-0.20 moderate, >0.20
strong.

Ranking variable (--rank)
-------------------------
    nzdep  (default) — NZDep2023 score / NZDep_Decile. Produces the paper's
                       Table 2 at outputs/equity_summary_final.csv.
    income           — 2023 Census median household income, negated so the rank
                       axis still runs least- to most-disadvantaged. NOT
                       size-adjusted, so it misreads large households as
                       better off; kept only for comparison.
    income_eq        — the same income divided by sqrt(mean household size)
                       (OECD square-root equivalisation). This is the
                       defensible income-based ranking.
    income_percap    — divided by household size outright (no economies of
                       scale). Brackets income_eq from the other side.
Commuter counts, trapped % and Moran's I are independent of the ranking
variable. The CIs, decile rates and bivariate clusters use the chosen ranking
(its disadvantage column for the CI and the neighbour lag, its deciles for the
group rates).

Input : outputs/burden_by_sa2_final.gpkg  (from stage 4c)
        data/income/statsnz-2023-census-...-GPKG.zip   (--rank income only)
Output: outputs/equity_summary_final[_income].csv
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import (  # noqa: E402
    attach_income,
    concentration_index,
    equity_reading,
    scheme_cis,
    trapped_share_spatial,
)

OUTPUT   = Path("outputs")
BURDEN   = OUTPUT / "burden_by_sa2_final.gpkg"
from _scenario_utils import SCENARIOS  # noqa: E402  (1a, 1c, 3c)

# Ranking variable -> (continuous disadvantage column, decile column, output file)
# The NZDep table is the manuscript's Table 2 (outputs/); the income-ranked
# variants are robustness checks and go with the other sensitivity analyses.
_SENS = "sensitivity_analysis/3_deprivation_measure/"
RANK_SPECS = {
    "nzdep":         ("NZDep2023", "NZDep_Decile",
                      "equity_summary_final.csv"),
    "income":        ("income_disadv", "income_decile",
                      _SENS + "equity_summary_final_income.csv"),
    "income_eq":     ("income_equiv_sqrt_disadv", "income_equiv_sqrt_decile",
                      _SENS + "equity_summary_final_income_eq.csv"),
    "income_percap": ("income_equiv_percap_disadv", "income_equiv_percap_decile",
                      _SENS + "equity_summary_final_income_percap.csv"),
}


def main(rank="nzdep"):
    if not (BURDEN.exists() and BURDEN.stat().st_size > 0):
        raise FileNotFoundError(f"No burden layer at {BURDEN}. Run stage 4c first.")
    rank_col, decile_col, out_name = RANK_SPECS[rank]

    sa2 = gpd.read_file(BURDEN)
    if rank.startswith("income"):
        sa2 = attach_income(sa2)
        n_missing = int(sa2["median_hh_income"].isna().sum())
        print(f"Ranking by median household income; suppressed for {n_missing} "
              f"SA2s holding {int(sa2.loc[sa2['median_hh_income'].isna(), 'pop'].sum())} "
              f"residents ({100 * sa2.loc[sa2['median_hh_income'].isna(), 'pop'].sum() / sa2['pop'].sum():.2f}% "
              f"of population), excluded from the CI.")

    dep = sa2[rank_col]
    car = sa2["car_commuters_out"]
    dec = sa2[decile_col]
    lo, hi = dec.between(1, 3), dec.between(8, 10)

    # RQ1 baseline: CI of 45-min job accessibility, population-weighted, all
    # SA2s with a score (497 for NZDep2023). Manuscript: +0.040.
    ci_base = concentration_index(sa2["access_45min"], dep, sa2["pop"])
    n_base = int((sa2["pop"] > 0).mul(dep.notna()).sum())
    print(f"Baseline CI (access_45min, population-weighted, n={n_base}): {ci_base:+.4f}"
          f"  [{equity_reading(ci_base)}]")

    def pct(num, den):
        return round(100 * num / den, 1) if den > 0 else np.nan

    rows = []
    for s in SCENARIOS:
        ch = sa2[f"od_charged_commuters_{s}"]
        tr = sa2[f"od_trapped_commuters_{s}"]
        charged, trapped = int(ch.sum()), int(tr.sum())
        cis = scheme_cis(car, ch, tr, dep)
        spatial, _ = trapped_share_spatial(sa2, ch, tr, dep)

        rows.append({
            "scenario": s,
            "charged_commuters": charged,
            "charged_pct": pct(charged, car.sum()),
            "trapped_commuters": trapped,
            "trapped_pct": pct(trapped, charged),
            # Share of each group's car commuters who are charged, and share of
            # each group's charged commuters who are trapped (manuscript RQ2:
            # "20 per cent ... but only 7 per cent"; "60 ... over 90 out of 100").
            "charged_rate_d1_3": pct(ch[lo].sum(), car[lo].sum()),
            "charged_rate_d8_10": pct(ch[hi].sum(), car[hi].sum()),
            "trapped_rate_d1_3": pct(tr[lo].sum(), ch[lo].sum()),
            "trapped_rate_d8_10": pct(tr[hi].sum(), ch[hi].sum()),
            # Where the trapped live: share of all trapped in each group.
            "d1_3_pct": pct(tr[lo].sum(), trapped),
            "d8_10_pct": pct(tr[hi].sum(), trapped),
            **cis,
            **{k.replace("CI_", "reading_"): equity_reading(v) for k, v in cis.items()},
            "CI_baseline_access45": ci_base,
            **{k: spatial[k] for k in ("moran_I", "moran_p", "n_moran",
                                       "n_HH", "n_HL", "n_LH", "n_LL")},
            "n_charged_SA2": int((ch > 0).sum()),
        })

    out = pd.DataFrame(rows)
    dest = OUTPUT / out_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False)
    show = ["scenario", "charged_commuters", "charged_pct", "trapped_pct",
            "charged_rate_d1_3", "charged_rate_d8_10",
            "trapped_rate_d1_3", "trapped_rate_d8_10"]
    print(out[show].to_string(index=False))
    print()
    print(out[["scenario", "CI_charged_share", "CI_trapped_share", "CI_trapped_all",
               "reading_trapped_share"]].to_string(index=False))
    print()
    print(out[["scenario", "moran_I", "moran_p", "n_moran", "n_HH", "n_HL", "n_LH",
               "n_LL"]].to_string(index=False))
    print(f"\nWritten: {dest}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rank", choices=list(RANK_SPECS), default="nzdep",
                    help="deprivation ranking variable (default: nzdep)")
    main(**vars(ap.parse_args()))
