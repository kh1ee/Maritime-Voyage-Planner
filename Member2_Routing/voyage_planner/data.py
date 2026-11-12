"""Reference-data loader (feeds T05 / T06 / T07 / T08).

Reads the four tabs of ``voyage_planner_datasets.xlsx`` that the engine needs
and turns them into small immutable objects.

Why this module exists
----------------------
* The workbook stores every number as *text* ("1.2644"), and blank cells are
  sometimes a single space (" ").  Everything is normalised here so the rest of
  the code never has to think about it.
* The workbook is the single source of truth.  Nothing in it is changed.
  Member 1's T02/T03 findings (identity exceptions, approach-point snap review)
  are loaded from ``data/port_review.json`` as *flags and team-decided aliases*
  (``ReferenceData.port_review``); supplied IDs and coordinates stay intact.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import openpyxl

DEFAULT_WORKBOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "voyage_planner_datasets.xlsx")

DEFAULT_REVIEW = os.path.join(os.path.dirname(DEFAULT_WORKBOOK), "port_review.json")

def _clean(value) -> Optional[str]:
    """Blank / whitespace / NaN -> None, otherwise a stripped string."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _num(value, what: str) -> float:
    text = _clean(value)
    if text is None:
        raise ValueError(f"Missing numeric value for {what}")
    return float(text)


@dataclass(frozen=True)
class Port:
    port_id: str
    port_name: str
    un_locode: str
    country: str
    latitude: float            # port coordinates (shown to the user)
    longitude: float
    approach_latitude: float   # point actually sent to the router
    approach_longitude: float
    aliases: Tuple[str, ...]
    status: str
    notes: Optional[str] = None


@dataclass(frozen=True)
class Passage:
    passage_id: str
    passage_name: str
    passage_type: str          # canal | cape | strait
    latitude: float
    longitude: float
    description: str = ""


@dataclass(frozen=True)
class Position:
    position_id: str
    position_name: str
    latitude: float
    longitude: float
    scenario: str = ""


@dataclass(frozen=True)
class Benchmark:
    benchmark_id: str
    route_name: str
    origin_type: str           # port | synthetic
    origin_id: str
    destination_type: str
    destination_id: str
    intermediate_stops: Tuple[str, ...]
    required_passage: Optional[str]
    excluded_passage: Optional[str]
    route_category: str
    expected_distance_nm: float
    acceptable_tolerance_nm: float
    notes: str = ""


@dataclass
class ReferenceData:
    ports: Dict[str, Port] = field(default_factory=dict)
    passages: Dict[str, Passage] = field(default_factory=dict)
    positions: Dict[str, Position] = field(default_factory=dict)
    benchmarks: List[Benchmark] = field(default_factory=list)
    data_notes: List[str] = field(default_factory=list)
    port_review: Dict[str, dict] = field(default_factory=dict)   # Member 1 T02/T03 flags
    review_meta: Dict[str, object] = field(default_factory=dict)
    source_path: str = ""
    _port_index: Dict[str, str] = field(default_factory=dict, repr=False)

    # ---- lookups -----------------------------------------------------
    def find_port(self, key) -> Optional[Port]:
        """Find a port by port_id, UN/LOCODE, name or alias (case-insensitive)."""
        text = _clean(key)
        if text is None:
            return None
        pid = self._port_index.get(text.lower())
        return self.ports[pid] if pid else None

    def find_passage(self, key) -> Optional[Passage]:
        text = _clean(key)
        return self.passages.get(text.upper().replace(" ", "_")) if text else None

    def find_position(self, key) -> Optional[Position]:
        text = _clean(key)
        return self.positions.get(text.upper()) if text else None


def _read_sheet(wb, name: str) -> List[Dict[str, object]]:
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h).strip() for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if any(c is not None for c in r)]


def _check_range(lat: float, lon: float, what: str) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"{what}: coordinates out of range ({lat}, {lon})")


def _load_review(ref: "ReferenceData", review_path: Optional[str]) -> None:
    """Load Member 1's T02/T03 review flags (optional file; absent -> no flags)."""
    review_path = review_path or os.environ.get("VOYAGE_PLANNER_REVIEW") or DEFAULT_REVIEW
    if not os.path.exists(review_path):
        ref.data_notes.append("port_review.json not found: no T02/T03 review flags loaded.")
        return
    with open(review_path) as f:
        doc = json.load(f)
    ref.port_review = doc.get("ports", {})
    ref.review_meta = {k: doc.get(k) for k in ("source", "snap_review_trigger_nm", "snap_review_trigger_basis",
                                                "searoute_version", "limitations")}


