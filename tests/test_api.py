"""T14 - API contract tests: check responses match API_SPECIFICATION.md."""
from fastapi.testclient import TestClient

from voyage_planner.api import app

client = TestClient(app)

ROUTE_FIELDS = {"route_id", "status", "distance_nm", "origin", "destination", "routing_points",
                "passages_used", "route_geometry", "assumptions", "warnings", "calculation_version"}
VOYAGE_FIELDS = {"voyage_id", "status", "legs", "total_distance_nm", "assumptions", "warnings", "calculation_version"}
LEG_FIELDS = {"leg_number", "origin_port_id", "destination_port_id", "distance_nm", "passages_used", "route_geometry"}
ENDPOINT_FIELDS = {"port_id", "port_name", "latitude", "longitude"}
ERROR_FIELDS = {"status", "error_code", "message", "warnings"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "calculation_version": "0.2.0"}


def test_ports_and_passages_lists():
    assert len(client.get("/ports").json()) == 29
    assert any(p["passage_id"] == "PANAMA" for p in client.get("/passages").json())


def test_route_contract():
    r = client.post("/route", json={"origin_port_id": "SGSIN", "destination_port_id": "NLRTM"})
    assert r.status_code == 200
    data = r.json()
    assert ROUTE_FIELDS <= data.keys()
    assert data["status"] == "success"
    assert ENDPOINT_FIELDS <= data["origin"].keys()
    assert data["route_geometry"]["type"] == "LineString"


def test_route_with_coordinates_contract():
    body = {"origin_coordinates": {"latitude": 10.0, "longitude": 114.0}, "destination_port_id": "SGSIN"}
    r = client.post("/route", json=body)
    assert r.status_code == 200 and r.json()["origin"]["port_id"] is None


def test_voyage_contract():
    body = {"legs": [{"origin_port_id": "SGSIN", "destination_port_id": "HKHKG"},
                     {"origin_port_id": "HKHKG", "destination_port_id": "LKCMB"},
                     {"origin_port_id": "LKCMB", "destination_port_id": "ZADUR"}]}
    r = client.post("/voyage", json=body)
    assert r.status_code == 200
    data = r.json()
    assert VOYAGE_FIELDS <= data.keys() and len(data["legs"]) == 3
    for leg in data["legs"]:
        assert LEG_FIELDS <= leg.keys()


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert ERROR_FIELDS <= body.keys()
    assert body["status"] == "error" and body["error_code"] == code


def test_error_port_not_found():
    assert_error(client.post("/route", json={"origin_port_id": "XXNOPE", "destination_port_id": "SGSIN"}),
                 404, "PORT_NOT_FOUND")


def test_error_missing_origin():
    assert_error(client.post("/route", json={"destination_port_id": "SGSIN"}), 400, "MISSING_ORIGIN")


def test_error_missing_destination():
    assert_error(client.post("/route", json={"origin_port_id": "SGSIN"}), 400, "MISSING_DESTINATION")


def test_error_invalid_coordinates():
    body = {"origin_coordinates": {"latitude": 123, "longitude": 0}, "destination_port_id": "SGSIN"}
    assert_error(client.post("/route", json=body), 400, "INVALID_COORDINATES")


def test_error_invalid_passage():
    body = {"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "required_passage": "ATLANTIS"}
    assert_error(client.post("/route", json=body), 400, "INVALID_PASSAGE")


def test_error_invalid_request_wrong_type():
    body = {"origin_coordinates": {"latitude": "north", "longitude": 0}, "destination_port_id": "SGSIN"}
    assert_error(client.post("/route", json=body), 400, "INVALID_REQUEST")


def test_error_invalid_request_empty_voyage():
    assert_error(client.post("/voyage", json={"legs": []}), 400, "INVALID_REQUEST")


def test_route_with_excluded_passage():
    body = {"origin_port_id": "NLRTM", "destination_port_id": "ZADUR", "excluded_passage": "SUEZ"}
    r = client.post("/route", json=body)
    assert r.status_code == 200 and "suez" not in r.json()["passages_used"]


def test_error_route_not_found_when_exclusion_blocks_all_paths():
    body = {"origin_port_id": "SGSIN", "destination_port_id": "EGSUZ", "excluded_passage": "SUEZ"}
    assert_error(client.post("/route", json=body), 422, "ROUTE_NOT_FOUND")


def test_error_required_passage_still_refused():
    body = {"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "required_passage": "PANAMA"}
    assert_error(client.post("/route", json=body), 501, "PASSAGE_NOT_SUPPORTED")
