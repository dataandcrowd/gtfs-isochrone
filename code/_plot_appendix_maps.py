"""Appendix maps: job accessibility and deprivation choropleths."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd

sns.set_theme(style="white", context="talk", font_scale=1.05)

g = gpd.read_file("outputs/sa2_equity.gpkg").to_crs(2193)
lisa = gpd.read_file("outputs/od_classification.gpkg").to_crs(2193)
_b = lisa[lisa["lisa_access45"] == "HH"].total_bounds
_pad = 5000
ZOOM = (_b[0]-_pad, _b[1]-_pad, _b[2]+_pad, _b[3]+_pad)


def add_inset(host, plot_fn, loc=(0.60, 0.60, 0.4, 0.4)):
    axins = host.inset_axes(list(loc))
    plot_fn(axins)
    axins.set_xlim(ZOOM[0], ZOOM[2]); axins.set_ylim(ZOOM[1], ZOOM[3])
    axins.set_xticks([]); axins.set_yticks([])
    for sp in axins.spines.values():
        sp.set_visible(True); sp.set_edgecolor("#333"); sp.set_linewidth(1.2)
    host.indicate_inset_zoom(axins, edgecolor="#333", lw=1.2, alpha=0.7)


fig, ax = plt.subplots(1, 2, figsize=(17, 10.5))

# (a) job accessibility choropleth
g.plot(column="access_45min", cmap="viridis", linewidth=0.1, edgecolor="#bbb",
       ax=ax[0], legend=True,
       legend_kwds={"label": "Jobs reachable in 45 min", "shrink": 0.55})
ax[0].set_title("(a) 45-minute job accessibility", loc="left", fontsize=18)
ax[0].set_axis_off(); ax[0].set_aspect("equal")
add_inset(ax[0], lambda a: g.plot(column="access_45min", cmap="viridis",
          linewidth=0.2, edgecolor="#bbb", ax=a, legend=False))

# (b) deprivation choropleth
g.plot(column="NZDep_Decile", cmap="YlOrRd", linewidth=0.1, edgecolor="#999",
       ax=ax[1], legend=True,
       legend_kwds={"label": "NZDep2023 decile (10 = most deprived)", "shrink": 0.55},
       missing_kwds={"color": "#dddddd"})
ax[1].set_title("(b) Deprivation (NZDep2023)", loc="left", fontsize=18)
ax[1].set_axis_off(); ax[1].set_aspect("equal")
add_inset(ax[1], lambda a: g.plot(column="NZDep_Decile", cmap="YlOrRd",
          linewidth=0.2, edgecolor="#999", ax=a, legend=False,
          missing_kwds={"color": "#dddddd"}))

fig.suptitle("Appendix: job accessibility and deprivation across Auckland SA2s",
             fontsize=19, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = "outputs/figures/fig_appendix_maps.png"
fig.savefig(out, dpi=165, bbox_inches="tight")
print("saved", out)
