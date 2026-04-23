# 01. Data Retrieval

All datasets live under `data/`. This page documents the source, licence, and retrieval procedure for each of the four primary inputs: OSM road network, Auckland Transport GTFS feed, NZDep2023 deprivation index, and Stats NZ Business Demography Statistics employee count.

Every file is re-obtainable from its public source; none are redistributed in the repository.

## 1. OpenStreetMap (OSM)

**Purpose.** Walking and cycling access/egress legs between SA2 centroids and GTFS stops, plus any street-level routing r5py needs when filling gaps in the transit network.

**Source.** Geofabrik daily snapshot of the New Zealand extract.

**File format requirement.** r5py accepts only `.osm.pbf`. GeoPackage (`.gpkg`) is used for boundaries and results outside the routing engine, but is not a legal network input for r5py.

### Retrieval and clipping

```bash
# Full NZ PBF (377 MB as of 2026-04-22 snapshot)
wget https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf \
     -O data/new-zealand-latest.osm.pbf
```

The NZ-wide file is too large for the routing problem and wastes `TransportNetwork` build time. It is clipped to an Auckland bounding box using the "complete ways" strategy: every way with at least one node inside the box is kept in full, so no highway is artificially truncated at the bounding edge.

**Bounding box (WGS84).** `minlon=174.4, minlat=-37.1, maxlon=175.3, maxlat=-36.7`. This covers urban Auckland from Pūkekohe north to Warkworth approaches, west to Muriwai, east to the Firth of Thames entrance.

The reference implementation uses `osmium-tool`:

```bash
osmium extract \
    --bbox 174.4,-37.1,175.3,-36.7 \
    --strategy=complete_ways \
    data/new-zealand-latest.osm.pbf \
    -o data/auckland.osm.pbf \
    --overwrite
```

If `osmium-tool` is not on your PATH, an equivalent three-pass Python implementation using the `osmium` package is provided as `code/clip_osm.py` (see below).

### Three-pass Python fallback

```python
"""
Pass 1: read all nodes, record IDs of nodes whose lon/lat is inside bbox.
Pass 2: read all ways; if any of their nodes is in pass-1 set, mark the way
        as kept and collect every node ID the way references.
Pass 3: stream the file again, writing kept nodes, kept ways, and any
        relation whose members reference a kept way or needed node.
"""
import osmium as o

IN_PBF  = "data/new-zealand-latest.osm.pbf"
OUT_PBF = "data/auckland.osm.pbf"
MINLON, MINLAT, MAXLON, MAXLAT = 174.4, -37.1, 175.3, -36.7

nodes_in_bbox = set()
for obj in o.FileProcessor(IN_PBF, o.osm.NODE):
    loc = obj.location
    if loc.valid() and MINLON <= loc.lon <= MAXLON and MINLAT <= loc.lat <= MAXLAT:
        nodes_in_bbox.add(obj.id)

kept_ways, needed_nodes = set(), set()
for obj in o.FileProcessor(IN_PBF, o.osm.WAY):
    refs = [n.ref for n in obj.nodes]
    if any(r in nodes_in_bbox for r in refs):
        kept_ways.add(obj.id)
        needed_nodes.update(refs)

with o.SimpleWriter(OUT_PBF) as w:
    for obj in o.FileProcessor(IN_PBF):
        if obj.is_node() and obj.id in needed_nodes:
            w.add_node(obj)
        elif obj.is_way() and obj.id in kept_ways:
            w.add_way(obj)
        elif obj.is_relation():
            if any((m.type=='w' and m.ref in kept_ways) or
                   (m.type=='n' and m.ref in needed_nodes) for m in obj.members):
                w.add_relation(obj)
```

### Observed statistics (Apr 2026 snapshot)

| Item | Value |
|---|---|
| NZ total nodes scanned | 55,095,850 |
| NZ total ways scanned | 4,560,851 |
| Nodes written to Auckland PBF | 7,191,516 |
| Ways written | 945,856 |
| Ways with `highway=*` | 204,263 |
| Relations written | 8,122 |
| Output file size | 51 MB |
| Runtime (three passes, single thread) | ~3 min 20 s |

**Licence.** OSM data is © OpenStreetMap contributors, distributed under the Open Database Licence (ODbL). Attribution is required in any downstream publication.

## 2. Auckland Transport GTFS feed

**Purpose.** The transit layer for r5py. Includes every scheduled bus, train, and ferry service operating under the AT brand.

**Source.** Auckland Transport public static GTFS feed at `https://gtfs.at.govt.nz/gtfs.zip`. The URL is stable; the payload is regenerated on Auckland Transport's timetable publication cycle.

### Retrieval

```bash
wget "https://gtfs.at.govt.nz/gtfs.zip" -O data/at_gtfs.zip
```

No transformation is needed. r5py reads the ZIP directly.

### Contents of the Apr 2026 snapshot