def load_reference_data(path: Optional[str] = None, review_path: Optional[str] = None) -> ReferenceData:
    """Load and validate the workbook.  ``path`` defaults to data/ in this repo
    (override with the VOYAGE_PLANNER_DATA environment variable)."""
    path = path or os.environ.get("VOYAGE_PLANNER_DATA") or DEFAULT_WORKBOOK
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ref = ReferenceData(source_path=os.path.abspath(path))
    _load_review(ref, review_path)

    # ---- ports -------------------------------------------------------
    for r in _read_sheet(wb, "Port Reference"):
        pid = _clean(r["port_id"])
        locode = _clean(r["un_locode"]) or pid
        lat, lon = _num(r["latitude"], f"{pid}.latitude"), _num(r["longitude"], f"{pid}.longitude")
        a_lat = _clean(r.get("approach_latitude"))
        a_lon = _clean(r.get("approach_longitude"))
        _check_range(lat, lon, pid)
        if a_lat is None or a_lon is None:
            a_lat, a_lon = lat, lon
            ref.data_notes.append(f"{pid}: no approach point supplied, port coordinates used.")
        else:
            a_lat, a_lon = float(a_lat), float(a_lon)
            _check_range(a_lat, a_lon, f"{pid} approach")
        aliases = tuple(a.strip() for a in (_clean(r.get("aliases")) or "").split("|") if a.strip())
        ref.ports[pid] = Port(
            port_id=pid, port_name=_clean(r["port_name"]), un_locode=locode,
            country=_clean(r.get("country")) or "", latitude=lat, longitude=lon,
            approach_latitude=a_lat, approach_longitude=a_lon, aliases=aliases,
            status=_clean(r.get("status")) or "", notes=_clean(r.get("notes")))

    # lookup index: id, corrected + original UN/LOCODE, name, aliases
    for pid, p in ref.ports.items():
        keys = {pid, p.un_locode, p.port_name, *p.aliases}
        accepted = ((ref.port_review.get(pid) or {}).get("identity_review") or {}).get("accepted_aliases") or []
        keys.update(accepted)       # team decisions (T02): GIGIB -> GIIBZ, CNSGH -> CNSHA, Manzanillo -> PAMIT
        for k in keys:
            k = k.lower()
            if k in ref._port_index and ref._port_index[k] != pid:
                raise ValueError(f"Ambiguous port key '{k}' ({ref._port_index[k]} vs {pid})")
            ref._port_index[k] = pid

    # ---- passages ----------------------------------------------------
    for r in _read_sheet(wb, "Passage Reference"):
        pid = _clean(r["passage_id"]).upper()
        lat, lon = _num(r["latitude"], pid), _num(r["longitude"], pid)
        _check_range(lat, lon, pid)
        ref.passages[pid] = Passage(pid, _clean(r["passage_name"]), _clean(r["passage_type"]),
                                    lat, lon, _clean(r.get("description")) or "")

    # ---- synthetic positions ----------------------------------------
    for r in _read_sheet(wb, "Synthetic Positions"):
        pid = _clean(r["position_id"]).upper()
        lat, lon = _num(r["latitude"], pid), _num(r["longitude"], pid)
        _check_range(lat, lon, pid)
        ref.positions[pid] = Position(pid, _clean(r["position_name"]), lat, lon,
                                      _clean(r.get("scenario")) or "")

    # ---- benchmarks --------------------------------------------------
    for r in _read_sheet(wb, "Benchmark Routes"):
        stops = _clean(r.get("intermediate_stops"))
        ref.benchmarks.append(Benchmark(
            benchmark_id=_clean(r["benchmark_id"]), route_name=_clean(r["route_name"]),
            origin_type=_clean(r["origin_type"]), origin_id=_clean(r["origin_id"]),
            destination_type=_clean(r["destination_type"]), destination_id=_clean(r["destination_id"]),
            intermediate_stops=tuple(s.strip() for s in stops.split("|")) if stops else (),
            required_passage=(_clean(r.get("required_passage")) or None),
            excluded_passage=(_clean(r.get("excluded_passage")) or None),
            route_category=_clean(r["route_category"]),
            expected_distance_nm=_num(r["expected_distance_nm"], "expected"),
            acceptable_tolerance_nm=_num(r["acceptable_tolerance_nm"], "tolerance"),
            notes=_clean(r.get("notes")) or ""))
    wb.close()
    return ref
