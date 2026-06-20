"""Figure 4.2b: trapped-payer LISA clusters for all six scenarios (2x3)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd
import pandas as pd
from matplotlib.patches import Patch

sns.set_theme(style="white", context="talk", font_scale=1.0)

g = gpd.read_file("outputs/od_classification.gpkg").to_crs(2193)

# global Moran's I of trapped commuters, per scenario
_m = pd.read_csv("outputs/od_morans_i.csv")
MORAN = _m[_m.variable == "od_trapped_commuters"].set_index("scenario")["morans_I"].to_dict()

# central-Auckland zoom extent (from the accessibility high-high cluster)
_b = g[g["lisa_access45"] == "HH"].total_bounds
_pad = 5000
ZOOM = (_b[0]-_pad, _b[1]-_pad, _b[2]+_pad, _b[3]+_pad)


def add_inset(host, color_series):
    axins = host.inset_axes([0.62, 0.62, 0.38, 0.38])
    g.plot(color=color_series, linewidth=0.15, edgecolor="#aaa", ax=axins)
    axins.set_xlim(ZOOM[0], ZOOM[2]); axins.set_ylim(ZOOM[1], ZOOM[3])
    axins.set_xticks([]); axins.set_yticks([])
    for sp in axins.spines.values():
        sp.set_visible(True); sp.set_edgecolor("#333"); sp.set_linewidth(1)
    host.indicate_inset_zoom(axins, edgecolor="#333", lw=1, alpha=0.6)

SCEN = ["1a", "1c", "2c", "3b", "3c", "3e"]
TITLES = {"1a": "1a City centre cordon", "1c": "1c City centre + fringe",
          "2c": "2c Isthmus double cordon", "3b": "3b Core motorways",
          "3c": "3c Core motorways + CBD", "3e": "3e Motorway hotspots"}
COL = {"HH": "#D4421E", "LL": "#2C7BB6", "HL": "#FDAE61", "LH": "#ABD9E9", "ns": "#EEEEEE"}

fig, axes = plt.subplots(2, 3, figsize=(13.5, 13))
for ax, s in zip(axes.flatten(), SCEN):
    col = f"lisa_trapped_{s}"
    c = g[col].map(COL).fillna("#EEEEEE")
    g.plot(color=c, linewidth=0.08, edgecolor="#aaa", ax=ax)
    n_hh = int((g[col] == "HH").sum())
    ax.set_title(f"{TITLES[s]}\nMoran's I = {MORAN[s]:.2f}  ·  {n_hh} hotspots",
                 fontsize=13)
    ax.set_axis_off(); ax.set_aspect("equal")
    add_inset(ax, c)

legend = [Patch(facecolor=COL[k], label=l) for k, l in
          [("HH", "Trapped hotspot (high-high)"), ("LL", "Low-low"),
           ("HL", "High-low outlier"), ("LH", "Low-high outlier"),
           ("ns", "Not significant")]]
fig.legend(handles=legend, loc="lower center", ncol=5, fontsize=13,
           frameon=False, bbox_to_anchor=(0.5, 0.02))
fig.suptitle("Trapped-payer clusters by scenario (local Moran's I; "
             "global Moran's I per panel, all p < 0.001)",
             fontsize=17, fontweight="bold")
fig.tight_layout(rect=[0, 0.05, 1, 0.96], w_pad=0.4, h_pad=1.2)
out = "outputs/figures/fig_4_2b_lisa_maps.png"
fig.savefig(out, dpi=160, bbox_inches="tight")
print("saved", out)
