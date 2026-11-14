"""
Stage 4h: Sensitivity of the trapped-payer result to the viable-PT definition.

The headline classifies a charged car commute as "trapped" when the same
residence->workplace trip has no transit option within 45 min (stage 4c,
VIABLE_PT_MINUTES). This script re-runs that split under:

  A. absolute thresholds T = 20, 25, ..., 90 min
       viable  <=>  transit_time <= T
  B. a relative criterion, PT/car travel-time ratio k = 1.25, 1.5, 2.0
       viable  <=>  transit_time <= k * car_time

The charged set does not depend on the threshold, so neither does the reported
CI (stage 4d: access_45min over charged residences). Only the trapped split,
and therefore who is trapped, moves.

Data limits (no re-routing is done here):
  * The stage-2 transit matrix is capped at 60 min (MAX_TRAVEL_TIME). For
    T > 60 the transit time is right-censored. Trips not reachable within 60
    min could become viable, so for T > 60 the trapped count shown is an UPPER
    BOUND. In practice it is flat above 60 because nothing new is observed.
    A true 60-90 min test needs stage 2 re-run with max_time=90.
  * Car travel time is not stored. It is proxied as R5 driving-route distance
    (outputs/route_motorway_share.csv, route_km) divided by an assumed
    door-to-door AM-peak speed (CAR_SPEEDS_KMH). The ratio result is therefore
    shown for several speeds. Ratio-viable trips whose transit time would be
    above 60 min are also censored (counted as trapped).

Input : outputs/intermediate/od_pairs_classified.parquet  (stage 4c: OD,
                                                           transit_time, charged_*)
        outputs/intermediate/od_charged_by_scenario.csv   (NZDep decile)
        outputs/route_motorway_share.csv                  (car route_km)
Output: outputs/sensitivity_analysis/1_pt_threshold/
            sensitivity_threshold_absolute.csv
            sensitivity_threshold_ratio.csv
            fig_sensitivity_threshold.png / .pdf
"""

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("outputs")
SENS = OUT / "sensitivity_analysis" / "1_pt_threshold"
SENS.mkdir(parents=True, exist_ok=True)
SCENARIOS = ["1a", "1c", "3c"]
THRESHOLDS = list(range(20, 95, 5))
MATRIX_CAP = 60
RATIOS = [1.25, 1.5, 2.0]
CAR_SPEEDS_KMH = [25, 30, 40]

od = pd.read_parquet(OUT / "intermediate" / "od_pairs_classified.parquet")
od["residence_sa2"] = od["residence_sa2"].astype(str)
od["workplace_sa2"] = od["workplace_sa2"].astype(str)

dec = (pd.read_csv(OUT / "intermediate" / "od_charged_by_scenario.csv",
                   dtype={"residence_sa2": str})
       .drop_duplicates("residence_sa2").set_index("residence_sa2")["NZDep_Decile"])
od["decile"] = od["residence_sa2"].map(dec)

# charged_* flags come from stage 4c, which classifies from data/scenarios/
# via _scenario_utils (manuscript: 1a 18,996, 1c 37,005, 3c 66,027 charged).
_expected = {"1a": 18996, "1c": 37005, "3c": 66027}
for s, n in _expected.items():
    got = int(od.loc[od[f"charged_{s}"], "car_commuters"].sum())
    if got != n:
        raise ValueError(f"charged_{s} = {got:,}, manuscript {n:,}. Re-run stage 4c.")

car = pd.read_csv(OUT / "route_motorway_share.csv",
                  usecols=["residence_sa2", "workplace_sa2", "route_km"],
                  dtype={"residence_sa2": str, "workplace_sa2": str})
od = od.merge(car, on=["residence_sa2", "workplace_sa2"], how="left")

w = od["car_commuters"].to_numpy()
tt = od["transit_time"].to_numpy()
d = od["decile"].to_numpy()
low, high = (d >= 1) & (d <= 3), (d >= 8) & (d <= 10)

# Per-residence-SA2 inputs for the manuscript CIs (same helper as Table 2).
import sys  # noqa: E402
import geopandas as gpd  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import scheme_cis  # noqa: E402

_nzdep = (gpd.read_file(OUT / "burden_by_sa2_final.gpkg",
                        columns=["SA22023_V1_00", "NZDep2023"], ignore_geometry=True)
          .assign(k=lambda x: x["SA22023_V1_00"].astype(str)).set_index("k")["NZDep2023"])
_car_sa2 = od.groupby("residence_sa2")["car_commuters"].sum()
_dep_sa2 = _nzdep.reindex(_car_sa2.index)


