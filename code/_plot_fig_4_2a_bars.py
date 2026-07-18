"""Figure 4.2a: scenario charge burden (standalone bar chart)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

sns.set_theme(style="whitegrid", context="talk", font_scale=1.2)

e = pd.read_csv("outputs/equity_summary_final.csv").set_index("scenario")
order = ["1a", "1c", "2c", "3b", "3c", "3e"]
e = e.loc[order]

fig, ax = plt.subplots(figsize=(11, 7.5))
xpos = np.arange(len(order))
withalt = (e["charged_commuters"] - e["trapped_commuters"]) / 1000
trapped = e["trapped_commuters"] / 1000
ax.bar(xpos, withalt, color="#2C7A7B", label="Pays, with alternative")
ax.bar(xpos, trapped, bottom=withalt, color="#D4421E",
       label="Pays, without alternative (trapped)")
for i in range(len(order)):
    ch = int(e["charged_commuters"].iloc[i])
    tr = int(e["trapped_commuters"].iloc[i])
    pct = e["trapped_pct"].iloc[i]
    top = withalt.iloc[i] + trapped.iloc[i]
    ax.text(i, top + 3, f"{ch:,} charged\n{tr:,} trapped\n({pct:.0f}%)",
            ha="center", va="bottom", fontsize=11, color="#222")
ax.set_xticks(xpos); ax.set_xticklabels(order, fontsize=15)
ax.set_xlabel("Scenario", fontsize=16)
ax.set_ylabel("Charged car commuters (thousands)", fontsize=16)
ax.set_title("Charge burden by scenario", fontsize=18)
ax.legend(fontsize=13, loc="upper left")
ax.set_ylim(0, (withalt + trapped).max() * 1.30)
fig.tight_layout()
out = "outputs/figures/fig_4_2a_burden_bars.png"
fig.savefig(out, dpi=170, bbox_inches="tight")
print("saved", out)
