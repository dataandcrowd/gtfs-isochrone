"""
Stage 4: Equity metrics
- Concentration Index (CI) of accessibility against NZDep rank
- Scenario-specific burden classification per SA2:
    pays_with_alternative / pays_without_alternative / no_charge
- Cross-tabulation of burden against NZDep decile for all 6 scenarios
- Outputs: sa2_equity.gpkg, equity_summary.csv
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _io_utils import safe_read_gpkg, safe_to_gpkg  # noqa: E402

OUTPUT = Path("outputs")
SA2_PATH = OUTPUT / "sa2_accessibility.gpkg"
if not (SA2_PATH.exists() and SA2_PATH.stat().st_size > 0):
    raise FileNotFoundError(f"No accessibility file at {SA2_PATH}. Run stage3 first.")

# ── 4a. Load accessibility layer ─────────────────────────────────────────────
sa2 = safe_read_gpkg(SA2_PATH)
print(f"Loaded {len(sa2)} SA2 units")

# ── 4b. Concentration Index ───────────────────────────────────────────────────
def concentration_index(health_var, deprivation_rank):
    """
    CI = (2 / mu) * Cov(y, r)
    where r is the fractional rank of the deprivation variable (0 to 1).

    Convention used here:
        deprivation_rank: higher value = more deprived (NZDep scale)
        CI < 0: accessibility is concentrated in more affluent SA2s
                (i.e. deprived areas have LESS access — regressive)
        CI > 0: accessibility is concentrated in more deprived SA2s
        CI = 0: equal distribution

    Parameters
    ----------
    health_var        : array-like, accessibility scores (A_i)
    deprivation_rank  : array-like, NZDep score per SA2

    Returns
    -------
    float, Concentration Index value
    """
    df = pd.DataFrame({
        "y": health_var,
        "rank": deprivation_rank
    }).dropna()

    if len(df) < 2:
        return np.nan

    n = len(df)
    df["r_frac"] = df["rank"].rank(method="average") / n
    mu = df["y"].mean()

    if mu == 0:
        return np.nan

    cov = np.cov(df["y"], df["r_frac"], bias=True)[0, 1]
    return round(2 * cov / mu, 4)

ci_30 = concentration_index(sa2["access_30min"], sa2["NZDep2023"])
ci_45 = concentration_index(sa2["access_45min"], sa2["NZDep2023"])

print(f"\nConcentration Index:")
print(f"  30-min accessibility: CI = {ci_30:.4f}")
print(f"  45-min accessibility: CI = {ci_45:.4f}")
print(f"  Interpretation: CI < 0 means accessibility is concentrated in")
print(f"  more affluent (low NZDep) SA2s — regressive pattern")

# ── 4c. Define AT TOUC scenario cordon / corridor SA2 sets ──────────────────
# Approximated from the Auckland Transport Time-of-Use Charging slide deck
# (scenario maps for 1a, 1c, 2c, 3b, 3c, 3e). Each scenario is listed by
# SA22026_V1_00_NAME; names are resolved to SA22023_V1_00 codes below.
# These are "best-fit" SA2 footprints for the AT polygons; the final paper
# should replace them with the actual shapefile-driven intersection once
# the AT boundary files are released.

# Scenario 1a — City Centre inner cordon (Cook St / Victoria St / Fanshawe St
# / Stanley St / K Rd north edge). Small polygon covering the CBD core.
_S1A_NAMES = [
    "Wynyard-Viaduct",
    "Victoria Park",
    "Quay Street-Customs Street",
    "Shortland Street",
    "Queen Street",
    "Queen Street South West",
    "Anzac Avenue",
    "The Strand",
    "Auckland-University",
    "Hobson Ridge North",
    "Hobson Ridge Central",
    "Hobson Ridge South",
    "Symonds Street East",
    "Symonds Street North West",
    "Symonds Street West",
]

# Scenario 1c — City Centre + inner fringe (adds K Rd, Freemans Bay,
# Saint Marys Bay, Eden Terrace, Grafton, Newmarket, Parnell).
_S1C_NAMES = _S1A_NAMES + [
    "Karangahape East",
    "Karangahape West",
    "Freemans Bay",
    "College Hill",
    "Saint Marys Bay",
    "Eden Terrace",
    "Grafton",
    "Grafton West",
    "Newmarket",
    "Newmarket Park",
    "Parnell East",
    "Parnell West",
]

# Scenario 2c — Isthmus double cordon. Covers the entire central isthmus
# between the Waitematā and Manukau harbours. Large polygon from Pt Chev /
# Westmere in the west through to Glendowie / Tāmaki / St Heliers in the
# east, bounded to the south by Onehunga / Penrose / Sylvia Park.
_S2C_NAMES = _S1C_NAMES + [
    # Inner-west
    "Ponsonby East", "Ponsonby West",
    "Herne Bay",
    "Saint Marys Bay",
    "Grey Lynn Central", "Grey Lynn East", "Grey Lynn North", "Grey Lynn West",
    "Westmere North", "Westmere South-Western Springs",
    "Morningside (Auckland)",
    "Kingsland",
    "Eden Park", "Eden Valley",
    "Point Chevalier East", "Point Chevalier North", "Point Chevalier West",
    "Waterview",
    # Mt Eden / Sandringham / Balmoral
    "Mount Eden East", "Mount Eden North", "Mount Eden North East",
    "Mount Eden South", "Mount Eden West",
    "Maungawhau",
    "Mount St John",
    "Sandringham Central", "Sandringham East", "Sandringham North", "Sandringham West",
    "Balmoral",
    "Ōwairaka East", "Ōwairaka West",
    # Epsom / Three Kings / Mt Albert / Mt Roskill
    "Epsom Central-North", "Epsom Central-South",
    "Epsom East", "Epsom North", "Epsom South",
    "Three Kings North", "Three Kings South",
    "Mount Albert Central", "Mount Albert North", "Mount Albert South", "Mount Albert West",
    "Mount Roskill Central East", "Mount Roskill Central North",
    "Mount Roskill Central South", "Mount Roskill Nirvana",
    "Mount Roskill North", "Mount Roskill North East",
    "Mount Roskill South", "Mount Roskill South East",
    "Mount Roskill West", "Mount Roskill White Swan",
    # South edge (harbour): Onehunga / Royal Oak / Penrose
    "Onehunga Central", "Onehunga North", "Onehunga West",
    "Onehunga-Te Papapa Industrial",
    "Te Papapa",
    "Royal Oak East (Auckland)", "Royal Oak West (Auckland)",
    "One Tree Hill Amaru", "One Tree Hill Oranga",
    "Oranga",
    "Penrose",
    "Hillsborough Central (Auckland)", "Hillsborough North (Auckland)",
    "Hillsborough South (Auckland)",
    "Hilltop (Auckland)",
    "Lynfield Central", "Lynfield Harbour View",
    "Blockhouse Bay Central", "Blockhouse Bay East", "Blockhouse Bay North",
    "Blockhouse Bay North East", "Blockhouse Bay South",
    "Waikowhai Bay",
    "New Windsor East", "New Windsor North", "New Windsor South",
    # Greenlane / Ellerslie / Remuera / Meadowbank / Orakei corridor
    "Greenlane Central", "Greenlane North", "Greenlane South",
    "Ellerslie Central", "Ellerslie East", "Ellerslie South", "Ellerslie West",
    "Remuera Abbotts Park", "Remuera East", "Remuera North", "Remuera South",
    "Remuera Waiata", "Remuera Waiatarua", "Remuera Waitaramoa", "Remuera West",
    "Meadowbank East", "Meadowbank West",
    "Orakei East", "Orakei West",
    "Mission Bay", "Mission Bay Eastridge",
    "Kohimarama Bay", "Kohimarama Stadium",
    "Saint Heliers North", "Saint Heliers South", "Saint Heliers West",
    "Glendowie North", "Glendowie South East", "Glendowie South West",
    # Eastern isthmus: St Johns / Stonefields / Tāmaki / Glen Innes
    "Saint Johns East", "Saint Johns West",
    "Stonefields East", "Stonefields West",
    "Tamaki East", "Tamaki West",
    "Glen Innes East-Wai O Taiki Bay", "Glen Innes West",
    "Point England North", "Point England South",
    "Panmure East", "Panmure West",
    "Panmure Glen Innes Industrial",
    # Mt Wellington / Sylvia Park industrial frame (south-east edge of isthmus)
    "Mount Wellington Central", "Mount Wellington East",
    "Mount Wellington Ferndale", "Mount Wellington Hamlin",
    "Mount Wellington Industrial",
    "Mount Wellington North East", "Mount Wellington North West",
    "Mount Wellington South East", "Mount Wellington South West",
    "Mount Wellington West",
    "Sylvia Park",
]

# Scenario 3b — Core Motorway corridors (SH1 North, SH1 South, SH16, SH20).
# SA2s that sit directly on or within ~1 km of the motorway alignment.
_S3B_NAMES = [
    # SH1 North — Harbour Bridge to Pūhoi, plus Upper Harbour (SH18) link
    "Northcote Point (Auckland)", "Northcote Central (Auckland)", "Northcote South (Auckland)",
    "Northcote Tuff Crater",
    "Akoranga",
    "Hillcrest East (Auckland)", "Hillcrest North (Auckland)", "Hillcrest West (Auckland)",
    "Wairau Valley",
    "Glenfield Central", "Glenfield East", "Glenfield North",
    "Glenfield South West", "Glenfield West",
    "Sunnynook North", "Sunnynook South",
    "Forrest Hill East", "Forrest Hill North", "Forrest Hill West",
    "Totara Vale North", "Totara Vale South",
    "Unsworth Heights East", "Unsworth Heights West",
    "Windsor Park",
    "Northcross",
    "Pinehill North", "Pinehill South",
    "Fairview Heights",
    "Schnapper Rock",
    "Oteha East", "Oteha West",
    "Albany Central", "Albany Heights", "Albany South", "Albany West",
    "North Harbour",
    "Dairy Flat South", "Dairy Flat West",
    # SH1 South — CBD fringe to Drury
    "Grafton", "Grafton West",
    "Newmarket", "Newmarket Park",
    "Parnell East", "Parnell West",
    "Mount Eden East", "Mount Eden South",
    "Greenlane Central", "Greenlane North", "Greenlane South",
    "Ellerslie Central", "Ellerslie East", "Ellerslie South", "Ellerslie West",
    "Penrose",
    "Mount Wellington South West", "Mount Wellington South East",
    "Mount Wellington Industrial",
    "Sylvia Park",
    "Ōtāhuhu Central", "Ōtāhuhu East", "Ōtāhuhu Industrial",
    "Ōtāhuhu North East", "Ōtāhuhu North West",
    "Ōtāhuhu South", "Ōtāhuhu South West",
    "Middlemore",
    "Papatoetoe Central East", "Papatoetoe Central West",
    "Papatoetoe East", "Papatoetoe North",
    "Papatoetoe North East", "Papatoetoe North West",
    "Papatoetoe South", "Papatoetoe South West", "Papatoetoe West",
    "Manukau Central",
    "Wiri East", "Wiri North", "Wiri West",
    "Manurewa Central", "Manurewa East", "Manurewa South", "Manurewa West",
    "Homai Central", "Homai East", "Homai West",
    "Takanini Central", "Takanini East", "Takanini Industrial",
    "Takanini McLennan", "Takanini North", "Takanini South",
    "Takanini South East", "Takanini West",
    "Papakura Central", "Papakura East", "Papakura Eastburn",
    "Papakura Industrial", "Papakura Kelvin", "Papakura Massey Park",
    "Papakura North", "Papakura North East", "Papakura West",
    "Ōpaheke",
    "Rosehill",
    "Drury East", "Drury West",
    "Hingaia",
    # SH16 — Northwestern Motorway, CBD (Grafton Gully) to Brigham Creek
    "St Lukes",
    "Morningside (Auckland)",
    "Waterview",
    "Rosebank Peninsula",
    "Avondale North East (Auckland)", "Avondale North West (Auckland)",
    "Avondale Rosebank (Auckland)", "Avondale Central (Auckland)",
    "Avondale South (Auckland)", "Avondale West (Auckland)",
    "Te Atatū Peninsula Central", "Te Atatū Peninsula East",
    "Te Atatū Peninsula North West", "Te Atatū Peninsula West",
    "Te Atatū South-Central", "Te Atatū South-Edmonton",
    "Te Atatū South-McLeod North", "Te Atatū South-McLeod South",
    "Te Atatū South-North",
    "Henderson Central", "Henderson East", "Henderson Larnoch",
    "Henderson Lincoln East", "Henderson Lincoln South", "Henderson Lincoln West",
    "Henderson North", "Henderson North East", "Henderson West",
    "Massey Central", "Massey Keegan", "Massey Red Hills",
    "Massey South", "Massey West",
    "Royal Heights North", "Royal Heights South",
    "Westgate Central", "Westgate South",
    "Hobsonville",
    "Hobsonville Point Catalina Bay", "Hobsonville Point Park", "Hobsonville Scott Point",
    "Whenuapai", "Whenuapai West",
    # SH20 — Southwestern Motorway, Waterview Tunnel to SH1 via Manukau
    "Mount Roskill South", "Mount Roskill South East",
    "Mount Roskill White Swan",
    "Royal Oak East (Auckland)", "Royal Oak West (Auckland)",
    "Onehunga Central", "Onehunga West",
    "Onehunga-Te Papapa Industrial",
    "Māngere Bridge", "Māngere Bridge Ambury",
    "Māngere Central", "Māngere East", "Māngere Mascot",
    "Māngere Mountain View", "Māngere North", "Māngere South",
    "Māngere South East", "Māngere West",
    "Favona East", "Favona North", "Favona West",
    "Auckland Airport",
]

# Scenario 3c — Core Motorways + City Centre (3b ∪ 1a)
_S3C_NAMES = list(set(_S3B_NAMES) | set(_S1A_NAMES))

# Scenario 3e — Targeted motorway hotspots (three AT pinch-points):
#  (i)  Upper Harbour / Constellation / Greville Rd (SH1 × SH18)
#  (ii) Waterview / SH16 × SH20 interchange
#  (iii) Papakura–Drury southern bottleneck (SH1 south)
_S3E_NAMES = [
    # (i) North Shore upper-harbour bottleneck
    "Albany South", "Unsworth Heights East", "Unsworth Heights West",
    "Pinehill North", "Pinehill South",
    "Oteha East", "Oteha West",
    "Windsor Park",
    # (ii) Waterview / western interchange
    "Waterview",
    "Point Chevalier East",
    "Mount Albert South",
    "Mount Roskill North",
    "Rosebank Peninsula",
    # (iii) Papakura–Drury southern bottleneck
    "Takanini Industrial", "Takanini South", "Takanini South East",
    "Papakura Industrial", "Papakura Kelvin",
    "Ōpaheke",
    "Drury East", "Drury West",
    "Hingaia",
]

# Resolve SA2 names → SA22023_V1_00 IDs, warning on any misses.
_name_to_id = dict(zip(sa2["SA22026_V1_00_NAME"], sa2["SA22023_V1_00"]))

def _names_to_ids(names, scenario_label):
    ids = set()
    missing = []
    for nm in names:
        code = _name_to_id.get(nm)
        if code is None:
            missing.append(nm)
        else:
            ids.add(code)
    if missing:
        print(f"  [warn] Scenario {scenario_label}: {len(missing)} name(s) not found in SA2 layer:")
        for m in missing:
            print(f"         - {m}")
    return ids

SCENARIO_SA2_SETS = {
    "1a": _names_to_ids(_S1A_NAMES, "1a"),
    "1c": _names_to_ids(_S1C_NAMES, "1c"),
    "2c": _names_to_ids(_S2C_NAMES, "2c"),
    "3b": _names_to_ids(_S3B_NAMES, "3b"),
    "3c": _names_to_ids(_S3C_NAMES, "3c"),
    "3e": _names_to_ids(_S3E_NAMES, "3e"),
}

print("\nScenario SA2 set sizes:")
for k, v in SCENARIO_SA2_SETS.items():
    print(f"  {k}: {len(v)} SA2s")

# ── 4d. Burden classification function ───────────────────────────────────────
# Viable alternative threshold: top quartile of 30-min job accessibility
VIABLE_ALT_THRESHOLD = sa2["access_30min"].quantile(0.75)

def classify_burden(sa2_id, access_30min, charged_sa2_set, threshold):
    """
    Returns one of three burden categories:
        'pays_with_alternative'    — in cordon, good PT access
        'pays_without_alternative' — in cordon, poor PT access (trapped payer)
        'no_charge'                — outside cordon
    """
    if sa2_id in charged_sa2_set:
        if access_30min >= threshold:
            return "pays_with_alternative"
        else:
            return "pays_without_alternative"
    return "no_charge"

# ── 4e. Apply burden classification for all scenarios ────────────────────────
ci_results = {}

for scenario, charged_set in SCENARIO_SA2_SETS.items():
    col = f"burden_{scenario}"
    sa2[col] = sa2.apply(
        lambda row: classify_burden(
            row["SA22023_V1_00"],
            row["access_30min"],
            charged_set,
            VIABLE_ALT_THRESHOLD
        ),
        axis=1
    )

    # CI for charged SA2s only
    charged_mask = sa2[col] != "no_charge"
    ci_charged = concentration_index(
        sa2.loc[charged_mask, "access_30min"],
        sa2.loc[charged_mask, "NZDep2023"]
    )
    ci_results[scenario] = ci_charged

    n_with    = (sa2[col] == "pays_with_alternative").sum()
    n_without = (sa2[col] == "pays_without_alternative").sum()
    print(f"  Scenario {scenario}: {n_with} pays+alt, {n_without} trapped, CI={ci_charged}")

# ── 4f. Cross-tabulation: burden x NZDep decile for each scenario ────────────
crosstabs = {}

for scenario in SCENARIO_SA2_SETS:
    col = f"burden_{scenario}"
    ct = (
        sa2.groupby(["NZDep_Decile", col])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    ct["scenario"] = scenario
    crosstabs[scenario] = ct

crosstab_all = pd.concat(crosstabs.values(), ignore_index=True)

# ── 4g. CI summary table ─────────────────────────────────────────────────────
ci_summary = pd.DataFrame({
    "scenario": list(ci_results.keys()),
    "CI_charged_sa2s": list(ci_results.values()),
    "CI_all_30min": ci_30,
    "CI_all_45min": ci_45,
    "viable_alt_threshold_jobs": VIABLE_ALT_THRESHOLD
})

print("\nCI summary by scenario:")
print(ci_summary.to_string(index=False))

# ── 4h. Save ──────────────────────────────────────────────────────────────────
OUT_GPKG = OUTPUT / "sa2_equity.gpkg"
safe_to_gpkg(sa2, OUT_GPKG)
print(f"  equity layer written to {OUT_GPKG.name}")
crosstab_all.to_csv(OUTPUT / "burden_crosstab.csv", index=False)
ci_summary.to_csv(OUTPUT / "equity_summary.csv", index=False)

print(f"\nStage 4 complete.")
print(f"  sa2_equity.gpkg       — SA2 polygons with burden classification")
print(f"  burden_crosstab.csv   — burden x NZDep decile cross-tabulation")
print(f"  equity_summary.csv    — CI per scenario")

# ── 4i. Scenario boundary polygons + 2x3 map ────────────────────────────────
# Dissolve each scenario's charged SA2s into one multipolygon and render a
# 2x3 grid map (fig0). This uses the in-memory `sa2` GeoDataFrame, so it runs
# in the same Python process as stage 4 (avoiding reload of any just-written
# GeoPackage).
print("\nBuilding scenario boundary polygons (stage 4i)...")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

FIGS = OUTPUT / "figures"; FIGS.mkdir(exist_ok=True)

SCENARIO_TITLES = {
    "1a": "1a, City centre cordon",
    "1c": "1c, City centre + fringe",
    "2c": "2c, Isthmus double cordon",
    "3b": "3b, Core motorways",
    "3c": "3c, Core motorways + CBD",
    "3e": "3e, Motorway hotspots",
}

_rows = []
for _sc in SCENARIO_SA2_SETS.keys():
    _col = f"burden_{_sc}"
    if _col not in sa2.columns:
        continue
    _charged = sa2[sa2[_col] != "no_charge"]
    if len(_charged) == 0:
        continue
    _n_sa2  = len(_charged)
    _n_trap = int((_charged[_col] == "pays_without_alternative").sum())
    _geom   = _charged.dissolve().geometry.iloc[0]
    _rows.append({
        "scenario": _sc,
        "label": SCENARIO_TITLES[_sc],
        "n_sa2": _n_sa2,
        "n_trapped_payers": _n_trap,
        "geometry": _geom,
    })
    print(f"  {_sc}: {_n_sa2} SA2s dissolved ({_n_trap} trapped)")

boundaries = gpd.GeoDataFrame(_rows, geometry="geometry", crs=sa2.crs)

_bnd_path = safe_to_gpkg(boundaries, OUTPUT / "scenario_boundaries.gpkg")
print(f"  scenario boundary layer written to {_bnd_path.name}")

# Also write a plain CSV (no geometry) so it can be read anywhere.
pd.DataFrame(boundaries.drop(columns="geometry")).to_csv(
    OUTPUT / "scenario_boundaries_summary.csv", index=False
)

# ── Map: 2x3 grid ────────────────────────────────────────────────────────────
CORDON_FILL  = "#2C7A7B"
CORDON_EDGE  = "#1D4E50"
MWAY_FILL    = "#C05621"
MWAY_EDGE    = "#7B2F10"
TRAPPED_FILL = "#D4421E"
BASE_FILL    = "#F4F1EA"
BASE_EDGE    = "#1B1917"

MAP_XLIM = (174.55, 175.00)
MAP_YLIM = (-37.10, -36.60)

sa2_wgs        = sa2.to_crs(epsg=4326)
boundaries_wgs = boundaries.to_crs(epsg=4326)

_fig, _axes = plt.subplots(2, 3, figsize=(15, 10), constrained_layout=True)

for _ax, _sc in zip(_axes.flatten(), list(SCENARIO_SA2_SETS.keys())):
    _ax.set_facecolor("white")
    sa2_wgs.plot(
        ax=_ax,
        facecolor=BASE_FILL,
        edgecolor=BASE_EDGE,
        linewidth=0.15,
    )
    _col = f"burden_{_sc}"
    _is_mway = _sc in ("3b", "3c", "3e")
    _fill = MWAY_FILL if _is_mway else CORDON_FILL
    _edge = MWAY_EDGE if _is_mway else CORDON_EDGE
    if _col in sa2_wgs.columns:
        _charged = sa2_wgs[sa2_wgs[_col] != "no_charge"]
        _trapped = sa2_wgs[sa2_wgs[_col] == "pays_without_alternative"]
        if not _charged.empty:
            _charged.plot(
                ax=_ax,
                facecolor=_fill,
                edgecolor=BASE_EDGE,
                linewidth=0.2,
                alpha=0.55,
            )
        if not _trapped.empty:
            _trapped.plot(
                ax=_ax,
                facecolor=TRAPPED_FILL,
                edgecolor=BASE_EDGE,
                linewidth=0.25,
                alpha=0.78,
            )
        _bnd_row = boundaries_wgs[boundaries_wgs["scenario"] == _sc]
        if not _bnd_row.empty:
            _bnd_row.boundary.plot(ax=_ax, edgecolor=_edge, linewidth=1.6)

    _mask = boundaries_wgs["scenario"] == _sc
    _n_sa2  = int(boundaries_wgs.loc[_mask, "n_sa2"].iloc[0]) if _mask.any() else 0
    _n_trap = int(boundaries_wgs.loc[_mask, "n_trapped_payers"].iloc[0]) if _mask.any() else 0

    _ax.set_title(
        f"{SCENARIO_TITLES[_sc]}\n"
        f"{_n_sa2} SA2s charged, {_n_trap} trapped payers",
        fontsize=10,
        loc="center",
    )
    _ax.set_xlim(*MAP_XLIM)
    _ax.set_ylim(*MAP_YLIM)
    _ax.set_xticks([]); _ax.set_yticks([])
    for _sp in _ax.spines.values():
        _sp.set_visible(False)

_legend = [
    Patch(facecolor=CORDON_FILL, edgecolor=CORDON_EDGE, alpha=0.55,
          label="Charged SA2 (cordon scenario)"),
    Patch(facecolor=MWAY_FILL, edgecolor=MWAY_EDGE, alpha=0.55,
          label="Charged SA2 (motorway corridor scenario)"),
    Patch(facecolor=TRAPPED_FILL, edgecolor=BASE_EDGE, alpha=0.78,
          label="Trapped payer (no 30-min PT alternative)"),
    Line2D([0], [0], color=CORDON_EDGE, linewidth=1.6,
           label="Scenario footprint (dissolved boundary)"),
]
_fig.legend(
    handles=_legend,
    loc="lower center",
    ncol=4,
    frameon=False,
    fontsize=9,
    bbox_to_anchor=(0.5, -0.02),
)
_fig.suptitle(
    "Auckland TOUC scenario footprints and trapped-payer exposure",
    fontsize=13,
    fontweight="bold",
)

_out_png = FIGS / "fig0_scenario_boundaries.png"
plt.savefig(_out_png, dpi=200, bbox_inches="tight")
plt.close(_fig)
print(f"  scenario boundary map written to {_out_png.name}")
print("Stage 4i complete.")
