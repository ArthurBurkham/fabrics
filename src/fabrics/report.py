"""Outputs — contract sections: baseline.csv, results.csv, assignments.csv, console verdict."""

import csv
import os


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_baseline_csv(out_dir, demand, existing, summary):
    by_fac = {f["facility_id"]: {"name": f.get("name", f["facility_id"]),
                                 "units": 0, "trips": 0, "cost": 0.0, "tm": 0.0}
              for f in existing}
    for p in demand:
        b = by_fac[p["base_facility"]]
        b["units"] += p["annual_units"]
        b["trips"] += p["trips"]
        b["cost"] += p["base_cost"]
        b["tm"] += p["trips"] * p["base_miles"]
    rows = [[fid, b["name"], b["units"], b["trips"],
             round(b["units"] / summary["units"], 4),
             round(b["cost"], 2), round(b["tm"] / b["trips"], 1) if b["trips"] else 0]
            for fid, b in by_fac.items()]
    rows.append(["TOTAL", "", summary["units"], summary["trips"], 1.0,
                 round(summary["annual_cost"], 2), round(summary["avg_miles"], 1)])
    _write(os.path.join(out_dir, "baseline.csv"),
           ["facility_id", "name", "units_served", "trips_served", "pct_of_network",
            "annual_transport_cost", "avg_miles"], rows)


def write_results_csv(out_dir, results):
    rows = [[r["site_id"], r["name"], r["opened"], round(r["capex"], 2),
             round(r["pv_fixed_costs"], 2), round(r["annual_line_haul_cost"], 2),
             round(r["pv_transport_savings"], 2), round(r["npv"], 2),
             round(r["payback_years"], 2) if r["payback_years"] else "",
             r["units_captured"], round(r["pct_demand_captured"], 4),
             round(r["avg_miles_before"], 1), round(r["avg_miles_after"], 1)]
            for r in results]
    _write(os.path.join(out_dir, "results.csv"),
           ["site_id", "name", "opened", "capex", "pv_fixed_costs",
            "annual_line_haul_cost", "pv_transport_savings", "npv", "payback_years",
            "units_captured", "pct_demand_captured", "avg_miles_before",
            "avg_miles_after"], rows)


def write_assignments_csv(out_dir, demand, results, params):
    from .model import road_miles
    rt = 2.0 if params["round_trip"] else 1.0
    winner = next((r for r in (results or []) if r["opened"]), None)
    rows = []
    for p in demand:
        fac_after, miles_after, cost_after = p["base_facility"], p["base_miles"], p["base_cost"]
        if winner and p["point_id"] in winner["captured_points"]:
            fac_after = winner["site_id"]
            cost_after = winner["captured_points"][p["point_id"]]
            miles_after = cost_after / (p["trips"] * rt * params["last_mile_cost_per_mile"])
        rows.append([p["point_id"], p["base_facility"], fac_after,
                     round(p["base_miles"], 1), round(miles_after, 1),
                     round(p["base_cost"], 2), round(cost_after, 2)])
    _write(os.path.join(out_dir, "assignments.csv"),
           ["point_id", "baseline_facility", "scenario_facility", "miles_before",
            "miles_after", "annual_cost_before", "annual_cost_after"], rows)


def console_verdict(summary, results, params):
    lines = []
    lines.append(
        f"Your {summary['facilities']}-facility network moves "
        f"{summary['units'] / 1e6:.1f}M units across {summary['trips']:,} deliveries "
        f"at ${summary['annual_cost'] / 1e6:.2f}M/yr "
        f"(${summary['cost_per_trip']:,.0f} per delivery, avg {summary['avg_miles']:.0f} mi).")
    if summary["tie_out_variance"] is not None:
        lines.append(
            f"Model vs. actual outbound spend: {summary['tie_out_variance']:+.1%} "
            f"(implied last-mile rate ${summary['implied_last_mile_rate']:.2f}/mi "
            f"vs. ${params['last_mile_cost_per_mile']:.2f} assumed).")
    else:
        lines.append("No actual_annual_transport_cost provided — add it to params.yaml "
                     "to tie the baseline out against your real freight spend.")
    if results:
        best = results[0]
        if best["opened"]:
            wk = best["line_haul_runs"] / 52
            lines.append(
                f"Best move: open {best['site_id']} ({best['name']}) — "
                f"${best['npv'] / 1e3:,.0f}K NPV over {params['horizon_years']} years, "
                f"payback {best['payback_years']:.1f} yrs.")
            lines.append(
                f"Captures {best['pct_demand_captured']:.0%} of volume; avg last-mile "
                f"distance for captured demand falls {best['avg_miles_before']:.0f} -> "
                f"{best['avg_miles_after']:.0f} mi, fed by ~{wk:.1f} line-haul runs/week.")
        else:
            lines.append("No candidate clears a positive NPV — the status quo wins. "
                         "Full ranking in results.csv.")
        lines.append("")
        lines.append(f"{'rank':<5}{'site':<6}{'name':<14}{'NPV':>12}{'payback':>9}"
                     f"{'capt%':>7}{'mi b->a':>12}")
        lines.append("-" * 65)
        for i, r in enumerate(results, 1):
            pb = f"{r['payback_years']:.1f}y" if r["payback_years"] else "n/a"
            lines.append(f"{i:<5}{r['site_id']:<6}{r['name']:<14}{r['npv']:>12,.0f}"
                         f"{pb:>9}{r['pct_demand_captured']:>7.0%}"
                         f"{r['avg_miles_before']:>5.0f} -> {r['avg_miles_after']:<4.0f}")
    return "\n".join(lines)
