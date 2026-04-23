# 03. Methods: Analysis Pipeline

This page documents the five-stage analysis pipeline in `code/`. Each stage is a single Python script that reads from `data/` and writes a versioned intermediate to `outputs/`, so any later stage can be re-run without re-executing upstream work. All stages are deterministic given the same inputs and the same JVM seed.

The end-to-end quantity of interest is a cumulative opportunity accessibility score per Statistical Area 2 (SA2),

> A_i = Σ_j O_j · 1{t_ij ≤ T}

where i indexes origin SA2s, j indexes destination SA2s, O_j is the workplace job count at j (BDS February 2025), t_ij is the median peak-period multimodal travel time from i to j (r5py, 07:00 to 09:00, TRANSIT + WALK), T is the time threshold (30 or 45 minutes), and 1{·} is the indicator function.

The distributional statistic is the Concentration Index,

> CI = (2 / μ) · Cov(A_i, r_i)

where r_i is the fractional rank of SA2 i on NZDep2023 (higher r means more deprived) and μ is the mean of A. By construction, CI = 0 means equal distribution, CI > 0 means accessibility is concentrated in more deprived SA2s (pro-poor), and CI < 0 means accessibility is concentrated in more affluent SA2s (regressive).

## Stage 1: Data preparation

**Script.** `code/stage1_data_prep.py`.
**Inputs.** `data/auckland_sa2.gpkg`, `data/nzdep2023.csv`, `data/employment_sa2.csv`.
**Output.** `outputs/sa2_prepared.gpkg`.

Actions, in order.

1. Load the SA2 polygons for the Auckland region, reproject to EPSG:2193 (NZTM2000) for areal operations, and drop any non-Auckland units.
2. Merge NZDep2023 on `SA22023_V1_00`, adding the score `NZDep2023` and the decile `NZDep_Decile`. SA2s that cannot be matched on the 2023 code (mostly unpopulated zones) keep NaN; there are nine such units of the 545 retained.
3. Merge BDS February 2025 employee counts on `SA22023_V1_00`, adding the opportunity weight `jobs_count` (integer). Auckland total is 811,060 employees.
4. Compute the WGS84 centroid of each SA2, storing `lon` and `lat` as plain float columns so stage 2 can consume them without a second reprojection.
5. Write the prepared layer to `outputs/sa2_prepared.gpkg`. On sandboxed or FUSE-mounted filesystems, where SQLite cannot acquire the locks the GeoPackage driver expects, the helper `code/_io_utils.py::safe_to_gpkg()` stages the write on a local scratch path and then copies the finished file into `outputs/` with `shutil.copy2`. This keeps a single-format output without needing a secondary driver.

## Stage 2: r5py routing

**Script.** `code/stage2_routing.py`.
**Inputs.** `data/auckland.osm.pbf`, `data/at_gtfs.zip` (or the cleaned `at_gtfs_clean.zip` with empty optional tables stripped), `outputs/sa2_prepared.gpkg`.
**Output.** `outputs/travel_time_matrix.parquet`.

Routing configuration.

- Departure: Tuesday 5 May 2026 at 07:00 NZST. Chosen because (a) it is a non-holiday weekday, (b) it sits inside the GTFS validity window (`feed_start_date=20260415`, `feed_end_date=20260731`), and (c) 5 May 2026 is outside the NZ Term 1 school holiday window.
- Departure time window: 120 minutes (07:00 to 09:00). r5py samples across every minute in this window and returns the median travel time at each OD pair.
- Modes: `TransportMode.TRANSIT` plus `TransportMode.WALK`. Car-only routing is not used because the study is about the PT alternative under a congestion charge, not about car travel.
- Maximum travel time: 60 minutes. Pairs exceeding this bound are emitted as NaN.
- Maximum walk time: 15 minutes. This bounds access and egress legs and cuts the search tree sharply without impairing realism in urban Auckland.
- Walk speed: 1.2 m/s (roughly 4.3 km/h). r5py is supplied the value in km/h (`speed_walking=4.32`).
- Percentile: 50 (median across the departure window).

The R5 engine builds a `TransportNetwork` by merging the OSM street graph with the GTFS stops, trips, and stop_times. On a 16 GB laptop this takes two to five minutes and writes a `.tmp` cache file next to the PBF so subsequent runs skip the build.

The resulting DataFrame has 545 × 545 = 297,025 OD pairs, with reachable pairs in the 40,000 to 50,000 range after applying the 60-minute ceiling (fewer pairs for peripheral SA2s).

**JVM heap.** The pipeline reads the heap size from the environment variable `R5PY_XMX` (default 2500M for the sandbox; bump to 8G locally for a 16 GB laptop). The flag is injected into `sys.argv` before the first `import r5py` call.

## Stage 3: Cumulative opportunity accessibility

**Script.** `code/stage3_accessibility.py`.
**Inputs.** `outputs/sa2_prepared.gpkg`, `outputs/travel_time_matrix.parquet`.
**Output.** `outputs/sa2_accessibility.gpkg`.

For each origin i, sum the job counts of all destinations reachable within T minutes,

```python
within = tt[tt["travel_time_p50"] <= T]
within["jobs"] = within["to_id"].map(jobs_series).fillna(0)
A_i = within.groupby("from_id")["jobs"].sum()
```

