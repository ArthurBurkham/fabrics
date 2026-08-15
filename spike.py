"""
Fabrics — block 3 solver spike.

Purpose: prove the stack (numpy + PuLP + HiGHS/CBC) can run the v0.1 contract
math end to end on synthetic data. This is throwaway scaffolding, not product
code — but every function maps to a section of the contract (README.md) so it
can be transplanted into src/fabrics later.

Run:  uv run spike.py
"""

import math
import numpy as np
import pulp

# ----------------------------------------------------------------------------
# SECTION 0 — params (mirrors params.yaml in the contract)
# ----------------------------------------------------------------------------
P = {
    "line_haul_cost_per_mile": 1.80,
    "last_mile_cost_per_mile": 2.60,
    "last_mile_truck_capacity": 200,     # units per delivery vehicle
    "line_haul_truck_capacity": 2000,    # units per line-haul truck
    "round_trip": True,
    "circuity_factor": 1.3,
    "discount_rate": 0.10,
    "horizon_years": 5,
    "max_new_sites": 1,
    # demo tie-out: pretend finance handed us actual outbound spend ~3% above model
    "actual_annual_transport_cost": "demo",
}

RT = 2.0 if P["round_trip"] else 1.0
ANNUITY = sum(1 / (1 + P["discount_rate"]) ** t
              for t in range(1, P["horizon_years"] + 1))

# ----------------------------------------------------------------------------
# SECTION 1 — synthetic Arizona network (seeded; ~200 demand points)
# ----------------------------------------------------------------------------
rng = np.random.default_rng(42)

EXISTING = [  # facility_id, name, lat, lon
    ("DC_DV", "Deer Valley DC", 33.683, -112.083),
    ("DC_TL", "Tolleson DC",    33.450, -112.259),
    ("DC_MS", "Mesa DC",        33.394, -111.841),
]

def _cluster(n, lat, lon, spread, units_lo, units_hi, tag):
    pts = []
    for i in range(n):
        u = int(rng.uniform(units_lo, units_hi))
        freq = 52 if u > 8000 else int(rng.choice([26, 52]))
        pts.append({
            "point_id": f"{tag}{i:03d}",
            "lat": lat + rng.normal(0, spread),
            "lon": lon + rng.normal(0, spread),
            "annual_units": u,
            "deliveries_per_year": freq,
        })
    return pts

DEMAND = (
    _cluster(50, 33.68, -112.08, 0.10, 2000, 20000, "PHX_N") +   # metro north
    _cluster(45, 33.45, -112.26, 0.10, 2000, 20000, "PHX_W") +   # metro west
    _cluster(45, 33.39, -111.84, 0.10, 2000, 20000, "PHX_E") +   # metro east
    _cluster(20, 35.19, -111.63, 0.06, 1000, 8000, "FLG") +      # Flagstaff
    _cluster(12, 34.55, -112.45, 0.05, 1000, 8000, "PRC") +      # Prescott
    _cluster(8,  34.75, -111.90, 0.07, 1000, 8000, "SED") +      # Sedona/Cottonwood
    _cluster(6,  34.24, -111.32, 0.04, 1000, 6000, "PAY") +      # Payson
    _cluster(8,  32.88, -111.73, 0.05, 1500, 9000, "CAG") +      # Casa Grande
    _cluster(4,  33.97, -112.73, 0.04, 1000, 5000, "WKB")        # Wickenburg
)

CANDIDATES = [  # site_id, name, lat, lon, capex, annual_fixed_cost, annual_unit_capacity
    ("S01", "Flagstaff",   35.198, -111.651, 850_000, 240_000, 250_000),
    ("S02", "Prescott",    34.556, -112.443, 600_000, 200_000, 150_000),
    ("S03", "Camp Verde",  34.564, -111.855, 550_000, 190_000, 150_000),
    ("S04", "Payson",      34.240, -111.323, 450_000, 160_000, 100_000),
    ("S05", "Casa Grande", 32.879, -111.757, 500_000, 180_000, 150_000),
    ("S06", "Kingman",     35.189, -114.053, 500_000, 180_000, 150_000),
    ("S07", "Tucson",      32.253, -110.912, 700_000, 220_000, 200_000),
    ("S08", "Surprise",    33.630, -112.368, 480_000, 175_000, 150_000),
    ("S09", "Queen Creek", 33.248, -111.634, 480_000, 175_000, 150_000),
    ("S10", "Anthem",      33.867, -112.147, 470_000, 170_000, 150_000),
]

