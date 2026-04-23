# GTFS Isochrone: Auckland Congestion Charging Health Equity Analysis

A reproducible Python pipeline that quantifies transit accessibility at the SA2 scale in Tāmaki Makaurau / Auckland and evaluates the health equity consequences of six proposed congestion charging scenarios (three CBD cordon variants, three motorway corridor variants).

The analysis combines:

- Multimodal routing over the General Transit Feed Specification (GTFS) feed published by Auckland Transport, using the r5py implementation of Conveyal R5.
- OpenStreetMap (OSM) road and pedestrian network for walking access and egress to stops.
- Stats NZ Statistical Area 2 (SA2) geography as the spatial unit, consistent with NZDep2023 publication units.
- NZDep2023 from the University of Otago, Wellington (Health Inequalities Research Programme) for the deprivation dimension.
- Stats NZ Business Demography Statistics (February 2025) employee counts as the opportunity measure.

The headline quantity is a cumulative opportunity accessibility index

> A_i = Σ_j O_j · f(t_ij)

per SA2 i, where O_j is job count at destination SA2 j and f(·) is a binary cumulative function at 30 and 45 minute cut-offs (07:00 to 09:00 weekday, TRANSIT plus WALK). The distributional outcome is the concentration index

> CI = (2 / μ) · Cov(A_i, r_i)

with r_i the fractional rank of SA2 i on NZDep2023 and μ the mean accessibility.

## Hypotheses

**H1. CBD cordon scenarios (1a, 1c, 2c) are broadly progressive.** Inner-suburb SA2s with the highest accessibility are concentrated in NZDep deciles 1 to 3 (Ponsonby, Grey Lynn, Mt Eden, Newmarket, Kingsland). A charge at the cordon reaches residents who have a credible modal shift option, producing a "pays with alternative" pattern. Expected CI in the range -0.08 to -0.14 (mild inequality).

**H2. Motorway corridor scenarios (3b, 3c, 3e) are broadly regressive.** SA2s in South and West Auckland (Māngere, Ōtara, Manurewa, Papakura, Henderson, Ranui) are NZDep 8 to 10 with weaker transit service frequency. A motorway charge would hit "pays without alternative" residents hardest. Expected CI in the range -0.30 to -0.48, with trapped payer shares up to 60 per cent in NZDep 8 to 10 under 3e.

**Auxiliary finding.** Scenarios that succeed on H1 also generate a positive public health externality for deprived SA2s adjacent to the CBD, via reduced traffic-related air pollution and road trauma, plus a plausible revenue redistribution route (connector bus expansion in South and West Auckland).

## Pipeline

Five numbered Python scripts in `code/` that run sequentially. Each writes its intermediate product to disk so later stages can be re-run without recomputing upstream state.

| Stage | Script | Purpose | Principal output |
|---|---|---|---|
| 1 | `stage1_data_prep.py` | Clip OSM, download GTFS, merge SA2 + NZDep + employment | `outputs/sa2_prepared.gpkg` |
| 2 | `stage2_routing.py` | Build r5py `TransportNetwork`, compute travel-time matrix | `outputs/travel_time_matrix.parquet` |
| 3 | `stage3_accessibility.py` | Cumulative opportunity accessibility at 30 and 45 min | `outputs/sa2_accessibility.gpkg` |
| 4 | `stage4_equity.py` | Concentration index, burden classification | `outputs/sa2_equity.gpkg`, `burden_crosstab.csv`, `equity_summary.csv` |
| 5 | `stage5_visualisation.py` | Choropleths, boxplots, stacked bars, CI forest plot | PNG figures, `outputs/sa2_final.gpkg` |

## Repository layout

```
gtfs-isochrone/
├── code/                 # five-stage pipeline
├── data/                 # raw inputs (ignored in .gitignore except manifest)
│   ├── auckland.osm.pbf  # clipped OSM network
│   ├── at_gtfs.zip       # Auckland Transport GTFS feed
│   ├── auckland_sa2.gpkg # SA2 polygons for the Auckland region
│   ├── nzdep2023.csv     # NZDep2023 score and decile by SA2
│   └── employment_sa2.csv# BDS Feb 2025 employee count by SA2
├── outputs/              # pipeline intermediates and final GeoPackage
├── wiki/                 # GitHub wiki pages (this file and siblings)
└── README.md / LICENSE
```

## Wiki index

- [01 Data Retrieval](01-Data-Retrieval): how each raw dataset was acquired and prepared, including the OSM extract strategy and the reason BDS was preferred over the 2023 Census travel-to-work matrix.
- [02 Analysis Tools](02-Analysis-Tools): rationale for r5py, alternatives considered (OpenTripPlanner 2, Valhalla, OpenRouteService), input format requirements, and JVM notes.
- [03 Methods: Analysis Pipeline](03-Methods-Analysis-Pipeline): formal description of the five-stage pipeline (data prep, routing, accessibility, equity, visualisation), including routing parameters, cumulative-opportunity and Concentration Index formulas, and runtime footprint.
- [04 Methods: Scenario Analysis](04-Methods-Scenario-Analysis): definitions of the six AT TOUC scenarios (1a, 1c, 2c, 3b, 3c, 3e), how SA2 membership is resolved from the AT slide deck, burden classification rules, and scenario-specific Concentration Index methodology.
- [05 Results 1: Baseline Accessibility and All-Auckland Equity](05-Results-Accessibility-and-Equity): 30 and 45-minute accessibility surfaces, descriptive statistics by NZDep decile, all-Auckland Concentration Index, Lorenz-type concentration curves, and trapped-payer risk population.
- [06 Results 2: Scenario Burden and Concentration Index](06-Results-Scenario-Burden): per-scenario charged-SA2 counts, trapped-payer counts, CI values, H1 and H2 hypothesis tests, and policy implications.

## Citation

When citing this analysis, please use the current `LICENSE` file and reference the research report in preparation for *Cities and Health*.

## Contact

Hyesop Shin, School of Environment, University of Auckland. GIScience and agent-based modelling for urban health and transport equity.
