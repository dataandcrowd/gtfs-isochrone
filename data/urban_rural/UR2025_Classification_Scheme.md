# Urban Rural (UR) 2025 Classification Scheme

**Dataset:** UR2025_V1_00
**Source:** Stats NZ
**Reference date:** 1 January 2025
**Coverage:** 689 UR areas (195 urban areas, 402 rural settlements)

The Urban Rural (UR) classification is an output geography that groups New Zealand into areas sharing common urban or rural characteristics. It is used to disseminate a broad range of Stats NZ's social, demographic, and economic statistics. Urban areas are built from the Statistical Area 2 (SA2) geography, while rural and water areas are built from the Statistical Area 1 (SA1) geography.

## 1. Urban Areas

Urban areas are statistically defined areas with no administrative or legal basis, delineated using the following criteria.

| Criterion | Definition |
|---|---|
| Geometry | A contiguous cluster of one or more SA2s |
| Population | Estimated resident population of more than 1,000 |
| Density | Usually more than 400 residents or 200 address points per square kilometre |
| Built environment | Residential dwellings and apartments; commercial structures (factories, office complexes, shopping centres); transport and communication facilities (airports, ports, railway and bus stations); medical, education, and community facilities; tourist attractions and accommodation; waste disposal and sewerage facilities; cemeteries; sports and recreation facilities (stadiums, golf courses, racecourses, showgrounds, fitness centres); green spaces (community parks, gardens, reserves) |
| Economic ties | Strong economic ties where people gather for work, social, cultural, and recreational interaction |
| Planning | Planned development within the next 5–8 years |

Urban boundaries are independent of local government and other administrative boundaries. The Richmond urban area (mainly in the Tasman District) is the only urban area that crosses territorial authority boundaries.

## 2. Rural Areas

Rural areas are classified as either rural settlements or other rural.

### 2.1 Rural Settlements

| Criterion | Definition |
|---|---|
| Geometry | A contiguous cluster of one or more SA1s |
| Population | Estimated resident population of 200–1,000, or at least 40 residential dwellings |
| Density | At least 200 residents or 100 address points per square kilometre |
| Facilities | At least one community or public building (e.g. church, school, or shop) |

To reach the target SA2 population size of more than 1,000 residents, rural settlements are usually combined with other rural SA1s to form an SA2. In some cases the settlement and the SA2 share the same name (e.g. Kirwee). Some rural settlements with populations just under 1,000 form a single SA2, allowing easy reclassification to urban status if their population grows.

### 2.2 Other Rural

Other rural areas are mainland areas and islands located outside urban areas or rural settlements, including land used for agriculture and forestry, conservation areas, and regional and national parks. Other rural areas are defined by territorial authority.

## 3. Water

Bodies of water are classified separately using the land/water demarcation in the *Statistical Standard for Meshblock*. Water areas are not named.

| Water class | Defined by | Contiguity |
|---|---|---|
| Inland water | Territorial authority | Non-contiguous |
| Inlets (incl. tidal areas and harbours) | Territorial authority | Non-contiguous |
| Oceanic | Regional council | Non-contiguous |

Separate meshblocks have been created for marinas, attached to adjacent land in the UR geography, to minimise suppression of population data.

## 4. Non-digitised Areas

Four non-digitised UR areas have been aggregated from 16 non-digitised meshblocks/SA2s:

| Code | Name |
|---|---|
| 6901 | Oceanic outside region |
| 6902 | Oceanic oil rigs |
| 6903 | Islands outside region |
| 6904 | Ross Dependency outside region |

## 5. UR Numbering and Naming

Each urban area and rural settlement is a single geographic entity with a name and a numeric code. Other rural areas, inland water areas, and inlets are defined by territorial authority; oceanic areas are defined by regional council. Each has a name and a numeric code.

| Code prefix | Region |
|---|---|
| 1 | North Island |
| 2 | South Island |
| 6 | Oceanic |
| 69 | Non-digitised |

## 6. Urban Rural Indicator (IUR)

The Urban Rural Indicator (IUR) classifies urban, rural, and water areas by type. Urban areas are further classified by estimated resident population size, based on 2018 Census data and 2021 population estimates. IUR status may change if the 2025 Census population count moves an area up or down a category.

| Code | Class | Population threshold |
|---|---|---|
| 11 | Major urban area | 100,000 or more residents |
| 12 | Large urban area | 30,000–99,999 residents |
| 13 | Medium urban area | 10,000–29,999 residents |
| 14 | Small urban area | 1,000–9,999 residents |
| 21 | Rural settlement | — |
| 22 | Rural other | — |
| 31 | Inland water | — |
| 32 | Inlet | — |
| 33 | Oceanic | — |

## 7. High Definition (HD) Version

The HD version is the most detailed geometry, suitable for GIS geometric analysis and the computation of areas, centroids, and other metrics. It is aligned to the LINZ cadastre.

## 8. Macrons

Place names are provided with and without tohutō/macrons. The column for names without macrons is suffixed "ascii".

## Additional Information

- **Digital data availability:** Digital boundary data became freely available on 1 July 2007.
- **Table downloads:** Geographic classifications in table formats (e.g. CSV) are available via Ariā.
- **Standard reference:** *Statistical Standard for Geographic Areas 2025* (formerly the 2023 edition).
- **Contact:** geography@stats.govt.nz
- **Identifier:** https://datafinder.stats.govt.nz/layer/120965-urban-rural-2025/
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Geographic coverage:** -47.841491, -180 to -33.559984, 180

---
*Source: Stats NZ, Dublin Core metadata for UR2025_V1_00*