# ----------------------------------------------------------------------------
# SECTION 2 — helpers (contract: model logic, distance + derived trips)
# ----------------------------------------------------------------------------
def road_miles(lat1, lon1, lat2, lon2):
    """Haversine straight-line miles x circuity factor."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * P["circuity_factor"]

def trips_per_year(point):
    """trips = max(service frequency, ceil(units / last-mile truck capacity))"""
    by_capacity = math.ceil(point["annual_units"] / P["last_mile_truck_capacity"])
    return max(point["deliveries_per_year"], by_capacity)

# ----------------------------------------------------------------------------
# SECTION 3 — Stage 0: baseline valuation (always runs)
# ----------------------------------------------------------------------------
for pt in DEMAND:
    pt["trips"] = trips_per_year(pt)
    dists = [(f[0], f[1], road_miles(pt["lat"], pt["lon"], f[2], f[3])) for f in EXISTING]
    fid, fname, d = min(dists, key=lambda t: t[2])
    pt["base_facility"], pt["base_miles"] = fid, d
    pt["base_cost"] = pt["trips"] * d * RT * P["last_mile_cost_per_mile"]

base_cost = sum(pt["base_cost"] for pt in DEMAND)
tot_units = sum(pt["annual_units"] for pt in DEMAND)
tot_trips = sum(pt["trips"] for pt in DEMAND)
trip_miles = sum(pt["trips"] * pt["base_miles"] * RT for pt in DEMAND)
avg_miles = sum(pt["trips"] * pt["base_miles"] for pt in DEMAND) / tot_trips

# tie-out (demo): pretend actuals came in 3% above model
actual = base_cost * 1.03 if P["actual_annual_transport_cost"] == "demo" else P["actual_annual_transport_cost"]
variance = (base_cost - actual) / actual
implied_rate = actual / trip_miles

# ----------------------------------------------------------------------------
# SECTION 4 — Stages 1+2: evaluate each candidate standalone (forced open)
# One small MIP per candidate: which points does it capture, given capacity
# and the integer number of line-haul trucks its volume requires?
# ----------------------------------------------------------------------------
def get_solver():
    try:
        return pulp.HiGHS(msg=False)
    except Exception:
        return pulp.PULP_CBC_CMD(msg=0)

def evaluate(site):
    sid, name, lat, lon, capex, fixed, cap = site
    origin = min(EXISTING, key=lambda f: road_miles(lat, lon, f[2], f[3]))
    lh_run_cost = road_miles(lat, lon, origin[2], origin[3]) * RT * P["line_haul_cost_per_mile"]

    prob = pulp.LpProblem(f"eval_{sid}", pulp.LpMinimize)
    x = {pt["point_id"]: pulp.LpVariable(f"x_{pt['point_id']}", cat="Binary") for pt in DEMAND}
    T = pulp.LpVariable("lh_trucks", lowBound=0, cat="Integer")

    lm = {pt["point_id"]: pt["trips"] * road_miles(pt["lat"], pt["lon"], lat, lon) * RT
          * P["last_mile_cost_per_mile"] for pt in DEMAND}

    # objective: change in annual cost vs baseline (negative = savings)
    prob += (pulp.lpSum(x[p["point_id"]] * (lm[p["point_id"]] - p["base_cost"]) for p in DEMAND)
             + T * lh_run_cost + fixed)
    prob += pulp.lpSum(x[p["point_id"]] * p["annual_units"] for p in DEMAND) <= cap
    prob += T * P["line_haul_truck_capacity"] >= pulp.lpSum(
        x[p["point_id"]] * p["annual_units"] for p in DEMAND)
    prob.solve(get_solver())

    captured = [p for p in DEMAND if x[p["point_id"]].value() and x[p["point_id"]].value() > 0.5]
    savings = -pulp.value(prob.objective)
    npv = savings * ANNUITY - capex
    payback = capex / savings if savings > 0 else float("inf")
    cap_trips = sum(p["trips"] for p in captured)
    return {
        "site_id": sid, "name": name, "npv": npv, "payback": payback,
        "savings": savings, "capex": capex,
        "lh_runs": int(T.value() or 0),
        "units_captured": sum(p["annual_units"] for p in captured),
        "pct_units": sum(p["annual_units"] for p in captured) / tot_units,
        "mi_before": (sum(p["trips"] * p["base_miles"] for p in captured) / cap_trips) if captured else 0.0,
        "mi_after": (sum(p["trips"] * road_miles(p["lat"], p["lon"], lat, lon) for p in captured) / cap_trips) if captured else 0.0,
    }

results = sorted((evaluate(s) for s in CANDIDATES), key=lambda r: -r["npv"])
best = results[0]
# NOTE for v0.1 proper: multi-site runs (max_new_sites > 1) need one joint MIP
# with annualized capex in the objective. Single-site = exhaustive table above.

# ----------------------------------------------------------------------------
# SECTION 5 — console verdict (contract: output 5)
# ----------------------------------------------------------------------------
print("=" * 78)
print("FABRICS spike — synthetic AZ network")
print("=" * 78)
print(f"Your {len(EXISTING)}-facility network moves {tot_units/1e6:.1f}M units across "
      f"{tot_trips:,} deliveries at ${base_cost/1e6:.2f}M/yr "
      f"(${base_cost/tot_trips:,.0f} per delivery, avg {avg_miles:.0f} mi).")
print(f"Model vs. actual outbound spend: {variance:+.1%} "
      f"(implied last-mile rate ${implied_rate:.2f}/mi vs. ${P['last_mile_cost_per_mile']:.2f} assumed).")
if best["npv"] > 0:
    print(f"Best move: open {best['site_id']} ({best['name']}) — "
          f"${best['npv']/1e3:,.0f}K NPV over {P['horizon_years']} years, "
          f"payback {best['payback']:.1f} yrs.")
    print(f"Captures {best['pct_units']:.0%} of volume; avg last-mile distance for captured demand "
          f"falls {best['mi_before']:.0f} -> {best['mi_after']:.0f} mi, "
          f"fed by ~{best['lh_runs']/52:.1f} line-haul runs/week.")
print()
print(f"{'rank':<5}{'site':<6}{'name':<13}{'NPV':>12}{'payback':>9}{'capt%':>7}"
      f"{'mi b->a':>12}{'LH runs/yr':>12}")
print("-" * 78)
for i, r in enumerate(results, 1):
    pb = f"{r['payback']:.1f}y" if r["payback"] != float("inf") else "n/a"
    print(f"{i:<5}{r['site_id']:<6}{r['name']:<13}{r['npv']:>12,.0f}{pb:>9}"
          f"{r['pct_units']:>7.0%}{r['mi_before']:>5.0f} -> {r['mi_after']:<4.0f}{r['lh_runs']:>10}")
print("-" * 78)
print(f"solver: {get_solver().name} | points: {len(DEMAND)} | candidates: {len(CANDIDATES)} "
      f"| horizon {P['horizon_years']}y @ {P['discount_rate']:.0%}")
