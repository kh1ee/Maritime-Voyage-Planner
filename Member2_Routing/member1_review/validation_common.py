"""Shared read-only input handling for Member 1's data checks."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import openpyxl


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_ports(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = iter(book['Port Reference'].values)
        header = next(rows)
        return [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
    finally:
        book.close()


def coordinate_pair(longitude, latitude):
    if isinstance(longitude, bool) or isinstance(latitude, bool):
        raise ValueError('Boolean is not a coordinate')
    lon, lat = float(longitude), float(latitude)
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Coordinates must be finite longitude [-180,180], latitude [-90,90]')
    return [lon, lat]


def distance_nm(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3440.065 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def duplicates(values):
    return sorted(str(v) for v, n in Counter(values).items() if n > 1)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
