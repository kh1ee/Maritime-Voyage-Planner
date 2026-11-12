"""T14 - regression tests against the Benchmark Routes tab.

IMPORTANT: the workbook marks every expected_distance_nm as a "Model-derived baseline"
produced with searoute-py 1.6.0. Passing these proves our code reproduces the supplied
baselines (internal reproducibility). It does NOT prove the distances are accurate in the
real world. External accuracy validation against published sources such as NGA
Publication 151 is a separate task (T13/T26, Member 1).
"""
import openpyxl
import pytest

from voyage_planner.engine import calculate_route, calculate_voyage
from voyage_planner.reference_data import _workbook_path
from voyage_planner.schemas import Coordinates, RouteRequest, VoyageRequest


def load_benchmarks():
    wb = openpyxl.load_workbook(_workbook_path(), read_only=True, data_only=True)
    rows = list(wb["Benchmark Routes"].iter_rows(values_only=True))
    pos_rows = list(wb["Synthetic Positions"].iter_rows(values_only=True))
    wb.close()
    header = rows[0]
    positions = {r[0]: (float(r[2]), float(r[3])) for r in pos_rows[1:] if r[0]}
    return [dict(zip(header, r)) for r in rows[1:] if r[0]], positions


BENCHMARKS, POSITIONS = load_benchmarks()


def endpoint(kind, ident, role):
    if kind == "synthetic":
        lat, lon = POSITIONS[ident]
        return {f"{role}_coordinates": Coordinates(latitude=lat, longitude=lon)}
    return {f"{role}_port_id": ident}


def run(bm) -> float:
    origin = endpoint(bm["origin_type"], bm["origin_id"], "origin")
    stops = [s for s in (bm["intermediate_stops"] or "").split("|") if s]
    if stops:  # multi-leg: origin -> stops -> destination
        ids = [bm["origin_id"], *stops, bm["destination_id"]]
        legs = [RouteRequest(origin_port_id=a, destination_port_id=b) for a, b in zip(ids, ids[1:])]
        return calculate_voyage(VoyageRequest(legs=legs)).total_distance_nm
    dest = endpoint(bm["destination_type"], bm["destination_id"], "destination")
    return calculate_route(RouteRequest(**origin, **dest)).distance_nm


def needs_passage_logic(bm) -> bool:
    return bool((bm["required_passage"] or "").strip() or (bm["excluded_passage"] or "").strip())


@pytest.mark.parametrize("bm", BENCHMARKS, ids=[b["benchmark_id"] for b in BENCHMARKS])
def test_reproduces_supplied_baseline(bm):
    if needs_passage_logic(bm):
        pytest.skip("Needs required/excluded passage enforcement (T17-T19, Member 2).")
    got = run(bm)
    expected, tolerance = float(bm["expected_distance_nm"]), float(bm["acceptable_tolerance_nm"])
    assert abs(got - expected) <= tolerance, f"{bm['benchmark_id']}: got {got} NM, baseline {expected} NM"
