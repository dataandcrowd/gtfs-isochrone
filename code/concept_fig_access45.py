"""
Conceptual figure: how access_45min is computed for one origin SA2.

For each origin SA2 i, look up the travel time to every destination SA2 j in
the GTFS travel-time matrix (transit + walking, weekday 07:00-09:00, median
percentile). Sum the jobs at every j with travel time <= 45 minutes. The
sum is access_45min for origin i. The figure picks three illustrative
origins (CBD, near-median, outer fringe) and shows for each:

  - the origin polygon outlined in heavy blue
  - destination polygons reachable within 45 minutes, coloured by jobs_count
  - destination polygons not reachable (or NaN travel time) in pale grey
  - the total reachable jobs (= access_45min) annotated on the panel

Exports: outputs/figures/concept_access45_origins.png
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

OUT_FIG = Path("outputs/figures/concept_access45_origins.png")
OUT_FIG.parent.mkdir(parents=True, exist_ok=True)

sa2 = safe_read_gpkg("data/sa2/sa2_final.gpkg").to_crs(epsg=4326)
ttm = pd.read_parquet("outputs/intermediate/travel_time_matrix.parquet")

# Three origins spanning the access_45min distribution
ORIGINS = [
    ("133200", "Queen Street (CBD)",        "high"),
    ("153500", "Ōtara West",                "median"),
    ("164301", "Drury West",                "low-fringe"),
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
    "Otara":     (174.873, -36.961),
    "Onehunga":  (174.782, -36.925),
}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})

# 3x1 vertical layout fits one journal column much better than 1x3:
# at full-width 7 inch print scale each panel is ~7 wide x ~6.5 tall, which
# is roughly 1.5x the per-panel area of a 1x3 horizontal layout. The figure
# width is kept close to the Auckland metro aspect ratio (lon 174.55-175.00
# is ~50 km, lat -37.10 to -36.60 is ~55 km) so the map fills the panel
# rather than leaving large left/right margins.
fig, axes = plt.subplots(3, 1, figsize=(7.0, 21),
                         gridspec_kw={"hspace": 0.16})

for ax, (oid, oname, _) in zip(axes, ORIGINS):
    # Travel times from this origin to every destination SA2
    tt = ttm[ttm["from_id"] == oid].set_index("to_id")["travel_time_p50"]

    panel = sa2.copy()
    panel["t_from_origin"] = panel["SA22023_V1_00"].map(tt)
    panel["reachable"] = (
        panel["t_from_origin"].notna()
        & (panel["t_from_origin"] <= THRESHOLD_MIN)
    )

    # Unreachable: pale grey background
    unreach = panel[~panel["reachable"]]
    unreach.plot(ax=ax, color="#EFEFEF",
                 edgecolor="#B5B5B5", linewidth=0.15)

    # Reachable: shaded by jobs_count (log scale handles long-tail)
    reach = panel[panel["reachable"]].copy()
    reach["jobs_for_plot"] = reach["jobs_count"].fillna(0).clip(lower=1)
    if not reach.empty:
        vmin, vmax = max(1, reach["jobs_for_plot"].min()), reach["jobs_for_plot"].max()
        reach.plot(
            ax=ax, column="jobs_for_plot",
            cmap="YlOrRd", norm=LogNorm(vmin=vmin, vmax=vmax),
            edgecolor="#1B1917", linewidth=0.18,
        )

    # Origin SA2: heavy blue outline
    origin_poly = panel[panel["SA22023_V1_00"] == oid]
    origin_poly.plot(ax=ax, facecolor="#1F77B4",
                     edgecolor="#0B3D6E", linewidth=1.6, alpha=0.85, zorder=5)

    # Origin centroid star
    if not origin_poly.empty:
        c = origin_poly.geometry.iloc[0].representative_point()
        ax.plot(c.x, c.y, marker="*", markersize=26,
                markerfacecolor="#1F77B4", markeredgecolor="white",
                markeredgewidth=1.4, zorder=6)

    # Landmarks
    for name, (x, y) in LANDMARKS.items():
        ax.plot(x, y, marker="o", color="#1B1917", markersize=3.0,
                markeredgecolor="white", markeredgewidth=0.6, zorder=6)
        ax.annotate(
            name, xy=(x, y), xytext=(4, 4), textcoords="offset points",
            fontsize=9, color="#1B1917",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="white",
                      edgecolor="#1B1917", linewidth=0.35, alpha=0.75),
            zorder=7,
        )

    # Annotate total reachable jobs (= access_45min)
    n_reach = len(reach)
    total_jobs = int(round(reach["jobs_count"].fillna(0).sum()))
    access_stored = int(round(panel.loc[
        panel["SA22023_V1_00"] == oid, "access_45min"
    ].iloc[0])) if (panel["SA22023_V1_00"] == oid).any() else None

    ax.set_title(
        f"Origin: {oname}",
        fontsize=14, fontweight="bold", loc="left", pad=8,
    )

    # Place the headline numbers as a text block in the top-right of the
    # map (over the Hauraki Gulf), where the panel is visually empty. This
    # keeps the panel title short and avoids overflow at column width.
    ax.text(
        0.98, 0.97,
        f"access_45min\n= {total_jobs:,} jobs\n"
        f"({n_reach} destinations\nin <= 45 min)",
        transform=ax.transAxes,
        ha="right", va="top",
        fontsize=11, fontweight="bold", color="#0B3D6E",
        linespacing=1.3,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#0B3D6E", linewidth=0.7, alpha=0.92),
    )

    ax.set_xlim(*MAP_XLIM); ax.set_ylim(*MAP_YLIM)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

# Shared legend at bottom
legend_handles = [
    mpatches.Patch(facecolor="#1F77B4", edgecolor="#0B3D6E", alpha=0.85,
                   label="Origin SA2"),
    mpatches.Patch(facecolor="#FED976", edgecolor="#1B1917",
                   label="Reachable in <= 45 min, shaded by jobs_count (log)"),
    mpatches.Patch(facecolor="#EFEFEF", edgecolor="#B5B5B5",
                   label="Not reachable in 45 min (or NaN travel time)"),
]
fig.legend(handles=legend_handles, loc="lower center", ncol=1,
           frameon=False, fontsize=11, bbox_to_anchor=(0.5, 0.01))

# Keep the suptitle wrapped onto three short lines so it fits inside the
# figure width (otherwise bbox_inches='tight' expands the whole canvas).
fig.suptitle(
    "How access_45min is computed for one origin SA2\n"
    "Sum the jobs at every destination SA2\n"
    "with transit travel time <= 45 min (weekday 07:00-09:00)",
    fontsize=14, fontweight="bold", y=0.995
)

# Use a fixed pad rather than bbox_inches='tight', so the saved image
# matches the requested figsize and prints at the intended scale.
plt.subplots_adjust(top=0.93, bottom=0.04, left=0.02, right=0.98)
plt.savefig(OUT_FIG, dpi=300)
plt.close()
print(f"Saved {OUT_FIG}")
