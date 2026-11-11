"""HTTP-level tests for the Voyage Planner API (Member 3: T09, T14, T23).

Run:  python -m pytest -q tests/test_api.py
These check the HTTP contract (status codes, body shapes); the routing
results themselves are covered by tests/test_engine.py (Member 2).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient                          # noqa: E402

from voyage_planner import CALCULATION_VERSION                       # noqa: E402
from voyage_planner.api import app                                   # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def assert_error(resp, http_status, code):
    assert resp.status_code == http_status, resp.text
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["warnings"], list)


# ---------------------------------------------------------------- lookups
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "calculation_version": CALCULATION_VERSION}


def test_ports(client):
    ports = client.get("/ports").json()
    ids = {p["port_id"] for p in ports}
    assert {"SGSIN", "NLRTM", "USHOU", "CLTOQ", "ZADUR"} <= ids
    assert {"port_id", "port_name", "un_locode", "country", "latitude", "longitude", "aliases"} <= set(ports[0])


def test_passages(client):
    passages = {p["passage_id"]: p for p in client.get("/passages").json()}
    assert {"PANAMA", "SUEZ", "CAPE_HORN", "CAPE_GOOD_HOPE", "GIBRALTAR", "MALACCA"} <= set(passages)
    assert all(p["can_be_required"] and p["can_be_excluded"] for p in passages.values())


def test_positions(client):
    positions = client.get("/positions").json()
    assert any(p["position_id"] == "POS_001" for p in positions)


# ---------------------------------------------------------------- /route
def test_route_port_to_port(client):
    r = client.post("/route", json={"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                    "calculation_version": CALCULATION_VERSION})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["distance_nm"] == pytest.approx(8368, abs=250)          # BM_003
    assert body["route_geometry"]["type"] == "LineString"
    assert len(body["route_geometry"]["coordinates"]) > 1
    for key in ("route_id", "origin", "destination", "passages_used", "routing_points",
                "assumptions", "warnings", "calculation_version"):
        assert key in body


def test_route_position_to_port(client):
    r = client.post("/route", json={"origin_coordinates": {"latitude": 35.0, "longitude": -40.0},
                                    "destination_port_id": "NLRTM"})
    assert r.status_code == 200, r.text
    assert r.json()["distance_nm"] > 0


def test_route_required_passage(client):
    r = client.post("/route", json={"origin_port_id": "USHOU", "destination_port_id": "CLTOQ",
                                    "required_passage": "PANAMA"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["distance_nm"] == pytest.approx(3594, abs=250)          # BM_005
    assert "PANAMA" in body["passages_used"]


def test_route_excluded_passage(client):
    r = client.post("/route", json={"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                    "excluded_passage": ["SUEZ"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "SUEZ" not in body["passages_used"]
    assert body["distance_nm"] > body["unconstrained_distance_nm"]


def test_route_unknown_port_is_404(client):
    r = client.post("/route", json={"origin_port_id": "XXXXX", "destination_port_id": "NLRTM"})
    assert_error(r, 404, "PORT_NOT_FOUND")


def test_route_missing_origin_is_400(client):
    r = client.post("/route", json={"destination_port_id": "NLRTM"})
    assert_error(r, 400, "MISSING_ORIGIN")


def test_route_invalid_coordinates_is_400(client):
    r = client.post("/route", json={"origin_coordinates": {"latitude": 95, "longitude": 0},
                                    "destination_port_id": "NLRTM"})
    assert_error(r, 400, "INVALID_COORDINATES")


def test_route_invalid_passage_is_400(client):
    r = client.post("/route", json={"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                    "required_passage": "NOT_A_PASSAGE"})
    assert_error(r, 400, "INVALID_PASSAGE")


def test_route_wrong_version_is_400(client):
    r = client.post("/route", json={"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                    "calculation_version": "9.9.9"})
    assert_error(r, 400, "INVALID_REQUEST")


@pytest.mark.parametrize("payload", ["not json", "[1, 2]"])
def test_route_malformed_body_is_400(client, payload):
    r = client.post("/route", content=payload, headers={"Content-Type": "application/json"})
    assert_error(r, 400, "INVALID_REQUEST")


# ---------------------------------------------------------------- /voyage
def test_voyage_brief_example(client):
    """Houston -> Tocopilla via Panama, Tocopilla -> Durban via Cape Horn (project brief)."""
    r = client.post("/voyage", json={
        "calculation_version": CALCULATION_VERSION,
        "legs": [
            {"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "required_passage": "PANAMA"},
            {"origin_port_id": "CLTOQ", "destination_port_id": "ZADUR", "required_passage": "CAPE_HORN"},
        ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["legs"]) == 2
    assert body["total_distance_nm"] == pytest.approx(sum(body["distance_by_leg_nm"]), abs=0.2)
    assert body["total_distance_nm"] == pytest.approx(10540, rel=0.05)   # brief: 10,540 nm
    assert "PANAMA" in body["legs"][0]["passages_used"]
    assert "CAPE_HORN" in body["legs"][1]["passages_used"]


def test_voyage_intermediate_stops(client):
    r = client.post("/voyage", json={"origin_port_id": "SGSIN", "intermediate_stops": ["ZADUR"],
                                     "destination_port_id": "NLRTM"})
    assert r.status_code == 200, r.text
    assert len(r.json()["legs"]) == 2


def test_voyage_unknown_port_in_leg_is_404(client):
    r = client.post("/voyage", json={"legs": [{"origin_port_id": "SGSIN", "destination_port_id": "XXXXX"}]})
    assert_error(r, 404, "PORT_NOT_FOUND")
    assert r.json()["message"].startswith("Leg 1:")


def test_voyage_empty_legs_is_400(client):
    r = client.post("/voyage", json={"legs": []})
    assert_error(r, 400, "INVALID_REQUEST")
