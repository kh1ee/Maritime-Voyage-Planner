"""Validate the engine against the 10 benchmark routes and save the evidence.

    python3 scripts/run_benchmarks.py

Writes results/benchmark_results.json (full responses, versions, coordinates
used) and results/benchmark_results.md (table for the validation write-up).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from voyage_planner import VoyagePlanner                       # noqa: E402
from voyage_planner.benchmarks import run_benchmarks            # noqa: E402


def main() -> int:
    planner = VoyagePlanner()
    rows = run_benchmarks(planner)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)

    engine = planner.backend.engine_info()
    with open(os.path.join(ROOT, "results", "benchmark_results.json"), "w") as fh:
        json.dump({"engine": engine, "workbook": planner.data.source_path,
                   "data_notes": planner.data.data_notes, "benchmarks": rows}, fh, indent=2, default=str)

    lines = [f"# Benchmark validation - routing engine {planner.health()['calculation_version']}", "",
             f"Routing library: {engine['name']} {engine['version']} "
             f"({engine.get('network_nodes')} nodes / {engine.get('network_edges')} edges), units: nautical miles, "
             f"default restrictions: {engine['default_restrictions']}, endpoint snapping not added to distance.", "",
             "| ID | Route | Constraints | Expected nm | Calculated nm | Diff | Tolerance | Result |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    ok = 0
    for r in rows:
        cons = []
        if r["required_passage"]:
            cons.append(f"via {r['required_passage']}")
        if r["excluded_passage"]:
            cons.append(f"excl. {r['excluded_passage']}")
        res = "PASS" if r["passed"] else "FAIL"
        ok += r["passed"]
        act = f"{r['actual_nm']:,.1f}" if r["actual_nm"] is not None else "error"
        diff = f"{r['difference_nm']:+.1f}" if r["difference_nm"] is not None else "-"
        lines.append(f"| {r['benchmark_id']} | {r['route_name']} | {', '.join(cons) or '-'} | "
                     f"{r['expected_nm']:,.0f} | {act} | {diff} | ±{r['tolerance_nm']:.0f} | {res} |")
    lines += ["", f"**{ok}/{len(rows)} benchmarks within tolerance.**", "",
              "Limitation: the expected values were generated with searoute-py 1.6.0 (same package as the engine), "
              "so agreement shows consistency with the baseline, not independent accuracy. BM_009 is a functional test."]
    text = "\n".join(lines)
    with open(os.path.join(ROOT, "results", "benchmark_results.md"), "w") as fh:
        fh.write(text + "\n")
    print(text)
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
