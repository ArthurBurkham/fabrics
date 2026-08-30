# Fabrics

**Value your network, then value changing it.**

Open-source facility location for logistics, built for finance-literate answers. Feed it CSVs of your demand, your existing facilities, and your candidate sites; get back an NPV-ranked verdict on which site to open, cost-to-serve diagnostics for the network you already run, and a map.

## Install

```
pip install fabrics-logistics
```

## Use

```
fabrics path/to/your/network/
```

A network folder needs `demand.csv` and `existing_facilities.csv` — that alone runs **Diagnose mode**, which values your current network's cost-to-serve and ties it out against your actual freight spend. Add `candidate_sites.csv` (and optionally `params.yaml`) to run **Evaluate mode**: a MIP decides which candidate to open and reports everything as a delta against your validated baseline.

Outputs, written to `<folder>/out/`:

- `baseline.csv` — per-facility cost rollup and network totals: the trust artifact
- `results.csv` — every candidate ranked by NPV, with payback, captured volume, and line-haul cost
- `assignments.csv` — per-point before/after: facility, miles, annual cost
- `map.html` — self-contained interactive map: cost-to-serve heat, the chosen site, the line-haul leg
- a console verdict in plain English

Try the built-in demo (a synthetic Arizona network — three Phoenix DCs, ~200 demand points, ten candidate micro-hub sites):

```
git clone https://github.com/ArthurBurkham/fabrics
cd fabrics
uv run fabrics examples/demo
```

Full input/output specification below. Fabrics is early (v0.1) and deliberately narrow — see "Non-goals" for what it doesn't do yet.

---

# The v0.1 Contract

**One-liner:** First, value what you have: **what does your current network actually cost to run?** Then overlay candidates: **which site should you open, and what is it worth against that baseline?**

## The questions v0.1 answers

**Mode 1 — Diagnose (candidates optional).** Value the current network's cost-to-serve: annual transport cost, PV over the horizon, per-facility and per-demand-point breakdown, and a tie-out against actual spend.

**Mode 2 — Evaluate.** Overlay candidate sites on the validated baseline. A MIP selects which to open; every result is reported as a delta vs. current state.

Brownfield only (greenfield is v0.2). Cost lens only: v0.1 values cost-to-serve, not the revenue a new store might capture.

---

## Inputs

### 1. `demand.csv` (required)

| column | type | notes |
|---|---|---|
| point_id | str | unique |
| name | str, optional | for map labels |
| lat | float | |
| lon | float | |
| annual_units | int | yearly volume delivered to this point |
| deliveries_per_year | int | required service frequency (52 = weekly) |

Deliveries (trips) are **derived, not input**:

```
trips = max(deliveries_per_year, ceil(annual_units / last_mile_truck_capacity))
```

A point is visited as often as service frequency demands, or as often as truck capacity forces — whichever binds.

### 2. `existing_facilities.csv` (required)

| column | type | notes |
|---|---|---|
| facility_id | str | unique |
| name | str, optional | |
| lat | float | |
| lon | float | |

Each demand point is assigned to its nearest existing facility to compute the current state. Existing facilities are treated as uncapacitated in v0.1.

### 3. `candidate_sites.csv` (optional — omit to run Diagnose mode only)

| column | type | notes |
|---|---|---|
| site_id | str | unique |
| name | str, optional | |
| lat | float | |
| lon | float | |
| capex | float | one-time cost to open |
| annual_fixed_cost | float | rent, labor, overhead per year |
| annual_unit_capacity | int | max units/year through this site |
| line_haul_origin | str, optional | facility_id that replenishes this site; default = nearest existing facility |

### 4. `params.yaml`

```yaml
line_haul_cost_per_mile: 1.80    # consolidated origin -> hub moves (placeholder)
last_mile_cost_per_mile: 2.60    # delivery runs to demand points (placeholder)
last_mile_truck_capacity: 200    # units per delivery vehicle
line_haul_truck_capacity: 2000   # units per line-haul truck
round_trip: true                 # cost applied to 2x one-way distance
circuity_factor: 1.3             # road miles ~= straight-line x this
discount_rate: 0.10
horizon_years: 5
max_new_sites: 1
actual_annual_transport_cost: null   # actual OUTBOUND delivery spend; enables tie-out
```

---

## Model logic (plain English)

**Stage 0 — Baseline valuation (always runs).** Derive trips per point (formula above). Assign every point to its nearest existing facility. Annual cost = Σ trips × distance × (2 if round_trip) × last_mile_cost_per_mile, with distance = haversine × circuity_factor. All baseline flow is last-mile. PV of that cost stream over the horizon = the value of the status-quo cost structure.

