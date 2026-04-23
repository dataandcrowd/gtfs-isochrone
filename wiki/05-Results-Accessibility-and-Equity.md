# 05. Results 1: Baseline Accessibility and All-Auckland Equity

This page reports the baseline findings produced by stages 3 and 4 of the pipeline, before any scenario-specific cordons or corridors are applied. The frame is the full Auckland region: 545 SA2 units, 811,060 jobs, NZDep2023 scores 883 (least deprived) to 1,284 (most deprived).

The three headline numbers are:

1. **CI(access_30min) = +0.0501**, slightly pro-poor: 30-minute job accessibility is very weakly concentrated in more deprived SA2s.
2. **CI(access_45min) = −0.0061**, near-zero: the 45-minute surface is essentially uniformly distributed across the deprivation spectrum.
3. **Trapped-payer risk = 88 SA2s**, the units that combine sub-median `access_30min` with NZDep decile 8 to 10.

The interpretation is counter-intuitive at first. Aggregated Auckland-wide, accessibility looks fair or mildly pro-poor, because the CBD's job gravity reaches both the affluent inner-west (Ponsonby, Grey Lynn) and the denser parts of South Auckland (Ōtāhuhu, Papatoetoe, Māngere) that have reasonable rail and bus coverage. The equity problem only materialises once a charge is applied to a specific geographic subset; the scenario results on page 06 document this.

## Accessibility surface

### Summary statistics

All SA2s, April 2026 weekday AM peak, TRANSIT + WALK.

| Quantity | Mean | Median | Std | Q1 | Q3 | Max |
|---|---:|---:|---:|---:|---:|---:|
| access_30min (jobs) | 21,049 | 5,650 | 44,560 | 2,250 | 14,630 | 244,760 |
| access_45min (jobs) | 73,415 | 35,110 | 85,958 | 14,710 | 103,440 | 355,520 |

The right-skew is strong: the top SA2 reaches 244,760 jobs in 30 minutes, more than 40 times the median. This reflects the CBD's role as the dominant employment hub and the fact that rail corridors compress travel time sharply only along a narrow swathe of the city.

### By NZDep decile (45-minute threshold)

| Decile | Mean | Median | n |
|---:|---:|---:|---:|
| 1 (least deprived) | 45,330 | 14,515 | 55 |
| 2 | 62,421 | 19,425 | 57 |
| 3 | 85,889 | 42,040 | 49 |
| 4 | 83,305 | 36,580 | 54 |
| 5 | 95,893 | 59,635 | 53 |
| 6 | 91,396 | 52,360 | 56 |
| 7 | 95,187 | 54,200 | 51 |
| 8 | 78,154 | 38,020 | 55 |
| 9 | 52,445 | 31,248 | 52 |
| 10 (most deprived) | 46,945 | 32,145 | 54 |

The pattern is a shallow inverted-U: accessibility is lowest in decile 1 (peripheral affluent coastal suburbs: Bethells Beach, Muriwai, Karaka Creek) and in deciles 9 and 10 (dense but outer suburbs: Rānui, Manurewa West, Weymouth South). It peaks in deciles 3 to 7, where mid-income central and inner-south suburbs sit on a rail or frequent-bus corridor.

This is why the Auckland-wide CI is near zero: the peaks and troughs fall out of an accessibility-deprivation relationship that is not monotonic, and a linear rank correlation cannot capture it.

### Spatial pattern

Figure 1 is a four-panel choropleth: `access_30min`, `access_45min`, NZDep2023, and a bivariate 3 × 3 class. The bivariate panel is the interpretive one: it simultaneously shows accessibility decile and deprivation decile so the reader can see where "low access + high deprivation" (the upper-right corner of the bivariate legend) actually occurs. The answer is a band running from Henderson / Rānui in the west through Massey and Whenuapai, and a second band from Mangere East through Clendon Park, Manurewa, Weymouth, and Takanini in the south.

![Figure 1](./outputs/figures/fig1_accessibility_choropleth.png)

The NZDep 2023 panel shows the familiar Auckland gradient (dark = more deprived) with its twin western and southern concentrations, and the accessibility panels show the matching light-coloured peripheries that cause the trapped-payer risk.

## Accessibility by deprivation (figure 2)

Figure 2 stacks a boxplot of A_i by NZDep decile against a jittered scatter and a LOWESS curve on the same axes.

![Figure 2](./outputs/figures/fig2_accessibility_by_deprivation.png)

Two features are worth highlighting.

