"""
Stage 4g: Does the desire-path test stand in for actual motorway use?

Motivation
----------
The corridor test charges an OD pair when the straight desire path between SA2
centroids intersects the priced corridor, and 92% of the commuters it charges
under 3b have a trip end inside the corridor rather than passing through it.
The substantive defence of that is Auckland's geography: the isthmus is pinched
between two harbours and SH1/SH16/SH20 are the only continuous cross-town
routes, so a car commute of any length funnels onto the motorway. That is an
assertion until the actual driving routes are measured.

This script routes a population-weighted sample of commutes on the OSM driving
network and measures, for each, what share of the route runs on a motorway and
on the PRICED motorway specifically.

Input : outputs/intermediate/od_pairs_classified.parquet
        data/sa2/sa2_prepared.gpkg, data/osm/auckland.osm.pbf
        data/scenarios/scenario_3b.gpkg
Output: outputs/route_motorway_share.csv
"""

import argparse
import datetime
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import r5py
from shapely.geometry import LineString

OUTPUT   = Path("outputs")
OSM      = Path("data") / "osm" / "auckland.osm.pbf"
SCENARIO = "3b"
MW_TOL   = 30.0     # m: how close a route segment must run to a motorway centreline


def build_sample(n):
    sa2 = gpd.read_file("data/sa2/sa2_prepared.gpkg")
    sa2["k"] = sa2["SA22023_V1_00"].astype(str)
    cen = gpd.GeoSeries(gpd.points_from_xy(sa2["lon"], sa2["lat"]), crs=4326)
    nztm = cen.to_crs(2193)
    xy = dict(zip(sa2["k"], zip(nztm.x, nztm.y)))
    wgs = dict(zip(sa2["k"], zip(cen.x, cen.y)))

    od = pd.read_parquet(OUTPUT / "intermediate" / "od_pairs_classified.parquet")
    od["res"] = od["residence_sa2"].astype(str)
    od["wrk"] = od["workplace_sa2"].astype(str)
    od = od[od["res"].isin(xy) & od["wrk"].isin(xy) & (od["res"] != od["wrk"])].copy()

    corridor = gpd.read_file(f"data/scenarios/scenario_{SCENARIO}.gpkg").to_crs(2193).geometry.union_all()
    od["charged"] = [LineString([xy[a], xy[b]]).intersects(corridor)
                     for a, b in zip(od["res"], od["wrk"])]
    od["straight_km"] = [np.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1]) / 1000
                         for a, b in zip(od["res"], od["wrk"])]

    if n and n > 0:
        sample = od[od["charged"]].nlargest(n, "car_commuters").copy()
        print(f"Sample: {len(sample):,} charged OD pairs carrying "
              f"{int(sample['car_commuters'].sum()):,} commuters "
              f"({100*sample['car_commuters'].sum()/od.loc[od['charged'],'car_commuters'].sum():.1f}% "
              f"of all {SCENARIO}-charged)")
    else:
        # Every OD pair, charged and not. The not-charged pairs are the control:
        # if the desire-path test picks out motorway users, they should show a
        # markedly lower share of route distance on the priced motorway.
        sample = od.copy()
        ch = sample.loc[sample["charged"], "car_commuters"].sum()
        print(f"Routing ALL {len(sample):,} OD pairs "
              f"({int(sample['car_commuters'].sum()):,} commuters); "
              f"{int(ch):,} charged, {int(sample['car_commuters'].sum()-ch):,} not charged")
    return sample, wgs, corridor


def main(n):
    sample, wgs, corridor = build_sample(n)

    origins = gpd.GeoDataFrame(
        {"id": [f"p{i}" for i in range(len(sample))]},
        geometry=gpd.points_from_xy([wgs[k][0] for k in sample["res"]],
                                    [wgs[k][1] for k in sample["res"]]), crs=4326)
    destinations = gpd.GeoDataFrame(
        {"id": origins["id"].values},
        geometry=gpd.points_from_xy([wgs[k][0] for k in sample["wrk"]],
                                    [wgs[k][1] for k in sample["wrk"]]), crs=4326)

    print("Building driving network...")
    net = r5py.TransportNetwork(osm_pbf=str(OSM))
    print("Routing (CAR, one-to-one)...")
    it = r5py.DetailedItineraries(
        net, origins=origins, destinations=destinations,
        transport_modes=[r5py.TransportMode.CAR],
        departure=datetime.datetime(2026, 5, 5, 8, 0),
        snap_to_network=True,
    )
    it = gpd.GeoDataFrame(it).set_crs(4326, allow_override=True).to_crs(2193)
    print(f"Itinerary rows: {len(it):,}   columns: {list(it.columns)}")

    # Motorway reference geometry, and the priced subset of it.
    mw = gpd.read_file(OSM, layer="lines", columns=["highway"],
                       where="highway IN ('motorway','motorway_link')").to_crs(2193).geometry.union_all()
    mw_buf = mw.buffer(MW_TOL)
    priced_buf = mw.intersection(corridor).buffer(MW_TOL)

    rows = []
    for pid, grp in it.groupby("from_id" if "from_id" in it.columns else "id"):
        geom = grp.geometry.union_all()
        total = geom.length
        if total <= 0:
            continue
        rows.append({
            "id": pid,
            "route_km": total / 1000,
            "motorway_km": geom.intersection(mw_buf).length / 1000,
            "priced_km": geom.intersection(priced_buf).length / 1000,
        })
    r = pd.DataFrame(rows)
    r["motorway_share"] = r["motorway_km"] / r["route_km"]
    r["priced_share"] = r["priced_km"] / r["route_km"]

    sample = sample.reset_index(drop=True)
    sample["id"] = [f"p{i}" for i in range(len(sample))]
    m = sample.merge(r, on="id", how="inner")
    print(f"Routed successfully: {len(m):,} of {len(sample):,} pairs")
    m.to_csv(OUTPUT / "route_motorway_share.csv", index=False)

    w = m["car_commuters"].to_numpy()
    def wq(col, q):
        s = m.sort_values(col)
        c = s["car_commuters"].cumsum() / s["car_commuters"].sum()
        return s.loc[c >= q, col].iloc[0]

    print("\n── Do desire-path-charged commutes actually use the motorway? ──")
    print(f"(commuter-weighted, scenario {SCENARIO}, {int(w.sum()):,} commuters)")

    groups = [("ALL routed", m)]
    if m["charged"].nunique() > 1:
        groups = [("CHARGED by desire path", m[m["charged"]]),
                  ("NOT charged (control)", m[~m["charged"]])]
    for gname, g in groups:
        gw = g["car_commuters"].to_numpy()
        print(f"\n  [{gname}]  {int(gw.sum()):,} commuters")
        for col, lab in [("priced_share", "the PRICED motorway"), ("motorway_share", "any motorway")]:
            sh = (g[col] * gw).sum() / gw.sum()
            over1 = 100 * gw[g[col] > 0.01].sum() / gw.sum()
            over10 = 100 * gw[g[col] > 0.10].sum() / gw.sum()
            over25 = 100 * gw[g[col] > 0.25].sum() / gw.sum()
            print(f"    {lab:22s} mean {100*sh:5.1f}%   >1%: {over1:5.1f}%   "
                  f">10%: {over10:5.1f}%   >25%: {over25:5.1f}%")
    print(f"\n  median route length: {wq('route_km',0.5):.1f} km"
          f"   (straight-line median {wq('straight_km',0.5):.1f} km)")
    print(f"\nWritten: {OUTPUT/'route_motorway_share.csv'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=1200, help="number of OD pairs to route")
    main(**vars(ap.parse_args()))
