"""Regenerates examples/demo/ — the synthetic AZ network from the solver spike,
exported in the contract's CSV format. Run from repo root:
    uv run python examples/make_demo_data.py
"""

import csv
import os
import numpy as np

HERE = os.path.join(os.path.dirname(__file__), "demo")
os.makedirs(HERE, exist_ok=True)
rng = np.random.default_rng(42)

EXISTING = [
    ("DC_DV", "Deer Valley DC", 33.683, -112.083),
    ("DC_TL", "Tolleson DC",    33.450, -112.259),
    ("DC_MS", "Mesa DC",        33.394, -111.841),
]

def cluster(n, lat, lon, spread, units_lo, units_hi, tag):
    pts = []
    for i in range(n):
        u = int(rng.uniform(units_lo, units_hi))
        freq = 52 if u > 8000 else int(rng.choice([26, 52]))
        pts.append((f"{tag}{i:03d}", f"{tag} point {i}",
                    round(lat + rng.normal(0, spread), 5),
                    round(lon + rng.normal(0, spread), 5), u, freq))
    return pts

DEMAND = (
    cluster(50, 33.68, -112.08, 0.10, 2000, 20000, "PHX_N") +
    cluster(45, 33.45, -112.26, 0.10, 2000, 20000, "PHX_W") +
    cluster(45, 33.39, -111.84, 0.10, 2000, 20000, "PHX_E") +
    cluster(20, 35.19, -111.63, 0.06, 1000, 8000, "FLG") +
    cluster(12, 34.55, -112.45, 0.05, 1000, 8000, "PRC") +
    cluster(8,  34.75, -111.90, 0.07, 1000, 8000, "SED") +
    cluster(6,  34.24, -111.32, 0.04, 1000, 6000, "PAY") +
    cluster(8,  32.88, -111.73, 0.05, 1500, 9000, "CAG") +
    cluster(4,  33.97, -112.73, 0.04, 1000, 5000, "WKB")
)

CANDIDATES = [
    ("S01", "Flagstaff",   35.198, -111.651, 850000, 240000, 250000),
    ("S02", "Prescott",    34.556, -112.443, 600000, 200000, 150000),
    ("S03", "Camp Verde",  34.564, -111.855, 550000, 190000, 150000),
    ("S04", "Payson",      34.240, -111.323, 450000, 160000, 100000),
    ("S05", "Casa Grande", 32.879, -111.757, 500000, 180000, 150000),
    ("S06", "Kingman",     35.189, -114.053, 500000, 180000, 150000),
    ("S07", "Tucson",      32.253, -110.912, 700000, 220000, 200000),
    ("S08", "Surprise",    33.630, -112.368, 480000, 175000, 150000),
    ("S09", "Queen Creek", 33.248, -111.634, 480000, 175000, 150000),
    ("S10", "Anthem",      33.867, -112.147, 470000, 170000, 150000),
]

with open(os.path.join(HERE, "demand.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["point_id", "name", "lat", "lon", "annual_units", "deliveries_per_year"])
    w.writerows(DEMAND)

with open(os.path.join(HERE, "existing_facilities.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["facility_id", "name", "lat", "lon"])
    w.writerows(EXISTING)

with open(os.path.join(HERE, "candidate_sites.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["site_id", "name", "lat", "lon", "capex",
                "annual_fixed_cost", "annual_unit_capacity"])
    w.writerows(CANDIDATES)

with open(os.path.join(HERE, "params.yaml"), "w") as f:
    f.write(
        "line_haul_cost_per_mile: 1.80\n"
        "last_mile_cost_per_mile: 2.60\n"
        "last_mile_truck_capacity: 200\n"
        "line_haul_truck_capacity: 2000\n"
        "round_trip: true\n"
        "circuity_factor: 1.3\n"
        "discount_rate: 0.10\n"
        "horizon_years: 5\n"
        "max_new_sites: 1\n"
        "# demo actuals ~3% above model, to show the tie-out working:\n"
        "actual_annual_transport_cost: 1630000\n")

print(f"wrote {len(DEMAND)} demand points, {len(EXISTING)} facilities, "
      f"{len(CANDIDATES)} candidates -> {HERE}")
