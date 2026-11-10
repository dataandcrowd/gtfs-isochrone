# /// script
# requires-python = ">=3.10"
# dependencies = ["plotnine>=0.15", "geopandas>=1.0", "pyogrio"]
# ///
"""Figure 3: baseline public transport job accessibility and deprivation.

Four panels for the 504 urban SA2s, all describing the baseline (no congestion
charge) situation:
  (a) public transport job accessibility map (45 min)
  (b) NZDep2023 decile map
  (c) median accessibility with interquartile range by decile
  (d) population-weighted concentration curve

Drawn with plotnine in Arial. Run from the repository root with uv, which
builds an isolated environment from the header above:

    uv run code/_plot_fig_3_baseline.py
"""
import warnings

import geopandas as gpd
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from plotnine import (
    aes, annotate, coord_fixed, element_blank, element_line, element_rect,
    element_text, geom_abline, geom_col, geom_errorbar, geom_line, geom_map,
    geom_ribbon, geom_segment, geom_text, ggplot, guide_colorbar, guide_legend,
    guides, labs, scale_color_manual, scale_fill_cmap, scale_fill_manual,
    scale_linetype_manual, scale_x_continuous, scale_y_continuous, theme,
    theme_minimal, theme_void,
)

warnings.filterwarnings("ignore")

FONT = "Arial"
INK = "#222222"
NAME = "SA22026_V1_00_NAME"
OUT = "outputs/figures/fig_3_baseline_pt_accessibility.png"
HALO = [pe.withStroke(linewidth=4, foreground="white")]

g = gpd.read_file("data/sa2/sa2_equity.gpkg").to_crs(2193)
land = gpd.read_file("data/sa2/auckland_sa2.gpkg").to_crs(2193)

x0, y0, x1, y1 = g.total_bounds
PAD = 3000
XLIM, YLIM = (x0 - PAD, x1 + PAD), (y0 - PAD, y1 + PAD)

# ── shared styling ───────────────────────────────────────────────────────────
TITLE = element_text(family=FONT, size=20, weight="bold", ha="left", color=INK)
map_theme = theme_void() + theme(
    text=element_text(family=FONT, color=INK),
    plot_title=TITLE,
    axis_text=element_blank(),
    axis_title=element_blank(),
    axis_ticks=element_blank(),
    legend_position="bottom",
    legend_title_position="top",
    legend_title=element_text(size=16, ha="center"),
    legend_text=element_text(size=14),
    plot_margin=0.02,
    plot_background=element_rect(fill="white", color="white"),
)
chart_theme = theme_minimal() + theme(
    text=element_text(family=FONT, color=INK),
    plot_title=TITLE,
    axis_title=element_text(size=17),
    axis_text=element_text(size=15, color="#444444"),
    axis_line=element_line(color="#888888", size=0.6),
    axis_ticks=element_line(color="#888888", size=0.6),
    panel_grid_major=element_line(color="#e9e9e9", size=0.5),
    panel_grid_minor=element_blank(),
    plot_margin=0.02,
    plot_background=element_rect(fill="white", color="white"),
)


def place_labels(spec, colours):
    """Label positions: SA2 centroid matched by name, offset by (dx, dy) metres."""
    rows = []
    for text, pattern, dx, dy, group in spec:
        geom = g.loc[g[NAME].str.contains(pattern, regex=True)].geometry.union_all()
        rows.append(dict(label=text, x=geom.centroid.x, y=geom.centroid.y,
                         lx=geom.centroid.x + dx, ly=geom.centroid.y + dy,
                         colour=colours[group]))
    return pd.DataFrame(rows)


def label_layers(df):
    """Leader lines and haloed bold labels for a map panel."""
    return [
        geom_segment(aes(x="x", y="y", xend="lx", yend="ly"), data=df,
                     color=df["colour"].tolist(), size=0.5, inherit_aes=False),
        geom_text(aes(x="lx", y="ly", label="label"), data=df,
                  color=df["colour"].tolist(), size=14.5, fontweight="bold",
                  family=FONT, path_effects=HALO, inherit_aes=False),
    ]


def base_map():
    return (ggplot()
            + geom_map(land, fill="#f1f1ef", color="none")
            + coord_fixed(xlim=XLIM, ylim=YLIM, expand=False)
            + map_theme)


# ── (a) baseline public transport job accessibility ──────────────────────────
ga = g.assign(access=g["access_45min"].clip(lower=100))
lab_a = place_labels([
    ("Massey",    "^Massey Red Hills$",        2500,  6000, "low"),
    ("Titirangi", "^Titirangi South$",        -5500,  1500, "low"),
    ("Ormiston",  "^Ormiston (South )?East$",  2500, -3500, "low"),
    ("Papakura",  "^Papakura East$",          -3000, -4500, "low"),
], {"low": "#3b1f6b"})
pa = (base_map()
      + geom_map(aes(fill="access"), data=ga, color="white", size=0.08)
      + scale_fill_cmap(
          "viridis", trans="log10",
          limits=(100, float(ga["access"].max())),
          breaks=[1e2, 1e3, 1e4, 1e5],
          labels=["100", "1,000", "10,000", "100,000"],
          name="Jobs reachable by public transport in 45 min")
      + guides(fill=guide_colorbar(nbin=200, display="gradient"))
      + label_layers(lab_a)
      + labs(title="(a) Baseline public transport\njob accessibility")
      + theme(legend_key_width=300, legend_key_height=16))

# ── (b) deprivation ──────────────────────────────────────────────────────────
dep_cols = [mpl.colors.to_hex(c)
            for c in mpl.colormaps["YlOrRd"](np.linspace(0.02, 1, 10))]
