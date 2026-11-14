"""Figure 4.2b: trapped-share clusters for the three manuscript scenarios (1x3).

Bivariate local Moran (stage 4c, _equity_utils.trapped_share_spatial): each
SA2's trapped share against the mean NZDep2023 of its neighbours, p < 0.05.
FIX 2026-11-14: previously a univariate LISA of the trapped COUNT, and the
inset showed the whole study area instead of the central isthmus.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd
import pandas as pd
from matplotlib.patches import Patch

sns.set_theme(style="white", context="talk", font_scale=1.0)

g = gpd.read_file("outputs/burden_by_sa2_final.gpkg").to_crs(2193)

# global Moran's I of the trapped share, per scenario (Table 2)
_m = pd.read_csv("outputs/equity_summary_final.csv")
MORAN = _m.set_index("scenario")["moran_I"].to_dict()

# central-isthmus zoom (NZTM): ~20 x 16 km around the city centre, where the
# SA2s are too small to read at full-area scale.
ZOOM = (1748000, 5909000, 1768000, 5925000)


def add_inset(host, color_series):
    axins = host.inset_axes([0.62, 0.66, 0.38, 0.34])
    g.plot(color=color_series, linewidth=0.15, edgecolor="#aaa", ax=axins)
    axins.set_aspect("equal", adjustable="box")
    axins.set_xlim(ZOOM[0], ZOOM[2]); axins.set_ylim(ZOOM[1], ZOOM[3])
    axins.set_xticks([]); axins.set_yticks([])
    axins.set_xlabel(""); axins.set_ylabel("")   # geopandas >= 1.0 adds CRS axis labels
    for sp in axins.spines.values():
        sp.set_visible(True); sp.set_edgecolor("#333"); sp.set_linewidth(1)
    host.indicate_inset_zoom(axins, edgecolor="#333", lw=1, alpha=0.6)

SCEN = ["1a", "1c", "3c"]   # manuscript scenarios (_scenario_utils.SCENARIOS)
TITLES = {"1a": "1a City centre cordon", "1c": "1c City centre + fringe",
          "3c": "3c Highway corridor + CBD"}
sys.path.insert(0, str(Path(__file__).parent))
from _equity_utils import BV_DESCRIPTIONS  # noqa: E402

COL = {"HH": "#D4421E", "HL": "#FDAE61", "LH": "#ABD9E9", "LL": "#2C7BB6",
       "ns": "#E6E6E6", "none": "#FFFFFF"}

fig, axes = plt.subplots(1, 3, figsize=(13.5, 7.5))
for ax, s in zip(axes.flatten(), SCEN):
    col = f"lisa_{s}"
    c = g[col].map(COL).fillna(COL["none"])
    g.plot(color=c, linewidth=0.08, edgecolor="#bbb", ax=ax)
    n_hh = int((g[col] == "HH").sum())
    n_hl = int((g[col] == "HL").sum())
    ax.set_title(f"{TITLES[s]}\nMoran's I = {MORAN[s]:.2f}  ·  HH {n_hh}  ·  HL {n_hl}",
                 fontsize=13)
    ax.set_axis_off(); ax.set_aspect("equal")
    add_inset(ax, c)

legend = [Patch(facecolor=COL[k], edgecolor="#999", label=BV_DESCRIPTIONS[k])
          for k in ("HH", "HL", "LH", "LL", "ns", "none")]
fig.legend(handles=legend, loc="lower center", ncol=2, fontsize=12,
           frameon=False, bbox_to_anchor=(0.5, 0.01))
fig.suptitle("Trapped share by scenario: bivariate local Moran with neighbours' "
             "NZDep2023 (p < 0.05)\nGlobal Moran's I of the trapped share per panel",
             fontsize=16, fontweight="bold")
fig.tight_layout(rect=[0, 0.12, 1, 0.94], w_pad=0.4, h_pad=1.2)
out = "outputs/figures/fig_4_2b_lisa_maps.png"
fig.savefig(out, dpi=160, bbox_inches="tight")
print("saved", out)
