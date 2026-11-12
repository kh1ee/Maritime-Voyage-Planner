"""Tests for Member 2's routing engine (T05-T08, T17, T18).

Run:  python3 -m pytest -q
These check *my* functions; Member 3 (T14/T19/T27-T29) writes the independent suite.
"""
import concurrent.futures
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voyage_planner import VoyagePlanner, VoyagePlannerError        # noqa: E402
from voyage_planner import errors                                    # noqa: E402
from voyage_planner.benchmarks import run_benchmarks                 # noqa: E402


@pytest.fixture(scope="module")
def planner():
    return VoyagePlanner()


def err(planner, fn, *a, **k):
    with pytest.raises(VoyagePlannerError) as exc:
        fn(*a, **k)
    return exc.value


# ---------------------------------------------------------------- data
def test_reference_data_counts(planner):
    d = planner.data
    assert (len(d.ports), len(d.passages), len(d.positions), len(d.benchmarks)) == (29, 6, 6, 10)


def test_gibraltar_locode_correction_and_aliases(planner):
    p = planner.data.find_port("GIGIB")                 # the UN/LOCODE record finds the port too (team decision)...
    assert p is not None and p.port_id == "GIIBZ" and p.un_locode == "GIIBZ"   # ...but the supplied ID is never replaced
    assert planner.data.find_port("giibz").port_id == "GIIBZ"      # original id still works
    assert planner.data.find_port("port of santos").port_id == "BRSSZ"  # alias, case-insensitive
    assert planner.data.find_port("Bombay").port_id == "INBOM"


def test_health(planner):
    assert planner.health() == {"status": "ok", "calculation_version": "0.1.0"}


# ---------------------------------------------------------------- benchmarks
@pytest.mark.parametrize("row", run_benchmarks(VoyagePlanner()), ids=lambda r: r["benchmark_id"])
def test_benchmark_within_tolerance(row):
    assert row["passed"], f"{row['benchmark_id']}: {row['actual_nm']} vs {row['expected_nm']}"


# ---------------------------------------------------------------- T06 port-to-port
def test_port_to_port_response_matches_spec(planner):
    r = planner.port_to_port("SGSIN", "NLRTM")
    for key in ("route_id", "status", "distance_nm", "origin", "destination", "routing_points",
                "passages_used", "route_geometry", "assumptions", "warnings", "calculation_version"):
        assert key in r
    assert r["status"] == "success" and r["calculation_version"] == "0.1.0"
    assert r["origin"]["port_id"] == "SGSIN" and r["destination"]["port_name"] == "Rotterdam"
    assert r["route_geometry"]["type"] == "LineString" and len(r["route_geometry"]["coordinates"]) > 2
    assert "Academic estimate; not for navigation." in r["warnings"]
    assert abs(r["distance_nm"] - 8368) < 250


def test_geometry_is_lon_lat_order(planner):
    r = planner.port_to_port("USHOU", "NLRTM")
    lon, lat = r["route_geometry"]["coordinates"][0]
    assert abs(lon - (-95.0)) < 2 and abs(lat - 29.7) < 2      # Houston, not (29.7, -95)


def test_port_lookup_by_name_alias_and_locode(planner):
    a = planner.port_to_port("Singapore", "Rotterdam")
    b = planner.port_to_port("SGSIN", "NLRTM")
    assert a["distance_nm"] == b["distance_nm"]


def test_distance_symmetric_enough(planner):
    ab = planner.port_to_port("SGSIN", "HKHKG")["distance_nm"]
    ba = planner.port_to_port("HKHKG", "SGSIN")["distance_nm"]
    assert abs(ab - ba) < 1.0


def test_same_port_gives_zero_and_valid_linestring(planner):
    r = planner.port_to_port("NLRTM", "NLRTM")
    assert r["distance_nm"] == 0 and len(r["route_geometry"]["coordinates"]) >= 2
    assert any("same" in w for w in r["warnings"])


def test_all_ports_reachable_from_singapore(planner):
    for p in planner.data.ports:
        r = planner.port_to_port("SGSIN", p)
        assert r["status"] == "success" and r["distance_nm"] >= 0


def test_determinism(planner):
    a = planner.port_to_port("USHOU", "CLTOQ", required_passage="PANAMA")
    b = VoyagePlanner().port_to_port("USHOU", "CLTOQ", required_passage="PANAMA")
    assert a == b                                     # includes route_id


