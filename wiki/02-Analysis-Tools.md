# 02. Analysis Tools (r5py)

This project uses r5py, the Python binding for Conveyal's R5 (Rapid Realistic Routing on Real-world and Reimagined networks) engine, as the multimodal routing backbone. This page documents the reasoning behind that choice, the alternatives considered, the exact inputs r5py requires, and the operational notes (JVM memory, caching) that matter when running the pipeline on a laptop.

## Why r5py

The accessibility calculation requires three properties that together rule out simpler tools:

1. **Multimodal with realistic transit schedules.** Every origin-destination travel time must reflect departure headways, transfers, walking access and egress, and waiting time, not straight-line distance or a static graph.
2. **Many-to-many batch.** Computing 619 × 619 ≈ 383,000 travel-time cells for each scenario is tractable only in a batch routing engine; per-request APIs would be orders of magnitude slower.
3. **Python ecosystem compatibility.** The rest of the pipeline (geopandas, pandas, matplotlib) is Python; switching languages for a single stage is fragile.

r5py satisfies all three. It wraps the same R5 JAR used by the Conveyal Analysis platform and by the R package `r5r`, so the scientific provenance is identical.

### Alternatives considered

| Tool | Multimodal transit | Python-native | Suitable for this study | Notes |
|---|---|---|---|---|
| **r5py** | Yes | Binding over Java JAR | **Adopted** | Requires JDK 11+. Memory-hungry but fast. |
| OpenTripPlanner 2 (OTP2) | Yes | REST client only | Overkill | Mature server, but needs a separately-managed Java service with its own graph build. REST round-trip costs dominate batch workloads. |
| Valhalla | Partial | Official Python bindings | Unsuitable | GTFS transit support is experimental and not production-ready; primary strength is road routing. |
| OpenRouteService | Limited | Yes | Unsuitable | Transit routing is restricted and quota-bound; no way to run locally on a custom feed. |
| `r5r` (R) | Yes | No (would need bridge) | Unnecessary | Same engine as r5py but forces a language context switch. |

For completeness, `pandana` and `graph-tool`-based solutions using precomputed walk networks were also considered. They provide very fast walking-accessibility calculations but do not natively consume GTFS schedules, so each transit mode would have to be modelled manually with average headways. This loses the transfer and waiting-time realism that is central to the health equity framing (a "viable alternative" exists only when the frequency and span of service make it one).

## Installation

### System dependencies

- **Java Development Kit, version 11 or newer.** R5 is a JVM application. On macOS: `brew install --cask temurin`. Verify with `java -version`.
- **Python 3.10 or newer**, with `pip` available.

```bash
java -version
# openjdk version "21.0.x" ...
```

### Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install \
    r5py \
    geopandas \
    pandas \
    numpy \
    pyarrow \
    matplotlib \
    shapely \
    requests
```

`pyarrow` is used by r5py for its parquet writeback of the travel-time matrix and is not a hard dependency, but avoids falling back to CSV for a table of ~400,000 rows × N scenarios.

## Input formats (strict)

| Input | Accepted format | Not accepted |
|---|---|---|
| Road / pedestrian network | `.osm.pbf` only | `.osm` (XML), `.gpkg`, shapefile, any GIS vector format |
| Transit | `.zip` archive following the GTFS static specification | GTFS-realtime, NETEX, OTP graph |
| Origins, destinations | `GeoDataFrame` passed through the Python API | Files are not read directly by r5py for these |

The `GeoDataFrame` must be in EPSG:4326 (WGS84). r5py extracts `geometry.x` and `geometry.y` as lon/lat internally; a point geometry column is sufficient. Any SA2 boundary polygon is reduced to its centroid upstream in the pipeline.

### CRS sanity checklist

- r5py expects EPSG:4326 for origins and destinations.
- Stats NZ SA2 products typically arrive in NZTM2000 (EPSG:2193).
- Convert before passing to r5py: `sa2 = sa2.to_crs(epsg=4326)`.

## TransportNetwork construction

The network graph is built once from the clipped OSM PBF plus the GTFS ZIP and cached in memory for the duration of the Python process.

```python
from r5py import TransportNetwork, TravelTimeMatrixComputer
import datetime