gb = g.dropna(subset=["NZDep_Decile"]).copy()
gb["decile"] = pd.Categorical(gb["NZDep_Decile"].astype(int), categories=range(1, 11))
lab_b = place_labels([
    ("Devonport", "^Devonport$",          5500,  6500, "least"),
    ("Remuera",   "^Remuera North$",     11000,  2000, "least"),
    ("Henderson", "^Henderson Central$", -1000,  4500, "most"),
    ("Māngere",   "^M.ngere Central$",  -10000, -2500, "most"),
    ("Manurewa",  "^Manurewa Central$",  -7500, -4500, "most"),
    ("Papakura",  "^Papakura Central$",    500, -5500, "most"),
], {"least": "#1f5fa8", "most": "#8f1d1d"})
pb = (base_map()
      + geom_map(g, fill="#dddddd", color="white", size=0.08)   # no-data SA2s
      + geom_map(aes(fill="decile"), data=gb, color="white", size=0.08)
      + scale_fill_manual(values=dep_cols, drop=False,
                          name="NZDep2023 decile (10 = most deprived)")
      + guides(fill=guide_legend(nrow=1))
      + label_layers(lab_b)
      + labs(title="(b) Deprivation\n(NZDep2023 decile)")
      + theme(legend_key_width=34, legend_key_height=16,
              legend_key_spacing_x=0, legend_text_position="bottom"))

# ── (c) median accessibility with IQR by decile ──────────────────────────────
d = g.dropna(subset=["NZDep_Decile", "access_45min"]).copy()
d["decile"] = d["NZDep_Decile"].astype(int)
q = (d.groupby("decile")["access_45min"].quantile([.25, .5, .75]).unstack() / 1000)
q.columns = ["q25", "median", "q75"]
q = q.reset_index()
q["label"] = q["median"].map("{:.0f}k".format)
q["fill"] = [dep_cols[i - 1] for i in q["decile"]]
q["ink"] = [INK if i <= 6 else "white" for i in q["decile"]]
pc = (ggplot(q, aes("decile", "median"))
      + geom_col(fill=q["fill"].tolist(), width=0.74)
      + geom_errorbar(aes(ymin="q25", ymax="q75"), width=0.22,
                      color="#6b6b6b", size=0.6)
      # median labels sit at the foot of each bar, below every lower quartile
      + geom_text(aes(label="label", y=6.5), size=14, fontweight="bold",
                  family=FONT, color=q["ink"].tolist())
      + scale_x_continuous(breaks=range(1, 11), limits=(0.4, 11.0), expand=(0, 0))
      + scale_y_continuous(expand=(0, 0, 0.04, 0))
      + labs(title="(c) Baseline public transport accessibility\n"
                   "by deprivation decile",
             x="NZDep2023 decile (1 = least, 10 = most deprived)",
             y="Median jobs reachable by public transport in 45 min\n"
               "(thousands), with interquartile range")
      + chart_theme
      + theme(panel_grid_major_x=element_blank()))

# ── (d) concentration curve (population-weighted) ────────────────────────────
c = (g[["NZDep2023", "access_45min", "pop"]].dropna()
       .sort_values("NZDep2023", ascending=False))
w, h = c["pop"].values, c["access_45min"].values
cx = np.concatenate([[0], np.cumsum(w) / w.sum()])
cy = np.concatenate([[0], np.cumsum(w * h) / np.sum(w * h)])
# Ranked from most to least deprived, so a curve below the diagonal (jobs
# concentrated among the less deprived) gives a positive index.
ci = 2 * np.trapezoid(cx - cy, cx)
print(f"concentration index = {ci:+.3f}")

EQ = "Line of equality"
CC = f"Baseline public transport accessibility,\n45 min (CI = {ci:+.3f})"
curve = pd.concat([
    pd.DataFrame({"x": [0, 1], "y": [0, 1], "series": EQ}),
    pd.DataFrame({"x": cx, "y": cy, "series": CC}),
])
curve["series"] = pd.Categorical(curve["series"], categories=[EQ, CC])
pd_ = (ggplot(curve, aes("x", "y"))
       + geom_ribbon(aes(x="x", ymin="y", ymax="x"),
                     data=pd.DataFrame({"x": cx, "y": cy}),
                     fill="#C1272D", alpha=0.10, inherit_aes=False)
       + geom_line(aes(color="series", linetype="series"), size=1.1)
       + scale_color_manual(values=["#444444", "#C1272D"], name=" ")
       + scale_linetype_manual(values=["dashed", "solid"], name=" ")
       + scale_x_continuous(limits=(0, 1), expand=(0, 0),
                            breaks=np.arange(0, 1.01, 0.2))
       + scale_y_continuous(limits=(0, 1), expand=(0, 0),
                            breaks=np.arange(0, 1.01, 0.2))
       + coord_fixed()
       + labs(title="(d) Concentration curve, baseline\n"
                    "public transport accessibility",
              x="Cumulative share of population\n"
                "(most deprived to least deprived)",
              y="Cumulative share of jobs reachable\nby public transport")
       + chart_theme
       + theme(legend_position=(0.03, 0.97),
               legend_title=element_blank(),
               legend_text=element_text(size=14, ha="left"),
               legend_background=element_rect(fill="white", color="#dddddd"),
               legend_key_width=26))

# ── compose ──────────────────────────────────────────────────────────────────
fig = ((pa | pb) / (pc | pd_)) & theme(figure_size=(15, 15))
fig.save(OUT, dpi=165)
print("saved", OUT)
