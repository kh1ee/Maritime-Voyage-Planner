"""T14 - automated tests for the routing engine.

These check the code behaves as designed (functional and mathematical tests).
They are NOT independent accuracy validation: see test_benchmarks.py for why.
"""
import math

import pytest

from voyage_planner.engine import VoyagePlannerError, calculate_route, calculate_voyage
from voyage_planner.schemas import Coordinates, RouteRequest, VoyageRequest


def great_circle_nm(lat1, lon1, lat2, lon2):
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_nm * math.asin(math.sqrt(a))


def port_route(a, b, **extra):
    return RouteRequest(origin_port_id=a, destination_port_id=b, **extra)


def error_code(request, fn=calculate_route):
    with pytest.raises(VoyagePlannerError) as info:
        fn(request)
    return info.value.error_code


# ---------------- Port-to-port ----------------

def test_port_to_port_basic():
    r = calculate_route(port_route("SGSIN", "HKHKG"))
    assert r.status == "success"
    assert r.distance_nm > 0
    assert r.origin.port_name == "Singapore" and r.destination.port_name == "Hong Kong"


def test_sea_distance_never_shorter_than_great_circle():
    r = calculate_route(port_route("SGSIN", "NLRTM"))
    gc = great_circle_nm(r.origin.latitude, r.origin.longitude, r.destination.latitude, r.destination.longitude)
    assert r.distance_nm >= gc * 0.99  # 1% slack for snapping to the network


def test_port_lookup_by_alias_and_name():
    by_id = calculate_route(port_route("INBOM", "SGSIN"))
    by_alias = calculate_route(port_route("Bombay", "Singapore"))
    assert by_alias.distance_nm == by_id.distance_nm


def test_repeatable():
    a = calculate_route(port_route("SGSIN", "HKHKG"))
    b = calculate_route(port_route("SGSIN", "HKHKG"))
    assert (a.route_id, a.distance_nm) == (b.route_id, b.distance_nm)


def test_warning_always_says_not_for_navigation():
    r = calculate_route(port_route("SGSIN", "HKHKG"))
    assert "Academic estimate; not for navigation." in r.warnings


# ---------------- Position-to-port ----------------

def test_synthetic_position_to_port():
    r = calculate_route(RouteRequest(origin_coordinates=Coordinates(latitude=10.0, longitude=114.0),
                                     destination_port_id="SGSIN"))
    assert r.origin.port_id is None
    assert r.distance_nm > 0


# ---------------- Waypoints ----------------

def test_waypoint_route_is_not_shorter_than_direct():
    direct = calculate_route(port_route("SGSIN", "HKHKG"))
    via = calculate_route(port_route("SGSIN", "HKHKG", waypoints=[Coordinates(latitude=10.0, longitude=114.0)]))
    assert via.distance_nm >= direct.distance_nm - 0.01
    assert len(via.routing_points) == 1


# ---------------- Multi-leg ----------------

def demo_voyage():
    return VoyageRequest(legs=[port_route("SGSIN", "HKHKG"), port_route("HKHKG", "LKCMB"),
                               port_route("LKCMB", "ZADUR")])


def test_voyage_leg_count_and_numbering():
    v = calculate_voyage(demo_voyage())
    assert [l.leg_number for l in v.legs] == [1, 2, 3]


def test_voyage_total_equals_sum_of_legs():
    v = calculate_voyage(demo_voyage())
    assert v.total_distance_nm == pytest.approx(sum(l.distance_nm for l in v.legs), abs=0.01)


def test_voyage_legs_match_single_routes():
    v = calculate_voyage(demo_voyage())
    single = calculate_route(port_route("HKHKG", "LKCMB"))
    assert v.legs[1].distance_nm == single.distance_nm


def test_voyage_warns_when_legs_do_not_connect():
    v = calculate_voyage(VoyageRequest(legs=[port_route("SGSIN", "HKHKG"), port_route("LKCMB", "ZADUR")]))
    assert any("does not start where" in w for w in v.warnings)


# ---------------- Geometry ----------------

def test_geometry_is_valid_geojson_linestring():
    g = calculate_route(port_route("SGSIN", "HKHKG")).route_geometry
    assert g["type"] == "LineString" and len(g["coordinates"]) >= 2
    for lon, lat in g["coordinates"]:
        assert -180 <= lon <= 180 and -90 <= lat <= 90


def test_geometry_is_longitude_first():
    """Singapore is at longitude ~104, latitude ~1. If swapped, the first value would be ~1."""
    first_lon, first_lat = calculate_route(port_route("SGSIN", "HKHKG")).route_geometry["coordinates"][0]
    assert first_lon > 100 and first_lat < 5


