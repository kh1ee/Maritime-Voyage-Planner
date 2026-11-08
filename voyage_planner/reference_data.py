"""Loads the Port Reference and Passage Reference tabs of voyage_planner_datasets.xlsx.

The workbook path can be changed without editing code by setting the environment
variable VOYAGE_DATA_FILE (for example when Member 1 freezes a cleaned version).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import openpyxl

DEFAULT_WORKBOOK = Path(__file__).resolve().parent.parent / "data" / "voyage_planner_datasets.xlsx"


@dataclass(frozen=True)
class Port:
    port_id: str
    port_name: str
    un_locode: str
    country: str
    latitude: float
    longitude: float
    approach_latitude: float | None
    approach_longitude: float | None
    aliases: tuple[str, ...]
    status: str

    @property
    def routing_point(self) -> tuple[float, float]:
        """(latitude, longitude) used for routing: the approach point when recorded."""
        if self.approach_latitude is not None and self.approach_longitude is not None:
            return self.approach_latitude, self.approach_longitude
        return self.latitude, self.longitude


@dataclass(frozen=True)
class Passage:
    passage_id: str
    passage_name: str
    passage_type: str
    latitude: float
    longitude: float


def _workbook_path() -> Path:
    return Path(os.environ.get("VOYAGE_DATA_FILE", DEFAULT_WORKBOOK))


def _rows(sheet: str) -> list[dict]:
    wb = openpyxl.load_workbook(_workbook_path(), read_only=True, data_only=True)
    rows = list(wb[sheet].iter_rows(values_only=True))
    wb.close()
    header = [str(h).strip() for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if any(v not in (None, "") for v in r)]


def _num(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


@lru_cache(maxsize=1)
def load_ports() -> dict[str, Port]:
    ports = {}
    for r in _rows("Port Reference"):
        p = Port(
            port_id=_text(r["port_id"]).upper(),
            port_name=_text(r["port_name"]),
            un_locode=_text(r.get("un_locode")).upper(),
            country=_text(r.get("country")),
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
            approach_latitude=_num(r.get("approach_latitude")),
            approach_longitude=_num(r.get("approach_longitude")),
            aliases=tuple(a.strip().lower() for a in _text(r.get("aliases")).split("|") if a.strip()),
            status=_text(r.get("status")).lower() or "active",
        )
        ports[p.port_id] = p
    return ports


@lru_cache(maxsize=1)
def load_passages() -> dict[str, Passage]:
    passages = {}
    for r in _rows("Passage Reference"):
        p = Passage(
            passage_id=_text(r["passage_id"]).upper(),
            passage_name=_text(r["passage_name"]),
            passage_type=_text(r.get("passage_type")).lower(),
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
        )
        passages[p.passage_id] = p
    return passages


def find_port(query: str) -> Port | None:
    """Match a port by ID, UN/LOCODE, name or alias (case-insensitive). None if not found."""
    ports = load_ports()
    key = query.strip()
    if key.upper() in ports:
        return ports[key.upper()]
    low = key.lower()
    for p in ports.values():
        if low in (p.port_name.lower(), p.un_locode.lower()) or low in p.aliases:
            return p
    return None
