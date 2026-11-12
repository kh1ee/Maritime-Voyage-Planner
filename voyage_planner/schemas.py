"""Data contract for the Voyage Planner (T04).

Field names follow the course's API_SPECIFICATION.md exactly, so the user interface,
tests and any future Orchestrator Agent all use the same shapes. Change a field here
only after agreeing it with Member 2 (routing) and Member 4 (user interface).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

CALCULATION_VERSION = "0.2.0"
NOT_FOR_NAVIGATION = "Academic estimate; not for navigation."


# ---------------- Requests ----------------

class Coordinates(BaseModel):
    latitude: float
    longitude: float


class RouteRequest(BaseModel):
    """One route. Origin and destination are each EITHER a port ID OR coordinates."""

    origin_port_id: Optional[str] = None
    origin_coordinates: Optional[Coordinates] = None
    destination_port_id: Optional[str] = None
    destination_coordinates: Optional[Coordinates] = None
    required_passage: Optional[str] = None
    excluded_passage: Optional[str] = None
    waypoints: list[Coordinates] = Field(default_factory=list,
                                         description="Optional points the route must pass through, in order")
    calculation_version: Optional[str] = None


class VoyageRequest(BaseModel):
    """A multi-leg voyage: each leg is a RouteRequest."""

    legs: list[RouteRequest] = Field(..., min_length=1)
    calculation_version: Optional[str] = None


# ---------------- Responses ----------------

class Endpoint(BaseModel):
    port_id: Optional[str]
    port_name: str
    latitude: float
    longitude: float


class RouteResponse(BaseModel):
    route_id: str
    status: Literal["success"] = "success"
    distance_nm: float
    origin: Endpoint
    destination: Endpoint
    routing_points: list[Coordinates]
    passages_used: list[str]
    route_geometry: dict  # GeoJSON LineString, coordinates [longitude, latitude]
    assumptions: list[str]
    warnings: list[str]
    calculation_version: str = CALCULATION_VERSION


class VoyageLeg(BaseModel):
    leg_number: int
    origin_port_id: Optional[str]
    destination_port_id: Optional[str]
    origin: Endpoint
    destination: Endpoint
    distance_nm: float
    passages_used: list[str]
    route_geometry: dict


class VoyageResponse(BaseModel):
    voyage_id: str
    status: Literal["success"] = "success"
    legs: list[VoyageLeg]
    total_distance_nm: float
    assumptions: list[str]
    warnings: list[str]
    calculation_version: str = CALCULATION_VERSION


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error_code: str
    message: str
    warnings: list[str] = Field(default_factory=list)