def test_snap_warning_for_tocopilla(planner):
    r = planner.port_to_port("USHOU", "CLTOQ")
    assert any("Tocopilla" in w and "nm from the nearest" in w for w in r["warnings"])
    snap = [p for p in r["routing_points"] if p["id"] == "CLTOQ"][0]["snap_distance_nm"]
    assert snap > 100


# ---------------------------------------------------------------- T07 position-to-port
def test_position_to_port_from_coordinates(planner):
    r = planner.position_to_port(10.0, 114.0, "SGSIN")
    assert r["origin"]["port_id"] is None and r["origin"]["location_type"] == "coordinates"
    assert abs(r["distance_nm"] - 721) < 150


def test_position_ids_equal_coordinates(planner):
    a = planner.route({"origin_position_id": "POS_001", "destination_port_id": "SGSIN"})
    b = planner.position_to_port(10.0, 114.0, "SGSIN")
    assert a["distance_nm"] == b["distance_nm"]
    assert a["origin"]["position_id"] == "POS_001"


@pytest.mark.parametrize("pos,port", [("POS_001", "SGSIN"), ("POS_002", "NLRTM"), ("POS_003", "PAPTY"),
                                      ("POS_004", "ZADUR"), ("POS_005", "ZACPT"), ("POS_006", "CLTOQ")])
def test_all_six_synthetic_positions(planner, pos, port):
    r = planner.route({"origin_position_id": pos, "destination_port_id": port})
    assert r["status"] == "success" and r["distance_nm"] > 0


# ---------------------------------------------------------------- T08 multi-leg
def test_multi_leg_total_is_sum_of_legs(planner):
    r = planner.multi_leg(["SGSIN", "HKHKG", "LKCMB", "ZADUR"])
    assert [l["leg_number"] for l in r["legs"]] == [1, 2, 3]
    assert r["total_distance_nm"] == round(sum(l["distance_nm"] for l in r["legs"]), 1)
    assert abs(r["total_distance_nm"] - 8271) < 300


def test_voyage_spec_example_request(planner):
    r = planner.voyage({"legs": [
        {"origin_port_id": "SGSIN", "destination_port_id": "HKHKG"},
        {"origin_port_id": "HKHKG", "destination_port_id": "LKCMB"},
        {"origin_port_id": "LKCMB", "destination_port_id": "ZADUR"}], "calculation_version": "0.1.0"})
    assert r["status"] == "success" and r["voyage_id"].startswith("voyage-")


def test_voyage_with_per_leg_passages_synopsis_example(planner):
    """Synopsis: Houston->Tocopilla via Panama, then Tocopilla->Durban via Cape Horn."""
    r = planner.multi_leg(["USHOU", "CLTOQ", "ZADUR"], required_passages=["PANAMA", "CAPE_HORN"])
    assert r["legs"][0]["passages_used"] == ["PANAMA"]
    assert "CAPE_HORN" in r["legs"][1]["passages_used"]
    assert r["total_distance_nm"] > r["legs"][0]["distance_nm"]


def test_voyage_mixed_stop_types(planner):
    r = planner.multi_leg([{"latitude": 10, "longitude": 114}, "SGSIN", "HKHKG"])
    assert len(r["legs"]) == 2 and r["legs"][0]["origin_port_id"] is None


def test_voyage_default_excluded_passage_applies_to_all_legs(planner):
    r = planner.voyage({"legs": [{"origin_port_id": "USHOU", "destination_port_id": "CLTOQ"}],
                        "excluded_passage": "PANAMA"})
    assert "PANAMA" not in r["passages_used"] and r["total_distance_nm"] > 8000


def test_voyage_error_names_the_leg(planner):
    e = err(planner, planner.voyage, {"legs": [{"origin_port_id": "SGSIN", "destination_port_id": "HKHKG"},
                                              {"origin_port_id": "HKHKG", "destination_port_id": "NOPE"}]})
    assert e.error_code == errors.PORT_NOT_FOUND and e.message.startswith("Leg 2")


def test_route_with_waypoints_is_sum_of_parts(planner):
    direct = planner.port_to_port("SGSIN", "ZADUR")["distance_nm"]
    via = planner.route({"origin_port_id": "SGSIN", "destination_port_id": "ZADUR",
                         "waypoints": ["HKHKG", "LKCMB"]})
    assert abs(via["distance_nm"] - 8271) < 300 and via["distance_nm"] > direct
    assert len(via["distance_by_leg_nm"]) == 3


