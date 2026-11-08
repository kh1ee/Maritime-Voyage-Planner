# Voyage Planner

Maritime distance and route-planning prototype for 40.318 Supply Chain Digitalisation and Design, Project 6. Academic prototype — not for navigation.

## Setup

Requires Python 3.11 or newer. From this folder:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests

```
python -m pytest -q
```

Expected: 116 passed, 4 skipped. The skipped tests need required-passage and cape routing, which is not built yet.

## Run the API

```
uvicorn voyage_planner.api:app --reload
```

Open http://127.0.0.1:8000/docs to try each endpoint in the browser.

Example voyage request for `POST /voyage`:

```json
{"legs": [
  {"origin_port_id": "SGSIN", "destination_port_id": "HKHKG"},
  {"origin_port_id": "HKHKG", "destination_port_id": "LKCMB"},
  {"origin_port_id": "LKCMB", "destination_port_id": "ZADUR"}
]}
```

## Use it from Python

```python
from voyage_planner.engine import calculate_route
from voyage_planner.schemas import RouteRequest

result = calculate_route(RouteRequest(origin_port_id="SGSIN", destination_port_id="NLRTM"))
print(result.distance_nm)
```

## Folders

| Path | Contents |
| --- | --- |
| `voyage_planner/` | Application code: reference data, data contract, routing engine, API |
| `tests/` | Automated tests |
| `data/voyage_planner_datasets.xlsx` | Ports, passages, synthetic positions, benchmark routes |
| `docs/` | Architecture and code review |
| `API_SPECIFICATION.md` | Course API specification |

## Changing the data file

To use a different version of the workbook without editing code:

```
export VOYAGE_DATA_FILE="/path/to/voyage_planner_datasets_v2.xlsx"
```