Two thresholds are computed: T = 30 and T = 45 minutes. The 30-minute threshold is the policy-relevant one (a charge is only plausible to pay voluntarily if a 30-minute PT alternative exists); the 45-minute threshold is kept as a robustness check, because it matches the cumulative opportunity definitions used in Conveyal's Analysis reports and in the literature on accessibility poverty (Páez, Scott, and Morency 2012).

A minmax-normalised copy `access_30min_norm` and `access_45min_norm` is added for cartographic use, and a within-Auckland decile `access_45min_decile` is added for the bivariate choropleth in stage 5. The "viable alternative" threshold for burden classification is the 75th percentile of `access_30min` (top-quartile accessibility), which in April 2026 evaluates to 14,630 jobs reachable within 30 minutes.

## Stage 4: Equity and burden classification

**Script.** `code/stage4_equity.py`.
**Inputs.** `outputs/sa2_accessibility.gpkg`.
**Outputs.** `outputs/sa2_equity.gpkg` (accessibility layer plus six `burden_*` columns and scenario boundaries), `outputs/equity_summary.csv`, `outputs/burden_crosstab.csv`, `outputs/scenario_boundaries.gpkg`, `outputs/scenario_boundaries_summary.csv`, `outputs/figures/fig0_scenario_boundaries.png`.

Four substages run in the same Python process.

**4a. Concentration Index, all SA2s.** Compute CI separately at 30 and 45 minutes using the covariance formulation above. With 545 SA2s, fractional ranks run from 1/545 to 1, and the estimator is unbiased in the `bias=True` covariance convention used by `numpy.cov`. Results are rounded to four decimal places.

**4b. Burden classification per SA2 per scenario.** For each scenario s and each SA2 i,

- if i is outside the scenario cordon or corridor, class is `no_charge`;
- else if i is inside and `access_30min ≥ Q75_30`, class is `pays_with_alternative`;
- else class is `pays_without_alternative` (the "trapped payer").

The boolean membership of i in scenario s is looked up in `SCENARIO_SA2_SETS[s]`, a Python set of SA22023 codes. The classification is vectorisable; a plain `DataFrame.apply` with a three-branch lambda is used for readability.

**4c. Cross-tabulation.** For each scenario, tabulate SA2 counts by (NZDep decile × burden class). All six cross-tabs are concatenated into `burden_crosstab.csv` with a `scenario` key column.

**4d. Scenario-specific Concentration Index.** For each scenario, compute CI of `access_30min` over the set of charged SA2s (those with `burden_s != no_charge`). This is the key equity number: a negative CI means the charge falls on SA2s with lower access and higher deprivation (regressive), a positive CI means the charge falls on SA2s with higher access and higher deprivation (pro-poor in the strict sense, although this is unusual for an accessibility-based analysis).

An in-process stage 4i dissolves the charged SA2s per scenario into one polygon and renders a 2 × 3 map, plus the `scenario_boundaries.gpkg` layer. See the "Methods: Scenario Analysis" page for the full scenario definitions.

## Stage 5: Visualisation

**Script.** `code/stage5_visualisation.py`.
**Inputs.** `outputs/sa2_equity.gpkg` plus the two CSV summaries.
**Outputs.** six PNG figures under `outputs/figures/`, plus `outputs/sa2_final.gpkg`.

| Figure | Content |
|---|---|
| `fig1_accessibility_choropleth.png` | Four-panel: access30, access45, NZDep2023, bivariate 3 × 3 class |
| `fig2_accessibility_by_deprivation.png` | Boxplot of A_i by NZDep decile, with scatter + LOWESS trend |
| `fig3_concentration_curve.png` | Lorenz-type concentration curve (cumulative access vs cumulative rank) |
| `fig4_access_vs_deprivation_scatter.png` | Scatter with labelled extreme SA2s (top-4 and bottom-4) |
| `fig5_burden_by_scenario.png` | 2 × 3 stacked bar: burden class count by NZDep decile for each scenario |
| `fig6_ci_forest_plot.png` | CI forest plot for the six scenarios, colour-coded by hypothesis group |

All maps use a 0.2 pt dark edge (`#1B1917`) on each SA2 to preserve micro-boundaries and a 14-point landmark label set with semi-transparent white pill backgrounds.

## Runtime footprint

| Stage | Duration (M1 Pro, 16 GB, 8G heap) | Disk write |
|---|---|---|
| Stage 1 | 15 s | 9 MB |
| Stage 2, first run (network build + OD matrix) | 18 min | 150 KB matrix + 40 MB R5 cache |
| Stage 2, cached | 8 min | same |
| Stage 3 | 5 s | 9 MB |
| Stage 4 | 4 s | 9 MB + 30 KB CSVs + 600 KB boundary layer |
| Stage 5 | 35 s | 4 MB PNG bundle |

Peak RAM is 6.5 GB during stage 2 (the R5 network build dominates).

## Reproducibility checklist

1. `git clone` the repository and install the Python environment from the requirements list in `wiki/02-Analysis-Tools`.
2. Ensure a JDK 17 or newer is on the PATH (`java -version`).
3. Place the five raw files in `data/` as described in `wiki/01-Data-Retrieval`.
4. Run the five stages in order; each script prints a short runtime summary.
5. Compare the `equity_summary.csv` against the baseline CI values listed in `wiki/05-Results-Accessibility-and-Equity`.

Every random seed used internally by r5py is deterministic under a fixed departure window. The pipeline writes a single GeoPackage per stage; all geometry is serialised through the `safe_to_gpkg()` helper described in Stage 1, which is a pure file-copy operation and therefore adds no numerical variance.
