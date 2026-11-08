# T01 Code Review — Voyage Planner Codebase

**Owner:** Member 3  **Date:** 28 Oct 2026

## 1. Summary

The original prototype scripts (the `analysis/` folder) were lost and could not be recovered, so they could not be audited. The project has been rebuilt as a structured Python package, `voyage_planner`, that separates reference data, the data contract, the routing engine and the API. This review covers that rebuilt codebase.

The rebuilt code reproduces the earlier prototype results. For example, Singapore → Hong Kong → Colombo → Durban gives 8,270.94 nautical miles, the same as before. All 116 automated tests pass. Four canal and cape scenarios are skipped because required-passage and cape routing are not built yet.

## 2. What happened to the original prototype

| Item | Status |
| --- | --- |
| `analysis/` scripts 01–07, `common.py`, `run_all.py`, `pitch_summary.py` | Lost; not available for review |
| `outputs/` tables, charts, maps | Lost; can be regenerated from the new code |
| `searoute-mcp/` | Lost; not needed for current tasks |
| `voyage_planner_datasets.xlsx`, `API_SPECIFICATION.md`, `DATASET_USAGE_README.md`, `PROJECT_SYNOPSIS_README.md` | Re-downloaded from course materials |

Earlier prototype figures quoted in team documents (for example the geodesic comparison) should be regenerated with the new code before being reused.

## 3. Codebase structure

| File | What it does | Owner |
| --- | --- | --- |
| `voyage_planner/reference_data.py` | Reads Port Reference and Passage Reference from the workbook; finds ports by ID, name, UN/LOCODE or alias | Member 3 (loader), Member 1 (data) |
| `voyage_planner/schemas.py` | Request and response models matching `API_SPECIFICATION.md` | Member 3 |
| `voyage_planner/engine.py` | `calculate_route` and `calculate_voyage`; validation and structured errors | Member 2 |
| `voyage_planner/api.py` | FastAPI endpoints `/health`, `/route`, `/voyage`, `/ports`, `/passages` | Member 3 |
| `tests/` | 116 automated tests | Member 3 |

## 4. Feature coverage against the brief

| Requirement | Status | Evidence |
| --- | --- | --- |
| Port-to-port distance | Working | `calculate_route`; BM_001–BM_004 |
| Vessel position to port | Working | Coordinate origin; BM_009 |
| Multi-leg itinerary | Working | `calculate_voyage`; BM_010 |
| User-specified waypoints | Working | `waypoints` field; `test_waypoint_route_is_not_shorter_than_direct` |
| Route geometry for map | Working | GeoJSON LineString, longitude first |
| Structured errors (all 7 required codes) | Working | `test_api.py` |
| Callable API | Working | `/route`, `/voyage` |
| Excluded passages (Panama, Suez, Gibraltar, Malacca) | Working | `excluded_passage`; tests in `test_engine.py` |
| Required passages; excluding capes | Missing | Refused with `PASSAGE_NOT_SUPPORTED`; tasks T18–T19 |
| Alternative route comparison | Missing | Planned `/compare`; tasks T20, T23 |
| User interface | Missing | Tasks T10–T12 (Member 4) |
| Results export | Missing | Task T24 |
| Independent benchmark validation | Missing | Tasks T13, T26 (Member 1) |

## 5. Reproduction of supplied benchmark baselines

The workbook labels all expected distances as model-derived baselines (searoute-py 1.6.0), not independent references. These results show the code reproduces them; they are **not** evidence of real-world accuracy.

| Benchmark | Route | Calculated (nautical miles) | Baseline | Difference | Tolerance | Result |
| --- | --- | --- | --- | --- | --- | --- |
| BM_001 | Singapore to Hong Kong | 1,438.77 | 1,439 | −0.23 | ±100 | Pass |
| BM_002 | Rotterdam to Hamburg | 297.67 | 298 | −0.33 | ±100 | Pass |
| BM_003 | Singapore to Rotterdam | 8,368.16 | 8,368 | +0.16 | ±250 | Pass |
| BM_004 | Houston to Rotterdam | 5,041.16 | 5,041 | +0.16 | ±250 | Pass |
| BM_005 | Houston to Tocopilla via Panama | — | 3,594 | — | ±250 | Not run (needs passage logic) |
| BM_006 | Houston to Tocopilla via Cape Horn | — | 9,973 | — | ±250 | Not run (needs passage logic) |
| BM_007 | Rotterdam to Durban via Suez | — | 7,943 | — | ±250 | Not run (needs passage logic) |
| BM_008 | Rotterdam to Durban via Cape of Good Hope | — | 7,179 | — | ±250 | Not run (needs passage logic) |
| BM_009 | Synthetic position POS_001 to Singapore | 720.82 | 721 | −0.18 | ±150 | Pass |
| BM_010 | Singapore → Hong Kong → Colombo → Durban | 8,270.94 | 8,271 | −0.06 | ±300 | Pass |

## 6. Issues found

| Issue | Impact | Recommendation | For |
| --- | --- | --- | --- |
| Original scripts lost | No audit trail of earlier results | Put the project on GitHub so it is never held on one laptop | Whole team |
| Blocking Panama does not force Cape Horn: searoute routes Houston → Tocopilla through the `chili` passage (9,773.24 nautical miles) | BM_006 cannot be reproduced by exclusion alone | Investigate a Cape Horn waypoint plus a geometry check | Member 2 |
| Endpoints snap to the nearest network point | Small distance differences at each end | Decide whether to warn above a threshold | Members 1 and 2 |
| Approach coordinates equal port coordinates for all 29 ports | Approach points have not been refined | Review approach points, especially river ports (Hamburg, Antwerp, Buenos Aires) | Member 1 |
| Only model-derived baselines available | No independent accuracy evidence yet | Collect published distances (for example NGA Publication 151) | Member 1 |

All 29 ports load, have coordinates in range, have a port ID equal to their UN/LOCODE, and connect to the sea network. These checks are automated in `tests/test_reference_data.py`.

## 7. Handoffs

- **To Member 2 (T05–T08):** `engine.py` is working and tested; take ownership and keep the function names. First priority: passage enforcement, starting from issue 2 above.
- **To Member 4 (T10–T12):** use `GET /ports` for the drop-down and `POST /voyage` for itineraries. Geometry is ready to draw on a map. Full contract in `docs/ARCHITECTURE.md`.
- **To Member 1 (T02, T13):** port data loads correctly. Approach points and independent benchmarks are the open items.
