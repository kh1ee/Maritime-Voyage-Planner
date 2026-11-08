"""Routing engine.

OWNERSHIP NOTE: the routing module is Member 2's task (T05-T08, T16-T18). This file is
the agreed interface (T04) plus a working implementation over searoute-py so the API and
tests run now. Member 2 may rewrite the internals; keep the names and signatures of
`calculate_route` and `calculate_voyage` so the API and tests keep working.
"""
from __future__ import annotations

import hashlib
import json
import warnings as py_warnings
from importlib.metadata import version

import searoute as sr

from .reference_data import find_port, load_passages
from .schemas import (CALCULATION_VERSION, NOT_FOR_NAVIGATION, Coordinates, Endpoint, RouteRequest,
                      RouteResponse, VoyageLeg, VoyageRequest, VoyageResponse)

SEAROUTE_VERSION = version("searoute")

ASSUMPTIONS = [
    "Port-level coordinates were used (approach point where recorded in the Port Reference).",
    f"Distance was calculated using the searoute-py {SEAROUTE_VERSION} maritime network.",
    "Distances are in nautical miles (1 nautical mile = 1,852 metres).",
    "searoute-py blocks the Northwest Passage by default.",
]


class VoyagePlannerError(Exception):
    """An error the API turns into a structured error response."""

    def __init__(self, error_code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.http_status = http_status


# ---------------- Helpers ----------------

def _check_coordinates(c: Coordinates, label: str) -> None:
    if not (-90 <= c.latitude <= 90) or not (-180 <= c.longitude <= 180):
        raise VoyagePlannerError("INVALID_COORDINATES",
                                 f"{label} coordinates out of range: latitude must be -90 to 90, "
                                 f"longitude -180 to 180.")


def _resolve(port_id: str | None, coords: Coordinates | None, role: str) -> Endpoint:
    """Turn a port ID or a coordinate pair into an Endpoint. role is 'origin' or 'destination'."""
    if port_id and coords:
        raise VoyagePlannerError("INVALID_REQUEST",
                                 f"Give either {role}_port_id or {role}_coordinates, not both.")
    if not port_id and not coords:
        raise VoyagePlannerError(f"MISSING_{role.upper()}", f"No {role} was supplied.")
    if port_id:
        port = find_port(port_id)
        if port is None:
            raise VoyagePlannerError("PORT_NOT_FOUND", f"The supplied {role} port ID was not found: {port_id}.",
                                     http_status=404)
        if port.status != "active":
            raise VoyagePlannerError("PORT_NOT_FOUND", f"The {role} port {port.port_id} is marked {port.status}.",
                                     http_status=404)
        lat, lon = port.routing_point
        return Endpoint(port_id=port.port_id, port_name=port.port_name, latitude=lat, longitude=lon)
    _check_coordinates(coords, role.capitalize())
    return Endpoint(port_id=None, port_name="Synthetic position", latitude=coords.latitude, longitude=coords.longitude)


# Passages that are a single connection in searoute's network, so blocking them is enforced by the
# network itself: our Passage Reference ID -> searoute's restriction name.
# Capes are not network connections, so they cannot be excluded this way.
SEAROUTE_BLOCKABLE = {"PANAMA": "panama", "SUEZ": "suez", "GIBRALTAR": "gibraltar", "MALACCA": "malacca"}

# searoute's own default: the Arctic Northwest Passage is always blocked.
DEFAULT_RESTRICTIONS = ["northwest"]


def _restrictions_for(request: RouteRequest) -> list[str]:
    """Validate the passage fields and return the searoute restriction list for this request."""
    known = load_passages()
    for value in (request.required_passage, request.excluded_passage):
        if value and value.upper() not in known:
            raise VoyagePlannerError("INVALID_PASSAGE",
                                     f"Unknown passage '{value}'. Supported: {', '.join(sorted(known))}.")

    # Requiring a passage is not enforced yet: refuse rather than ignore, because a route that
    # silently ignores "via Panama" looks right but isn't.
    if request.required_passage:
        raise VoyagePlannerError("PASSAGE_NOT_SUPPORTED",
                                 "Required passages are not enforced yet (planned tasks T18-T19).",
                                 http_status=501)

    restrictions = list(DEFAULT_RESTRICTIONS)
    if request.excluded_passage:
        passage = request.excluded_passage.upper()
        if passage not in SEAROUTE_BLOCKABLE:
            raise VoyagePlannerError("PASSAGE_NOT_SUPPORTED",
                                     f"Excluding {passage} is not supported yet. Passages that can be excluded: "
                                     f"{', '.join(sorted(SEAROUTE_BLOCKABLE))}.",
                                     http_status=501)
        restrictions.append(SEAROUTE_BLOCKABLE[passage])
    return restrictions


def _stable_id(prefix: str, payload: dict) -> str:
    """Same request + same version -> same ID, so results are traceable and reproducible."""
    text = json.dumps(payload, sort_keys=True) + CALCULATION_VERSION + SEAROUTE_VERSION
    return f"{prefix}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"


def _searoute(a: Endpoint, b: Endpoint, restrictions: list[str]) -> dict:
    no_route = VoyagePlannerError("ROUTE_NOT_FOUND",
                                  f"No sea route found between {a.port_name} and {b.port_name}"
                                  + (f" with {', '.join(r for r in restrictions if r != 'northwest')} excluded."
                                     if len(restrictions) > 1 else "."),
                                  http_status=422)
    try:
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore")  # searoute warns on no path; we raise our own error instead
            feature = sr.searoute([a.longitude, a.latitude], [b.longitude, b.latitude], units="naut",
                                  restrictions=restrictions, return_passages=True)
    except Exception as exc:  # searoute raises various errors when no path exists
        raise no_route from exc
    # When restrictions cut every path, searoute returns length 0 instead of raising.
    same_point = (a.latitude, a.longitude) == (b.latitude, b.longitude)
    if float(feature["properties"]["length"]) <= 0 and not same_point:
        raise no_route
    return feature


# ---------------- Public functions ----------------

def calculate_route(request: RouteRequest) -> RouteResponse:
    origin = _resolve(request.origin_port_id, request.origin_coordinates, "origin")
    destination = _resolve(request.destination_port_id, request.destination_coordinates, "destination")
    restrictions = _restrictions_for(request)
    for i, wp in enumerate(request.waypoints, start=1):
        _check_coordinates(wp, f"Waypoint {i}")

    # Route origin -> each waypoint -> destination, joining the pieces into one line.
    stops = [origin] + [Endpoint(port_id=None, port_name=f"Waypoint {i}", latitude=w.latitude, longitude=w.longitude)
                        for i, w in enumerate(request.waypoints, start=1)] + [destination]
    distance, coords, passages = 0.0, [], []
    for a, b in zip(stops, stops[1:]):
        piece = _searoute(a, b, restrictions)
        distance += float(piece["properties"]["length"])
        piece_coords = piece["geometry"]["coordinates"]
        coords.extend(piece_coords if not coords else piece_coords[1:])
        for p in piece["properties"].get("traversed_passages") or []:
            if p not in passages:
                passages.append(p)

    # Independent check that the exclusion actually held in the calculated route.
    if request.excluded_passage:
        blocked = SEAROUTE_BLOCKABLE[request.excluded_passage.upper()]
        if blocked in passages:
            raise VoyagePlannerError("ROUTE_NOT_FOUND",
                                     f"Calculated route still uses {request.excluded_passage.upper()}; "
                                     f"result rejected.", http_status=422)

    warnings = [NOT_FOR_NAVIGATION]
    if request.excluded_passage:
        warnings.append(f"{request.excluded_passage.upper()} was excluded from this route.")
    if origin.port_id and origin.port_id == destination.port_id:
        warnings.append("Origin and destination are the same port.")
    if request.calculation_version and request.calculation_version != CALCULATION_VERSION:
        warnings.append(f"Requested calculation version {request.calculation_version}; "
                        f"service is running {CALCULATION_VERSION}.")

    return RouteResponse(
        route_id=_stable_id("route", request.model_dump()),
        distance_nm=round(distance, 2),
        origin=origin,
        destination=destination,
        routing_points=request.waypoints,
        passages_used=passages,
        route_geometry={"type": "LineString", "coordinates": coords},
        assumptions=ASSUMPTIONS,
        warnings=warnings,
    )


def calculate_voyage(request: VoyageRequest) -> VoyageResponse:
    legs: list[VoyageLeg] = []
    warnings = [NOT_FOR_NAVIGATION]
    for n, leg_request in enumerate(request.legs, start=1):
        try:
            r = calculate_route(leg_request)
        except VoyagePlannerError as e:
            raise VoyagePlannerError(e.error_code, f"Leg {n}: {e.message}", e.http_status) from e
        legs.append(VoyageLeg(
            leg_number=n,
            origin_port_id=r.origin.port_id,
            destination_port_id=r.destination.port_id,
            origin=r.origin,
            destination=r.destination,
            distance_nm=r.distance_nm,
            passages_used=r.passages_used,
            route_geometry=r.route_geometry,
        ))
        warnings += [w for w in r.warnings if w not in warnings]

    for prev, nxt in zip(legs, legs[1:]):
        if (prev.destination.latitude, prev.destination.longitude) != (nxt.origin.latitude, nxt.origin.longitude):
            warnings.append(f"Leg {nxt.leg_number} does not start where leg {prev.leg_number} ends.")

    return VoyageResponse(
        voyage_id=_stable_id("voyage", request.model_dump()),
        legs=legs,
        total_distance_nm=round(sum(l.distance_nm for l in legs), 2),
        assumptions=ASSUMPTIONS,
        warnings=warnings,
    )