- Thirteen standard GTFS files: `feed_info`, `agency`, `calendar`, `calendar_dates`, `routes`, `trips`, `stops`, `stop_times`, `shapes`, `transfers`, `fare_attributes`, `fare_rules`, `frequencies`
- 6,471 stops
- 220 routes, of which 198 bus (route_type 3), 17 ferry (route_type 4), 5 rail (route_type 2)
- `feed_start_date = 20260415`, `feed_end_date = 20260731`
- Feed publisher: Auckland Transport
- File size: 37 MB

**Licence.** Creative Commons Attribution 4.0, per Auckland Transport's data terms.

## 3. NZDep2023

**Purpose.** Area-level deprivation score and decile for every SA2 in Aotearoa New Zealand, published by the Health Inequalities Research Programme (HIRP) at the University of Otago, Wellington. Used as the distributional axis in the concentration index and as the stratification variable for burden classification.

**Source.** HIRP resources page on `otago.ac.nz`. The site sits behind Cloudflare challenge pages, so a plain `wget` or `curl` request receives a 403 HTML interstitial rather than the XLSX. Use the `cloudscraper` Python package (or a full browser) to retrieve the files.

### Retrieval

```python
import cloudscraper
s = cloudscraper.create_scraper()
urls = {
    "NZDep2023_WgtAvSA2.xlsx":
        "https://www.otago.ac.nz/__data/assets/excel_doc/0024/593142/NZDep2023_WgtAvSA2.xlsx",
    "NZDep2023_SA1_withHigherGeo.xlsx":
        "https://www.otago.ac.nz/__data/assets/excel_doc/0028/593146/NZDep2023_SA1_withHigherGeo.xlsx",
    "NZDep2023_SA1.xlsx":
        "https://www.otago.ac.nz/__data/assets/excel_doc/0029/593138/NZDep2023_SA1.xlsx",
    "NZDep2023-Users-Manual.pdf":
        "https://www.otago.ac.nz/__data/assets/pdf_file/0027/593136/NZDep2023-Users-Manual-31-October-2024.pdf",
}
for fname, url in urls.items():
    r = s.get(url, timeout=60)
    open(f"data/{fname}", "wb").write(r.content)
```

### Conversion to pipeline CSV

The SA2 weighted-average XLSX has six columns: `SA22023_code`, `SA22023_name`, `SA2_average_NZDep2023` (decile), `SA2_average_NZDep2023_score` (score), `SA32023_code`, `SA32023_name`. Stage 1 of the pipeline expects a CSV named `nzdep2023.csv` with column `NZDep2023` holding the raw score (so it can compute deciles consistently via `pd.qcut`).

```python
import pandas as pd
df = pd.read_excel("data/NZDep2023_WgtAvSA2.xlsx", sheet_name="NZDep2023_WgtAvSA2")
df = df.rename(columns={
    "SA22023_code": "SA22023_V1_00",
    "SA2_average_NZDep2023_score": "NZDep2023",
    "SA2_average_NZDep2023": "NZDep2023_decile",
})
df.to_csv("data/nzdep2023.csv", index=False)
```

### Observed statistics

| Item | Value |
|---|---|
| SA2 rows | 2,321 |
| Missing rows (unpopulated SA2s) | 0 |
| Score range | 924 (least deprived) to 1,253 (most deprived) |
| Decile 10 SA2 count | 231 |

**Citation.** Atkinson J, Salmond C, Crampton P. NZDep2023 Index of Socioeconomic Deprivation: Research Report. University of Otago, Wellington, 2024. See `data/NZDep2023-Users-Manual.pdf` for distributional notes and imputation treatment.

## 4. Employment (Business Demography Statistics, Feb 2025)

**Purpose.** Employee count by SA2 workplace address, used as the opportunity weight O_j in the cumulative accessibility formula.

