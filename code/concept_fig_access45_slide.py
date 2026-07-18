"""Slide-friendly horizontal (1x3) version of concept_access45_origins.png.

The paper version is 7 x 21 portrait so it fits a journal column. That
aspect is wrong for a 16:9 presentation slide, where the figure ends up
~1.3 in wide x ~4 in tall, leaving the three panels unreadable. This
script regenerates the same data in a 16 x 6 landscape layout, with
bigger fonts and lighter chrome so it scales down well in the slide.
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg

OUT_FIG = Path("outputs/figures/concept_access45_origins_slide.png")
OUT_FIG.parent.mkdir(parents=True, exist_ok=True)

sa2 = safe_read_gpkg("data/sa2/sa2_final.gpkg").to_crs(epsg=4326)
ttm = pd.read_parquet("outputs/travel_time_matrix.parquet")

ORIGINS = [
    ("133200", "Queen Street (CBD)"),
    ("153500", "Ōtara West"),
    ("164301", "Drury West"),
]
THRESHOLD_MIN = 45.0

sa2["SA22023_V1_00"] = sa2["SA22023_V1_00"].astype(str)
ttm["from_id"] = ttm["from_id"].astype(str)
ttm["to_id"]   = ttm["to_id"].astype(str)

MAP_XLIM = (174.55, 175.00)
MAP_YLIM = (-37.10, -36.60)

LANDMARKS = {
    "CBD":       (174.765, -36.848),
    "Albany":    (174.698, -36.735),
    "Henderson": (174.628, -36.875),
    "Mangere":   (174.805, -36.968),
    "Manurewa":  (174.897, -37.024),
    "Papakura":  (174.943, -37.063),
    "Onehunga":  (174.782, -36.925),
}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})

# 1x3 horizontal sized for a slide footprint at ~9 in display width
fig, axes = plt.subplots(1, 3, figsize=(16, 7), gridspec_kw={"wspace": 0.04})

for ax, (oid, oname) in zip(axes, ORIGINS):
    tt = ttm[ttm["from_id"] == oid].set_index("to_id")["travel_time_p50"]
    panel = sa2.copy()
    panel["t"] = panel["SA22023_V1_00"].map(tt)
    panel["reach"] = panel["t"].notna() & (panel["t"] <= THRESHOLD_MIN)

    unreach = panel[~panel["reach"]]
    unreach.plot(ax=ax, color="#EFEFEF", edgecolor="#B5B5B5", linewidth=0.15)

    reach = panel[panel["reach"]].copy()
    reach["jp"] = reach["jobs_count"].fillna(0).clip(lower=1)
    if not reach.empty:
        reach.plot(
            ax=ax, column="jp", cmap="YlOrRd",
            norm=LogNorm(vmin=max(1, reach["jp"].min()), vmax=reach["jp"].max()),
            edgecolor="#1B1917", linewidth=0.18,
        )

    origin_poly = panel[panel["SA22023_V1_00"] == oid]
    origin_poly.plot(ax=ax, facecolor="#1F77B4",
                     edgecolor="#0B3D6E", linewidth=1.8, alpha=0.85, zorder=5)
    if not origin_poly.empty:
        c = origin_poly.geometry.iloc[0].representative_point()
        ax.plot(c.x, c.y, marker="*", markersize=30,
                markerfacecolor="#1F77B4", markeredgecolor="white",
                markeredgewidth=1.5, zorder=6)

    for name, (x, y) in LANDMARKS.items():
        ax.plot(x, y, marker="o", color="#1B1917", markersize=3.0,
                markeredgecolor="white", markeredgewidth=0.6, zorder=6)
        ax.annotate(name, xy=(x, y), xytext=(4, 4), textcoords="offset points",
                    fontsize=9, color="#1B1917",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor="#1B1917", linewidth=0.35, alpha=0.75),
                    zorder=7)

    n_reach = len(reach)
    total_jobs = int(round(reach["jobs_count"].fillna(0).sum()))

    ax.set_title(f"Origin: {oname}", fontsize=15, fontweight="bold", loc="left", pad=8)

    ax.text(
        0.98, 0.97,
        f"access_45min\n= {total_jobs:,} jobs\n({n_reach} dests\nin <= 45 min)",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=12, fontweight="bold", color="#0B3D6E", linespacing=1.3,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#0B3D6E", linewidth=0.7, alpha=0.92),
    )

    ax.set_xlim(*MAP_XLIM); ax.set_ylim(*MAP_YLIM)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)

# Shared legend at bottom
legend_handles = [
    mpatches.Patch(facecolor="#1F77B4", edgecolor="#0B3D6E", alpha=0.85, label="Origin SA2"),
    mpatches.Patch(facecolor="#FED976", edgecolor="#1B1917", label="Reachable in <= 45 min, shaded by jobs_count (log)"),
    mpatches.Patch(facecolor="#EFEFEF", edgecolor="#B5B5B5", label="Not reachable in 45 min"),
]
fig.legend(handles=legend_handles, loc="lower center", ncol=3,
           frameon=False, fontsize=11, bbox_to_anchor=(0.5, 0.02))

plt.subplots_adjust(top=0.93, bottom=0.10, left=0.01, right=0.99)
plt.savefig(OUT_FIG, dpi=200)
plt.close()
print(f"Saved {OUT_FIG}")
