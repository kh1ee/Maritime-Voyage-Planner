"""Run the 10 Cargill benchmark routes through the engine (validation for T06-T08).

The expected values are *only read*, never used to adjust the engine. They are
a model-derived baseline (searoute-py 1.6.0), so a pass shows consistency with
that baseline - not independent accuracy (see the brief, "Using the Benchmark
Routes").
"""
from __future__ import annotations

from typing import Any, Dict, List

from .data import Benchmark
from .engine import VoyagePlanner
from .errors import VoyagePlannerError


def _spec(kind: str, ident: str, side: str) -> Dict[str, Any]:
    key = "position_id" if kind == "synthetic" else "port_id"
    return {f"{side}_{key}": ident}


def benchmark_request(bm: Benchmark) -> Dict[str, Any]:
    """Translate a Benchmark Routes row into an API request (route or voyage)."""
    req: Dict[str, Any] = {}
    req.update(_spec(bm.origin_type, bm.origin_id, "origin"))
    req.update(_spec(bm.destination_type, bm.destination_id, "destination"))
    if bm.required_passage:
        req["required_passage"] = bm.required_passage
    if bm.excluded_passage:
        req["excluded_passage"] = bm.excluded_passage
    if bm.intermediate_stops:
        req["intermediate_stops"] = list(bm.intermediate_stops)
    return req


def run_benchmarks(planner: VoyagePlanner) -> List[Dict[str, Any]]:
    rows = []
    for bm in planner.data.benchmarks:
        req = benchmark_request(bm)
        endpoint = "voyage" if bm.intermediate_stops else "route"
        row: Dict[str, Any] = {
            "benchmark_id": bm.benchmark_id, "route_name": bm.route_name, "endpoint": endpoint,
            "category": bm.route_category, "request": req,
            "required_passage": bm.required_passage, "excluded_passage": bm.excluded_passage,
            "expected_nm": bm.expected_distance_nm, "tolerance_nm": bm.acceptable_tolerance_nm,
        }
        try:
            res = planner.voyage(req) if endpoint == "voyage" else planner.route(req)
            actual = res["total_distance_nm"] if endpoint == "voyage" else res["distance_nm"]
            row.update(actual_nm=actual, difference_nm=round(actual - bm.expected_distance_nm, 1),
                       passed=abs(actual - bm.expected_distance_nm) <= bm.acceptable_tolerance_nm,
                       passages_used=res["passages_used"] if "passages_used" in res else [],
                       distance_by_leg_nm=res.get("distance_by_leg_nm"),
                       warnings=res["warnings"], response=res)
        except VoyagePlannerError as exc:
            row.update(actual_nm=None, difference_nm=None, passed=False, error=exc.to_dict())
        rows.append(row)
    return rows