def summarise(viable, label):
    rows = []
    for s in SCENARIOS:
        ch = od[f"charged_{s}"].to_numpy()
        tr = ch & ~viable
        C, T = w[ch].sum(), w[tr].sum()
        by = (pd.DataFrame({"r": od["residence_sa2"], "c": w * ch, "t": w * tr})
              .groupby("r")[["c", "t"]].sum().reindex(_car_sa2.index, fill_value=0))
        cis = scheme_cis(_car_sa2, by["c"], by["t"], _dep_sa2)
        rows.append({
            **label, "scenario": s,
            "charged": int(C), "trapped": int(T),
            "trapped_pct": round(100 * T / C, 1),
            # who the trapped are
            "trapped_d8_10_share": round(100 * w[tr & high].sum() / max(T, 1), 1),
            "trapped_d1_3_share": round(100 * w[tr & low].sum() / max(T, 1), 1),
            # deprivation gradient in the trapped RATE among charged
            "trapped_rate_d8_10": round(100 * w[tr & high].sum() / max(w[ch & high].sum(), 1), 1),
            "trapped_rate_d1_3": round(100 * w[tr & low].sum() / max(w[ch & low].sum(), 1), 1),
            # manuscript CIs (positive = concentrated among the less deprived)
            "CI_trapped_share": cis["CI_trapped_share"],
            "CI_trapped_all": cis["CI_trapped_all"],
        })
    return rows


# -- A. absolute thresholds ---------------------------------------------------
abs_rows = []
for T in THRESHOLDS:
    viable = ~np.isnan(tt) & (tt <= T)
    abs_rows += summarise(viable, {"threshold_min": T, "censored": T > MATRIX_CAP})
abs_df = pd.DataFrame(abs_rows)
abs_df["rate_gap_pp"] = abs_df["trapped_rate_d8_10"] - abs_df["trapped_rate_d1_3"]
abs_df.to_csv(SENS / "sensitivity_threshold_absolute.csv", index=False)

# Rank order of scenarios by trapped % at each threshold
rank = (abs_df.pivot(index="threshold_min", columns="scenario", values="trapped_pct")
        .rank(axis=1, ascending=False).astype(int))

# -- B. ratio criterion -------------------------------------------------------
km = od["route_km"].to_numpy()
ratio_rows = []
for v in CAR_SPEEDS_KMH:
    car_min = km / v * 60
    for k in RATIOS:
        viable = ~np.isnan(tt) & ~np.isnan(car_min) & (tt <= k * car_min)
        # share of charged commuters whose ratio test needs PT time > cap
        cens = ~np.isnan(car_min) & (k * car_min > MATRIX_CAP) & np.isnan(tt)
        rows = summarise(viable, {"car_speed_kmh": v, "ratio_k": k})
        for r in rows:
            ch = od[f"charged_{r['scenario']}"].to_numpy()
            r["censored_pct_of_charged"] = round(100 * w[ch & cens].sum() / w[ch].sum(), 1)
        ratio_rows += rows
ratio_df = pd.DataFrame(ratio_rows)
ratio_df["rate_gap_pp"] = ratio_df["trapped_rate_d8_10"] - ratio_df["trapped_rate_d1_3"]
ratio_df.to_csv(SENS / "sensitivity_threshold_ratio.csv", index=False)

# -- Report -------------------------------------------------------------------
pd.set_option("display.width", 200)
miss = w[np.isnan(km) & od[[f"charged_{s}" for s in SCENARIOS]].any(axis=1).to_numpy()].sum()
print(f"Charged commuters with no car route_km (excluded from ratio test as non-viable): {int(miss):,}")
print("\nA. Trapped % of charged, by absolute threshold (T>60 censored):")
print(abs_df.pivot(index="threshold_min", columns="scenario", values="trapped_pct").to_string())
print("\nScenario rank by trapped % (1 = highest):")
print(rank.to_string())
print("\nShare of trapped living in NZDep 8-10:")
print(abs_df.pivot(index="threshold_min", columns="scenario", values="trapped_d8_10_share").to_string())
print("\nTrapped-rate gap, NZDep 8-10 minus 1-3 (pp):")
print(abs_df.pivot(index="threshold_min", columns="scenario", values="rate_gap_pp").round(1).to_string())
print("\nB. Ratio criterion, trapped % of charged:")
print(ratio_df.pivot_table(index=["car_speed_kmh", "ratio_k"], columns="scenario",
                           values="trapped_pct").to_string())
print("\nB. Censored share of charged (needs PT > 60 min to test):")
print(ratio_df.pivot_table(index=["car_speed_kmh", "ratio_k"], columns="scenario",
                           values="censored_pct_of_charged").to_string())
print("\nB. Trapped-rate gap NZDep 8-10 minus 1-3 (pp):")
print(ratio_df.pivot_table(index=["car_speed_kmh", "ratio_k"], columns="scenario",
                           values="rate_gap_pp").round(1).to_string())

