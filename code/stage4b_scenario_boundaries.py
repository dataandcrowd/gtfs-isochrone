"""
Stage 4b: Scenario boundary polygons and map (standalone re-run).

Stage 4 already produces scenario_boundaries.gpkg and fig0 in-process; this
script is retained as a standalone option for re-rendering fig0 after the
SCENARIO_SA2_SETS have been revised, without rerunning the full equity stage.

- Dissolves charged SA2s per scenario into a single polygon (or multipolygon)
- Saves outputs/scenario_boundaries.gpkg with one row per scenario
- Renders outputs/figures/fig0_scenario_boundaries.png (2x3 grid map)
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

OUTPUT = Path("outputs")
FIGS   = OUTPUT / "figures"; FIGS.mkdir(exist_ok=True)

SA2_PATH = OUTPUT / "sa2_equity.gpkg"
if not (SA2_PATH.exists() and SA2_PATH.stat().st_size > 0):
    raise FileNotFoundError(f"No sa2_equity.gpkg at {SA2_PATH}. Run stage 4 first.")
print(f"Reading equity layer: {SA2_PATH.name}")

sa2 = safe_read_gpkg(SA2_PATH)

SCENARIOS = ["1a", "1c", "2c", "3b", "3c", "3e"]
SCENARIO_TITLES = {
    "1a": "1a, City centre cordon",
    "1c": "1c, City centre + fringe",
    "2c": "2c, Isthmus double cordon",
    "3b": "3b, Core motorways",
    "3c": "3c, Core motorways + CBD",
    "3e": "3e, Motorway hotspots",
}

# ── 4b.1  Build dissolved boundary per scenario ──────────────────────────────
rows = []
for sc in SCENARIOS:
    col = f"burden_{sc}"
    if col not in sa2.columns:
        print(f"  [warn] column {col} not found; skipping scenario {sc}")
        continue
    charged = sa2[sa2[col] != "no_charge"].copy()
    n_sa2   = len(charged)
    n_trap  = (charged[col] == "pays_without_alternative").sum()
    if n_sa2 == 0:
        print(f"  [warn] scenario {sc}: no charged SA2s; skipping")
        continue
    # Dissolve all charged SA2s into a single (multi)polygon
    dissolved = charged.dissolve()
    geom = dissolved.geometry.iloc[0]
    rows.append({
        "scenario": sc,
        "label": SCENARIO_TITLES[sc],
        "n_sa2": n_sa2,
        "n_trapped_payers": int(n_trap),
        "geometry": geom,
    })
    print(f"  {sc}: {n_sa2} SA2s dissolved ({n_trap} trapped)")

boundaries = gpd.GeoDataFrame(rows, geometry="geometry", crs=sa2.crs)

# ── 4b.2  Save as GeoPackage ─────────────────────────────────────────────────
written = safe_to_gpkg(boundaries, OUTPUT / "scenario_boundaries.gpkg")
print(f"  scenario boundary layer written to {written.name}")

# ── 4b.3  Render 2x3 grid map ────────────────────────────────────────────────
# Colour palette: cordons in a green-teal, motorway corridors in a warm orange.
CORDON_FILL  = "#2C7A7B"
CORDON_EDGE  = "#1D4E50"
MWAY_FILL    = "#C05621"
MWAY_EDGE    = "#7B2F10"
TRAPPED_FILL = "#D4421E"
BASE_FILL    = "#F4F1EA"
BASE_EDGE    = "#1B1917"

# Metro Auckland extent (matches stage 5 maps)
MAP_XLIM = (174.55, 175.00)
MAP_YLIM = (-37.10, -36.60)

sa2_wgs = sa2.to_crs(epsg=4326)
boundaries_wgs = boundaries.to_crs(epsg=4326)

fig, axes = plt.subplots(
    2, 3,
    figsize=(15, 10),
    constrained_layout=True,
)

for ax, sc in zip(axes.flatten(), SCENARIOS):
    ax.set_facecolor("white")

    # Basemap: all SA2s with pale fill and thin dark outline
    sa2_wgs.plot(
        ax=ax,
        facecolor=BASE_FILL,
        edgecolor=BASE_EDGE,
        linewidth=0.15,
    )

    col = f"burden_{sc}"
    is_motorway = sc in ("3b", "3c", "3e")
    fill_colour = MWAY_FILL if is_motorway else CORDON_FILL
    edge_colour = MWAY_EDGE if is_motorway else CORDON_EDGE

    if col in sa2_wgs.columns:
        charged = sa2_wgs[sa2_wgs[col] != "no_charge"]
        trapped = sa2_wgs[sa2_wgs[col] == "pays_without_alternative"]

        # Charged SA2s filled in scenario colour
        charged.plot(
            ax=ax,
            facecolor=fill_colour,
            edgecolor=BASE_EDGE,
            linewidth=0.2,
            alpha=0.55,
        )
        # Trapped payers highlighted with warmer hatch
        if not trapped.empty:
            trapped.plot(
                ax=ax,
                facecolor=TRAPPED_FILL,
                edgecolor=BASE_EDGE,
                linewidth=0.25,
                alpha=0.78,
            )

        # Outer dissolved boundary on top for the scenario footprint
        bnd_row = boundaries_wgs[boundaries_wgs["scenario"] == sc]
        if not bnd_row.empty:
            bnd_row.boundary.plot(
                ax=ax,
                edgecolor=edge_colour,
                linewidth=1.6,
            )

    n_sa2 = int(boundaries_wgs.loc[
        boundaries_wgs["scenario"] == sc, "n_sa2"
    ].iloc[0]) if (boundaries_wgs["scenario"] == sc).any() else 0
    n_trap = int(boundaries_wgs.loc[
        boundaries_wgs["scenario"] == sc, "n_trapped_payers"
    ].iloc[0]) if (boundaries_wgs["scenario"] == sc).any() else 0

    ax.set_title(
        f"{SCENARIO_TITLES[sc]}\n"
        f"{n_sa2} SA2s charged, {n_trap} trapped payers",
        fontsize=10,
        loc="center",
    )
    ax.set_xlim(*MAP_XLIM)
    ax.set_ylim(*MAP_YLIM)
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

# Shared legend at bottom
legend_handles = [
    Patch(facecolor=CORDON_FILL, edgecolor=CORDON_EDGE, alpha=0.55,
          label="Charged SA2 (cordon scenario)"),
    Patch(facecolor=MWAY_FILL, edgecolor=MWAY_EDGE, alpha=0.55,
          label="Charged SA2 (motorway corridor scenario)"),
    Patch(facecolor=TRAPPED_FILL, edgecolor=BASE_EDGE, alpha=0.78,
          label="Trapped payer (no 30-min PT alternative)"),
    Line2D([0], [0], color=CORDON_EDGE, linewidth=1.6,
           label="Scenario footprint (dissolved boundary)"),
]
fig.legend(
    handles=legend_handles,
    loc="lower center",
    ncol=4,
    frameon=False,
    fontsize=9,
    bbox_to_anchor=(0.5, -0.02),
)
fig.suptitle(
    "Auckland TOUC scenario footprints and trapped-payer exposure",
    fontsize=13,
    fontweight="bold",
)

OUT_PNG = FIGS / "fig0_scenario_boundaries.png"
plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"  scenario boundary map written to {OUT_PNG.name}")

print("\nStage 4b complete.")