network = TransportNetwork(
    osm_pbf="data/auckland.osm.pbf",
    gtfs=["data/at_gtfs.zip"],
)
```

### Observed build time

On an Apple M-series laptop with 16 GB RAM, building the network from the 51 MB Auckland PBF and the 37 MB AT GTFS feed takes about one to two minutes. Once built, it is held as a field on a single long-lived `TransportNetwork` object and reused across all six scenarios.

### Caching strategy

`TransportNetwork` does not serialise itself to disk by default. Two tactics keep iteration fast during development:

1. Run a single Python process (Jupyter kernel, IPython session, or `code/stage2_routing.py` that computes all six scenarios in one invocation) and reuse the object in memory.
2. Pickle the travel-time matrix outputs to Parquet (`outputs/travel_time_matrix_{scenario}.parquet`) so downstream equity and visualisation stages never re-run the routing step.

## TravelTimeMatrixComputer

The many-to-many travel-time matrix is computed per scenario. Parameters for this study:

```python
computer = TravelTimeMatrixComputer(
    network,
    origins=sa2_centroids,            # GeoDataFrame in EPSG:4326
    destinations=sa2_centroids,       # same for cumulative opportunity
    departure=datetime.datetime(2026, 5, 5, 7, 0),     # Tuesday
    departure_time_window=datetime.timedelta(hours=2), # 07:00 to 09:00
    transport_modes=["TRANSIT", "WALK"],
    max_time=datetime.timedelta(minutes=90),           # ceiling; cumulative threshold applied later
    max_time_walking=datetime.timedelta(minutes=15),   # walk cap to first stop
    percentiles=[50],                                   # median across the departure window
)
matrix = computer.compute_travel_times()
```

Notes:

- `max_time_walking=15 min` matches the "station catchment" framing. Residents further than 15 min walk from a stop are treated as lacking a viable transit alternative.
- `percentiles=[50]` returns the median travel time across the departure window. Setting, say, `[25, 50, 75]` would quantify service unreliability, useful for the Albany intra-SA2 discussion in the H2 hypothesis.
- The departure date is a Tuesday outside school holidays to represent a typical weekday service pattern.

## JVM memory

R5 is memory-hungry. Defaults are too small for a regional network. Set heap size before the first r5py import:

```python
import sys
sys.argv += ["-Xmx8G"]          # max heap 8 GB
import r5py                     # after the flag is in place
```

Or on the command line:

```bash
export JAVA_TOOL_OPTIONS="-Xmx8G"
python code/stage2_routing.py
```

Symptoms of an undersized heap include silent crashes, `OutOfMemoryError` stack traces from inside the JVM, or extremely slow matrix computation while the JIT thrashes.

## Known constraints

- **Single-threaded GTFS build.** Assembling the transit graph is not parallelised. The 37 MB AT feed builds in ~30 seconds; there is no benefit to pre-splitting the feed.
- **No elevation.** By default r5py does not use elevation when computing walk/cycle times. For Auckland's topography this is an acceptable simplification at the SA2 scale; at finer scales (e.g., hilly inner suburbs like Mount Eden or Parnell) a terrain-aware model would be warranted.
- **Static feed only.** GTFS-realtime is not consumed. All travel times reflect the published schedule, not observed vehicle punctuality.

## Downstream stages

Once the travel-time matrix is written, stages 3 to 5 operate on DataFrames and GeoDataFrames alone. They do not touch the JVM, do not need `java` on the PATH, and can be re-run freely without recomputing the routing step.

- **Stage 3** applies the cumulative opportunity indicator at 30 and 45 min.
- **Stage 4** computes the concentration index and burden classification per scenario.
- **Stage 5** produces the choropleth, boxplot, stacked-bar, and forest-plot figures for the paper.

## References

- Conveyal, R5 routing engine, https://github.com/conveyal/r5
- r5py documentation, https://r5py.readthedocs.io
- Pereira et al., "r5r: Rapid Realistic Routing on Multimodal Transport Networks with R5 in R", Findings, 2021. (Companion R package; same JAR.)