# -- Figure -------------------------------------------------------------------
# plotnine, Helvetica (falls back to Arial, its metric clone, where Helvetica
# is not installed). Only the observed range 20-60 min is plotted: above the
# 60-min matrix cap the lines would be flat by construction, not by data.
try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    from plotnine import (aes, annotate, element_blank, element_line,
                          element_rect, element_text, facet_wrap, geom_hline,
                          geom_line, geom_point, geom_text, geom_vline, ggplot,
                          labs, scale_color_manual, scale_x_continuous,
                          scale_y_continuous, theme, theme_minimal)

    _installed = {f.name for f in font_manager.fontManager.ttflist}
    FONT = next((f for f in ("Helvetica", "Helvetica Neue", "Arial") if f in _installed),
                "sans-serif")
    matplotlib.rcParams["font.family"] = FONT

    # Reference categorical slots 1-3 (validated all-pairs, light surface).
    PALETTE = {"1a": "#2a78d6", "1c": "#eb6834", "3c": "#1baf7a"}
    INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
    GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

    # Two panels on one y-scale: the trapped share of all charged commuters,
    # and of the charged commuters living in the most deprived SA2s.
    PANELS = {
        "trapped_pct": "A  Trapped share, all charged commuters (%)",
        "trapped_rate_d8_10": "B  Trapped share, charged commuters in NZDep 8–10 (%)",
    }
    plot_df = (abs_df[abs_df["threshold_min"] <= MATRIX_CAP]
               .melt(id_vars=["threshold_min", "scenario"],
                     value_vars=list(PANELS), var_name="metric")
               .assign(metric=lambda d: pd.Categorical(
                   d["metric"].map(PANELS), categories=list(PANELS.values()))))
    # End labels, nudged apart vertically where lines finish close together.
    ends = plot_df[plot_df["threshold_min"] == MATRIX_CAP].copy()
    ends["label_y"] = ends["value"]
    for _, g in ends.groupby("metric", observed=True):
        rng = plot_df.loc[plot_df["metric"] == g["metric"].iloc[0], "value"]
        gap = 0.07 * (rng.max() - rng.min())
        prev = None
        for i in g.sort_values("value").index:
            if prev is not None and ends.at[i, "label_y"] - prev < gap:
                ends.at[i, "label_y"] = prev + gap
            prev = ends.at[i, "label_y"]
    p = (
        ggplot(plot_df, aes("threshold_min", "value", color="scenario"))
        + geom_vline(xintercept=45, color=MUTED, linetype="dashed", size=0.5)
        + geom_line(size=1.0)
        + geom_point(size=2.2, fill=SURFACE, stroke=0.8, shape="o")
        + geom_text(ends, aes(y="label_y", label="scenario"), ha="left", nudge_x=1.2,
                    size=8.5, family=FONT, fontweight="bold", show_legend=False)
        + facet_wrap("~metric", ncol=2)
        + scale_color_manual(values=PALETTE, name="Scenario")
        + scale_x_continuous(breaks=range(20, MATRIX_CAP + 1, 10),
                             limits=(18, MATRIX_CAP + 5))
        + scale_y_continuous(limits=(30, 100), breaks=range(30, 101, 10))
        + labs(x="Viable public-transport threshold (min)", y=None,
               caption="Dashed line: 45-min headline threshold. Transit matrix "
                       "is capped at 60 min, so longer thresholds are not observed.")
        + theme_minimal(base_family=FONT, base_size=9)
        + theme(
            figure_size=(9, 4.0),
            plot_background=element_rect(fill=SURFACE, color=SURFACE),
            panel_grid_major_x=element_blank(),
            panel_grid_minor=element_blank(),
            panel_grid_major_y=element_line(color=GRID, size=0.4),
            axis_line_x=element_line(color=AXIS, size=0.5),
            axis_text=element_text(color=MUTED, size=8),
            axis_title_x=element_text(color=INK2, size=9, margin={"t": 6}),
            axis_title_y=element_blank(),
            strip_text=element_text(color=INK, size=9, ha="left",
                                    fontweight="bold"),
            strip_background=element_blank(),
            legend_position="top",
            legend_title=element_text(color=INK2, size=8.5),
            legend_text=element_text(color=INK2, size=8.5),
            legend_key=element_blank(),
            plot_caption=element_text(color=MUTED, size=7.5, ha="left"),
            panel_spacing_x=0.04,
        )
    )
    out_png = SENS / "fig_sensitivity_threshold.png"
    p.save(out_png, dpi=300, verbose=False)
    p.save(out_png.with_suffix(".pdf"), verbose=False)
    print(f"\nFigure ({FONT}): {out_png} (+ .pdf)")
except ImportError as e:
    print(f"\nFigure skipped: {e}")
