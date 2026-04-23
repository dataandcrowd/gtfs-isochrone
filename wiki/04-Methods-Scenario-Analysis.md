# 04. Methods: Scenario Analysis

This page documents how the six Auckland Transport Time-of-Use Charging (TOUC) scenarios were operationalised for the equity analysis. The source of truth is the AT TOUC public slide deck that presents six candidate scheme footprints: three cordons (1a, 1c, 2c) and three motorway-based designs (3b, 3c, 3e). The scenarios differ in both geographic extent and the theory of behavioural change (cordon charging versus corridor charging), so they produce very different distributional effects.

## Scenario definitions

| Code | Short name | Geography | Description |
|---|---|---|---|
| 1a | City centre cordon | CBD inner | Charges vehicles entering the Auckland CBD bounded roughly by Cook St, Fanshawe St, Stanley St, and the Karangahape Rd approach. |
| 1c | City centre + fringe | CBD + K Rd + Newmarket arc | Extends 1a south and east to include K Rd, Eden Terrace, Grafton, Newmarket, and Parnell. |
| 2c | Isthmus double cordon | Central isthmus | Charges vehicles crossing into the Auckland isthmus from either the Harbour Bridge (north cordon) or SH20 / SH1 south (south cordon). Charged area spans from Pt Chevalier / Westmere in the west to Glendowie / St Heliers in the east, bounded at Onehunga / Penrose / Sylvia Park. |
| 3b | Core motorways | SH1N, SH1S, SH16, SH20 | Distance-based charge applied to all vehicles using the four core motorways. |
| 3c | Core motorways + CBD | 3b ∪ 1a | Combines motorway charging with a small CBD cordon, recognising that many motorway users terminate in the CBD. |
| 3e | Motorway hotspots | Three bottleneck segments | Charges applied only at three known congestion hotspots: the SH1 × SH18 Upper Harbour interchange, the SH16 × SH20 Waterview interchange, and the SH1 south Papakura to Drury pinch-point. |

The exact SA2 membership of each scenario is stored as a Python list in `code/stage4_equity.py` (variables `_S1A_NAMES` through `_S3E_NAMES`) and is resolved to SA22023 codes at runtime via the `_names_to_ids(...)` helper. This keeps the scenario definitions legible in source form while the burden classification remains indexed by the numeric code.

## SA2 as the spatial unit

Four alternatives were considered and rejected.

1. **Road segment.** Using the network-level link IDs would be faithful to AT's own design unit but would not interface with NZDep2023 (an SA2-level score) or with BDS 2025 employment (also SA2). It would also require a spatial-join pipeline that crosses every SA2 with every charged segment, yielding many-to-many relationships.
2. **Raster cell.** Gridding Auckland to 250 m cells would give a uniform resolution but would be ahead of what SA2 can deliver; every result would need to be re-aggregated to SA2 for reporting.
3. **SA1.** Stats NZ's SA1 unit is finer than SA2 and has its own NZDep2023 publication, but Auckland Transport's scheme footprints are deliberately coarser than SA1 boundaries; using SA1 introduces spurious precision on both the charged side (fractional SA1 membership of a cordon) and the accessibility side (many SA1s have zero jobs, distorting the denominator in A_i).
4. **Meshblock.** Same concern as SA1, amplified.

SA2 is the smallest unit at which all three ingredients (deprivation score, job count, travel time) are produced with full coverage for Auckland. It is also the unit at which AT's own community engagement is conducted, so the burden classification can be reported directly to community stakeholders without a unit conversion.

## From AT slide footprint to SA2 set

The AT TOUC slide deck provides PDF-resolution polygons drawn on a basemap; the underlying shapefile is not currently published. The operationalisation is therefore a best-fit SA2 list, produced in three steps.

1. **Visual transcription.** The AT polygon for each scenario is overlaid mentally on the SA2 boundaries, and the SA2s whose centroids fall inside (or whose area intersects the polygon by more than about 50 per cent) are listed by `SA22026_V1_00_NAME`. For motorway scenarios (3b, 3c, 3e), the list contains every SA2 that borders or is transected by the motorway alignment.
2. **Name resolution.** The list is fed to `_names_to_ids(...)` which looks up each name in the SA2 GeoDataFrame's `SA22026_V1_00_NAME` column and emits the `SA22023_V1_00` code. Any unmatched name is printed with a warning; the current pipeline matches all 15 (1a), 27 (1c), 158 (2c), 173 (3b), 188 (3c), and 22 (3e) names cleanly, with no warnings.
3. **Dissolve.** In stage 4i, the charged SA2s for each scenario are dissolved into one polygon (or multipolygon) and written to `outputs/scenario_boundaries.gpkg` with columns `scenario`, `label`, `n_sa2`, `n_trapped_payers`, `geometry`. The PNG map `outputs/figures/fig0_scenario_boundaries.png` renders these dissolved boundaries at 2 × 3 over the Auckland SA2 basemap.