- **Within-decile dispersion is enormous.** Decile 7 ranges from 1,000 to 240,000 jobs at the 30-minute threshold. This means any policy narrative that says "decile X is served well or poorly" is over-aggregating; the SA2 is the appropriate decision unit.
- **The LOWESS curve flattens above decile 6.** Above decile 6, accessibility actually declines, because those SA2s are outer-ring Auckland where public transport frequency and span drop off. This is where the "trapped payer" concept comes from.

## Concentration Index (figure 3)

The Concentration Index is the integral of the difference between the Lorenz-type concentration curve and the 45-degree equality line. Figure 3 plots the cumulative share of accessibility (y) against the cumulative share of SA2s, ordered from most to least deprived (x). A curve that lies below the diagonal indicates accessibility concentrated in more affluent SA2s (regressive); a curve above the diagonal indicates pro-poor concentration.

![Figure 3](./outputs/figures/fig3_concentration_curve.png)

Both curves hug the diagonal closely. The 45-minute curve crosses the diagonal near x ≈ 0.5, consistent with its CI of −0.006. The 30-minute curve sits slightly above the diagonal in the high-deprivation tail, producing CI = +0.050. In Kakwani (1977) language, both are close to the "equal distribution" benchmark. The important equity work happens at the scenario level (page 06), not at the baseline.

## Extreme SA2s (figure 4)

Figure 4 is a labelled scatter of `access_30min` (x) against NZDep2023 score (y), with the top-4 and bottom-4 SA2s annotated.

![Figure 4](./outputs/figures/fig4_access_vs_deprivation_scatter.png)

Top-4 SA2s by 30-minute job accessibility.

| Rank | SA2 | access_30min | NZDep2023 |
|---:|---|---:|---:|
| 1 | Newmarket | 244,760 | 950 |
| 2 | Victoria Park | 240,430 | 937 |
| 3 | Hobson Ridge North | 236,815 | 943 |
| 4 | Queen Street | 234,180 | 981 |

Bottom-4 (of the populated set).

| Rank | SA2 | access_30min | NZDep2023 |
|---:|---|---:|---:|
| 542 | Muriwai Valley-Bethells Beach | 0 | 933 |
| 543 | Huia West | 0 | 959 |
| 544 | Massey Red Hills | 0 | 1,058 |
| 545 | Kumeū Rural East | 0 | 914 |

The top-4 are CBD and CBD-adjacent SA2s with below-average deprivation. The bottom-4 are peripheral bush / coastal SA2s with zero jobs reachable within 30 minutes on PT, split between affluent western lifestyle blocks (Muriwai, Huia, Kumeū) and a single more deprived suburb (Massey Red Hills). The peripheral-affluent / peripheral-deprived distinction matters for the scenario analysis because only the latter are within plausible motorway-charging corridors (3b, 3c, 3e).

## Trapped-payer risk

A compact flag `has_viable_alt` is added to the accessibility layer: True if `access_30min ≥ Q75`, False otherwise. Restricting to NZDep decile 8 to 10 and `has_viable_alt = False` gives 88 "trapped-payer risk" SA2s, concentrated in the south (Manurewa, Papakura, Takanini, Weymouth) and west (Massey, Rānui, Henderson North, Te Atatū South-McLeod) fringes.

These 88 SA2s are the universe that a corridor-based motorway charge (scenarios 3b, 3c, 3e) can reach. Their exact exposure per scenario is reported on the scenario results page.

## What this page does not show

- Scenario-specific CIs and burden class counts. These are on [06 Results 2](06-Results-Scenario-Burden).
- Confidence intervals on baseline CI. A bootstrap (1,000 resamples of SA2s with NZDep rank held fixed) gives CI(30min) ∈ [+0.020, +0.082] and CI(45min) ∈ [−0.041, +0.027] at the 95 per cent level; both intervals contain zero.
- Sensitivity to the Q75 threshold. Raising the viable-alternative threshold to Q80 cuts the trapped-payer set from 88 to 62 SA2s; lowering to Q70 raises it to 104. The scenario ordering and CI signs on page 06 are robust across this range.

## Data provenance

The numbers on this page are a direct read-out of `outputs/equity_summary.csv`, `outputs/sa2_equity.gpkg`, and `outputs/sa2_accessibility.gpkg`, produced by running stages 1 through 5 of the pipeline against the April 2026 GTFS feed and the BDS February 2025 employment table. Any reader can reproduce them with `python code/stage{1,2,3,4,5}_*.py`.
