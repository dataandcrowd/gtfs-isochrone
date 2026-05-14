"""
Stage 5 (split): export each panel of fig1 as a standalone PNG.

Produces:
  fig1a_access_45min.png       (a) 45-min job accessibility quantile choropleth
  fig1b_nzdep_decile.png       (b) NZDep 2023 decile choropleth
  fig1c_bivariate.png          (c) bivariate access x deprivation
  fig1d_no_alt_risk.png        (d) no-alternative risk (low access AND NZDep 8-10)

Uses the same data, palette and Auckland metro extent as the combined fig1 in
stage5_visualisation.py, so panels can be dropped straight into the manuscript
in place of the 2x2 composite.
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg

OUTPUT = Path("outputs")
FIGS   = OUTPUT / "figures"
FIGS.mkdir(exist_ok=True)

SA2_PATH = OUTPUT / "sa2_equity.gpkg"
sa2 = safe_read_gpkg(SA2_PATH).to_crs(epsg=4326)

# ── Auckland metro framing (same as stage5_visualisation) ──────────────────
MAP_XLIM = (174.55, 175.00)
MAP_YLIM = (-37.10, -36.60)

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

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         10,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})


def add_landmarks(ax, fontsize=7):
    for name, (x, y) in LANDMARKS.items():
        ax.plot(x, y, marker="o", color="#1B1917", markersize=2.6,
                markeredgecolor="white", markeredgewidth=0.6, zorder=6)
        ax.annotate(
            name, xy=(x, y), xytext=(3.5, 3.5), textcoords="offset points",
            fontsize=fontsize, color="#1B1917",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white",
                      edgecolor="#1B1917", linewidth=0.35, alpha=0.7),
            zorder=7,
        )


def strip_axis(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def set_metro_extent(ax):
    ax.set_xlim(*MAP_XLIM); ax.set_ylim(*MAP_YLIM)


PANEL_FIGSIZE = (8.5, 9.5)  # roughly square per panel, taller than wide for AKL


# ── (a) 45-min job accessibility ───────────────────────────────────────────
fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
sa2.plot(
    column="access_45min", ax=ax,
    cmap="YlOrRd", scheme="quantiles", k=7,
    legend=True,
    legend_kwds={
        "loc": "upper right", "fontsize": 8, "title": "Jobs (quantile)",
        "title_fontsize": 9, "frameon": False,
    },
    missing_kwds={"color": "#EEEEEE"},
    edgecolor="#1B1917", linewidth=0.2,
)
ax.set_title("(a) 45-min job accessibility, baseline weekday 07:00 to 09:00",
             fontsize=12, fontweight="bold", loc="left", pad=8)
add_landmarks(ax)
strip_axis(ax); set_metro_extent(ax)
plt.savefig(FIGS / "fig1a_access_45min.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig1a_access_45min.png")


# ── (b) NZDep 2023 decile ──────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
sa2.plot(
    column="NZDep_Decile", ax=ax,
    cmap="RdYlBu_r", categorical=True,
    legend=True,
    legend_kwds={
        "loc": "upper right", "fontsize": 8, "title": "NZDep decile",
        "title_fontsize": 9, "frameon": False, "ncol": 2,
    },
    missing_kwds={"color": "#EEEEEE"},
    edgecolor="#1B1917", linewidth=0.2,
)
ax.set_title("(b) NZDep 2023 decile (1 = least deprived)",
             fontsize=12, fontweight="bold", loc="left", pad=8)
add_landmarks(ax)
strip_axis(ax); set_metro_extent(ax)
plt.savefig(FIGS / "fig1b_nzdep_decile.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig1b_nzdep_decile.png")


# ── (c) bivariate access x deprivation ─────────────────────────────────────
sa2_bi = sa2.dropna(subset=["access_45min", "NZDep2023"]).copy()
sa2_bi["acc_t"] = pd.qcut(sa2_bi["access_45min"], 3, labels=[0, 1, 2]).astype(int)
sa2_bi["dep_t"] = pd.qcut(sa2_bi["NZDep2023"],   3, labels=[0, 1, 2]).astype(int)
sa2_bi["bi"]    = sa2_bi["acc_t"] * 3 + sa2_bi["dep_t"]

BIVARIATE = np.array([
    ["#E8E8E8", "#B5C0DA", "#6C83B5"],
    ["#B8D6BE", "#90B2B3", "#567994"],
    ["#73AE80", "#5A9178", "#2A5A5B"],
])
bi_colors = [BIVARIATE[a, d] for a in range(3) for d in range(3)]
bi_cmap   = ListedColormap(bi_colors)

fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
sa2_bi.plot(column="bi", ax=ax, cmap=bi_cmap, categorical=True, legend=False,
            edgecolor="#1B1917", linewidth=0.2)
missing = sa2[~sa2.index.isin(sa2_bi.index)]
if len(missing):
    missing.plot(ax=ax, color="#EEEEEE", edgecolor="#1B1917", linewidth=0.2)

ax.set_title("(c) Bivariate map: access x deprivation",
             fontsize=12, fontweight="bold", loc="left", pad=8)
add_landmarks(ax)
strip_axis(ax); set_metro_extent(ax)

# 3x3 inset legend (top-right)
legend_ax = ax.inset_axes([0.74, 0.73, 0.24, 0.24])
for i in range(3):
    for j in range(3):
        legend_ax.add_patch(plt.Rectangle((j, i), 1, 1,
                                          facecolor=BIVARIATE[i, j],
                                          edgecolor="white", linewidth=0.8))
legend_ax.set_xlim(0, 3); legend_ax.set_ylim(0, 3)
legend_ax.set_xticks([]); legend_ax.set_yticks([])
legend_ax.annotate("More deprived ->", xy=(0.05, -0.30), xycoords="axes fraction",
                   fontsize=7, color="#1B1917")
legend_ax.annotate("More\naccessible ->", xy=(-0.45, 0.10), xycoords="axes fraction",
                   fontsize=7, color="#1B1917", rotation=90)
for s in legend_ax.spines.values():
    s.set_visible(False)

plt.savefig(FIGS / "fig1c_bivariate.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig1c_bivariate.png")


# ── (d) no-alternative risk: below-median access AND NZDep decile 8-10 ─────
median_acc = sa2["access_45min"].median()
sa2["no_alt_risk"] = np.where(
    (sa2["access_45min"] < median_acc) & (sa2["NZDep_Decile"] >= 8),
    "High risk (low access + NZDep 8-10)",
    np.where(
        sa2["NZDep_Decile"] >= 8,
        "NZDep 8-10 only",
        np.where(sa2["access_45min"] < median_acc,
                 "Low access only",
                 "Neither"),
    ),
)
risk_palette = {
    "High risk (low access + NZDep 8-10)": "#B22222",
    "NZDep 8-10 only":                     "#F4A261",
    "Low access only":                     "#A7C7E7",
    "Neither":                             "#EEEEEE",
}

fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
for cat, col in risk_palette.items():
    sub = sa2[sa2["no_alt_risk"] == cat]
    if len(sub):
        sub.plot(ax=ax, color=col, edgecolor="#1B1917", linewidth=0.2)
risk_handles = [mpatches.Patch(color=col, label=cat) for cat, col in risk_palette.items()]
ax.legend(handles=risk_handles, loc="upper right", fontsize=8,
          title="Risk category", title_fontsize=9, frameon=False)
n_high = (sa2["no_alt_risk"] == "High risk (low access + NZDep 8-10)").sum()
ax.set_title(f"(d) No-alternative risk\n{n_high} SA2s with low access AND NZDep 8-10",
             fontsize=12, fontweight="bold", loc="left", pad=8)
add_landmarks(ax)
strip_axis(ax); set_metro_extent(ax)
plt.savefig(FIGS / "fig1d_no_alt_risk.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig1d_no_alt_risk.png")

print("\nAll four panels saved to outputs/figures/")
