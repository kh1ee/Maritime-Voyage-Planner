"""Small spherical-geometry helpers (no external dependencies)."""
from __future__ import annotations

import math
from typing import Sequence, Tuple

from .config import EARTH_RADIUS_NM

LonLat = Tuple[float, float]


def haversine_nm(a: LonLat, b: LonLat) -> float:
    """Great-circle distance in nautical miles between two (lon, lat) points."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(h)))


def _bearing(a: LonLat, b: LonLat) -> float:
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))
    return math.atan2(y, x)


def point_to_segment_nm(p: LonLat, a: LonLat, b: LonLat) -> float:
    """Shortest distance (nm) from point p to the great-circle segment a-b.

    Uses the cross-track formula, falling back to the nearer end point when the
    perpendicular foot lies outside the segment.
    """
    d_ab = haversine_nm(a, b) / EARTH_RADIUS_NM          # angular length
    if d_ab < 1e-12:
        return haversine_nm(p, a)
    d_ap = haversine_nm(a, p) / EARTH_RADIUS_NM
    cross = math.asin(max(-1.0, min(1.0,
            math.sin(d_ap) * math.sin(_bearing(a, p) - _bearing(a, b)))))
    cos_cross = math.cos(cross)
    if abs(cos_cross) < 1e-12:
        return min(haversine_nm(p, a), haversine_nm(p, b))
    along = math.acos(max(-1.0, min(1.0, math.cos(d_ap) / cos_cross)))
    # Negative along-track (foot behind A) shows up as a bearing difference > 90 deg.
    if math.cos(_bearing(a, p) - _bearing(a, b)) < 0 or along > d_ab:
        return min(haversine_nm(p, a), haversine_nm(p, b))
    return abs(cross) * EARTH_RADIUS_NM


def distance_to_path_nm(p: LonLat, path: Sequence[Sequence[float]]) -> Tuple[float, int]:
    """Return (min distance in nm, index of the nearest path segment)."""
    if len(path) == 1:
        return haversine_nm(p, (path[0][0], path[0][1])), 0
    best, best_i = float("inf"), 0
    for i in range(len(path) - 1):
        d = point_to_segment_nm(p, (path[i][0], path[i][1]), (path[i + 1][0], path[i + 1][1]))
        if d < best:
            best, best_i = d, i
    return best, best_i
