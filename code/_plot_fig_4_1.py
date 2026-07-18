"""Figure 4.1: baseline distributions (accessibility, deprivation, concentration curve)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd
import pandas as pd
import numpy as np

sns.set_theme(style="whitegrid", context="talk", font_scale=1.2)

g = gpd.read_file("data/sa2/sa2_equity.gpkg")
g["SA22023_V1_00"] = g["SA22023_V1_00"].astype(str)
sa1 = pd.read_excel("data/deprivation/NZDep2023_SA1_withHigherGeo.xlsx")
sa1["SA22023_code"] = sa1["SA22023_code"].astype(str)
g["pop"] = g["SA22023_V1_00"].map(
    sa1.groupby("SA22023_code")["URPopnSA1_2023"].sum()).fillna(0)

TT, LB = 18, 16
fig, axes = plt.subplots(2, 2, figsize=(15, 13.5))
ax = [axes[0, 0], axes[0, 1], axes[1, 0]]
axes[1, 1].axis("off")

# (a) job accessibility distribution
acc = g["access_45min"].dropna() / 1000
sns.histplot(acc, bins=40, kde=True, color="#4C72B0", ax=ax[0],
             edgecolor="white", alpha=0.65, line_kws={"lw": 2.5})
ax[0].axvline(g.access_45min.median()/1000, color="#C44E52", ls="--", lw=2.5,
              label=f"median {g.access_45min.median():,.0f}")
ax[0].axvline(g.access_45min.quantile(.75)/1000, color="#55A868", ls="--", lw=2.5,
              label=f"Q75 {g.access_45min.quantile(.75):,.0f}")
ax[0].set_xlabel("Jobs reachable in 45 min (thousands)", fontsize=LB)
ax[0].set_ylabel("Number of SA2s", fontsize=LB)
ax[0].set_title("(a) Job accessibility", loc="left", fontsize=TT)
ax[0].legend(fontsize=12)

# (b) mean accessibility by NZDep decile
d = g.dropna(subset=["NZDep_Decile"]).copy()
d["NZDep_Decile"] = d["NZDep_Decile"].astype(int)
d["acc_k"] = d["access_45min"] / 1000
sns.barplot(data=d, x="NZDep_Decile", y="acc_k", hue="NZDep_Decile",
            palette="YlOrRd", legend=False, errorbar=("ci", 95),
            err_kws={"linewidth": 1.5}, capsize=0.3, ax=ax[1])
ax[1].set_xlabel("NZDep2023 decile (1 = least, 10 = most deprived)", fontsize=LB)
ax[1].set_ylabel("Mean jobs reachable in 45 min (thousands)", fontsize=LB)
ax[1].set_title("(b) Mean accessibility by deprivation decile", loc="left", fontsize=TT)

# (c) concentration curve (population-weighted)
def conc(col):
    d = g[["NZDep2023", col, "pop"]].dropna().sort_values("NZDep2023", ascending=False)
    w, h = d["pop"].values, d[col].values
    x = np.concatenate([[0], np.cumsum(w)/w.sum()])
    y = np.concatenate([[0], np.cumsum(w*h)/np.sum(w*h)])
    return x, y, round(2*np.trapezoid(y - x, x), 3)
ax[2].plot([0, 1], [0, 1], color="#444", ls="--", lw=2, label="Line of equality")
for col, c, lab in [("access_45min", "#4C72B0", "45-min"),
                    ("access_30min", "#DD8452", "30-min")]:
    x, y, ci = conc(col)
    ax[2].plot(x, y, color=c, lw=3, label=f"{lab} (CI = {ci:+.3f})")
ax[2].set_xlabel("Cumulative share of population\n(most deprived → least deprived)",
                 fontsize=LB)
ax[2].set_ylabel("Cumulative share of jobs", fontsize=LB)
ax[2].set_title("(c) Concentration curve", loc="left", fontsize=TT)
ax[2].set_xlim(0, 1); ax[2].set_ylim(0, 1); ax[2].set_aspect("equal")
ax[2].legend(fontsize=12, loc="upper left")

for a in ax:
    a.tick_params(labelsize=13)
fig.suptitle("Baseline 45-minute job accessibility and deprivation",
             fontsize=21, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
out = "outputs/figures/fig_4_1_distributions.png"
fig.savefig(out, dpi=165, bbox_inches="tight")
print("saved", out)
