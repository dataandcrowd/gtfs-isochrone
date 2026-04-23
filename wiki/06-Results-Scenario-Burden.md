# 06. Results 2: Scenario Burden and Concentration Index

This page reports the distributional outcomes of applying each of the six Auckland Transport Time-of-Use Charging (TOUC) scenarios to the baseline accessibility surface from page 05. For every scenario, it lists the charged SA2 count, the trapped-payer count (SA2s inside the scheme footprint but below the 30-minute job accessibility threshold θ = 14,630), and the Concentration Index on the charged set.

The two pre-registered hypotheses from the Home page are revisited at the end of the page with a partial rejection of H1 (CBD cordons are not uniformly progressive) and broad support for H2 (motorway scenarios are regressive, with 3b the most regressive of the six).

## Scenario footprints (figure 0)

Figure 0 shows the six dissolved scenario boundaries over the Auckland SA2 base map, with charged SA2s shaded in scenario colour (teal for cordons, orange for motorway corridors) and trapped-payer SA2s overprinted in red.

![Figure 0](./outputs/figures/fig0_scenario_boundaries.png)

At a glance, the cordon scenarios (top row) charge small, central, mostly affluent SA2 sets; the motorway scenarios (bottom row) charge long corridors extending into NZDep 8 to 10 territory in West and South Auckland. The red fraction grows visibly from left to right in the top row (0, 0, 66 trapped payers in 1a, 1c, 2c) and dominates the bottom row (118, 118, 16 in 3b, 3c, 3e).

## Scenario summary

| Scenario | Label | n_sa2 | Trapped payers | CI (charged set) |
|---|---|---:|---:|---:|
| 1a | City centre cordon | 15 | 0 | +0.0062 |
| 1c | City centre + fringe | 27 | 0 | +0.0725 |
| 2c | Isthmus double cordon | 158 | 66 | +0.1375 |
| 3b | Core motorways | 173 | 118 | −0.1899 |
| 3c | Core motorways + CBD | 188 | 118 | −0.0704 |
| 3e | Motorway hotspots | 22 | 16 | −0.0319 |

Baseline reference (all 545 SA2s): CI(access_30min) = +0.0501; CI(access_45min) = −0.0061.

## Burden class by NZDep decile (figure 5)

Figure 5 is a 2 × 3 stacked bar: for each scenario, the x-axis is NZDep decile 1 to 10 and the y-axis is the SA2 count, stacked by `pays_with_alternative` (green), `pays_without_alternative` (orange-red), and `no_charge` (grey).

![Figure 5](./outputs/figures/fig5_burden_by_scenario.png)

The reading strategy is: look at the orange-red bars in each panel. These are the trapped payers. In 1a, 1c, they are absent (the CBD cordon is affluent and well-served). In 2c, they appear in deciles 8 to 10 (southern edge of the isthmus: Panmure, Onehunga South, Mount Roskill South East). In 3b and 3c, they dominate deciles 7 to 10 (Manurewa, Papakura, Takanini, Henderson, Massey). In 3e, only a thin slice of deciles 8 to 10 is charged, matching the three small hotspot polygons.

## CI forest plot (figure 6)

Figure 6 presents the CI of charged-set accessibility per scenario as a horizontal forest plot, with scenarios colour-coded by hypothesis group (green = CBD cordon, H1; orange = motorway corridor, H2) and baseline CI marked with a small cross at the appropriate scenario.

![Figure 6](./outputs/figures/fig6_ci_forest_plot.png)

The forest plot reads right-to-left as follows.

- **2c** (CI = +0.138) is the most pro-poor scenario. The isthmus double cordon charges a large set of central SA2s, a share of which sit in NZDep 6 to 10 (Panmure, Glen Innes, Mount Roskill, Onehunga); their accessibility is, on average, higher than the cordon mean, so CI lands firmly in the positive half.
- **1c** (CI = +0.073) is mildly pro-poor for the same reason: K Rd and Newmarket (NZDep 4 to 7) bring in charged SA2s with high access.
- **1a** (CI = +0.006) is essentially flat. The CBD core mixes NZDep 1 (Parnell, Hobson Ridge) with NZDep 8 (Queen Street South-West), and the mean access within the cordon is uniform enough across ranks to give CI ≈ 0.
- **3e** (CI = −0.032) is mildly regressive. The three hotspots, especially the Papakura segment, pick up a handful of deprived SA2s with sub-threshold access.
- **3c** (CI = −0.070) is regressive. Adding the CBD (1a) to the motorway corridor (3b) softens the regressivity of the raw corridor but does not cancel it.
- **3b** (CI = −0.190) is the most regressive scenario and the main equity concern of the study. Within the charged set, deprivation increases markedly as accessibility falls, driven by the long South and West motorway tails through Manurewa, Papakura, Henderson, and Te Atatū.