The limitations of this approach are acknowledged explicitly in the paper. Most importantly, (a) the southern edge of 2c is approximate because the AT slide is not precise about whether Ōtāhuhu is inside or outside the double cordon, and (b) the three hotspot polygons in 3e are small enough that a one-SA2 shift materially changes the charged population. Both limitations disappear once AT publishes the shapefile; the replacement in the code is one line (`SCENARIO_SA2_SETS[s] = set(gpd.sjoin(sa2, at_cordon_s)["SA22023_V1_00"])`) and does not propagate.

## Burden classification

Every SA2 i receives a per-scenario burden label L_i^s ∈ {`no_charge`, `pays_with_alternative`, `pays_without_alternative`},

> L_i^s = no_charge,                         if i ∉ S_s
> L_i^s = pays_with_alternative,             if i ∈ S_s and A_i^{30} ≥ θ
> L_i^s = pays_without_alternative,          if i ∈ S_s and A_i^{30} < θ

where S_s is the SA2 set for scenario s, A_i^{30} is the 30-minute cumulative job accessibility of i, and θ is the Q75 of A^{30} over all 545 Auckland SA2s. The rationale for using a within-Auckland Q75, rather than a universal benchmark, is that Auckland's CBD-centric job distribution inflates absolute accessibility values in a way that is not comparable to other cities.

The interpretation of the three classes is:

- **pays_with_alternative.** The SA2 is inside the cordon or on the corridor, but its residents can plausibly shift to PT without a disproportionate travel-time penalty. These SA2s are the intended behavioural target of the charge.
- **pays_without_alternative (trapped payer).** The SA2 is charged but has sub-threshold PT accessibility; residents face a real income loss with no modal alternative. These SA2s are the equity concern.
- **no_charge.** Outside the scheme footprint; included in the distributional analysis only as the reference group.

The threshold θ = 14,630 reachable jobs within 30 minutes is reported in the `viable_alt_threshold_jobs` column of `equity_summary.csv`, so a reader can replicate the classification with any alternative threshold they prefer.

## Scenario-specific Concentration Index

Two CI quantities are reported per scenario.

1. **CI_charged_sa2s.** Restricts the calculation to the SA2s where L_i^s ≠ `no_charge`. This is the CI of accessibility across the charged population only, against NZDep rank of the charged population. It is the number that bears directly on the equity interpretation: how is the burden distributed by deprivation among those who actually pay?
2. **CI_all_30min** and **CI_all_45min.** Baseline CI across all 545 Auckland SA2s, independent of the scenario. These are the same numbers in every row of the summary CSV.

The two are complementary. If `CI_charged_sa2s` is close to zero, the charged SA2s are distributionally representative of the city. If it is substantially negative (more deprived + less access inside the scheme), the scenario is regressive in the strict Kakwani sense (Wagstaff, Paci, and van Doorslaer 1991, originally applied to health). Positive values indicate pro-poor concentration of charged accessibility, which is rare but can occur for scenarios like 2c where the high-access suburbs inside the cordon cluster in mid-deprivation deciles.

Confidence intervals on CI are not reported in the current release because the standard bootstrapping (1,000 resamples over SA2s) is sensitive to the small number of charged SA2s in 1a (n = 15) and 3e (n = 22). A planned extension uses Gaussian Process smoothing on NZDep rank (Erreygers and van Ourti 2011) to produce confidence bands that remain informative at small n.

## Reproducibility of the six scenarios

The full SA2 name list for each scenario, the `_names_to_ids(...)` helper, and the dissolve step are all in `code/stage4_equity.py` between the comment headers `# ── 4c.` and `# ── 4i.`. A re-run of stage 4 regenerates the `sa2_equity`, `scenario_boundaries`, and `fig0` outputs from the accessibility layer. None of this depends on data beyond what `code/stage1_data_prep.py` has already produced.
