"""T14 - data-quality checks on the Port Reference tab.

Catches problems early that would otherwise show up as strange routes.
"""
import pytest

from voyage_planner.engine import calculate_route
from voyage_planner.reference_data import load_passages, load_ports
from voyage_planner.schemas import RouteRequest

PORTS = load_ports()


def test_expected_port_count():
    assert len(PORTS) == 29


def test_port_ids_match_un_locode():
    mismatched = [p.port_id for p in PORTS.values() if p.un_locode and p.un_locode != p.port_id]
    assert not mismatched, f"port_id differs from un_locode for: {mismatched}"


@pytest.mark.parametrize("port_id", sorted(PORTS))
def test_coordinates_in_range(port_id):
    p = PORTS[port_id]
    assert -90 <= p.latitude <= 90 and -180 <= p.longitude <= 180


@pytest.mark.parametrize("port_id", sorted(PORTS))
def test_every_port_can_be_routed(port_id):
    """Each port's routing point must connect to the sea network (a basic approach-point check)."""
    other = "SGSIN" if port_id != "SGSIN" else "HKHKG"
    r = calculate_route(RouteRequest(origin_port_id=port_id, destination_port_id=other))
    assert r.distance_nm > 0


def test_passage_ids_present():
    assert {"PANAMA", "SUEZ", "CAPE_HORN", "CAPE_GOOD_HOPE"} <= set(load_passages())
