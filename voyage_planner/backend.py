"""Thin, safe wrapper around ``searoute-py`` (T05 / T16).

All the knowledge about *how searoute behaves* is concentrated here so the rest
of the engine only sees a clean ``shortest_leg()`` call.  Four behaviours of
searoute 1.6.0 are handled explicitly (details in docs/T16_network_findings.md):

1. **Silent failure** - when restrictions make a destination unreachable,
   searoute returns ``length = 0`` and an empty geometry and only emits a
   Python warning.  We turn that into ``ROUTE_NOT_FOUND`` instead of reporting
   a 0 nm voyage.
2. **Snapping** - searoute does not route from your exact coordinate, it jumps
   to the nearest node of its network.  We measure that jump (``snap_nm``).
3. **Shared global state** - ``searoute()`` stores the restriction list on a
   global graph object, so two threads using different restrictions can
   corrupt each other.  All calls are serialised with a lock.
4. **Loose validation** - searoute accepts longitude 200; we validate first.
"""
from __future__ import annotations

import threading
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from . import errors
from .config import DEFAULT_RESTRICTION_TAGS
from .errors import VoyagePlannerError
from .gates import Gate, build_gated_marnet
from .geo import haversine_nm

try:  # pragma: no cover - import guard
    import searoute as _sr
except ImportError as exc:  # pragma: no cover
    raise ImportError("searoute-py is required: pip install searoute==1.6.0") from exc

LonLat = Tuple[float, float]


@dataclass(frozen=True)
class LegResult:
    """Result of one searoute shortest-path call."""
    distance_nm: float
    coordinates: Tuple[LonLat, ...]      # route polyline, (lon, lat)
    traversed_tags: Tuple[str, ...]      # searoute edge tags crossed (e.g. 'suez')
    origin_node: LonLat                  # network node the origin snapped to
    destination_node: LonLat
    origin_snap_nm: float                # request point -> snapped node
    destination_snap_nm: float


def _installed_version() -> str:
    try:
        from importlib.metadata import version
        return version("searoute")
    except Exception:  # pragma: no cover
        return getattr(_sr, "__version__", "unknown")


class SearouteBackend:
    name = "searoute-py"

    def __init__(self) -> None:
        self.version = _installed_version()
        self._lock = threading.Lock()
        self._graph_info: Optional[Dict[str, int]] = None
        self._gated_graphs: Dict[Tuple[Gate, ...], object] = {}

    # ---- public ------------------------------------------------------
    def shortest_leg(self, origin: LonLat, destination: LonLat,
                     exclude_tags: Sequence[str] = (),
                     gates: Sequence[Gate] = ()) -> LegResult:
        """Shortest sea route between two (lon, lat) points, in nautical miles.

        ``exclude_tags`` are *extra* searoute edge tags to block, on top of the
        default restrictions.  ``gates`` are cape gates (see gates.py): edges
        crossing them are blocked in a private copy of the network.  The call is cached: identical inputs always
        return the identical object (determinism + speed).
        """
        for lon, lat in (origin, destination):
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise VoyagePlannerError(errors.INVALID_COORDINATES,
                                         f"Coordinates out of range: lat={lat}, lon={lon}.")
        gates = tuple(sorted(set(gates), key=lambda g: g.passage_id))
        tags = tuple(sorted(set(DEFAULT_RESTRICTION_TAGS) | set(exclude_tags) | {g.tag for g in gates}))
        return self._cached_leg((float(origin[0]), float(origin[1])),
                                (float(destination[0]), float(destination[1])), tags, gates)

    def engine_info(self) -> Dict[str, object]:
        """Version + configuration to store with every result (brief requirement)."""
        info: Dict[str, object] = {
            "name": self.name,
            "version": self.version,
            "units": "nautical miles",
            "default_restrictions": list(DEFAULT_RESTRICTION_TAGS),
            "append_orig_dest": False,
        }
        info.update(self._network_size())
        return info

    # ---- internals ---------------------------------------------------
    @lru_cache(maxsize=8192)
    def _cached_leg(self, origin: LonLat, destination: LonLat,
                    tags: Tuple[str, ...], gates: Tuple[Gate, ...] = ()) -> LegResult:
        with self._lock:                                   # (3) global state
            network = self._gated_network(gates) if gates else None
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    feature = _sr.searoute(
                        list(origin), list(destination), units="naut",
                        append_orig_dest=False,            # baseline behaviour
                        restrictions=list(tags), return_passages=True,
                        M=network)                         # None = searoute's own network
                except ValueError as exc:
                    raise VoyagePlannerError(errors.INVALID_COORDINATES, str(exc))
        coords = [tuple(c) for c in feature["geometry"]["coordinates"]]
        if not coords:                                     # (1) silent failure
            reason = "; ".join(str(w.message) for w in caught) or "no path in network"
            raise VoyagePlannerError(
                errors.ROUTE_NOT_FOUND,
                "No sea route exists between the requested points with the "
                f"current passage restrictions ({reason}).")
        if len(coords) == 1:                               # same node: make a valid LineString
            coords = coords * 2
        props = feature["properties"]
        return LegResult(
            distance_nm=float(props["length"]),
            coordinates=tuple((c[0], c[1]) for c in coords),
            traversed_tags=tuple(sorted(props.get("traversed_passages") or [])),
            origin_node=(coords[0][0], coords[0][1]),
            destination_node=(coords[-1][0], coords[-1][1]),
            origin_snap_nm=haversine_nm(origin, (coords[0][0], coords[0][1])),   # (2) snapping
            destination_snap_nm=haversine_nm(destination, (coords[-1][0], coords[-1][1])),
        )

    def _gated_network(self, gates: Tuple[Gate, ...]):
        """Private network copy with the gates blocked (built once per gate set)."""
        if gates not in self._gated_graphs:
            from searoute.searoute import get_graphs
            base, _ = get_graphs(None, None, "networkx")
            self._gated_graphs[gates] = build_gated_marnet(base, gates)
        return self._gated_graphs[gates]

    def _network_size(self) -> Dict[str, int]:
        if self._graph_info is None:
            try:
                from searoute.searoute import get_graphs
                marnet, _ = get_graphs(None, None, "networkx")
                self._graph_info = {"network_nodes": marnet.number_of_nodes(),
                                    "network_edges": marnet.number_of_edges()}
            except Exception:  # internal API - never let it break a request
                self._graph_info = {}
        return self._graph_info