# ---------------------------------------------------------------- T18 required passages
def test_required_panama_is_used(planner):
    r = planner.port_to_port("USHOU", "CLTOQ", required_passage="PANAMA")
    assert "PANAMA" in r["passages_used"] and r["required_passage"] == "PANAMA"
    assert r["routing_points"][1]["role"] == "required_passage"


@pytest.mark.parametrize("o,d,passage", [
    ("NLRTM", "ZADUR", "SUEZ"), ("NLRTM", "ZADUR", "CAPE_GOOD_HOPE"), ("USHOU", "CLTOQ", "CAPE_HORN"),
    ("SGSIN", "NLRTM", "MALACCA"), ("SGSIN", "NLRTM", "GIBRALTAR")])
def test_required_passage_geometry_goes_through_point(planner, o, d, passage):
    from voyage_planner.geo import distance_to_path_nm
    excl = "PANAMA" if passage == "CAPE_HORN" else None
    r = planner.port_to_port(o, d, required_passage=passage, excluded_passage=excl)
    p = planner.data.passages[passage]
    dist, _ = distance_to_path_nm((p.longitude, p.latitude), r["route_geometry"]["coordinates"])
    snap = [x for x in r["routing_points"] if x["id"] == passage][0]["snap_distance_nm"]
    assert dist <= snap + 1.0                      # route passes through the node the point snapped to
    assert passage in r["passages_used"]


def test_multiple_required_passages_are_ordered_by_shortest(planner):
    a = planner.port_to_port("SGSIN", "NLRTM", required_passage=["SUEZ", "GIBRALTAR"])
    b = planner.port_to_port("SGSIN", "NLRTM", required_passage=["GIBRALTAR", "SUEZ"])
    assert a["distance_nm"] == b["distance_nm"]                # same optimum whatever the input order
    assert a["passages_used"].index("SUEZ") < a["passages_used"].index("GIBRALTAR")


# ---------------------------------------------------------------- T17 excluded passages
def test_excluding_panama_changes_route(planner):
    base = planner.port_to_port("USHOU", "CLTOQ")
    r = planner.port_to_port("USHOU", "CLTOQ", excluded_passage="PANAMA")
    assert "PANAMA" in base["passages_used"] and "PANAMA" not in r["passages_used"]
    assert "panama" not in r["network_passages_traversed"]
    assert r["distance_nm"] > base["distance_nm"] + 5000
    # Cargill note: direct run with Panama excluded is slightly SHORTER than BM_006 (9,973)
    assert r["distance_nm"] < 9973 + 1


def test_excluding_suez_forces_cape_route(planner):
    r = planner.port_to_port("SGSIN", "NLRTM", excluded_passage="SUEZ")
    assert "SUEZ" not in r["passages_used"] and r["distance_nm"] > 11000


def test_excluding_an_unused_passage_changes_nothing(planner):
    a = planner.port_to_port("SGSIN", "HKHKG")
    b = planner.port_to_port("SGSIN", "HKHKG", excluded_passage="PANAMA")
    assert a["distance_nm"] == b["distance_nm"]


@pytest.mark.parametrize("value", [None, "", " ", []])
def test_blank_passage_values_mean_no_constraint(planner, value):
    r = planner.route({"origin_port_id": "SGSIN", "destination_port_id": "HKHKG",
                       "required_passage": value, "excluded_passage": value})
    assert r["required_passage"] is None and r["excluded_passage"] is None


def test_passage_ids_are_case_insensitive(planner):
    assert planner.port_to_port("USHOU", "CLTOQ", required_passage="panama")["required_passage"] == "PANAMA"


# ---------------------------------------------------------------- errors (spec section 8)
def test_error_port_not_found(planner):
    e = err(planner, planner.port_to_port, "ZZZZZ", "SGSIN")
    assert e.error_code == errors.PORT_NOT_FOUND
    assert planner.handle_route({"origin_port_id": "ZZZZZ", "destination_port_id": "SGSIN"}) == {
        "status": "error", "error_code": "PORT_NOT_FOUND", "message": e.message, "warnings": []}


def test_error_missing_origin_and_destination(planner):
    assert err(planner, planner.route, {"destination_port_id": "SGSIN"}).error_code == errors.MISSING_ORIGIN
    assert err(planner, planner.route, {"origin_port_id": "SGSIN"}).error_code == errors.MISSING_DESTINATION


