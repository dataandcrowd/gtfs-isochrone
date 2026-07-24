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
Every other column (commuter counts, trapped %, Moran's I) is independent of
the ranking variable and is identical in both tables by construction.

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
from esda.moran import Moran
from libpysal.weights import Queen

sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import (  # noqa: E402
    attach_income,
    ci_population_weighted,
    equity_reading,
)

OUTPUT   = Path("outputs")
BURDEN   = OUTPUT / "burden_by_sa2_final.gpkg"
SCENARIOS = ["1a", "1c", "2c", "3b", "3c", "3e"]

# Ranking variable -> (continuous disadvantage column, decile column, output file)
RANK_SPECS = {
    "nzdep":         ("NZDep2023", "NZDep_Decile",
                      "equity_summary_final.csv"),
    "income":        ("income_disadv", "income_decile",
                      "equity_summary_final_income.csv"),
    "income_eq":     ("income_equiv_sqrt_disadv", "income_equiv_sqrt_decile",
                      "equity_summary_final_income_eq.csv"),
    "income_percap": ("income_equiv_percap_disadv", "income_equiv_percap_decile",
                      "equity_summary_final_income_percap.csv"),
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

    # Global Moran's I on the trapped-payer count (queen contiguity), per scenario.
    w = Queen.from_dataframe(sa2, use_index=False)
    w.transform = "r"

    rows = []
    for s in SCENARIOS:
        chg = f"od_charged_commuters_{s}"
        trp = f"od_trapped_commuters_{s}"
        charged_sa2 = sa2[sa2[chg] > 0]

        ci = ci_population_weighted(
            charged_sa2["access_45min"], charged_sa2[rank_col], charged_sa2["pop"]
        )
        charged = int(sa2[chg].sum())
        trapped = int(sa2[trp].sum())
        dec = sa2[decile_col]
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
    dest = OUTPUT / out_name
    out.to_csv(dest, index=False)
    print(out.to_string(index=False))
    print(f"\nWritten: {dest}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rank", choices=list(RANK_SPECS), default="nzdep",
                    help="deprivation ranking variable (default: nzdep)")
    main(**vars(ap.parse_args()))
