"""Input loading + validation. Every error message here is customer-facing:
say what's wrong, in which file, and what good looks like."""

import csv
import os
import yaml

from .model import DEFAULTS


class FabricsInputError(Exception):
    """Raised when input files are missing, malformed, or incomplete."""


REQUIRED = {
    "demand.csv": ["point_id", "lat", "lon", "annual_units", "deliveries_per_year"],
    "existing_facilities.csv": ["facility_id", "lat", "lon"],
    "candidate_sites.csv": ["site_id", "lat", "lon", "capex",
                            "annual_fixed_cost", "annual_unit_capacity"],
}
NUMERIC = {"lat": float, "lon": float, "annual_units": int, "deliveries_per_year": int,
           "capex": float, "annual_fixed_cost": float, "annual_unit_capacity": int}


def _read_csv(path, filename):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise FabricsInputError(f"{filename} has a header but no data rows.")
    missing = [c for c in REQUIRED[filename] if c not in rows[0]]
    if missing:
        raise FabricsInputError(
            f"{filename} is missing required column(s): {', '.join(missing)}.\n"
            f"  Expected at least: {', '.join(REQUIRED[filename])}\n"
            f"  Found: {', '.join(rows[0].keys())}")
    out = []
    for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        for col, cast in NUMERIC.items():
            if col in clean and clean[col] not in (None, ""):
                try:
                    clean[col] = cast(float(clean[col]))
                except ValueError:
                    raise FabricsInputError(
                        f"{filename}, row {i}: '{clean[col]}' in column '{col}' "
                        f"is not a number.")
        out.append(clean)
    return out


def _check_unique(rows, key, filename):
    seen = set()
    for r in rows:
        if r[key] in seen:
            raise FabricsInputError(
                f"{filename}: duplicate {key} '{r[key]}'. Each row needs a unique {key}.")
        seen.add(r[key])


def load_network(folder):
    """Load a network folder. Returns (demand, existing, candidates|None, params).
    candidate_sites.csv is optional — without it, Fabrics runs in Diagnose mode."""
    if not os.path.isdir(folder):
        raise FabricsInputError(f"'{folder}' is not a folder I can open.")

    for req in ("demand.csv", "existing_facilities.csv"):
        if not os.path.exists(os.path.join(folder, req)):
            raise FabricsInputError(
                f"{req} not found in {folder}. Diagnose mode needs demand.csv "
                f"and existing_facilities.csv; add candidate_sites.csv to evaluate openings.")

    demand = _read_csv(os.path.join(folder, "demand.csv"), "demand.csv")
    existing = _read_csv(os.path.join(folder, "existing_facilities.csv"),
                         "existing_facilities.csv")
    _check_unique(demand, "point_id", "demand.csv")
    _check_unique(existing, "facility_id", "existing_facilities.csv")

    candidates = None
    cand_path = os.path.join(folder, "candidate_sites.csv")
    if os.path.exists(cand_path):
        candidates = _read_csv(cand_path, "candidate_sites.csv")
        _check_unique(candidates, "site_id", "candidate_sites.csv")
        facility_ids = {f["facility_id"] for f in existing}
        for c in candidates:
            origin = c.get("line_haul_origin")
            if origin and origin not in facility_ids:
                raise FabricsInputError(
                    f"candidate_sites.csv: site '{c['site_id']}' names line_haul_origin "
                    f"'{origin}', which isn't a facility_id in existing_facilities.csv.")

    params = dict(DEFAULTS)
    params_path = os.path.join(folder, "params.yaml")
    if os.path.exists(params_path):
        with open(params_path, encoding="utf-8") as f:
            user_params = yaml.safe_load(f) or {}
        unknown = set(user_params) - set(DEFAULTS)
        if unknown:
            raise FabricsInputError(
                f"params.yaml has setting(s) I don't recognize: {', '.join(sorted(unknown))}.\n"
                f"  Valid settings: {', '.join(sorted(DEFAULTS))}")
        params.update(user_params)

    return demand, existing, candidates, params
