"""HTTP API for the Voyage Planner (T09 / T23, Member 3).

A thin FastAPI layer over Member 2's routing engine (``VoyagePlanner``).
All routing, validation and error decisions are made by the engine; this
module only maps them onto HTTP. See docs/HANDOFF_NOTES.md for the contract.

Run (from the repository root):
    uvicorn voyage_planner.api:app --reload
Docs:
    http://127.0.0.1:8000/docs   (interactive, generated automatically)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Dict, List

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import errors
from .config import CALCULATION_VERSION
from .engine import VoyagePlanner

@asynccontextmanager
async def _lifespan(_: FastAPI):
    get_planner()          # load the workbook and routing network once, at startup
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="Voyage Planner API",
    version=CALCULATION_VERSION,
    description=(
        "Maritime distance and route-planning service (Project 6). "
        "Academic prototype built on searoute-py; not for navigation."
    ),
)

# Engine error code -> HTTP status (mapping suggested in docs/HANDOFF_NOTES.md).
# Any code not listed here is a client error -> 400.
HTTP_STATUS = {
    errors.PORT_NOT_FOUND: 404,
    errors.ROUTE_NOT_FOUND: 422,
}


class ErrorResponse(BaseModel):
    """Error body defined in API_SPECIFICATION.md section 8."""
    status: str = "error"
    error_code: str
    message: str
    warnings: List[str] = []


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid request (bad input, passage or version)"},
    404: {"model": ErrorResponse, "description": "PORT_NOT_FOUND"},
    422: {"model": ErrorResponse, "description": "ROUTE_NOT_FOUND"},
}


@lru_cache(maxsize=1)
def get_planner() -> VoyagePlanner:
    """One shared engine instance (it is thread-safe; loading it reads the workbook)."""
    return VoyagePlanner()


def _respond(result: Dict[str, Any]) -> JSONResponse:
    """Turn an engine result dict into a JSON response with the right HTTP status."""
    if result.get("status") == "error":
        return JSONResponse(status_code=HTTP_STATUS.get(result.get("error_code"), 400), content=result)
    return JSONResponse(status_code=200, content=result)


@app.exception_handler(RequestValidationError)
def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Malformed JSON or a non-object body -> spec error body, not FastAPI's default 422."""
    first = exc.errors()[0] if exc.errors() else {"loc": (), "msg": "Invalid request body"}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = f"{where}: {first['msg']}" if where else first["msg"]
    body = ErrorResponse(error_code=errors.INVALID_REQUEST, message=message)
    return JSONResponse(status_code=400, content=body.model_dump())


# ---------------------------------------------------------------- lookups
@app.get("/health", tags=["service"])
def health() -> Dict[str, str]:
    return get_planner().health()


@app.get("/ports", tags=["reference data"])
def list_ports() -> List[Dict[str, Any]]:
    """Ports accepted as origin/destination (by port_id, UN/LOCODE, name or alias)."""
    return get_planner().list_ports()


@app.get("/passages", tags=["reference data"])
def list_passages() -> List[Dict[str, Any]]:
    """Passage IDs accepted in required_passage / excluded_passage."""
    return get_planner().list_passages()


@app.get("/positions", tags=["reference data"])
def list_positions() -> List[Dict[str, Any]]:
    """Synthetic vessel positions (usable as origin_position_id)."""
    return get_planner().list_positions()


# ---------------------------------------------------------------- calculations
ROUTE_EXAMPLES = {
    "port_to_port": {
        "summary": "Port to port",
        "value": {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                  "calculation_version": CALCULATION_VERSION},
    },
    "position_to_port": {
        "summary": "Vessel position to port",
        "value": {"origin_coordinates": {"latitude": 35.0, "longitude": -40.0},
                  "destination_port_id": "NLRTM", "calculation_version": CALCULATION_VERSION},
    },
    "required_passage": {
        "summary": "Required passage (via Panama)",
        "value": {"origin_port_id": "USHOU", "destination_port_id": "CLTOQ",
                  "required_passage": "PANAMA", "calculation_version": CALCULATION_VERSION},
    },
    "excluded_passage": {
        "summary": "Excluded passage (avoid Suez)",
        "value": {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                  "excluded_passage": ["SUEZ"], "calculation_version": CALCULATION_VERSION},
    },
}

VOYAGE_EXAMPLES = {
    "legs": {
        "summary": "Multi-leg with per-leg passages (brief example)",
        "value": {
            "calculation_version": CALCULATION_VERSION,
            "legs": [
                {"origin_port_id": "USHOU", "destination_port_id": "CLTOQ", "required_passage": "PANAMA"},
                {"origin_port_id": "CLTOQ", "destination_port_id": "ZADUR", "required_passage": "CAPE_HORN"},
            ],
        },
    },
    "intermediate_stops": {
        "summary": "Origin, intermediate stops and destination",
        "value": {"origin_position_id": "POS_001", "intermediate_stops": ["SGSIN"],
                  "destination_port_id": "ZADUR", "calculation_version": CALCULATION_VERSION},
    },
}


COMPARE_EXAMPLES = {
    "panama_vs_cape_horn": {
        "summary": "Via Panama vs via Cape Horn (T20)",
        "value": {
            "origin_port_id": "USHOU", "destination_port_id": "CLTOQ",
            "calculation_version": CALCULATION_VERSION,
            "options": [
                {"route_name": "Via Panama Canal", "required_passage": "PANAMA"},
                {"route_name": "Via Cape Horn", "required_passage": "CAPE_HORN", "excluded_passage": "PANAMA"},
            ],
        },
    },
    "suez_vs_cape_good_hope": {
        "summary": "Via Suez vs via Cape of Good Hope (T20)",
        "value": {
            "origin_port_id": "NLRTM", "destination_port_id": "ZADUR",
            "calculation_version": CALCULATION_VERSION,
            "options": [
                {"route_name": "Via Suez Canal", "required_passage": "SUEZ"},
                {"route_name": "Via Cape of Good Hope", "required_passage": "CAPE_GOOD_HOPE",
                 "excluded_passage": "SUEZ"},
            ],
        },
    },
}


@app.post("/route", tags=["calculations"], responses=ERROR_RESPONSES)
def route(request: Dict[str, Any] = Body(..., openapi_examples=ROUTE_EXAMPLES)) -> JSONResponse:
    """Single route: port or position to port, with optional required/excluded passages."""
    return _respond(get_planner().handle_route(request))


@app.post("/voyage", tags=["calculations"], responses=ERROR_RESPONSES)
def voyage(request: Dict[str, Any] = Body(..., openapi_examples=VOYAGE_EXAMPLES)) -> JSONResponse:
    """Multi-leg voyage: distance per leg plus total distance."""
    return _respond(get_planner().handle_voyage(request))


@app.post("/compare", tags=["calculations"], responses=ERROR_RESPONSES)
def compare(request: Dict[str, Any] = Body(..., openapi_examples=COMPARE_EXAMPLES)) -> JSONResponse:
    """Route comparison (API spec section 7): one origin/destination, 2-6 passage options.

    Each option has a ``route_name`` and optional ``required_passage`` / ``excluded_passage``.
    Returns every option's distance, passages and geometry, plus ``distance_difference_nm``
    (longest minus shortest) and ``shortest_option``.
    """
    return _respond(get_planner().handle_compare(request))
