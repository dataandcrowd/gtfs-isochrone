"""
Stage 5: Visualisation and figure export

Figures produced (baseline scenario; scenario-specific figures are regenerated
once stage4 has real SCENARIO_SA2_SETS):

  fig1_accessibility_choropleth.png
      2x2 panel: (a) 45-min job accessibility, (b) NZDep 2023 decile,
      (c) bivariate accessibility-deprivation, (d) trapped-payer risk map
      (low access AND high deprivation).

  fig2_accessibility_by_deprivation.png
      Box plot of 45-min accessibility by NZDep decile, with scatter overlay
      and a LOWESS trend line.

  fig3_concentration_curve.png
      Lorenz-type concentration curve: cumulative share of accessibility on y,
      cumulative share of population (ranked by NZDep) on x. Deviation from
      the 45-degree line of equality equals half the Concentration Index.

  fig4_access_vs_deprivation_scatter.png
      Scatter of NZDep score vs 45-min accessibility with the most accessible
      and least accessible SA2s labelled.

  fig5_burden_by_scenario.png (only if SCENARIO_SA2_SETS is populated)
  fig6_ci_forest_plot.png      (only if CI_charged_sa2s values are finite)
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

OUTPUT = Path("outputs")
FIGS   = OUTPUT / "figures"; FIGS.mkdir(exist_ok=True)

SA2_PATH = OUTPUT / "sa2_equity.gpkg"
if not (SA2_PATH.exists() and SA2_PATH.stat().st_size > 0):
    raise FileNotFoundError(f"No equity file at {SA2_PATH}. Run stage4 first.")
print(f"Reading equity layer: {SA2_PATH.name}")
CI_CSV        = OUTPUT / "equity_summary.csv"
CROSSTAB_CSV  = OUTPUT / "burden_crosstab.csv"

sa2        = safe_read_gpkg(SA2_PATH)
ci_summary = pd.read_csv(CI_CSV)
crosstab   = pd.read_csv(CROSSTAB_CSV)

SCENARIOS = ["1a", "1c", "2c", "3b", "3c", "3e"]

PALETTE = {
    "pays_with_alternative":    "#1D9E75",
    "pays_without_alternative": "#D85A30",
    "no_charge":                "#D3D1C7",
}

SCENARIO_LABELS = {
    "1a": "1a, City centre cordon",
    "1c": "1c, City centre + fringe",
    "2c": "2c, Isthmus double cordon",
    "3b": "3b, Core motorways",
    "3c": "3c, Core motorways + CBD",
    "3e": "3e, Motorway hotspots",
}

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         10,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})

# ── Key Auckland suburb centroids for labelling (lon, lat) ───────────────────
LANDMARKS = {
    "CBD":        (174.765, -36.848),
    "Ponsonby":   (174.742, -36.857),
    "Newmarket":  (174.775, -36.869),
    "Mt Eden":    (174.754, -36.878),
    "Albany":     (174.698, -36.735),
    "Takapuna":   (174.772, -36.787),
    "Henderson":  (174.628, -36.875),
    "New Lynn":   (174.683, -36.908),
    "Onehunga":   (174.782, -36.925),
    "Otahuhu":    (174.841, -36.944),
    "Mangere":    (174.805, -36.968),
    "Otara":      (174.873, -36.961),
    "Manurewa":   (174.897, -37.024),
    "Papakura":   (174.943, -37.063),
}

def add_landmarks(ax, fontsize=6, which=None):
    """Overlay a small label + marker for each suburb on a map axis. Labels
    are drawn on an opaque white pill so they stay readable over dark
    choropleth classes."""
    for name, (x, y) in LANDMARKS.items():
        if which is not None and name not in which:
            continue
        ax.plot(x, y, marker="o", color="#1B1917", markersize=2.4,
                markeredgecolor="white", markeredgewidth=0.6, zorder=6)
        ax.annotate(
            name, xy=(x, y), xytext=(3.5, 3.5), textcoords="offset points",
            fontsize=fontsize, color="#1B1917",
            bbox=dict(
                boxstyle="round,pad=0.18",
                facecolor="white",
                edgecolor="#1B1917",
                linewidth=0.35,
                alpha=0.65,
            ),
            zorder=7,
        )

def strip_axis(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

# Map extent focused on Auckland metro (excludes outer Hauraki Gulf islands)
MAP_XLIM = (174.55, 175.00)
MAP_YLIM = (-37.10, -36.60)

def set_metro_extent(ax):
    ax.set_xlim(MAP_XLIM)
    ax.set_ylim(MAP_YLIM)


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 1: 2x2 choropleth (access, NZDep, bivariate, trapped-payer risk)  │
# ╰──────────────────────────────────────────────────────────────────────────╯
fig = plt.figure(figsize=(14, 13))
gs = fig.add_gridspec(2, 2, wspace=0.05, hspace=0.12)

# (a) 45-min accessibility
ax1 = fig.add_subplot(gs[0, 0])
sa2.plot(
    column="access_45min", ax=ax1,
    cmap="YlOrRd",
    scheme="quantiles", k=7,
    legend=True,
    legend_kwds={
        "loc": "lower left", "fontsize": 7, "title": "Jobs (quantile)",
        "title_fontsize": 8, "frameon": False
    },
    missing_kwds={"color": "#EEEEEE"},
    edgecolor="#1B1917", linewidth=0.2
)
ax1.set_title("(a) 45-min job accessibility",
              fontsize=11, fontweight="bold", loc="left", pad=6)
add_landmarks(ax1)
strip_axis(ax1); set_metro_extent(ax1)

# (b) NZDep 2023 decile
ax2 = fig.add_subplot(gs[0, 1])
sa2.plot(
    column="NZDep_Decile", ax=ax2,
    cmap="RdYlBu_r",
    categorical=True,
    legend=True,
    legend_kwds={
        "loc": "lower left", "fontsize": 7, "title": "NZDep decile",
        "title_fontsize": 8, "frameon": False, "ncol": 2
    },
    missing_kwds={"color": "#EEEEEE"},
    edgecolor="#1B1917", linewidth=0.2
)
ax2.set_title("(b) NZDep 2023 decile (1 = least deprived)",
              fontsize=11, fontweight="bold", loc="left", pad=6)
add_landmarks(ax2)
strip_axis(ax2); set_metro_extent(ax2)

# (c) Bivariate map: accessibility tertile × deprivation tertile
sa2_bi = sa2.dropna(subset=["access_45min", "NZDep2023"]).copy()
sa2_bi["acc_t"] = pd.qcut(sa2_bi["access_45min"], 3, labels=[0, 1, 2]).astype(int)
sa2_bi["dep_t"] = pd.qcut(sa2_bi["NZDep2023"],   3, labels=[0, 1, 2]).astype(int)
sa2_bi["bi"]    = sa2_bi["acc_t"] * 3 + sa2_bi["dep_t"]   # 0..8

# 3x3 bivariate palette (low access / low dep at top-left)
BIVARIATE = np.array([
    ["#E8E8E8", "#B5C0DA", "#6C83B5"],   # low access
    ["#B8D6BE", "#90B2B3", "#567994"],   # mid access
    ["#73AE80", "#5A9178", "#2A5A5B"],   # high access
])
bi_colors = [BIVARIATE[a, d] for a in range(3) for d in range(3)]
bi_cmap   = ListedColormap(bi_colors)

ax3 = fig.add_subplot(gs[1, 0])
sa2_bi.plot(
    column="bi", ax=ax3, cmap=bi_cmap,
    categorical=True, legend=False,
    edgecolor="#1B1917", linewidth=0.2
)
# Plot SA2s missing the bivariate key in grey
missing = sa2[~sa2.index.isin(sa2_bi.index)]
if len(missing):
    missing.plot(ax=ax3, color="#EEEEEE", edgecolor="#1B1917", linewidth=0.2)

ax3.set_title("(c) Bivariate map: access × deprivation",
              fontsize=11, fontweight="bold", loc="left", pad=6)
add_landmarks(ax3)
strip_axis(ax3); set_metro_extent(ax3)

# Inset legend for bivariate map
legend_ax = ax3.inset_axes([0.015, 0.03, 0.22, 0.22])
for i in range(3):
    for j in range(3):
        legend_ax.add_patch(plt.Rectangle((j, i), 1, 1, facecolor=BIVARIATE[i, j],
                                          edgecolor="white", linewidth=0.8))
legend_ax.set_xlim(0, 3); legend_ax.set_ylim(0, 3)
legend_ax.set_xticks([]); legend_ax.set_yticks([])
legend_ax.annotate("More deprived →", xy=(0.05, -0.3), xycoords="axes fraction",
                   fontsize=6.5, color="#1B1917")
legend_ax.annotate("More\naccessible →", xy=(-0.45, 0.1), xycoords="axes fraction",
                   fontsize=6.5, color="#1B1917", rotation=90)
for s in legend_ax.spines.values():
    s.set_visible(False)

# (d) Trapped-payer risk: below-median access AND NZDep decile 8-10
median_acc = sa2["access_45min"].median()
sa2["trapped_risk"] = np.where(
    (sa2["access_45min"] < median_acc) & (sa2["NZDep_Decile"] >= 8),
    "High risk (low access + NZDep 8-10)",
    np.where(
        sa2["NZDep_Decile"] >= 8,
        "NZDep 8-10 only",
        np.where(
            sa2["access_45min"] < median_acc,
            "Low access only",
            "Neither"
        )
    )
)
risk_palette = {
    "High risk (low access + NZDep 8-10)": "#B22222",
    "NZDep 8-10 only":                     "#F4A261",
    "Low access only":                     "#A7C7E7",
    "Neither":                             "#EEEEEE",
}

ax4 = fig.add_subplot(gs[1, 1])
for cat, col in risk_palette.items():
    sub = sa2[sa2["trapped_risk"] == cat]
    if len(sub):
        sub.plot(ax=ax4, color=col, edgecolor="#1B1917", linewidth=0.2)
# geopandas .plot drops PathCollection labels, so use proxy patches instead.
risk_handles = [mpatches.Patch(color=col, label=cat)
                for cat, col in risk_palette.items()]
ax4.legend(
    handles=risk_handles,
    loc="lower left", fontsize=7, title="Risk category", title_fontsize=8,
    frameon=False
)
n_high = (sa2["trapped_risk"] == "High risk (low access + NZDep 8-10)").sum()
ax4.set_title(
    f"(d) Trapped-payer risk map\n{n_high} SA2s flagged (low access AND NZDep 8-10)",
    fontsize=11, fontweight="bold", loc="left", pad=6
)
add_landmarks(ax4)
strip_axis(ax4); set_metro_extent(ax4)

fig.suptitle(
    "Auckland transit accessibility and deprivation, baseline, weekday 07:00 to 09:00",
    fontsize=13, fontweight="bold", y=0.995
)
plt.savefig(FIGS / "fig1_accessibility_choropleth.png",
            dpi=300, bbox_inches="tight")
plt.close()
print("Figure 1 saved (4-panel choropleth).")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 2: Boxplot with scatter + LOWESS trend                            │
# ╰──────────────────────────────────────────────────────────────────────────╯
fig, ax = plt.subplots(figsize=(11, 5.5))

groups = [
    sa2.loc[sa2["NZDep_Decile"] == d, "access_45min"].dropna().values
    for d in range(1, 11)
]
bp = ax.boxplot(
    groups, positions=range(1, 11),
    patch_artist=True,
    medianprops=dict(color="#BA7517", linewidth=2),
    boxprops=dict(facecolor="#E1F5EE", edgecolor="#0F6E56", linewidth=0.8),
    whiskerprops=dict(color="#0F6E56", linewidth=0.8),
    capprops=dict(color="#0F6E56", linewidth=0.8),
    flierprops=dict(marker="", markersize=0),
    widths=0.55, showfliers=False,
)

# Jittered scatter overlay
rng = np.random.default_rng(42)
for d in range(1, 11):
    yv = sa2.loc[sa2["NZDep_Decile"] == d, "access_45min"].dropna().values
    xv = d + rng.uniform(-0.18, 0.18, size=len(yv))
    ax.scatter(xv, yv, s=8, color="#0F6E56", alpha=0.35, edgecolor="none", zorder=3)

# LOWESS (hand-rolled, avoids statsmodels dependency)
def lowess(x, y, frac=0.4):
    x = np.asarray(x, float); y = np.asarray(y, float)
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    n = len(xs); r = int(np.ceil(frac * n))
    yhat = np.zeros_like(ys)
    for i in range(n):
        d = np.abs(xs - xs[i])
        h = np.sort(d)[r - 1] if r - 1 < n else d.max()
        w = np.clip(d / max(h, 1e-12), 0, 1)
        w = (1 - w ** 3) ** 3
        W = np.diag(w)
        A = np.vstack([np.ones(n), xs]).T
        try:
            beta = np.linalg.solve(A.T @ W @ A, A.T @ W @ ys)
            yhat[i] = beta[0] + beta[1] * xs[i]
        except np.linalg.LinAlgError:
            yhat[i] = ys[i]
    return xs, yhat

x_all = sa2["NZDep_Decile"].astype(float).dropna().values
y_all = sa2.loc[sa2["NZDep_Decile"].notna(), "access_45min"].values
lx, ly = lowess(x_all, y_all, frac=0.5)
ax.plot(lx, ly, color="#B22222", linewidth=2.2, zorder=4, label="LOWESS trend")

ax.set_xticks(range(1, 11))
ax.set_xlabel("NZDep 2023 decile (1 = least deprived, 10 = most deprived)")
ax.set_ylabel("Jobs reachable within 45 min")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
q75 = sa2["access_45min"].quantile(0.75)
ax.axhline(q75, color="#D85A30", linestyle="--", linewidth=1.1,
           label=f"Q75 = {q75/1000:.0f}k jobs")
ci45 = ci_summary["CI_all_45min"].iloc[0]
ci30 = ci_summary["CI_all_30min"].iloc[0]
ax.set_title(
    f"Transit job accessibility by NZDep decile  (CI 45-min = {ci45:+.3f},  CI 30-min = {ci30:+.3f})",
    fontsize=11, fontweight="bold"
)
ax.legend(fontsize=9, frameon=False, loc="upper right")
plt.tight_layout()
plt.savefig(FIGS / "fig2_accessibility_by_deprivation.png",
            dpi=300, bbox_inches="tight")
plt.close()
print("Figure 2 saved (boxplot + scatter + LOWESS).")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 3: Concentration curve (Lorenz-type)                              │
# ╰──────────────────────────────────────────────────────────────────────────╯
def concentration_curve(y, rank_var):
    df = pd.DataFrame({"y": y, "r": rank_var}).dropna()
    df = df.sort_values("r")                      # ascending rank
    cum_pop = np.arange(1, len(df) + 1) / len(df)
    cum_y   = df["y"].cumsum() / df["y"].sum()
    return cum_pop, cum_y.values

fig, axes = plt.subplots(1, 2, figsize=(12, 5.3))

for ax, col, label in zip(
    axes,
    ["access_30min", "access_45min"],
    ["30-min accessibility", "45-min accessibility"]
):
    cx, cy = concentration_curve(sa2[col], sa2["NZDep2023"])
    ax.plot([0, 1], [0, 1], color="#888780", linestyle="--", linewidth=1,
            label="Line of equality")
    # Area shading where the curve deviates from equality
    ax.fill_between(cx, cx, cy,
                    where=cy >= cx, facecolor="#1D9E7533", edgecolor="none")
    ax.fill_between(cx, cx, cy,
                    where=cy < cx, facecolor="#D85A3033", edgecolor="none")
    ax.plot(cx, cy, color="#0F6E56", linewidth=2, label="Concentration curve")

    ci_val = ci_summary[f"CI_all_{label[:2]}min".replace("mi", "min")].iloc[0] \
        if False else (ci30 if "30" in label else ci45)
    ax.set_title(
        f"{label}\nCI = {ci_val:+.4f}",
        fontsize=11, fontweight="bold"
    )
    ax.set_xlabel("Cumulative share of SA2s, ranked by NZDep (affluent → deprived)")
    ax.set_ylabel("Cumulative share of jobs accessible")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.legend(fontsize=8, frameon=False, loc="upper left")

fig.suptitle(
    "Concentration curves, baseline transit accessibility",
    fontsize=13, fontweight="bold", y=1.02
)
plt.tight_layout()
plt.savefig(FIGS / "fig3_concentration_curve.png",
            dpi=300, bbox_inches="tight")
plt.close()
print("Figure 3 saved (concentration curves).")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 4: Scatter NZDep vs access with labelled extreme SA2s             │
# ╰──────────────────────────────────────────────────────────────────────────╯
fig, ax = plt.subplots(figsize=(11, 6.5))

mask = sa2[["NZDep2023", "access_45min"]].notna().all(axis=1)
sub  = sa2[mask].copy()
sc = ax.scatter(
    sub["NZDep2023"], sub["access_45min"],
    c=sub["NZDep_Decile"], cmap="RdYlBu_r",
    s=24, alpha=0.8, edgecolor="#FFFFFF", linewidth=0.4
)
cb = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.01)
cb.set_label("NZDep decile", fontsize=9)

# Linear fit for reference
coefs = np.polyfit(sub["NZDep2023"], sub["access_45min"], 1)
xline = np.linspace(sub["NZDep2023"].min(), sub["NZDep2023"].max(), 50)
ax.plot(xline, np.polyval(coefs, xline),
        color="#1B1917", linewidth=1.2, linestyle="--",
        label=f"Linear fit: slope = {coefs[0]:.1f} jobs per NZDep point")

# Label top-4 most and bottom-4 least accessible SA2s (stagger offsets to
# avoid collisions at the top and bottom edges of the scatter).
name_col = "SA22026_V1_00_NAME"
top = sub.nlargest(4, "access_45min")
bot = sub[sub["access_45min"] > 0].nsmallest(4, "access_45min")
# Top: stagger vertically upward
offsets_top = [(6, 4), (6, 14), (6, -8), (6, 22)]
for (dx, dy), (_, row) in zip(offsets_top, top.iterrows()):
    ax.annotate(
        row[name_col],
        xy=(row["NZDep2023"], row["access_45min"]),
        xytext=(dx, dy), textcoords="offset points",
        fontsize=7.5, color="#1B1917",
        arrowprops=dict(arrowstyle="-", color="#888780", linewidth=0.5),
        zorder=10,
    )
# Bottom: push labels below the x-axis line and spread horizontally
offsets_bot = [(-30, -14), (10, -14), (-30, -26), (10, -26)]
for (dx, dy), (_, row) in zip(offsets_bot, bot.iterrows()):
    ax.annotate(
        row[name_col],
        xy=(row["NZDep2023"], row["access_45min"]),
        xytext=(dx, dy), textcoords="offset points",
        fontsize=7.5, color="#1B1917",
        arrowprops=dict(arrowstyle="-", color="#888780", linewidth=0.5),
        zorder=10,
    )

ax.set_xlabel("NZDep 2023 score (higher = more deprived)")
ax.set_ylabel("Jobs reachable within 45 min")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
ax.set_title(
    "SA2-level accessibility versus deprivation, with extreme SA2s labelled",
    fontsize=11, fontweight="bold"
)
ax.legend(fontsize=9, frameon=False, loc="upper right")
plt.tight_layout()
plt.savefig(FIGS / "fig4_access_vs_deprivation_scatter.png",
            dpi=300, bbox_inches="tight")
plt.close()
print("Figure 4 saved (scatter with labelled SA2s).")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 5: Stacked-bar burden (only if any scenario has non-empty SA2 set)│
# ╰──────────────────────────────────────────────────────────────────────────╯
has_any_scenario = any(
    (sa2[f"burden_{s}"] != "no_charge").any() for s in SCENARIOS
    if f"burden_{s}" in sa2.columns
)

if has_any_scenario:
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharey=True, sharex=True)
    burden_cols = ["pays_with_alternative", "pays_without_alternative", "no_charge"]
    labels_map = {
        "pays_with_alternative":    "Pays, has PT alternative",
        "pays_without_alternative": "Pays, no viable alternative (trapped)",
        "no_charge":                "Not charged",
    }
    for ax, scenario in zip(axes.flatten(), SCENARIOS):
        col = f"burden_{scenario}"
        ct = (
            sa2.groupby(["NZDep_Decile", col])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=burden_cols, fill_value=0)
        )
        bottom = np.zeros(len(ct))
        for bcat in burden_cols:
            if bcat in ct.columns:
                vals = ct[bcat].values
                ax.bar(ct.index, vals, bottom=bottom,
                       color=PALETTE[bcat], width=0.7, linewidth=0)
                bottom += vals
        ci_val = ci_summary.loc[ci_summary["scenario"] == scenario,
                                "CI_charged_sa2s"].values
        ci_str = (f"CI = {ci_val[0]:+.3f}"
                  if len(ci_val) and not np.isnan(ci_val[0]) else "")
        ax.set_title(f"{SCENARIO_LABELS[scenario]}\n{ci_str}",
                     fontsize=9, fontweight="bold")
        ax.set_xticks(range(1, 11))
    for ax in axes[1]:
        ax.set_xlabel("NZDep decile", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("SA2 count", fontsize=9)
    legend_patches = [mpatches.Patch(color=PALETTE[k], label=labels_map[k])
                      for k in burden_cols]
    fig.legend(handles=legend_patches, loc="lower center", ncol=3,
               fontsize=9, bbox_to_anchor=(0.5, -0.02), frameon=False)
    fig.suptitle("Burden classification by NZDep decile across six scenarios",
                 fontsize=12, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(FIGS / "fig5_burden_by_scenario.png",
                dpi=300, bbox_inches="tight")
    plt.close()
    print("Figure 5 saved (burden by scenario).")
else:
    print("Figure 5 skipped: SCENARIO_SA2_SETS in stage4 is empty.")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Figure 6: CI forest plot (only if any scenario CI is finite)             │
# ╰──────────────────────────────────────────────────────────────────────────╯
has_scenario_ci = ci_summary["CI_charged_sa2s"].notna().any()
if has_scenario_ci:
    fig, ax = plt.subplots(figsize=(8, 4))
    ci_vals   = ci_summary["CI_charged_sa2s"].values
    scenarios = ci_summary["scenario"].values
    colors    = ["#1D9E75" if s in ["1a", "1c", "2c"] else "#D85A30"
                 for s in scenarios]
    ax.barh(scenarios, ci_vals, color=colors, height=0.5, edgecolor="none")
    ax.axvline(0, color="#444441", linewidth=0.8)
    ax.set_xlabel("Concentration Index (charged SA2s)")
    ax.invert_yaxis()
    for i, (val, s) in enumerate(zip(ci_vals, scenarios)):
        if not np.isnan(val):
            ax.text(val - 0.005, i, f"{val:+.3f}",
                    va="center",
                    ha="right" if val < 0 else "left",
                    fontsize=9, color="white", fontweight="bold")
    ax.legend(handles=[
        mpatches.Patch(color="#1D9E75", label="CBD cordon (H1)"),
        mpatches.Patch(color="#D85A30", label="Motorway corridor (H2)"),
    ], fontsize=9, frameon=False)
    ax.set_title("Concentration Index by scenario",
                 fontsize=10, fontweight="bold")
    plt.tight_layout()
    plt.savefig(FIGS / "fig6_ci_forest_plot.png",
                dpi=300, bbox_inches="tight")
    plt.close()
    print("Figure 6 saved (CI forest plot).")
else:
    print("Figure 6 skipped: no scenario has a finite CI.")


# ── Final layer ─────────────────────────────────────────────────────────────
# sa2_equity.gpkg already carries the same payload; write sa2_final as a
# convenience copy for downstream consumers.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_to_gpkg  # noqa: E402
safe_to_gpkg(sa2, OUTPUT / "sa2_final.gpkg")

print("\nStage 5 complete.")