# ---------------- Invalid inputs (one test per required error code) ----------------

def test_port_not_found():
    assert error_code(port_route("SGSIN", "XXNOPE")) == "PORT_NOT_FOUND"


def test_missing_origin():
    assert error_code(RouteRequest(destination_port_id="SGSIN")) == "MISSING_ORIGIN"


def test_missing_destination():
    assert error_code(RouteRequest(origin_port_id="SGSIN")) == "MISSING_DESTINATION"


@pytest.mark.parametrize("lat, lon", [(95, 10), (-91, 10), (10, 181), (10, -200)])
def test_invalid_coordinates(lat, lon):
    req = RouteRequest(origin_coordinates=Coordinates(latitude=lat, longitude=lon), destination_port_id="SGSIN")
    assert error_code(req) == "INVALID_COORDINATES"


def test_port_and_coordinates_together_is_invalid_request():
    req = RouteRequest(origin_port_id="SGSIN", origin_coordinates=Coordinates(latitude=1, longitude=104),
                       destination_port_id="HKHKG")
    assert error_code(req) == "INVALID_REQUEST"


def test_unknown_passage():
    assert error_code(port_route("USHOU", "CLTOQ", required_passage="ATLANTIS")) == "INVALID_PASSAGE"


def test_known_passage_refused_until_enforced():
    assert error_code(port_route("USHOU", "CLTOQ", required_passage="PANAMA")) == "PASSAGE_NOT_SUPPORTED"


def test_voyage_error_names_the_leg():
    with pytest.raises(VoyagePlannerError) as info:
        calculate_voyage(VoyageRequest(legs=[port_route("SGSIN", "HKHKG"), port_route("HKHKG", "XXNOPE")]))
    assert info.value.error_code == "PORT_NOT_FOUND" and info.value.message.startswith("Leg 2")


# ---------------- Excluded passages ----------------

def test_exclude_suez_avoids_suez_and_is_longer():
    normal = calculate_route(port_route("NLRTM", "SGSIN"))
    avoid = calculate_route(port_route("NLRTM", "SGSIN", excluded_passage="SUEZ"))
    assert "suez" in normal.passages_used
    assert "suez" not in avoid.passages_used
    assert avoid.distance_nm > normal.distance_nm


def test_exclude_panama_avoids_panama():
    r = calculate_route(port_route("USHOU", "CLTOQ", excluded_passage="PANAMA"))
    assert "panama" not in r.passages_used


def test_exclude_is_case_insensitive():
    a = calculate_route(port_route("NLRTM", "SGSIN", excluded_passage="suez"))
    b = calculate_route(port_route("NLRTM", "SGSIN", excluded_passage="SUEZ"))
    assert a.distance_nm == b.distance_nm


def test_exclusion_is_reported_in_warnings():
    r = calculate_route(port_route("NLRTM", "SGSIN", excluded_passage="SUEZ"))
    assert "SUEZ was excluded from this route." in r.warnings


def test_exclude_unrelated_passage_changes_nothing():
    normal = calculate_route(port_route("SGSIN", "HKHKG"))
    avoid = calculate_route(port_route("SGSIN", "HKHKG", excluded_passage="PANAMA"))
    assert avoid.distance_nm == normal.distance_nm


def test_northwest_passage_always_blocked():
    """Rotterdam-Shanghai through the Arctic would be about 8,358 NM; the normal route is about 10,576 NM."""
    r = calculate_route(port_route("NLRTM", "CNSHA"))
    assert "northwest" not in r.passages_used
    assert r.distance_nm > 10000


@pytest.mark.parametrize("cape", ["CAPE_HORN", "CAPE_GOOD_HOPE"])
def test_excluding_a_cape_is_refused(cape):
    assert error_code(port_route("NLRTM", "SGSIN", excluded_passage=cape)) == "PASSAGE_NOT_SUPPORTED"


def test_exclusion_that_blocks_every_path_is_route_not_found():
    """Singapore to Suez port is only reachable through the canal region when Suez is blocked."""
    assert error_code(port_route("SGSIN", "EGSUZ", excluded_passage="SUEZ")) == "ROUTE_NOT_FOUND"


def test_exclusion_applies_to_each_voyage_leg():
    v = calculate_voyage(VoyageRequest(legs=[port_route("NLRTM", "SGSIN", excluded_passage="SUEZ"),
                                             port_route("SGSIN", "HKHKG")]))
    assert "suez" not in v.legs[0].passages_used