@pytest.mark.parametrize("coords", [{"latitude": 95, "longitude": 10}, {"latitude": 10, "longitude": 200},
                                    {"latitude": "x", "longitude": 10}, {"latitude": 10},
                                    {"latitude": float("nan"), "longitude": 1}, {"latitude": True, "longitude": 1},
                                    [10, 20], "10,20"])
def test_error_invalid_coordinates(planner, coords):
    e = err(planner, planner.route, {"origin_coordinates": coords, "destination_port_id": "SGSIN"})
    assert e.error_code == errors.INVALID_COORDINATES


def test_error_invalid_passage_unknown(planner):
    for field in ("required_passage", "excluded_passage"):
        e = err(planner, planner.route, {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM", field: "ATLANTIS"})
        assert e.error_code == errors.INVALID_PASSAGE


# ---------------------------------------------------------------- cape exclusion (gates)
def test_excluding_cape_good_hope_forces_suez_route(planner):
    base = planner.port_to_port("NLRTM", "ZADUR")
    r = planner.port_to_port("NLRTM", "ZADUR", excluded_passage="CAPE_GOOD_HOPE")
    assert "CAPE_GOOD_HOPE" in base["passages_used"]
    assert "CAPE_GOOD_HOPE" not in r["passages_used"] and "SUEZ" in r["passages_used"]
    assert abs(r["distance_nm"] - 7943) < 1          # identical to benchmark BM_007 (via Suez)


def test_excluding_cape_horn_keeps_magellan_open(planner):
    # Valparaiso -> Buenos Aires already uses the Strait of Magellan, so nothing changes
    a = planner.port_to_port("CLVAP", "ARBUE")
    b = planner.port_to_port("CLVAP", "ARBUE", excluded_passage="CAPE_HORN")
    assert a["distance_nm"] == b["distance_nm"] and "CAPE_HORN" not in b["passages_used"]


def test_excluding_cape_horn_and_panama_uses_magellan(planner):
    r = planner.port_to_port("USHOU", "CLTOQ", excluded_passage=["PANAMA", "CAPE_HORN"])
    assert "chili" in r["network_passages_traversed"] and r["distance_nm"] == 9773.2


def test_excluding_unused_cape_changes_nothing(planner):
    assert (planner.port_to_port("SGSIN", "HKHKG")["distance_nm"]
            == planner.port_to_port("SGSIN", "HKHKG", excluded_passage="CAPE_HORN")["distance_nm"])


def test_cape_and_canal_exclusion_combined(planner):
    r = planner.port_to_port("SGSIN", "NLRTM", excluded_passage=["SUEZ", "CAPE_GOOD_HOPE"])
    assert r["passages_used"] == ["PANAMA"] and r["distance_nm"] > 12000     # round the Pacific


def test_excluded_cape_is_never_reported_as_used(planner):
    # Cape Town is 27 nm from the Cape of Good Hope point: heuristic would flag it, exclusion must not
    r = planner.port_to_port("NLRTM", "ZACPT", excluded_passage="CAPE_GOOD_HOPE")
    assert "CAPE_GOOD_HOPE" not in r["passages_used"]


@pytest.mark.parametrize("cape", ["CAPE_HORN", "CAPE_GOOD_HOPE"])
def test_excluded_cape_geometry_never_crosses_gate(planner, cape):
    from voyage_planner.gates import gate_for
    gate = gate_for(planner.data.passages[cape])
    origins = ["SGSIN", "NLRTM", "USHOU", "AUSYD", "BRSSZ", "ZADUR", "CLTOQ", "AEFJR"]
    for o in origins:
        for d in origins:
            if o == d:
                continue
            try:
                r = planner.port_to_port(o, d, excluded_passage=cape)
            except VoyagePlannerError as e:
                assert e.error_code == errors.ROUTE_NOT_FOUND
                continue
            assert not gate.crossed_by(r["route_geometry"]["coordinates"]), (o, d)


def test_gate_crossing_function():
    from voyage_planner.gates import Gate, crossing_latitude
    # a great circle between two points on one parallel bows poleward: atan(tan40/cos10) = 40.43
    assert crossing_latitude((10, -40), (30, -40), 20) == pytest.approx(-40.43, abs=0.01)
    assert crossing_latitude((10, -40), (15, -40), 20) is None                            # does not reach
    g = Gate("X", 20.0, -34.0)
    assert g.blocks_segment((10, -40), (30, -40)) and not g.blocks_segment((10, -30), (30, -30))


def test_list_passages_reports_all_excludable(planner):
    assert all(p["can_be_excluded"] for p in planner.list_passages())


def test_concurrent_cape_and_canal_exclusions(planner):
    fresh = VoyagePlanner()
    expect = {None: 7018.4, "CAPE_GOOD_HOPE": 7943.3, "SUEZ": 7018.4}

    def run(i):
        ex = [None, "CAPE_GOOD_HOPE", "SUEZ"][i % 3]
        r = fresh.route({"origin_coordinates": {"latitude": 51.95 + i * 1e-4, "longitude": 4.14},
                         "destination_port_id": "ZADUR", "excluded_passage": ex})
        return ex, r["distance_nm"]

    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        results = list(pool.map(run, range(90)))
    assert all(abs(expect[ex] - d) < 6 for ex, d in results)


def test_error_route_not_found_instead_of_zero_distance(planner):
    """searoute silently returns 0 nm here - the engine must refuse."""
    e = err(planner, planner.port_to_port, "EGPSD", "NLRTM", excluded_passage=["GIBRALTAR", "SUEZ"])
    assert e.error_code == errors.ROUTE_NOT_FOUND


def test_error_invalid_request_variants(planner):
    assert err(planner, planner.route, "not a dict").error_code == errors.INVALID_REQUEST
    assert err(planner, planner.route, {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                        "calculation_version": "9.9.9"}).error_code == errors.INVALID_REQUEST
    both = {"origin_port_id": "SGSIN", "origin_coordinates": {"latitude": 1, "longitude": 1},
            "destination_port_id": "NLRTM"}
    assert err(planner, planner.route, both).error_code == errors.INVALID_REQUEST
    conflict = {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                "required_passage": "SUEZ", "excluded_passage": "SUEZ"}
    assert err(planner, planner.route, conflict).error_code == errors.INVALID_REQUEST
    assert err(planner, planner.voyage, {"legs": []}).error_code == errors.INVALID_REQUEST
    assert err(planner, planner.voyage, {"legs": ["x"]}).error_code == errors.INVALID_REQUEST
    assert err(planner, planner.route, {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                        "waypoints": ["HKHKG"], "required_passage": "SUEZ"}).error_code == errors.INVALID_REQUEST


def test_waypoint_not_found(planner):
    e = err(planner, planner.route, {"origin_port_id": "SGSIN", "destination_port_id": "ZADUR", "waypoints": ["NOPE"]})
    assert e.error_code == errors.PORT_NOT_FOUND


# ---------------------------------------------------------------- robustness
def test_concurrent_requests_do_not_mix_restrictions(planner):
    """searoute keeps the restriction list on a global object. Without the backend lock,
    parallel requests with different exclusions corrupt each other (verified: the engine's
    own 'route uses excluded passage' check fires). Unique origins bypass the cache."""
    expected = {None: 3594.3, "PANAMA": 9773.2}
    fresh = VoyagePlanner()

    def run(i):
        ex = None if i % 2 == 0 else "PANAMA"
        r = fresh.route({"origin_coordinates": {"latitude": 29.73 + i * 1e-4, "longitude": -95.0},
                         "destination_port_id": "CLTOQ", "excluded_passage": ex})
        return ex, r["distance_nm"]

    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        results = list(pool.map(run, range(120)))
    assert all(abs(expected[ex] - dist) < 5 for ex, dist in results)


def test_response_is_json_serialisable(planner):
    import json
    json.dumps(planner.multi_leg(["USHOU", "CLTOQ", "ZADUR"], required_passages=["PANAMA", "CAPE_HORN"]))


# ---------------------------------------------------------------- Member 1 review integration (T02 / T03)
EIGHT_SNAPPED = {"CLTOQ": 114.179, "ZARCB": 50.957, "PECLL": 32.437, "CLVAP": 18.781,
                 "ARBUE": 17.229, "CNSHA": 17.204, "EGSUZ": 15.234, "HKHKG": 14.130}


def test_supplied_ids_and_coordinates_are_untouched(planner):
    import openpyxl
    from voyage_planner.data import DEFAULT_WORKBOOK
    wb = openpyxl.load_workbook(DEFAULT_WORKBOOK, read_only=True, data_only=True)
    rows = list(wb["Port Reference"].iter_rows(values_only=True))
    head = list(rows[0])
    for row in rows[1:]:
        rec = dict(zip(head, row))
        p = planner.data.ports[rec["port_id"]]
        assert (p.port_id, p.un_locode) == (rec["port_id"], rec["un_locode"] or rec["port_id"])
        assert (p.latitude, p.longitude) == (float(rec["latitude"]), float(rec["longitude"]))
        assert (p.approach_latitude, p.approach_longitude) == (float(rec["approach_latitude"]), float(rec["approach_longitude"]))


def test_review_flags_match_member1_t03_exactly(planner):
    flagged = {p["port_id"]: p["data_review"]["approach_snap_nm"] for p in planner.list_ports()
               if p["data_review"]["approach_snap_review"]}
    assert flagged == EIGHT_SNAPPED
    assert all(not p["data_review"]["approach_approved"] for p in planner.list_ports())


def test_identity_decisions_are_recorded_as_aliases_not_renames(planner):
    by_id = {p["port_id"]: p for p in planner.list_ports()}
    review = {k: v["data_review"] for k, v in by_id.items()}
    assert review["GIIBZ"]["identity_status"] == "team_decision" and review["GIIBZ"]["accepted_aliases"] == ["GIGIB"]
    assert review["CNSHA"]["identity_status"] == "team_decision" and review["CNSHA"]["accepted_aliases"] == ["CNSGH"]
    assert review["PAMIT"]["identity_status"] == "team_decision" and review["PAMIT"]["known_as"] == "Manzanillo"
    assert sum(1 for v in review.values() if v["identity_status"] != "ok") == 3
    # supplied identity is untouched
    assert (by_id["GIIBZ"]["un_locode"], by_id["CNSHA"]["un_locode"], by_id["PAMIT"]["un_locode"]) == ("GIIBZ", "CNSHA", "PAMIT")


@pytest.mark.parametrize("alias,port_id", [("GIGIB", "GIIBZ"), ("GIIBZ", "GIIBZ"), ("gigib", "GIIBZ"),
                                           ("CNSGH", "CNSHA"), ("CNSHA", "CNSHA"),
                                           ("Manzanillo", "PAMIT"), ("manzanillo", "PAMIT"), ("PAMIT", "PAMIT"),
                                           ("Colon", "PAMIT"), ("Cristobal", "PAMIT")])
def test_decided_aliases_resolve_to_the_supplied_port(planner, alias, port_id):
    assert planner.data.find_port(alias).port_id == port_id


@pytest.mark.parametrize("alias,port_id", [("GIGIB", "GIIBZ"), ("CNSGH", "CNSHA"), ("Manzanillo", "PAMIT")])
def test_routes_by_alias_equal_routes_by_supplied_id(planner, alias, port_id):
    for a, b in ((alias, "NLRTM"), ("NLRTM", alias)):
        by_alias = planner.handle_route({"origin_port_id": a, "destination_port_id": b})
        by_id = planner.handle_route({"origin_port_id": port_id if a == alias else a,
                                      "destination_port_id": port_id if b == alias else b})
        assert by_alias["status"] == "success" and by_alias["distance_nm"] == by_id["distance_nm"]
        assert by_alias["route_geometry"] == by_id["route_geometry"]


def test_identity_decisions_appear_in_route_assumptions(planner):
    r = planner.handle_route({"origin_port_id": "CNSGH", "destination_port_id": "Manzanillo"})
    text = " ".join(r["assumptions"])
    assert "CNSGH is accepted as an alias of CNSHA" in text and "treated as Manzanillo" in text


def test_alias_does_not_collide_with_any_other_port(planner):
    seen = {}
    for p in planner.data.ports.values():
        for k in {p.port_id, p.un_locode, p.port_name, *p.aliases} | set(
                ((planner.data.port_review.get(p.port_id) or {}).get("identity_review") or {}).get("accepted_aliases") or []):
            assert seen.setdefault(k.lower(), p.port_id) == p.port_id, k


@pytest.mark.parametrize("port,snap", sorted(EIGHT_SNAPPED.items()))
def test_snap_warning_fires_for_each_of_the_eight_ports(planner, port, snap):
    dest = "NLRTM" if port == "SGSIN" else "SGSIN"
    r = planner.port_to_port(port, dest)
    text = " ".join(r["warnings"])
    assert "nearest routing-network node" in text and "pending geographic review" in text


def test_no_snap_warning_for_a_port_below_trigger(planner):
    r = planner.port_to_port("SGSIN", "NLRTM")
    assert not any("nearest routing-network node" in w for w in r["warnings"])


# ---------------------------------------------------------------- spec section 7 comparison
def test_compare_panama_vs_cape_horn(planner):
    r = planner.compare_standard_alternatives("USHOU", "CLTOQ", "panama_vs_cape_horn")
    names = [o["route_name"] for o in r["options"]]
    assert names == ["Via Panama Canal", "Via Cape Horn"] and r["status"] == "success"
    pan, horn = r["options"]
    assert pan["passages_used"] == ["PANAMA"] and horn["passages_used"] == ["CAPE_HORN"]
    assert horn["excluded_passage"] == "PANAMA"      # single value echoed as given (spec example style)
    assert r["distance_difference_nm"] == pytest.approx(horn["distance_nm"] - pan["distance_nm"], abs=0.11)
    assert r["shortest_option"] == "Via Panama Canal"
    assert r["calculation_version"] == "0.1.0" and r["comparison_id"].startswith("comparison-")


def test_compare_suez_vs_cape_good_hope_uses_real_calculations(planner):
    r = planner.compare_standard_alternatives("NLRTM", "ZADUR", "suez_vs_cape_good_hope")
    suez, cgh = r["options"]
    assert "SUEZ" in suez["passages_used"] and cgh["passages_used"] == ["CAPE_GOOD_HOPE"]
    # each option equals the plain /route result: no benchmark numbers are substituted
    direct = planner.port_to_port("NLRTM", "ZADUR", required_passage="CAPE_GOOD_HOPE", excluded_passage="SUEZ")
    assert cgh["distance_nm"] == direct["distance_nm"]
    assert r["distance_difference_nm"] == pytest.approx(abs(suez["distance_nm"] - cgh["distance_nm"]), abs=0.11)


def test_compare_is_deterministic_and_json_serialisable(planner):
    import json as _json
    a = planner.compare_standard_alternatives("USHOU", "CLTOQ", "panama_vs_cape_horn")
    b = planner.compare_standard_alternatives("USHOU", "CLTOQ", "panama_vs_cape_horn")
    assert a == b and _json.loads(_json.dumps(a)) == a


def test_compare_accepts_coordinates_and_excluded_only_options(planner):
    r = planner.compare({"origin_coordinates": {"latitude": 1.29, "longitude": 103.85},
                         "destination_port_id": "NLRTM",
                         "options": [{"route_name": "Automatic"},
                                     {"route_name": "No Suez", "excluded_passage": ["SUEZ"]}]})
    auto, nosuez = r["options"]
    assert nosuez["distance_nm"] > auto["distance_nm"] and "SUEZ" not in nosuez["passages_used"]
    assert r["shortest_option"] == "Automatic"


@pytest.mark.parametrize("request_body,code", [
    ({"origin_port_id": "USHOU", "destination_port_id": "CLTOQ"}, "INVALID_REQUEST"),
    ({"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "options": [{"route_name": "x"}]}, "INVALID_REQUEST"),
    ({"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "options": ["a", "b"]}, "INVALID_REQUEST"),
    ({"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "options": [{}, {"required_passage": "NOPE"}]}, "INVALID_PASSAGE"),
    ({"origin_port_id": "NOPE", "destination_port_id": "CLTOQ", "options": [{}, {}]}, "PORT_NOT_FOUND"),
    ({"destination_port_id": "CLTOQ", "options": [{}, {}]}, "MISSING_ORIGIN"),
])
def test_compare_errors_follow_spec(planner, request_body, code):
    r = planner.handle_compare(request_body)
    assert r["status"] == "error" and r["error_code"] == code


def test_compare_unknown_preset_rejected(planner):
    with pytest.raises(VoyagePlannerError):
        planner.compare_standard_alternatives("USHOU", "CLTOQ", "nonsense")


def test_every_excludable_passage_can_be_excluded_in_the_ui_list(planner):
    ids = {p["passage_id"] for p in planner.list_passages() if p["can_be_excluded"]}
    assert ids == {"PANAMA", "SUEZ", "GIBRALTAR", "MALACCA", "CAPE_HORN", "CAPE_GOOD_HOPE"}
