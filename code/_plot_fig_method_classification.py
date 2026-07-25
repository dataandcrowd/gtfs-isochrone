"""
Methods schematic for section 3.3: how each car commute is classified.

Three panels, drawn on the real study geometry:
    (a) CBD cordon test, using 2c so the double cordon is visible
    (b) Motorway corridor test, using the 3b 2 km buffer
    (c) The two-way classification and the trapped rate

Output: outputs/figures/fig_method_classification.png
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))

OUT = Path("outputs") / "figures"
OUT.mkdir(parents=True, exist_ok=True)

CHARGED   = "#c1272d"   # charged
NOCHARGE  = "#9aa0a6"   # not charged
TRAPPED   = "#7b1113"   # charged and no alternative
ALT       = "#2a7f62"   # has an alternative
CORDON_IN = "#f2b705"
CORDON_OUT= "#d98f8f"
CORRIDOR  = "#2f6b3c"

# Explanatory prose lives in the manuscript body, not inside the figure.
SHOW_CAPTIONS = False


def load():
    sa2 = gpd.read_file("outputs/burden_by_sa2_final.gpkg").to_crs(2193)
    prep = gpd.read_file("data/sa2/sa2_prepared.gpkg",
                         columns=["SA22023_V1_00", "lon", "lat"], ignore_geometry=True)
    prep["k"] = prep["SA22023_V1_00"].astype(str)
    sa2["k"] = sa2["SA22023_V1_00"].astype(str)
    sa2 = sa2.merge(prep[["k", "lon", "lat"]], on="k", how="left")
    cen = gpd.GeoSeries(gpd.points_from_xy(sa2["lon"], sa2["lat"]), crs=4326).to_crs(2193)
    sa2["cx"], sa2["cy"] = cen.x.values, cen.y.values
    od = pd.read_parquet("outputs/intermediate/od_pairs_classified.parquet")
    od["res"] = od["residence_sa2"].astype(str)
    od["wrk"] = od["workplace_sa2"].astype(str)
    return sa2, od


def codes(s):
    g = gpd.read_file(f"data/scenarios/scenario_{s}.gpkg")
    col = next(c for c in g.columns if c.startswith("SA22") and c.endswith("V1_00"))
    return set(g[col].astype(str)), g.to_crs(2193)


def arrow(ax, p, q, colour, ls="-", lw=2.0, z=5, alpha=1.0):
    ax.add_patch(FancyArrowPatch(
        p, q, arrowstyle="-|>", mutation_scale=13, lw=lw, ls=ls,
        color=colour, alpha=alpha, zorder=z, shrinkA=0, shrinkB=0,
        connectionstyle="arc3,rad=0.08"))


def pick(od, sa2, res_pred, wrk_pred, win=None, min_len=3500, used=None):
    """A real OD pair matching the predicates, long enough to read on the map.

    Prefers heavily used pairs, but only among those whose endpoints both sit
    inside the plotting window and that are far enough apart to draw clearly.
    """
    xy = dict(zip(sa2["k"], zip(sa2["cx"], sa2["cy"])))
    sub = od[od["res"].map(res_pred).fillna(False) & od["wrk"].map(wrk_pred).fillna(False)]
    sub = sub[sub["res"].isin(xy) & sub["wrk"].isin(xy) & (sub["res"] != sub["wrk"])]
    if sub.empty:
        return None
    used = used if used is not None else set()
    best = None
    for _, r in sub.nlargest(600, "car_commuters").iterrows():
        a, b = xy[r["res"]], xy[r["wrk"]]
        if win is not None:
            x0, y0, x1, y1 = win
            if not (x0 <= a[0] <= x1 and y0 <= a[1] <= y1 and
                    x0 <= b[0] <= x1 and y0 <= b[1] <= y1):
                continue
        if np.hypot(a[0] - b[0], a[1] - b[1]) < min_len:
            continue
        if (r["res"], r["wrk"]) in used:
            continue
        used.add((r["res"], r["wrk"]))
        best = (a, b)
        break
    return best


def panel_cordon(ax, sa2, od):
    outer, g2c = codes("2c")
    inner, _ = codes("1c")
    ring = outer - inner

    minx, miny, maxx, maxy = g2c.total_bounds
    pad = 5200
    box = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    win = sa2.cx[box[0]:box[2], box[1]:box[3]]
    win.plot(ax=ax, color="#f4f4f2", edgecolor="white", linewidth=0.4, zorder=0)
    sa2[sa2["k"].isin(ring)].dissolve().plot(
        ax=ax, color=CORDON_OUT, edgecolor="#a35555", linewidth=1.2, alpha=.85, zorder=1)
    sa2[sa2["k"].isin(inner)].dissolve().plot(
        ax=ax, color=CORDON_IN, edgecolor="#b8860b", linewidth=1.2, alpha=.95, zorder=2)

    used = set()
    ex = [
        # outside -> inner: crosses BOTH boundaries
        (pick(od, sa2, lambda k: k not in outer, lambda k: k in inner, box, 6000, used), CHARGED, "1"),
        # fringe ring -> inner: crosses the INNER boundary only (the double-cordon case)
        (pick(od, sa2, lambda k: k in ring, lambda k: k in inner, box, 3000, used), CHARGED, "2"),
        # outside -> fringe ring: crosses the OUTER boundary only
        (pick(od, sa2, lambda k: k not in outer, lambda k: k in ring, box, 6000, used), CHARGED, "3"),
        # inner -> inner: intra-cordon, never charged
        (pick(od, sa2, lambda k: k in inner, lambda k: k in inner, box, 1200, used), NOCHARGE, "4"),
        # outside -> outside: neither endpoint in a cordon
        (pick(od, sa2, lambda k: k not in outer, lambda k: k not in outer, box, 6000, used), NOCHARGE, "5"),
    ]
    for pr, col, tag in ex:
        if pr is None:
            continue
        a, b = pr
        charged = col == CHARGED
        arrow(ax, a, b, col, ls="-" if charged else (0, (4, 3)), lw=2.6 if charged else 1.9,
              alpha=1.0 if charged else .95)
        ax.plot(*a, "o", ms=7, mfc="white", mec=col, mew=1.6, zorder=6)
        ax.text(a[0], a[1], tag, fontsize=7.5, ha="center", va="center",
                color=col, zorder=7, fontweight="bold")

    ax.set_title("(a)  CBD cordon test — scenario 2c", loc="left",
                 fontsize=16, fontweight="bold")
    if SHOW_CAPTIONS:
      ax.text(0.02, 0.03,
            "Charged when the workplace lies inside a cordon\n"
            "and the residence outside it. 2c is a double cordon,\n"
            "so a trip from the fringe ring into the centre is\n"
            "charged at the inner boundary.",
            transform=ax.transAxes, fontsize=10.5, va="bottom", zorder=9,
            bbox=dict(boxstyle="round,pad=0.55", fc="white", ec="#cccccc", alpha=.93))
    ax.legend(handles=[
        plt.Rectangle((0, 0), 1, 1, fc=CORDON_IN, ec="#b8860b", label="Inner cordon (city centre + fringe)"),
        plt.Rectangle((0, 0), 1, 1, fc=CORDON_OUT, ec="#a35555", label="Outer cordon (isthmus ring)"),
        Line2D([], [], color=CHARGED, lw=2.4, label="Charged commute"),
        Line2D([], [], color=NOCHARGE, lw=1.8, ls="--", label="Not charged"),
    ], loc="upper right", fontsize=16, framealpha=.94)


def panel_motorway(ax, sa2, od):
    poly = gpd.read_file("data/scenarios/scenario_3b.gpkg").to_crs(2193)
    corridor = poly.geometry.union_all()

    minx, miny, maxx, maxy = poly.total_bounds
    pad = 4000
    box = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    win = sa2.cx[box[0]:box[2], box[1]:box[3]]
    win.plot(ax=ax, color="#f4f4f2", edgecolor="white", linewidth=0.4, zorder=0)
    poly.plot(ax=ax, color=CORRIDOR, alpha=.26, edgecolor=CORRIDOR, linewidth=1.1, zorder=1)

    # the priced alignment itself, so the buffer reads as a corridor not a blob
    try:
        mw = gpd.read_file("data/osm/auckland.osm.pbf", layer="lines", columns=["highway"],
                           where="highway = 'motorway'").to_crs(2193)
        mw[mw.geometry.intersects(corridor)].plot(
            ax=ax, color=CORRIDOR, linewidth=1.5, alpha=.95, zorder=2)
    except Exception:
        pass

    xy = dict(zip(sa2["k"], zip(sa2["cx"], sa2["cy"])))
    hits, misses, used = [], [], set()
    for _, r in od.nlargest(4000, "car_commuters").iterrows():
        if r["res"] not in xy or r["wrk"] not in xy or r["res"] == r["wrk"]:
            continue
        a, b = xy[r["res"]], xy[r["wrk"]]
        if not all(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] for p in (a, b)):
            continue
        if np.hypot(a[0] - b[0], a[1] - b[1]) < 7000:
            continue
        crosses = LineString([a, b]).intersects(corridor)
        if crosses and len(hits) < 3:
            hits.append((a, b))
        elif not crosses and len(misses) < 2:
            misses.append((a, b))
        if len(hits) >= 3 and len(misses) >= 2:
            break
    for a, b in hits:
        arrow(ax, a, b, CHARGED, lw=2.6)
        ax.plot(*a, "o", ms=7, mfc="white", mec=CHARGED, mew=1.6, zorder=6)
    for a, b in misses:
        arrow(ax, a, b, NOCHARGE, ls=(0, (4, 3)), lw=1.9, alpha=.95)
        ax.plot(*a, "o", ms=7, mfc="white", mec=NOCHARGE, mew=1.6, zorder=6)

    ax.set_title("(b)  Motorway corridor test — scenario 3b", loc="left",
                 fontsize=16, fontweight="bold")
    if SHOW_CAPTIONS:
      ax.text(0.02, 0.03,
            "Charged when the straight-line desire path between\n"
            "the population-weighted residence and workplace\n"
            "centroids intersects the corridor. The corridor is a\n"
            "2 km buffer of the priced motorway alignment.",
            transform=ax.transAxes, fontsize=10.5, va="bottom", zorder=9,
            bbox=dict(boxstyle="round,pad=0.55", fc="white", ec="#cccccc", alpha=.93))
    ax.legend(handles=[
        plt.Rectangle((0, 0), 1, 1, fc=CORRIDOR, alpha=.32, ec=CORRIDOR, label="Priced corridor (2 km buffer)"),
        Line2D([], [], color=CHARGED, lw=2.4, label="Desire path intersects — charged"),
        Line2D([], [], color=NOCHARGE, lw=1.8, ls="--", label="No intersection — not charged"),
    ], loc="upper right", fontsize=16, framealpha=.94)


def panel_matrix(ax, od=None):
    """The two-way classification only: no counts, no formula.

    Counts and the trapped-rate definition are given in the manuscript body.
    """
    ax.set_xlim(0, 10)
    ax.set_ylim(4.2, 9.4)
    ax.axis("off")
    ax.set_title("(c)  Classification of each car commute", loc="left",
                 fontsize=16, fontweight="bold")

    x0, y0, w, h = 2.6, 4.6, 3.3, 1.9
    labels = {(1, 0): "Trapped payer", (1, 1): "Pays, has\nalternative",
              (0, 0): "Not charged,\nno alternative", (0, 1): "Not charged,\nhas alternative"}
    for (c, a), lab in labels.items():
        px = x0 + (0 if a == 0 else w)
        py = y0 + (h if c == 1 else 0)
        face = TRAPPED if (c, a) == (1, 0) else ("#efefef" if c == 0 else "#f6d9d9")
        txt = "white" if (c, a) == (1, 0) else "#222222"
        ax.add_patch(Rectangle((px, py), w, h, fc=face, ec="#8a8a8a", lw=1.1))
        ax.text(px + w / 2, py + h * .5, lab, ha="center", va="center",
                fontsize=15, color=txt, fontweight="bold" if (c, a) == (1, 0) else "normal")

    ax.text(x0 - .25, y0 + h * 1.5, "Charged", rotation=90, ha="center", va="center", fontsize=14)
    ax.text(x0 - .25, y0 + h * .5, "Not charged", rotation=90, ha="center", va="center", fontsize=14)
    ax.text(x0 + w * .5, y0 + 2 * h + .3, "No 45-min\nPT alternative", ha="center", va="bottom", fontsize=14)
    ax.text(x0 + w * 1.5, y0 + 2 * h + .3, "Has 45-min\nPT alternative", ha="center", va="bottom", fontsize=14)


def panel_sensitivity(ax):
    """How the charged count and the equity reading respond to corridor width."""
    s = pd.read_csv("outputs/scenario_geometry_sensitivity.csv")
    s = s[s["half_width_m"].notna()]
    g = s.groupby("half_width_m").agg(charged=("charged_commuters", "mean"),
                                      ci=("CI_nzdep", "mean"),
                                      ci_eq=("CI_income_eq", "mean")).reset_index()
    x = g["half_width_m"] / 1000

    ax.plot(x, g["charged"] / 1000, "o-", color=CHARGED, lw=2.4, ms=7,
            label="Charged commuters (thousands)")
    ax.set_xlabel("Corridor half-width (km)", fontsize=14)
    ax.set_ylabel("Charged commuters (thousands)", color=CHARGED, fontsize=14)
    ax.tick_params(axis="y", labelcolor=CHARGED, labelsize=13)
    ax.tick_params(axis="x", labelsize=13)
    ax.axvline(2.0, color="#888888", ls=":", lw=1.6, zorder=0)
    ax.annotate("adopted width", xy=(2.0, ax.get_ylim()[1]), xytext=(-8, -6),
                textcoords="offset points", fontsize=13, color="#666666",
                va="top", ha="right", rotation=90)

    ax2 = ax.twinx()
    ax2.plot(x, g["ci"], "s--", color="#1f4e79", lw=2.0, ms=6, label="CI (NZDep2023)")
    ax2.plot(x, g["ci_eq"], "^--", color="#2a7f62", lw=2.0, ms=6, label="CI (equivalised income)")
    ax2.axhspan(-0.05, 0.05, color="#dddddd", alpha=.55, zorder=0)
    ax2.set_ylabel("Concentration Index", fontsize=14)
    ax2.set_ylim(-0.22, 0.06)
    ax2.tick_params(axis="y", labelsize=13)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="center left", fontsize=16, framealpha=.94)
    ax.set_title("(d)  Sensitivity to corridor width", loc="left",
                 fontsize=16, fontweight="bold")
    if SHOW_CAPTIONS:
      ax.text(0.985, 0.055,
            "The charged headcount scales with corridor width, but the\n"
            "equity reading does not: across ±250 m to ±3 km the CI stays\n"
            "inside one band on both deprivation measures. Shaded band\n"
            "marks |CI| < 0.05, read as neutral.",
            transform=ax.transAxes, fontsize=10.5, va="bottom", ha="right", zorder=9,
            bbox=dict(boxstyle="round,pad=0.55", fc="white", ec="#cccccc", alpha=.93))


def _finish_map(ax):
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor("#cccccc")


def main():
    sa2, od = load()
    panels = [
        ("a_cordon",      lambda ax: panel_cordon(ax, sa2, od),   True,  (8.6, 8.0)),
        ("b_motorway",    lambda ax: panel_motorway(ax, sa2, od), True,  (8.6, 8.0)),
        ("c_classification", lambda ax: panel_matrix(ax),         False, (8.6, 5.0)),
        ("d_sensitivity", panel_sensitivity,                      False, (8.6, 6.4)),
    ]

    # one PNG per panel
    for name, draw, is_map, size in panels:
        fig, ax = plt.subplots(figsize=size)
        draw(ax)
        if is_map:
            _finish_map(ax)
        fig.tight_layout()
        dest = OUT / f"fig_method_{name}.png"
        fig.savefig(dest, dpi=220, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"Written: {dest}")

    # combined 2x2 for reference
    fig, axes = plt.subplots(2, 2, figsize=(17.5, 14.5))
    flat = [axes[0][0], axes[0][1], axes[1][0], axes[1][1]]
    for (name, draw, is_map, _), ax in zip(panels, flat):
        draw(ax)
        if is_map:
            _finish_map(ax)
    fig.tight_layout(h_pad=2.0, w_pad=2.0)
    dest = OUT / "fig_method_classification.png"
    fig.savefig(dest, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Written: {dest}")


if __name__ == "__main__":
    main()
