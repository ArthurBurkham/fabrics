"""Fabrics test suite — the contract's acceptance tests, codified.
Run: uv run pytest -q"""

import os
import pathlib
import shutil

import pytest

import fabrics
from fabrics import FabricsInputError
from fabrics.io import load_network
from fabrics.model import (DEFAULTS, road_miles, trips_per_year,
                           run_baseline, evaluate_candidate)

REPO = pathlib.Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "demo"


# --- unit: distance and derived trips ----------------------------------------

def test_road_miles_phx_to_flagstaff():
    # frozen reference: haversine x 1.3 circuity, PHX city hall -> Flagstaff
    d = road_miles(33.4484, -112.0740, 35.1983, -111.6513, 1.3)
    assert d == pytest.approx(160.3, abs=0.5)


def test_trips_frequency_bound():
    # 500 units needs ceil(500/200)=3 trips, but weekly-ish service demands 26
    pt = {"annual_units": 500, "deliveries_per_year": 26}
    assert trips_per_year(pt, DEFAULTS) == 26


def test_trips_capacity_bound():
    # 15,000 units needs 75 truckloads — more than the 52 the calendar asks for
    pt = {"annual_units": 15000, "deliveries_per_year": 52}
    assert trips_per_year(pt, DEFAULTS) == 75


# --- micro-network: the MIP does the obviously right thing -------------------

def _micro():
    existing = [{"facility_id": "F", "name": "Home DC", "lat": 33.0, "lon": -112.0}]
    demand = [
        # far northern point — expensive from F, right next to candidate S
        {"point_id": "FAR", "lat": 35.0, "lon": -112.0,
         "annual_units": 4000, "deliveries_per_year": 26},
        # decoy next door to F — capturing it would be nonsense
        {"point_id": "NEAR", "lat": 33.02, "lon": -112.0,
         "annual_units": 4000, "deliveries_per_year": 26},
    ]
    site = {"site_id": "S", "name": "North Hub", "lat": 35.0, "lon": -112.05,
            "capex": 10000, "annual_fixed_cost": 5000, "annual_unit_capacity": 50000}
    return demand, existing, site


def test_micro_network_captures_only_the_far_point():
    demand, existing, site = _micro()
    params = dict(DEFAULTS)
    run_baseline(demand, existing, params)
    r = evaluate_candidate(site, demand, existing, params)
    assert set(r["captured_points"]) == {"FAR"}
    assert r["npv"] > 0
    assert r["payback_years"] < 1.0
    # 4,000 captured units / 2,000-unit line-haul trucks = exactly 2 runs
    assert r["line_haul_runs"] == 2
    assert r["line_haul_origin_id"] == "F"


# --- validation: errors speak product, not traceback -------------------------

def test_missing_column_names_the_file_and_column(tmp_path):
    shutil.copy(DEMO / "existing_facilities.csv", tmp_path)
    text = (DEMO / "demand.csv").read_text().replace("annual_units", "units", 1)
    (tmp_path / "demand.csv").write_text(text)
    with pytest.raises(FabricsInputError) as e:
        load_network(str(tmp_path))
    assert "demand.csv" in str(e.value)
    assert "annual_units" in str(e.value)


def test_unknown_param_is_rejected(tmp_path):
    shutil.copy(DEMO / "demand.csv", tmp_path)
    shutil.copy(DEMO / "existing_facilities.csv", tmp_path)
    (tmp_path / "params.yaml").write_text("discountrate: 0.1\n")
    with pytest.raises(FabricsInputError) as e:
        load_network(str(tmp_path))
    assert "discountrate" in str(e.value)


def test_diagnose_mode_without_candidates(tmp_path):
    shutil.copy(DEMO / "demand.csv", tmp_path)
    shutil.copy(DEMO / "existing_facilities.csv", tmp_path)
    demand, existing, candidates, params = load_network(str(tmp_path))
    assert candidates is None
    assert len(demand) == 198


# --- acceptance: the demo network's hand-checked answer, frozen --------------

def test_acceptance_demo_network(tmp_path):
    summary, results = fabrics.run(str(DEMO), out_dir=str(tmp_path))
    assert summary["annual_cost"] == pytest.approx(1_584_592, rel=1e-3)
    best = results[0]
    assert best["site_id"] == "S03" and best["opened"]
    assert best["npv"] == pytest.approx(601_490, rel=1e-3)
    for f in ("baseline.csv", "results.csv", "assignments.csv", "map.html"):
        assert os.path.exists(os.path.join(tmp_path, f))
