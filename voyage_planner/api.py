"""HTTP API for the Voyage Planner (T09), following API_SPECIFICATION.md.

Run:   uvicorn voyage_planner.api:app --reload
Docs:  http://127.0.0.1:8000/docs   (interactive, generated automatically)
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .engine import VoyagePlannerError, calculate_route, calculate_voyage
from .reference_data import load_passages, load_ports
from .schemas import CALCULATION_VERSION, ErrorResponse, RouteRequest, RouteResponse, VoyageRequest, VoyageResponse

app = FastAPI(
    title="Voyage Planner API",
    version=CALCULATION_VERSION,
    description="Academic prototype for maritime distance calculation. Not for navigation.",
)

ERROR_RESPONSES = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                   422: {"model": ErrorResponse}, 501: {"model": ErrorResponse}}


@app.exception_handler(VoyagePlannerError)
def handle_planner_error(_: Request, exc: VoyagePlannerError) -> JSONResponse:
    body = ErrorResponse(error_code=exc.error_code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@app.exception_handler(RequestValidationError)
def handle_bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first["loc"] if p != "body")
    body = ErrorResponse(error_code="INVALID_REQUEST", message=f"{where}: {first['msg']}")
    return JSONResponse(status_code=400, content=body.model_dump())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "calculation_version": CALCULATION_VERSION}


@app.get("/ports")
def list_ports() -> list[dict]:
    """Port list for the user interface drop-down."""
    return [{"port_id": p.port_id, "port_name": p.port_name, "country": p.country,
             "latitude": p.latitude, "longitude": p.longitude, "status": p.status}
            for p in load_ports().values()]


@app.get("/passages")
def list_passages() -> list[dict]:
    """Passage IDs accepted in required_passage / excluded_passage."""
    return [{"passage_id": p.passage_id, "passage_name": p.passage_name, "passage_type": p.passage_type}
            for p in load_passages().values()]


@app.post("/route", response_model=RouteResponse, responses=ERROR_RESPONSES)
def route(request: RouteRequest) -> RouteResponse:
    return calculate_route(request)


@app.post("/voyage", response_model=VoyageResponse, responses=ERROR_RESPONSES)
def voyage(request: VoyageRequest) -> VoyageResponse:
    return calculate_voyage(request)
