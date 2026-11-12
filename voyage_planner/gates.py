"""Cape exclusion by 'gates' (T17 extension).

Problem: the searoute network has no edges tagged for Cape Horn or the Cape of
Good Hope, so there is nothing to block by name (see docs/T16_network_findings.md).

Solution: a cape is a *point where a ship rounds the southern tip of a
continent*.  To forbid rounding it we draw a **gate**: the cape's meridian,
running from the cape's reference point south to the pole.  Any route that goes
from one ocean to the other round that cape must cross this line.  We make a
private copy of the network, tag every edge that crosses the gate with a
unique label, and block that label.  Routes that do not exclude a cape use the
original network and are unaffected.

* Cape Horn gate        : meridian of the Cape Horn reference point, latitudes south of it.
  The Strait of Magellan and Beagle Channel lie north of the point, so they stay open
  (exactly what "avoid Cape Horn" means to a mariner).
* Cape of Good Hope gate: same construction at the Cape of Good Hope reference point.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .config import CAPE_GATE_PASSAGES

LonLat = Tuple[float, float]


def _norm_lon(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def crossing_latitude(a: Sequence[float], b: Sequence[float], meridian: float) -> Optional[float]:
    """Latitude where the great-circle segment a-b crosses ``meridian`` (None if it does not)."""
    lon1, lat1 = _norm_lon(a[0]), a[1]
    lon2, lat2 = _norm_lon(b[0]), b[1]
    m = _norm_lon(meridian)
    if abs(lon1 - lon2) > 180:          # segment wraps round the antimeridian, not our gates
        return None
    d1, d2 = lon1 - m, lon2 - m
    if d1 * d2 > 0:                      # both ends on the same side
        return None
    if d1 == 0 and d2 == 0:
        return min(lat1, lat2)
    if d1 == 0:
        return lat1
    if d2 == 0:
        return lat2
    p1, p2 = math.radians(lat1), math.radians(lat2)
    l1, l2, lm = math.radians(lon1), math.radians(lon2), math.radians(m)
    num = math.sin(p1) * math.cos(p2) * math.sin(lm - l2) - math.sin(p2) * math.cos(p1) * math.sin(lm - l1)
    den = math.cos(p1) * math.cos(p2) * math.sin(l1 - l2)
    return math.degrees(math.atan(num / den)) if den else None


@dataclass(frozen=True)
class Gate:
    """A line along ``meridian`` from ``lat_limit`` southwards to the pole."""
    passage_id: str
    meridian: float
    lat_limit: float

    @property
    def tag(self) -> str:                # label written on the blocked edges
        return f"gate_{self.passage_id.lower()}"

    def blocks_segment(self, a: Sequence[float], b: Sequence[float]) -> bool:
        lat = crossing_latitude(a, b, self.meridian)
        return lat is not None and lat <= self.lat_limit + 1e-9

    def crossed_by(self, path: Sequence[Sequence[float]]) -> bool:
        return any(self.blocks_segment(path[i], path[i + 1]) for i in range(len(path) - 1))


def gate_for(passage) -> Gate:
    """Build the gate for a Passage object (longitude/latitude from the Passage Reference tab)."""
    if passage.passage_id not in CAPE_GATE_PASSAGES:
        raise ValueError(f"{passage.passage_id} has no gate definition")
    return Gate(passage.passage_id, passage.longitude, passage.latitude)


def build_gated_marnet(base, gates: Sequence[Gate]):
    """Deep copy of the searoute network with gate-crossing edges relabelled."""
    graph = copy.deepcopy(base)
    # searoute keeps a separate attribute dict for each direction (u->v and v->u);
    # both must carry the label or the reverse direction would stay open.
    for u, v in list(graph.edges()):
        for gate in gates:
            if gate.blocks_segment(u, v):
                graph[u][v]["passage"] = gate.tag
                graph[v][u]["passage"] = gate.tag
                break
    return graph