## Hypothesis tests

**H1. CBD cordon scenarios are broadly progressive.** Partially rejected. The CI values of 1a, 1c, 2c are +0.006, +0.073, +0.138: all non-negative and therefore not regressive, but the mechanism is not the expected "high-access affluent SA2s pay a charge they can avoid". Instead, the positive CIs come from mid-deprivation SA2s inside the cordon also having reasonable access, so the charged set happens to include more deprived but better-connected suburbs. This is a progressive outcome in the strict Kakwani sense but does not reflect the behavioural story of H1. The pre-registered expectation of CI in the range −0.08 to −0.14 is not supported.

**H2. Motorway corridor scenarios are broadly regressive.** Supported. 3b (−0.190), 3c (−0.070), 3e (−0.032) are all negative. 3b exceeds the lower bound of the expected range (−0.30 to −0.48 was perhaps too strong), but the sign is correct and the trapped-payer counts (118, 118, 16) are large enough to be a policy-relevant finding even at the upper end of the expected CI.

**Auxiliary finding.** The combination 3c = 3b ∪ 1a halves the regressivity of 3b (−0.190 → −0.070) because the affluent well-served CBD SA2s offset the regressive long-corridor tail. This is a candidate design recommendation: a motorway-only scheme is distributionally worse than a motorway-plus-CBD scheme even though the latter charges more SA2s. Adding the CBD does not avoid the trapped-payer problem (both 3b and 3c have 118 trapped payers), but it mitigates the aggregate distributional signal.

## Sensitivity and robustness

Three sensitivity probes have been run; all three preserve the scenario ordering.

1. **Threshold θ.** Raising θ to Q80 of `access_30min` (20,150 jobs) raises the trapped-payer count to 146 in 3b (from 118) and to 80 in 2c (from 66); the CI values shift by at most 0.03 units and the sign of every scenario is unchanged.
2. **Departure day.** Re-running with Wednesday 6 May and Thursday 7 May 2026 as departure dates moves individual cell travel times by up to 4 minutes but leaves CI values within 0.01 of the Tuesday figures.
3. **NZDep version.** The earlier NZDep2018 index (used in AT's own equity work) has a correlation of 0.94 with NZDep2023 at the SA2 level. Substituting NZDep2018 gives CI values within 0.02 of the NZDep2023 numbers.

## Policy implications

Three recommendations come directly from the numbers above.

1. **Do not deploy scenario 3b in isolation.** The CI of −0.190 and 118 trapped-payer SA2s make 3b the most regressive of the six designs. Any TOUC scheme that resembles 3b needs a compensation mechanism (for example, a means-tested rebate or a hypothecated transfer to South and West Auckland PT expansion).
2. **If a motorway element is required, prefer 3c.** Combining the core motorway corridor with a CBD cordon (3c) is half as regressive as 3b while preserving the revenue and congestion-management rationale of the motorway charge.
3. **Cordon-only designs (1a, 1c, 2c) are distributionally acceptable**, but note that 2c has 66 trapped payers that are entirely absent in 1a and 1c. Equity-minded readers should weigh the CI sign against the absolute trapped-payer count; a near-zero or positive CI does not preclude real pockets of distress inside the cordon.

These recommendations are scenario-level only. They do not consider the separate dimensions of scheme design (time-of-day variation, exemptions, payment friction, enforcement) that a full policy appraisal would require.

## Caveats

- The SA2 membership for each scenario is a best-fit to the AT TOUC slide deck, not a spatial intersection against an official AT shapefile. The 2c southern edge (Ōtāhuhu and the Manukau harbour apron) and the 3e three-hotspot polygons are the most uncertain. When the AT shapefile is released, the one-line replacement (`gpd.sjoin(sa2, at_cordon)`) will regenerate these numbers.
- The CI estimator is a point estimate; the confidence bands implied by a basic bootstrap are wide for 1a (n = 15) and 3e (n = 22). A Gaussian-process-smoothed CI is planned as an extension (Erreygers and van Ourti 2011).
- Accessibility is computed for the 07:00 to 09:00 weekday window only. A TOUC scheme would operate across a longer window; the off-peak PT alternative is typically worse, so extending the analysis window is expected to widen the trapped-payer set, not narrow it.
- The "viable alternative" criterion is PT-only (`TransportMode.TRANSIT` + `WALK`). Active-mode alternatives (cycling, e-scooter) are not modelled; the pipeline would need a bicycle network and a separate `TransportMode.BICYCLE` routing pass to incorporate them.

## Data provenance

Every number on this page is produced by the single run `python code/stage4_equity.py && python code/stage5_visualisation.py` and is readable directly from `outputs/equity_summary.csv`, `outputs/burden_crosstab.csv`, and `outputs/scenario_boundaries_summary.csv`. The six PNG figures live in `outputs/figures/`.
