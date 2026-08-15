"""Fabrics — value your network, then value changing it.

Usage:
    python -m fabrics <network_folder> [--out <folder>]

or from Python:
    import fabrics
    fabrics.run("examples/demo")
"""

import os

from .io import load_network, FabricsInputError
from .model import run_baseline, run_evaluation
from . import report

__version__ = "0.1.0.dev0"
__all__ = ["run", "load_network", "FabricsInputError"]


def run(folder, out_dir=None):
    """Run Fabrics on a network folder. Returns (baseline_summary, results|None)."""
    demand, existing, candidates, params = load_network(folder)
    out_dir = out_dir or os.path.join(folder, "out")
    os.makedirs(out_dir, exist_ok=True)

    summary = run_baseline(demand, existing, params)
    summary["facilities"] = len(existing)
    results = run_evaluation(demand, existing, candidates, params) if candidates else None

    report.write_baseline_csv(out_dir, demand, existing, summary)
    report.write_assignments_csv(out_dir, demand, results, params)
    if results:
        report.write_results_csv(out_dir, results)
    print(report.console_verdict(summary, results, params))
    print(f"\nwrote: {out_dir}")
    return summary, results