**Tie-out.** If `actual_annual_transport_cost` (outbound delivery spend) is provided, report variance (model vs. actual, %) and the **implied last-mile cost per mile** (actual ÷ modeled trip-miles). Working rule: don't trust any overlay delta until the baseline ties within ~10%.

**Stage 1 — Scenario.** A MIP selects up to `max_new_sites` candidates and reassigns demand subject to `annual_unit_capacity`. An opened site's cost has two legs:

- **Last mile:** trips from the site to its assigned points, same formula and rate as baseline.
- **Line haul (inbound):** `ceil(units through site / line_haul_truck_capacity)` runs × distance(origin → site) × (2 if round_trip) × line_haul_cost_per_mile. Origin = `line_haul_origin` if given, else nearest existing facility.

The economics live in the spread: a hub wins when few cheap consolidated inbound runs plus short delivery runs beat many long delivery runs.

**Stage 2 — Value.** Annual savings = baseline cost − scenario cost (net of new fixed and line-haul costs). NPV = PV(savings over horizon at discount_rate) − capex. Pre-tax cash flows, real dollars, no terminal value.

**Stated simplifications (v0.1):**
- Every delivery is a dedicated out-and-back run — no multi-stop routing (that's VRP, out of scope)
- Truck capacities are fleet-level constants, not per-point
- Existing facilities' own inbound replenishment is held constant across scenarios; captured demand's vanished inbound at relieved facilities is uncounted, so **reported NPVs are conservative**

---

## Outputs

### 1. `baseline.csv` — the trust artifact

One row per existing facility, plus a network totals row:

| column | notes |
|---|---|
| facility_id, name | |
| units_served | |
| trips_served | derived |
| pct_of_network | by units |
| annual_transport_cost | |
| avg_miles | |

Totals block: network annual cost, cost per delivery, cost per unit, PV of baseline cost over horizon, tie-out variance vs. actuals, implied last-mile cost per mile.

### 2. `results.csv` — the hero artifact (Evaluate mode)

One row per candidate site, **ranked by NPV**:

| column | notes |
|---|---|
| site_id, name | |
| opened | bool — in the optimal solution |
| capex | |
| pv_fixed_costs | |
| annual_line_haul_cost | the consolidation price tag, visible |
| pv_transport_savings | net of line haul |
| npv | |
| payback_years | |
| units_captured / pct_demand_captured | |
| avg_miles_before / avg_miles_after | last-mile, across captured demand |

When `max_new_sites: 1`, every candidate is evaluated standalone (exhaustive), so the ranking is complete. Multi-site runs report the chosen set plus a scenario summary.

### 3. `assignments.csv`

| point_id | baseline_facility | scenario_facility | miles_before | miles_after | annual_cost_before | annual_cost_after |

The cost-to-serve columns power the diagnostic heatmap: which demand points are bleeding money today.

### 4. `map.html`

Single self-contained HTML map (folium). Diagnose mode: demand points colored by cost-to-serve. Evaluate mode: colored by assignment change, chosen site highlighted, line-haul leg drawn. Opens in any browser — this is the screenshot that sells.

### 5. Console summary

Plain-English verdict, baseline first:

> Your 14-facility network moves 1.2M units across 51,400 deliveries at $2.06M/yr ($40 per delivery, avg 38 mi).
> Model ties to actual outbound spend within 3%.
> Opening SITE_07 (Flagstaff) is worth $412K NPV over 5 years. Payback: 2.3 years.
> Captures 34% of volume; avg last-mile distance for captured demand falls 41 → 17 mi, fed by ~1 line-haul run per week.

---

## Non-goals for v0.1 (so it ships)

- No drive-time APIs — circuity factor stands in
- No routing/VRP, multi-stop delivery, or scheduling
- No heterogeneous fleets — one truck type per leg, capacities in params
- No demand forecasting — demand is an input
- No revenue / demand-capture modeling — a new store's sales potential is a different model; v0.1 values cost-to-serve only
- No tax, depreciation, or terminal value — pre-tax cash flows only
- No greenfield mode (empty existing network)
- No multi-period or staged openings

## Acceptance tests

1. **Diagnose:** `examples/demo/` runs with only `demand.csv` + `existing_facilities.csv` and produces baseline.csv, map, and console verdict.
2. **Evaluate:** full dataset (~200 demand points, 10 candidates) runs end-to-end in under 10 seconds and the ranked table matches a hand-checked answer.

## License

MIT © 2026 Arthur Burkham