**Source.** Stats NZ Business Demography Statistics information release (Feb 2025), supporting dataset "Geographic units by industry and statistical area: 2000 to 2025 descending order", published 16 Oct 2025. The release page is [here](https://www.stats.govt.nz/information-releases/new-zealand-business-demography-statistics-at-february-2025/).

### Why BDS instead of the 2023 Census travel-to-work matrix

An earlier attempt used the 2023 Census "Main means of travel to work by SA2" flow matrix (ArcGIS Hub item `fedc1252...`) and aggregated `2023_Total_stated` over workplace SA2 as a proxy for job counts. That produced:

- NZ total employed with stated workplace: 1.94 million
- Auckland total: 611,664

Those counts are depressed by (a) random-rounding and cell suppression with `-999` in low-count flows, and (b) respondents without a fixed workplace address being routed to a non-SA2 residual. They are also frozen to the 2023 reference date, which is 18 months older than BDS Feb 2025.

BDS Feb 2025 is an administrative-data product (linked employer monthly tax returns) with no cell suppression at the SA2-by-total-industry level. It gives:

- NZ total employees: 2,450,066 (matches the official BDS headline)
- Auckland total: 859,139
- 618 of 619 Auckland SA2 units matched (one unpopulated SA2 has no EC_count)

BDS is therefore adopted as the primary opportunity measure.

### Retrieval and extraction

Download the zip from the information release page. It contains two files: the main CSV (152 MB, 7.05 million rows) and an XLSX metadata workbook.

```bash
# Via the browser, downloaded to data/
# geographic-units-by-industry-and-statistical-area-2000-2025-descending-order.zip

unzip data/geographic-units-by-industry-and-statistical-area-2000-2025-descending-order.zip \
      -d data/bds_raw/
```

### Schema of the BDS CSV

| Column | Description |
|---|---|
| `anzsic06` | ANZSIC06 industry code. `Total` = all industries aggregated. Letter codes `A` to `S` are divisions; numeric codes are finer subdivisions. |
| `Area` | Geography. Prefix indicates level: `R##` Regional Council, `T###` Territorial Authority, `C###` Community Board, `A######` SA2. Special codes: `RTotal`, `TTotal`, `CTotal`. |
| `year` | February reference year, 2000 to 2025. |
| `geo_count` | Number of geographic units (workplace sites). |
| `ec_count` | Employee count, head count of salary and wage earners for the February reference month, sourced from IRD PAYE data. |

### Aggregation to `employment_sa2.csv`

Filter to all-industry totals, SA2 areas, latest year, then strip the `A` prefix and attach SA2 names from the metadata's `LookupAREA` sheet.

```python
import pandas as pd

df = pd.read_csv(
    "data/bds_raw/geographic-units-by-industry-and-statistical-area-2000-2025-descending-order-february-2025.csv",
    dtype={"Area": str, "anzsic06": str},
)
sub = df[(df["anzsic06"] == "Total")
         & df["Area"].str.match(r"^A\d{6}$")
         & (df["year"] == 2025)].copy()
sub["SA22023_V1_00"] = sub["Area"].str[1:]

meta = pd.read_excel(
    "data/bds_raw/metadata-for-geographic-units-by-industry-and-statistical-area-2000-2025-descending-order-february-2025.xlsx",
    sheet_name="LookupAREA",
)
meta_sa2 = (meta[meta["Area"].astype(str).str.match(r"^A\d{6}$")]
            .assign(SA22023_V1_00=lambda d: d["Area"].str[1:])
            .rename(columns={"Description": "SA22023_name"})
            [["SA22023_V1_00", "SA22023_name"]])

out = (sub.rename(columns={"ec_count": "jobs_count"})
          [["SA22023_V1_00", "geo_count", "jobs_count"]]
          .merge(meta_sa2, on="SA22023_V1_00", how="left"))

out[["SA22023_V1_00", "SA22023_name", "geo_count", "jobs_count"]].to_csv(
    "data/employment_sa2.csv", index=False
)
```

### Observed top-10 Auckland SA2s (`jobs_count`, Feb 2025)

| SA2 code | Name | geo_count | jobs_count |
|---:|---|---:|---:|
| 147900 | Auckland Airport | 1,098 | 31,800 |
| 145900 | Penrose | 2,136 | 30,700 |
| 152300 | East Tāmaki | 2,529 | 29,900 |
| 131300 | Wynyard-Viaduct | 1,422 | 25,600 |
| 133301 | Quay Street-Customs Street | 2,661 | 25,500 |
| 118600 | North Harbour | 3,969 | 24,200 |
| 155500 | Manukau Central | 1,677 | 19,100 |
| 157600 | Wiri West | 828 | 18,400 |
| 138501 | Newmarket | 3,174 | 17,900 |
| 133200 | Queen Street | 2,856 | 17,400 |

Industrial and airport SA2s dominate the ranking above the CBD spine, which is consistent with the Auckland Council employment survey and provides face validity.

**Licence.** Stats NZ products are Creative Commons Attribution 4.0 International.

## 5. SA2 geography

**Purpose.** Spatial unit of analysis. Every SA2 polygon is a row in the final GeoPackage.

**Source.** Stats NZ Geographic Data Service. The `auckland_sa2.gpkg` in this repository is a regional clip of the SA2 layer.

**Note on code versioning.** The supplied `auckland_sa2.gpkg` carries column `SA22026_V1_00` rather than `SA22023_V1_00`. 618 of 619 codes match the 2023 boundary set exactly, so join to NZDep2023 and BDS 2025 succeeds on almost every unit. Stage 1's auto-rename logic looks for `2023` in a column name and will miss `SA22026_V1_00`. Either extend the match to include `2026`, or rename the column before running the pipeline.

## Manifest

After all retrieval steps:

```
data/
├── auckland.osm.pbf                       51 MB
├── auckland_region.gpkg                   11 MB   (TA boundary, optional)
├── auckland_sa2.gpkg                      13 MB
├── at_gtfs.zip                            37 MB
├── employment_sa2.csv                     66 KB
├── nzdep2023.csv                         121 KB
├── NZDep2023_WgtAvSA2.xlsx               120 KB
├── NZDep2023_SA1_withHigherGeo.xlsx      2.2 MB
├── NZDep2023_SA1.xlsx                    1.2 MB
├── NZDep2023-Users-Manual.pdf            354 KB
└── bds_raw/                              153 MB
```

Only the six files in the root are required for the pipeline. The rest are reference copies kept for provenance.
