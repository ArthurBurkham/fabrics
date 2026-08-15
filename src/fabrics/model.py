"""Model logic — maps 1:1 to the contract's "Model logic" section."""

import math
import pulp

DEFAULTS = {
    "line_haul_cost_per_mile": 1.80,
    "last_mile_cost_per_mile": 2.60,
    "last_mile_truck_capacity": 200,
    "line_haul_truck_capacity": 2000,
    "round_trip": True,
    "circuity_factor": 1.3,
    "discount_rate": 0.10,
    "horizon_years": 5,
    "max_new_sites": 1,
    "actual_annual_transport_cost": None,
}


def road_miles(lat1, lon1, lat2, lon2, circuity):
    """Haversine straight-line miles x circuity factor."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * circuity


def trips_per_year(point, params):
    """trips = max(service frequency, ceil(units / last-mile truck capacity))"""
    by_capacity = math.ceil(point["annual_units"] / params["last_mile_truck_capacity"])
    return max(point["deliveries_per_year"], by_capacity)


def annuity(params):
    r, h = params["discount_rate"], params["horizon_years"]
    return sum(1 / (1 + r) ** t for t in range(1, h + 1))


def run_baseline(demand, existing, params):
    """Stage 0: assign each point to its nearest existing facility; value the status quo."""
    rt = 2.0 if params["round_trip"] else 1.0
    for pt in demand:
        pt["trips"] = trips_per_year(pt, params)
        near = min(existing, key=lambda f: road_miles(
            pt["lat"], pt["lon"], f["lat"], f["lon"], params["circuity_factor"]))
        pt["base_facility"] = near["facility_id"]
        pt["base_miles"] = road_miles(pt["lat"], pt["lon"], near["lat"], near["lon"],
                                      params["circuity_factor"])
        pt["base_cost"] = pt["trips"] * pt["base_miles"] * rt * params["last_mile_cost_per_mile"]

    total_cost = sum(p["base_cost"] for p in demand)
    total_trips = sum(p["trips"] for p in demand)
    trip_miles = sum(p["trips"] * p["base_miles"] * rt for p in demand)
    summary = {
        "annual_cost": total_cost,
        "units": sum(p["annual_units"] for p in demand),
        "trips": total_trips,
        "avg_miles": sum(p["trips"] * p["base_miles"] for p in demand) / total_trips,
        "cost_per_trip": total_cost / total_trips,
        "pv_cost": total_cost * annuity(params),
        "tie_out_variance": None,
        "implied_last_mile_rate": None,
    }
    actual = params.get("actual_annual_transport_cost")
    if actual:
        summary["tie_out_variance"] = (total_cost - actual) / actual
        summary["implied_last_mile_rate"] = actual / trip_miles
    return summary


def _solver():
    try:
        return pulp.HiGHS(msg=False)
    except Exception:
        return pulp.PULP_CBC_CMD(msg=0)


def evaluate_candidate(site, demand, existing, params):
    """Stages 1+2 for one candidate, forced open: which points does it capture,
    what does its line haul cost, and what is it worth vs. the baseline?"""
    rt = 2.0 if params["round_trip"] else 1.0
    circ = params["circuity_factor"]

    if site.get("line_haul_origin"):
        origin = next(f for f in existing if f["facility_id"] == site["line_haul_origin"])
    else:
        origin = min(existing, key=lambda f: road_miles(
            site["lat"], site["lon"], f["lat"], f["lon"], circ))
    lh_run_cost = road_miles(site["lat"], site["lon"], origin["lat"], origin["lon"], circ) \
        * rt * params["line_haul_cost_per_mile"]

    lm = {p["point_id"]: p["trips"] * road_miles(p["lat"], p["lon"], site["lat"], site["lon"], circ)
          * rt * params["last_mile_cost_per_mile"] for p in demand}

    prob = pulp.LpProblem(f"eval_{site['site_id']}", pulp.LpMinimize)
    x = {p["point_id"]: pulp.LpVariable(f"x_{p['point_id']}", cat="Binary") for p in demand}
    trucks = pulp.LpVariable("lh_trucks", lowBound=0, cat="Integer")

    prob += (pulp.lpSum(x[p["point_id"]] * (lm[p["point_id"]] - p["base_cost"]) for p in demand)
             + trucks * lh_run_cost)
    prob += pulp.lpSum(x[p["point_id"]] * p["annual_units"] for p in demand) \
        <= site["annual_unit_capacity"]
    prob += trucks * params["line_haul_truck_capacity"] >= pulp.lpSum(
        x[p["point_id"]] * p["annual_units"] for p in demand)
    prob.solve(_solver())

    captured = [p for p in demand if (x[p["point_id"]].value() or 0) > 0.5]
    lm_savings = sum(p["base_cost"] - lm[p["point_id"]] for p in captured)
    lh_cost = (trucks.value() or 0) * lh_run_cost
    net_annual = lm_savings - lh_cost - site["annual_fixed_cost"]
    a = annuity(params)
    cap_trips = sum(p["trips"] for p in captured)

    return {
        "site_id": site["site_id"],
        "name": site.get("name", site["site_id"]),
        "capex": site["capex"],
        "pv_fixed_costs": site["annual_fixed_cost"] * a,
        "annual_line_haul_cost": lh_cost,
        "pv_transport_savings": (lm_savings - lh_cost) * a,
        "npv": (lm_savings - lh_cost) * a - site["annual_fixed_cost"] * a - site["capex"],
        "payback_years": site["capex"] / net_annual if net_annual > 0 else None,
        "line_haul_runs": int(trucks.value() or 0),
        "units_captured": sum(p["annual_units"] for p in captured),
        "captured_points": {p["point_id"]: lm[p["point_id"]] for p in captured},
        "avg_miles_before": (sum(p["trips"] * p["base_miles"] for p in captured) / cap_trips)
        if captured else 0.0,
        "avg_miles_after": (sum(p["trips"] * road_miles(p["lat"], p["lon"], site["lat"],
                                                        site["lon"], circ) for p in captured)
                            / cap_trips) if captured else 0.0,
    }


def run_evaluation(demand, existing, candidates, params):
    """Evaluate every candidate standalone; mark the best positive-NPV site as opened.
    (max_new_sites > 1 needs a joint MIP with annualized capex — v0.2.)"""
    results = sorted((evaluate_candidate(s, demand, existing, params) for s in candidates),
                     key=lambda r: -r["npv"])
    total_units = sum(p["annual_units"] for p in demand)
    for i, r in enumerate(results):
        r["pct_demand_captured"] = r["units_captured"] / total_units
        r["opened"] = (i == 0 and r["npv"] > 0)
    return results
