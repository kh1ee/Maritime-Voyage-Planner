"""The Voyage Planner routing engine (tasks T05, T06, T07, T08, T17, T18).

Public entry points
-------------------
``VoyagePlanner.route(request)``     POST /route   (one origin, one destination)
``VoyagePlanner.voyage(request)``    POST /voyage  (multi-leg)
``VoyagePlanner.handle_route / handle_voyage``
        same, but a ``VoyagePlannerError`` is returned as the specification's
        error dictionary instead of being raised (convenient for the API layer).
``port_to_port`` (T06), ``position_to_port`` (T07), ``multi_leg`` (T08)
        friendly Python wrappers around the two methods above.

The class only deals with *plain dictionaries* in and out, so the API layer
(Member 3) can pass the parsed JSON body straight in and return the result.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import errors
from .backend import LegResult, SearouteBackend
from .config import (CALCULATION_VERSION, EXPECTED_SEAROUTE_VERSION, MAX_LEGS,
                     MAX_REQUIRED_PASSAGES, PASSAGE_DETECTION_NM,
                     CAPE_GATE_PASSAGES, EXCLUDABLE_PASSAGES, PASSAGE_TO_SEAROUTE_TAG,
                     SNAP_WARNING_NM, STANDARD_WARNING)
from .data import ReferenceData, load_reference_data
from .errors import VoyagePlannerError
from .gates import Gate, gate_for
from .geo import distance_to_path_nm


# --------------------------------------------------------------------------
# small internal data holders
# --------------------------------------------------------------------------
@dataclass
class _Stop:
    """A place the route must visit, already resolved to coordinates."""
    kind: str                      # port | position | coordinates | passage
    ident: Optional[str]           # port_id / position_id / passage_id
    name: Optional[str]
    lat: float                     # coordinates shown to the user
    lon: float
    route_lat: float               # coordinates sent to the router
    route_lon: float

    @property
    def route_point(self) -> Tuple[float, float]:
        return (self.route_lon, self.route_lat)

    def key(self) -> List[Any]:    # used to build deterministic ids
        return [self.kind, self.ident] if self.ident else [self.kind, self.lat, self.lon]

    def describe(self) -> Dict[str, Any]:
        """The 'origin' / 'destination' object of the response."""
        d: Dict[str, Any] = {
            "port_id": self.ident if self.kind == "port" else None,
            "port_name": self.name if self.kind == "port" else None,
            "latitude": self.lat,
            "longitude": self.lon,
            "location_type": self.kind,
        }
        if self.kind == "position":
            d["position_id"] = self.ident
            d["position_name"] = self.name
        return d


@dataclass
class _ParsedLeg:
    origin: _Stop
    destination: _Stop
    via: List[_Stop] = field(default_factory=list)       # user waypoints, in order
    required: List[str] = field(default_factory=list)    # passage IDs
    excluded: List[str] = field(default_factory=list)


@dataclass
class _LegOutcome:
    parsed: _ParsedLeg
    chain: List[_Stop]
    segments: List[LegResult]
    segment_nm: List[float]
    distance_nm: float
    coordinates: List[List[float]]
    passages_used: List[str]
    network_tags: List[str]
    unconstrained_nm: Optional[float]
    warnings: List[str]
    assumptions: List[str]


def _jsonable_num(x: float) -> float:
    return round(float(x), 1)


class VoyagePlanner:
    """Deterministic maritime distance service built on searoute-py."""

    def __init__(self, data: Optional[ReferenceData] = None,
                 backend: Optional[SearouteBackend] = None,
                 data_path: Optional[str] = None) -> None:
        self.data = data or load_reference_data(data_path)
        self.backend = backend or SearouteBackend()

    # ======================================================================
    # simple service / lookup helpers
    # ======================================================================
    def health(self) -> Dict[str, str]:
        """GET /health"""
        return {"status": "ok", "calculation_version": CALCULATION_VERSION}

    def list_ports(self) -> List[Dict[str, Any]]:
        return [{"port_id": p.port_id, "port_name": p.port_name, "un_locode": p.un_locode,
                 "country": p.country, "latitude": p.latitude, "longitude": p.longitude,
                 "approach_latitude": p.approach_latitude, "approach_longitude": p.approach_longitude,
                 "aliases": list(p.aliases),
                 "data_review": self._port_review(p.port_id)} for p in self.data.ports.values()]

    def _port_review(self, port_id: str) -> Dict[str, Any]:
        """Member 1 T02/T03 flags for a port (documentation only - never changes a value)."""
        r = self.data.port_review.get(port_id) or {}
        ident = r.get("identity_review") or {}
        return {"identity_status": ident.get("status", "ok"),
                "accepted_aliases": list(ident.get("accepted_aliases") or []),
                "known_as": ident.get("known_as"),
                "identity_note": ident.get("note"),
                "approach_snap_nm": r.get("approach_snap_nm"),
                "approach_snap_review": bool(r.get("approach_snap_review", False)),
                "approach_approved": bool(r.get("approach_approved", False))}

    def list_passages(self) -> List[Dict[str, Any]]:
        return [{"passage_id": p.passage_id, "passage_name": p.passage_name,
                 "passage_type": p.passage_type, "latitude": p.latitude,
                 "longitude": p.longitude,
                 "can_be_required": True,
                 "can_be_excluded": p.passage_id in EXCLUDABLE_PASSAGES}
                for p in self.data.passages.values()]

    def list_positions(self) -> List[Dict[str, Any]]:
        return [{"position_id": p.position_id, "position_name": p.position_name,
                 "latitude": p.latitude, "longitude": p.longitude, "scenario": p.scenario}
                for p in self.data.positions.values()]

    # ======================================================================
    # friendly wrappers (the named deliverables T06 / T07 / T08)
    # ======================================================================
    def port_to_port(self, origin_port: str, destination_port: str,
                     required_passage=None, excluded_passage=None) -> Dict[str, Any]:
        """T06 - distance between two ports (ID, UN/LOCODE, name or alias)."""
        return self.route({"origin_port_id": origin_port,
                           "destination_port_id": destination_port,
                           "required_passage": required_passage,
                           "excluded_passage": excluded_passage})

    def position_to_port(self, latitude: float, longitude: float, destination_port: str,
                         required_passage=None, excluded_passage=None) -> Dict[str, Any]:
        """T07 - route from a (synthetic) vessel position to a port."""
        return self.route({"origin_coordinates": {"latitude": latitude, "longitude": longitude},
                           "destination_port_id": destination_port,
                           "required_passage": required_passage,
                           "excluded_passage": excluded_passage})

    def multi_leg(self, stops: Sequence[Any], required_passages: Optional[Sequence[Any]] = None,
                  excluded_passage=None) -> Dict[str, Any]:
        """T08 - voyage through ``stops`` (port IDs, position IDs or coordinate dicts).

        ``required_passages`` is an optional list with one entry per leg
        (``len(stops) - 1``), e.g. ``["PANAMA", "CAPE_HORN"]``; use ``None``
        for legs without a requirement.
        """
        if len(stops) < 2:
            raise VoyagePlannerError(errors.INVALID_REQUEST, "A voyage needs at least two stops.")
        n_legs = len(stops) - 1
        if required_passages is not None and len(required_passages) != n_legs:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     f"required_passages must have {n_legs} entries (one per leg).")
        legs = []
        for i in range(n_legs):
            leg: Dict[str, Any] = {}
            leg.update(self._token_to_spec(stops[i], "origin"))
            leg.update(self._token_to_spec(stops[i + 1], "destination"))
            if required_passages and required_passages[i]:
                leg["required_passage"] = required_passages[i]
            legs.append(leg)
        return self.voyage({"legs": legs, "excluded_passage": excluded_passage})

    # ======================================================================
    # API entry points
    # ======================================================================
    def handle_route(self, request: Any) -> Dict[str, Any]:
        """Like route() but returns the spec's error dictionary instead of raising."""
        try:
            return self.route(request)
        except VoyagePlannerError as exc:
            return exc.to_dict()

    def handle_voyage(self, request: Any) -> Dict[str, Any]:
        try:
            return self.voyage(request)
        except VoyagePlannerError as exc:
            return exc.to_dict()

    def route(self, request: Any) -> Dict[str, Any]:
        """POST /route - one origin, one destination (API spec sections 3 and 5)."""
        self._check_request(request)
        leg = self._parse_leg(request, default_excluded=None, allow_via_key=True)
        outcome = self._compute_leg(leg)
        payload = {"v": CALCULATION_VERSION, "leg": self._leg_key(leg)}
        required = self._echo(leg.required)
        excluded = self._echo(leg.excluded)
        return {
            "route_id": self._stable_id("route", payload),
            "status": "success",
            "distance_nm": outcome.distance_nm,
            "origin": leg.origin.describe(),
            "destination": leg.destination.describe(),
            "routing_points": self._routing_points(outcome),
            "passages_used": outcome.passages_used,
            "required_passage": required,
            "excluded_passage": excluded,
            "distance_by_leg_nm": outcome.segment_nm,
            "unconstrained_distance_nm": outcome.unconstrained_nm,
            "network_passages_traversed": outcome.network_tags,
            "route_geometry": {"type": "LineString", "coordinates": outcome.coordinates},
            "assumptions": outcome.assumptions,
            "warnings": [STANDARD_WARNING] + outcome.warnings,
            "calculation_version": CALCULATION_VERSION,
            "routing_engine": self._engine_info(),
        }

    def compare(self, request: Any) -> Dict[str, Any]:
        """Route comparison (API specification section 7).

        ``request`` is an ordinary /route body (origin + destination, any of the
        supported forms) plus ``options``: a list of at least two objects, each
        with a ``route_name`` and optionally ``required_passage`` /
        ``excluded_passage`` (those replace any passage fields at the top level).
        Every option is a real engine calculation - nothing is looked up from the
        benchmark table.  The response follows the specification's shape
        (``comparison_id``, ``options``, ``distance_difference_nm``, ``warnings``)
        with extra, additive fields: per-option distance and passages used, and
        which option is shortest.
        """
        self._check_request(request)
        options = request.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     "'options' must be a list of at least two route options to compare.")
        if len(options) > 6:
            raise VoyagePlannerError(errors.INVALID_REQUEST, "At most 6 options can be compared at once.")
        base = {k: v for k, v in request.items()
                if k not in ("options", "comparison_id", "required_passage", "excluded_passage")}
        results: List[Dict[str, Any]] = []
        warnings: List[str] = [STANDARD_WARNING]
        for number, option in enumerate(options, start=1):
            if not isinstance(option, dict):
                raise VoyagePlannerError(errors.INVALID_REQUEST, f"Option {number} must be a JSON object.")
            body = dict(base)
            for key in ("required_passage", "excluded_passage"):
                if key in option and option[key] not in (None, "", []):
                    body[key] = option[key]
            try:
                routed = self.route(body)
            except VoyagePlannerError as exc:
                raise VoyagePlannerError(exc.error_code, f"Option {number}: {exc.message}", exc.warnings)
            name = option.get("route_name") or f"Option {number}"
            results.append({
                "route_name": name,
                "required_passage": routed["required_passage"],
                "excluded_passage": routed["excluded_passage"],
                "distance_nm": routed["distance_nm"],
                "passages_used": routed["passages_used"],
                "route_geometry": routed["route_geometry"],
            })
            for w in routed["warnings"]:
                if w not in warnings:
                    warnings.append(w)
        distances = [r["distance_nm"] for r in results]
        shortest = min(range(len(results)), key=lambda i: distances[i])
        for r in results:
            r["extra_distance_vs_shortest_nm"] = _jsonable_num(r["distance_nm"] - distances[shortest])
        payload = {"v": CALCULATION_VERSION, "req": json.loads(json.dumps(base, sort_keys=True, default=str)),
                   "options": [{k: r[k] for k in ("route_name", "required_passage", "excluded_passage")}
                               for r in results]}
        return {
            "comparison_id": self._stable_id("comparison", payload),
            "status": "success",
            "options": results,
            "distance_difference_nm": _jsonable_num(max(distances) - min(distances)),
            "shortest_option": results[shortest]["route_name"],
            "warnings": warnings,
            "calculation_version": CALCULATION_VERSION,
        }

    def handle_compare(self, request: Any) -> Dict[str, Any]:
        try:
            return self.compare(request)
        except VoyagePlannerError as exc:
            return exc.to_dict()

    def compare_standard_alternatives(self, origin_port: str, destination_port: str,
                                      alternatives: str) -> Dict[str, Any]:
        """The two T20 comparisons: ``alternatives`` is 'panama_vs_cape_horn' or 'suez_vs_cape_good_hope'."""
        presets = {
            "panama_vs_cape_horn": [
                {"route_name": "Via Panama Canal", "required_passage": "PANAMA"},
                {"route_name": "Via Cape Horn", "required_passage": "CAPE_HORN", "excluded_passage": "PANAMA"}],
            "suez_vs_cape_good_hope": [
                {"route_name": "Via Suez Canal", "required_passage": "SUEZ"},
                {"route_name": "Via Cape of Good Hope", "required_passage": "CAPE_GOOD_HOPE",
                 "excluded_passage": "SUEZ"}],
        }
        if alternatives not in presets:
            raise VoyagePlannerError(errors.INVALID_REQUEST, f"alternatives must be one of {sorted(presets)}.")
        return self.compare({"origin_port_id": origin_port, "destination_port_id": destination_port,
                             "options": presets[alternatives]})

    def voyage(self, request: Any) -> Dict[str, Any]:
        """POST /voyage - multi-leg itinerary (API spec sections 4 and 6).

        Accepts either ``{"legs": [...]}`` (per specification; each leg may also
        carry its own ``required_passage`` / ``excluded_passage``) or the
        shorthand ``origin_*`` + ``destination_*`` + ``intermediate_stops``.
        A top-level ``excluded_passage`` is a default for every leg.
        """
        self._check_request(request)
        if request.get("required_passage") not in (None, "", " ", []):
            raise VoyagePlannerError(
                errors.INVALID_REQUEST,
                "required_passage is not allowed at voyage level; set it on the individual legs.")
        default_excluded = request.get("excluded_passage")
        legs: List[_ParsedLeg] = []
        if request.get("legs") is not None:
            if any(request.get(k) not in (None, "", [], {}) for k in
                   ("origin_port_id", "origin_coordinates", "origin_position_id",
                    "destination_port_id", "destination_coordinates",
                    "destination_position_id", "intermediate_stops", "waypoints")):
                raise VoyagePlannerError(errors.INVALID_REQUEST,
                                         "Use either 'legs' or origin/destination/intermediate_stops, not both.")
            specs = request["legs"]
            if not isinstance(specs, list) or not specs:
                raise VoyagePlannerError(errors.INVALID_REQUEST, "'legs' must be a non-empty list.")
            if len(specs) > MAX_LEGS:
                raise VoyagePlannerError(errors.INVALID_REQUEST, f"At most {MAX_LEGS} legs are supported.")
            for i, spec in enumerate(specs, start=1):
                legs.append(self._wrap_leg_errors(i, lambda s=spec: self._parse_leg(
                    s, default_excluded=default_excluded, allow_via_key=True)))
        else:
            origin = self._resolve_endpoint(request, "origin")
            destination = self._resolve_endpoint(request, "destination")
            stops_raw = request.get("intermediate_stops") or request.get("waypoints") or []
            if not isinstance(stops_raw, list):
                raise VoyagePlannerError(errors.INVALID_REQUEST, "'intermediate_stops' must be a list.")
            chain = [origin] + [self._resolve_via(t) for t in stops_raw] + [destination]
            if len(chain) - 1 > MAX_LEGS:
                raise VoyagePlannerError(errors.INVALID_REQUEST, f"At most {MAX_LEGS} legs are supported.")
            excl = self._normalise_passages(default_excluded, "excluded_passage", exclusion=True)
            legs = [_ParsedLeg(a, b, [], [], list(excl)) for a, b in zip(chain[:-1], chain[1:])]

        outcomes: List[_LegOutcome] = []
        for i, leg in enumerate(legs, start=1):
            outcomes.append(self._wrap_leg_errors(i, lambda l=leg: self._compute_leg(l)))

        leg_payloads, assumptions, warnings = [], [], []
        used_union: List[str] = []
        for i, oc in enumerate(outcomes, start=1):
            leg = oc.parsed
            leg_payloads.append({
                "leg_number": i,
                "origin_port_id": leg.origin.ident if leg.origin.kind == "port" else None,
                "destination_port_id": leg.destination.ident if leg.destination.kind == "port" else None,
                "origin": leg.origin.describe(),
                "destination": leg.destination.describe(),
                "distance_nm": oc.distance_nm,
                "passages_used": oc.passages_used,
                "required_passage": self._echo(leg.required),
                "excluded_passage": self._echo(leg.excluded),
                "routing_points": self._routing_points(oc),
                "unconstrained_distance_nm": oc.unconstrained_nm,
                "route_geometry": {"type": "LineString", "coordinates": oc.coordinates},
            })
            for p in oc.passages_used:
                if p not in used_union:
                    used_union.append(p)
            for a in oc.assumptions:
                if a not in assumptions:
                    assumptions.append(a)
            for w in oc.warnings:
                tagged = f"Leg {i}: {w}"
                if tagged not in warnings:
                    warnings.append(tagged)
        distances = [oc.distance_nm for oc in outcomes]
        assumptions.append("total_distance_nm is the sum of the leg distances (each rounded to 0.1 nm).")
        payload = {"v": CALCULATION_VERSION, "legs": [self._leg_key(l) for l in legs]}
        return {
            "voyage_id": self._stable_id("voyage", payload),
            "status": "success",
            "legs": leg_payloads,
            "distance_by_leg_nm": distances,
            "total_distance_nm": _jsonable_num(sum(distances)),
            "passages_used": used_union,
            "assumptions": assumptions,
            "warnings": [STANDARD_WARNING] + warnings,
            "calculation_version": CALCULATION_VERSION,
            "routing_engine": self._engine_info(),
        }

    # ======================================================================
    # request parsing / validation
    # ======================================================================
    @staticmethod
    def _check_request(request: Any) -> None:
        if not isinstance(request, dict):
            raise VoyagePlannerError(errors.INVALID_REQUEST, "The request body must be a JSON object.")
        version = request.get("calculation_version")
        if version not in (None, "") and version != CALCULATION_VERSION:
            raise VoyagePlannerError(
                errors.INVALID_REQUEST,
                f"Unsupported calculation_version '{version}'; this service provides '{CALCULATION_VERSION}'.")

    @staticmethod
    def _wrap_leg_errors(number: int, fn):
        try:
            return fn()
        except VoyagePlannerError as exc:
            raise VoyagePlannerError(exc.error_code, f"Leg {number}: {exc.message}", exc.warnings)

    def _token_to_spec(self, token: Any, side: str) -> Dict[str, Any]:
        if isinstance(token, dict):
            return {f"{side}_coordinates": token}
        if isinstance(token, str) and self.data.find_port(token) is None \
                and self.data.find_position(token) is not None:
            return {f"{side}_position_id": token}
        return {f"{side}_port_id": token}

    def _parse_leg(self, spec: Any, default_excluded: Any, allow_via_key: bool) -> _ParsedLeg:
        if not isinstance(spec, dict):
            raise VoyagePlannerError(errors.INVALID_REQUEST, "Each leg must be a JSON object.")
        origin = self._resolve_endpoint(spec, "origin")
        destination = self._resolve_endpoint(spec, "destination")

        via_raw, alt_raw = spec.get("waypoints"), spec.get("intermediate_stops")
        if via_raw and alt_raw:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     "Provide 'waypoints' or 'intermediate_stops', not both.")
        via_raw = via_raw or alt_raw or []
        if not isinstance(via_raw, list):
            raise VoyagePlannerError(errors.INVALID_REQUEST, "'waypoints' must be a list.")
        via = [self._resolve_via(t) for t in via_raw]

        required = self._normalise_passages(spec.get("required_passage"), "required_passage", exclusion=False)
        excl_value = spec.get("excluded_passage")
        if excl_value in (None, "", " ", []):
            excl_value = default_excluded
        excluded = self._normalise_passages(excl_value, "excluded_passage", exclusion=True)

        overlap = [p for p in required if p in excluded]
        if overlap:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     f"{', '.join(overlap)} cannot be both required and excluded.")
        if len(required) > MAX_REQUIRED_PASSAGES:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     f"At most {MAX_REQUIRED_PASSAGES} required passages are supported.")
        if via and required:
            raise VoyagePlannerError(
                errors.INVALID_REQUEST,
                "waypoints cannot be combined with required_passage on one route; "
                "use /voyage with one leg per segment instead.")
        return _ParsedLeg(origin, destination, via, required, excluded)

    # ---- locations ---------------------------------------------------
    def _resolve_endpoint(self, spec: Dict[str, Any], side: str) -> _Stop:
        keys = [f"{side}_port_id", f"{side}_coordinates", f"{side}_position_id"]
        given = [k for k in keys if spec.get(k) not in (None, "", {})]
        if not given:
            code = errors.MISSING_ORIGIN if side == "origin" else errors.MISSING_DESTINATION
            raise VoyagePlannerError(code, f"No {side} was supplied (use {keys[0]} or {keys[1]}).")
        if len(given) > 1:
            raise VoyagePlannerError(errors.INVALID_REQUEST,
                                     f"Supply only one of {', '.join(given)} for the {side}.")
        key = given[0]
        if key.endswith("_port_id"):
            port = self.data.find_port(spec[key])
            if port is None:
                raise VoyagePlannerError(errors.PORT_NOT_FOUND,
                                         f"The supplied {side} port ID was not found: {spec[key]!r}.")
            return self._port_stop(port)
        if key.endswith("_position_id"):
            pos = self.data.find_position(spec[key])
            if pos is None:
                raise VoyagePlannerError(errors.INVALID_REQUEST,
                                         f"The supplied {side} position ID was not found: {spec[key]!r}.")
            return _Stop("position", pos.position_id, pos.position_name,
                         pos.latitude, pos.longitude, pos.latitude, pos.longitude)
        lat, lon = self._parse_coordinates(spec[key], side)
        return _Stop("coordinates", None, None, lat, lon, lat, lon)

    @staticmethod
    def _port_stop(port) -> _Stop:
        return _Stop("port", port.port_id, port.port_name, port.latitude, port.longitude,
                     port.approach_latitude, port.approach_longitude)

    @staticmethod
    def _parse_coordinates(value: Any, what: str) -> Tuple[float, float]:
        def bad(msg: str):
            return VoyagePlannerError(errors.INVALID_COORDINATES, f"Invalid {what} coordinates: {msg}")
        if not isinstance(value, dict) or "latitude" not in value or "longitude" not in value:
            raise bad("expected an object with 'latitude' and 'longitude'.")
        lat, lon = value["latitude"], value["longitude"]
        for name, v in (("latitude", lat), ("longitude", lon)):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise bad(f"{name} must be a finite number.")
        if not -90 <= lat <= 90:
            raise bad("latitude must be between -90 and 90.")
        if not -180 <= lon <= 180:
            raise bad("longitude must be between -180 and 180.")
        return float(lat), float(lon)

    def _resolve_via(self, token: Any) -> _Stop:
        """A waypoint may be a port, a passage ID, a position ID or a coordinate object."""
        if isinstance(token, dict):
            lat, lon = self._parse_coordinates(token, "waypoint")
            return _Stop("coordinates", None, None, lat, lon, lat, lon)
        port = self.data.find_port(token)
        if port is not None:
            return self._port_stop(port)
        passage = self.data.find_passage(token)
        if passage is not None:
            return self._passage_stop(passage.passage_id)
        pos = self.data.find_position(token)
        if pos is not None:
            return _Stop("position", pos.position_id, pos.position_name,
                         pos.latitude, pos.longitude, pos.latitude, pos.longitude)
        raise VoyagePlannerError(errors.PORT_NOT_FOUND, f"The supplied waypoint was not found: {token!r}.")

    def _passage_stop(self, passage_id: str) -> _Stop:
        p = self.data.passages[passage_id]
        return _Stop("passage", p.passage_id, p.passage_name, p.latitude, p.longitude,
                     p.latitude, p.longitude)

    # ---- passages ----------------------------------------------------
    def _normalise_passages(self, value: Any, field_name: str, exclusion: bool) -> List[str]:
        """None / '' / ' ' -> []; 'suez' -> ['SUEZ']; lists allowed; validated."""
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        out: List[str] = []
        for item in items:
            if item is None or (isinstance(item, str) and not item.strip()):
                continue
            if not isinstance(item, str):
                raise VoyagePlannerError(errors.INVALID_REQUEST, f"{field_name} must be text or a list of text.")
            passage = self.data.find_passage(item)
            if passage is None:
                valid = ", ".join(self.data.passages)
                raise VoyagePlannerError(errors.INVALID_PASSAGE,
                                         f"Unknown passage '{item}' in {field_name}. Valid passages: {valid}.")
            if exclusion and passage.passage_id not in EXCLUDABLE_PASSAGES:
                raise VoyagePlannerError(
                    errors.INVALID_PASSAGE,
                    f"{passage.passage_id} cannot be excluded. Passages that can be excluded: "
                    f"{', '.join(EXCLUDABLE_PASSAGES)}.")
            if passage.passage_id not in out:
                out.append(passage.passage_id)
        return out

    @staticmethod
    def _echo(ids: List[str]):
        """Single passage -> 'PANAMA' (as in the spec examples); none -> None; many -> list."""
        if not ids:
            return None
        return ids[0] if len(ids) == 1 else list(ids)

    # ======================================================================
    # the actual routing
    # ======================================================================
    def _compute_leg(self, leg: _ParsedLeg) -> _LegOutcome:
        exclude_tags, gates = self._exclusion(leg)

        # required passages become mandatory intermediate points (T18)
        mid = leg.via
        if leg.required:
            mid = self._order_required(leg, exclude_tags, gates)
        chain = [leg.origin] + list(mid) + [leg.destination]

        segments: List[LegResult] = [
            self.backend.shortest_leg(a.route_point, b.route_point, exclude_tags, gates)
            for a, b in zip(chain[:-1], chain[1:])]
        segment_nm = [_jsonable_num(s.distance_nm) for s in segments]
        distance = _jsonable_num(sum(segment_nm))

        # join the polylines (consecutive segments share their snapped node)
        coords: List[List[float]] = []
        for seg in segments:
            pts = [list(c) for c in seg.coordinates]
            if coords and coords[-1] == pts[0]:
                pts = pts[1:]
            coords.extend(pts)

        network_tags = sorted({t for s in segments for t in s.traversed_tags})
        warnings: List[str] = []
        assumptions = self._assumptions(leg, chain)

        # exclusions must really be respected - verify, never trust
        for pid in leg.excluded:
            if pid in PASSAGE_TO_SEAROUTE_TAG and PASSAGE_TO_SEAROUTE_TAG[pid] in network_tags:
                raise RuntimeError(f"Internal error: route uses excluded passage {pid}")
        for gate in gates:
            if gate.crossed_by(coords):
                raise RuntimeError(f"Internal error: route rounds excluded cape {gate.passage_id}")

        # an excluded passage is never reported as used (e.g. a port next to the cape)
        passages_used = [p for p in self._detect_passages(coords, network_tags, leg.required)
                         if p not in leg.excluded]

        # same origin / destination
        if len(chain) == 2 and segments[0].distance_nm == 0:
            warnings.append("Origin and destination resolve to the same network location; distance is 0 nm.")

        # points that are far from the network (distance to the node is NOT counted)
        for i, stop in enumerate(chain):
            snap = segments[0].origin_snap_nm if i == 0 else segments[i - 1].destination_snap_nm
            if snap > SNAP_WARNING_NM:
                label = stop.name or f"{stop.lat:.3f}, {stop.lon:.3f}"
                if stop.kind == "passage":
                    warnings.append(f"Passage point {stop.ident} is {snap:.1f} nm from the nearest routing-network "
                                    "node; the route passes through that node instead.")
                else:
                    pending = (" Its approach point is pending geographic review (T03)."
                               if stop.kind == "port" and self._port_review(stop.ident)["approach_snap_review"]
                               else "")
                    warnings.append(f"{label} is {snap:.1f} nm from the nearest routing-network node; "
                                    f"that access distance is not included in distance_nm.{pending}")

        # compare with the unconstrained route (only meaningful for passage constraints)
        unconstrained: Optional[float] = None
        if (leg.required or leg.excluded) and not leg.via:
            base = self.backend.shortest_leg(leg.origin.route_point, leg.destination.route_point, [], ())
            unconstrained = _jsonable_num(base.distance_nm)
            extra = _jsonable_num(distance - unconstrained)
            pct = (extra / unconstrained * 100) if unconstrained else 0.0
            assumptions.append(
                f"Passage constraints change the distance from {unconstrained:,.1f} nm (unconstrained) "
                f"to {distance:,.1f} nm ({extra:+,.1f} nm, {pct:+.0f}%).")
            if unconstrained and distance > 1.5 * unconstrained:
                warnings.append("The constrained route is more than 50% longer than the unconstrained route; "
                                "check that the passage constraints are intended.")

        if self.backend.version != EXPECTED_SEAROUTE_VERSION:
            warnings.append(f"searoute-py {self.backend.version} is installed; the benchmark baselines were "
                            f"generated with {EXPECTED_SEAROUTE_VERSION}.")

        return _LegOutcome(leg, chain, segments, segment_nm, distance, coords, passages_used,
                           network_tags, unconstrained, warnings, assumptions)

    def _exclusion(self, leg: _ParsedLeg) -> Tuple[List[str], Tuple[Gate, ...]]:
        """Excluded passages -> (searoute edge tags to block, cape gates to block)."""
        tags = [PASSAGE_TO_SEAROUTE_TAG[p] for p in leg.excluded if p in PASSAGE_TO_SEAROUTE_TAG]
        gates = tuple(gate_for(self.data.passages[p]) for p in leg.excluded if p in CAPE_GATE_PASSAGES)
        return tags, gates

    def _order_required(self, leg: _ParsedLeg, exclude_tags: List[str],
                        gates: Tuple[Gate, ...] = ()) -> List[_Stop]:
        """Order the required passages along the voyage (shortest total distance wins)."""
        stops = [self._passage_stop(p) for p in leg.required]
        if len(stops) == 1:
            return stops
        best: Optional[Tuple[float, List[_Stop]]] = None
        for perm in itertools.permutations(stops):          # at most 4! = 24 orders
            chain = [leg.origin] + list(perm) + [leg.destination]
            total = sum(self.backend.shortest_leg(a.route_point, b.route_point, exclude_tags, gates).distance_nm
                        for a, b in zip(chain[:-1], chain[1:]))
            if best is None or total < best[0] - 1e-9:      # ties keep the user's order
                best = (total, list(perm))
        return best[1]  # type: ignore[index]

    def _detect_passages(self, coords: List[List[float]], network_tags: List[str],
                         required: List[str]) -> List[str]:
        """Which of the 6 reference passages does this route use, in travel order?

        * canals / straits that exist as tagged network edges (Panama, Suez,
          Gibraltar, Malacca) are detected from those tags - exact;
        * capes have no tagged edges, so a cape counts as used when the route
          passes within PASSAGE_DETECTION_NM of its reference point - heuristic;
        * required passages are always listed.
        """
        found: List[Tuple[int, str]] = []
        for pid, p in self.data.passages.items():
            d, idx = distance_to_path_nm((p.longitude, p.latitude), coords)
            if pid in PASSAGE_TO_SEAROUTE_TAG:
                hit = PASSAGE_TO_SEAROUTE_TAG[pid] in network_tags
            else:
                hit = d <= PASSAGE_DETECTION_NM
            if hit or pid in required:
                found.append((idx, pid))
        return [pid for _, pid in sorted(found)]

    # ======================================================================
    # response helpers
    # ======================================================================
    def _routing_points(self, oc: _LegOutcome) -> List[Dict[str, Any]]:
        pts = []
        last = len(oc.chain) - 1
        for i, stop in enumerate(oc.chain):
            if i == 0:
                node, snap = oc.segments[0].origin_node, oc.segments[0].origin_snap_nm
                role = "origin"
            else:
                node, snap = oc.segments[i - 1].destination_node, oc.segments[i - 1].destination_snap_nm
                role = ("destination" if i == last else
                        "required_passage" if stop.kind == "passage" and oc.parsed.required else "waypoint")
            pts.append({
                "sequence": i + 1, "role": role, "type": stop.kind,
                "id": stop.ident, "name": stop.name,
                "requested_latitude": stop.route_lat, "requested_longitude": stop.route_lon,
                "network_latitude": node[1], "network_longitude": node[0],
                "snap_distance_nm": _jsonable_num(snap),
            })
        return pts

    def _assumptions(self, leg: _ParsedLeg, chain: List[_Stop]) -> List[str]:
        a = ["Distances are shortest paths on the searoute-py maritime network, in nautical miles.",
             "Each requested point is snapped to the nearest network node; the access distance to that "
             "node is not included in distance_nm.",
             "The Arctic 'northwest' passage is blocked by default (searoute-py default)."]
        kinds = {s.kind for s in chain}
        if "port" in kinds:
            a.append("Port approach points from the Port Reference tab were used as routing coordinates.")
        if "position" in kinds:
            a.append("Vessel positions are synthetic (not real vessel positions).")
        if "coordinates" in kinds:
            a.append("User-supplied coordinates were used as given.")
        seen = set()
        for s in chain:
            if s.kind == "port" and s.ident not in seen:
                seen.add(s.ident)
                note = self._port_review(s.ident)["identity_note"]
                if note:
                    a.append(f"{s.ident} (data review, T02): {note}")
        for pid in leg.required:
            p = self.data.passages[pid]
            a.append(f"Required passage {pid} is enforced by routing via its reference point "
                     f"({p.latitude}, {p.longitude}); the total is the sum of the legs either side of it.")
        for pid in leg.excluded:
            if pid in PASSAGE_TO_SEAROUTE_TAG:
                a.append(f"Excluded passage {pid} is enforced by blocking the searoute network edges tagged "
                         f"'{PASSAGE_TO_SEAROUTE_TAG[pid]}'.")
            else:
                p = self.data.passages[pid]
                a.append(f"Excluded cape {pid} is enforced by blocking every network edge that crosses the "
                         f"meridian {p.longitude} south of latitude {p.latitude} (a route cannot round the cape).")
        if leg.via:
            a.append("User waypoints are visited in the order given; the distance is the sum of the legs.")
        return a

    def _engine_info(self) -> Dict[str, Any]:
        return self.backend.engine_info()

    @staticmethod
    def _leg_key(leg: _ParsedLeg) -> Dict[str, Any]:
        return {"o": leg.origin.key(), "d": leg.destination.key(),
                "via": [s.key() for s in leg.via],
                "req": leg.required, "exc": leg.excluded}

    @staticmethod
    def _stable_id(prefix: str, payload: Dict[str, Any]) -> str:
        """Deterministic id: the same request always yields the same id."""
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:10]
        return f"{prefix}-{digest}"
