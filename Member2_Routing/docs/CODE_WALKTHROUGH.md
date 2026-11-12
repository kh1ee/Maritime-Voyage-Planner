# Member 2 - what the code does and why (plain-language walkthrough)

## 1. The project in one paragraph

Cargill wants a **service that returns the sailing distance in nautical miles between ports** - following the sea, not a
straight line - and can be told to **go through** (e.g. Suez) or **avoid** (e.g. Panama) certain passages. The team builds
four layers; data flows left to right:

```
 Member 4: UI + map  ──►  Member 3: API (FastAPI/Flask)  ──►  MEMBER 2: routing engine  ──►  searoute-py (open-source library)
                                                                  ▲
                                           Member 1: validated port data + benchmarks
```

Member 1 cleaned the data (is each port code real? are coordinates on water?). **You (Member 2)** are the engine in the
middle: it turns "Houston to Tocopilla via Panama" into numbers + a line to draw. Member 3 wraps it in HTTP; Member 4 draws it.

## 2. Your tasks (from the tracker) and where each one lives

| Task | What | Where in the code |
|---|---|---|
| T05 | Reusable routing functions | the whole `voyage_planner/` package (`VoyagePlanner` class) |
| T06 | Port-to-port distance | `VoyagePlanner.port_to_port()` → `route()` |
| T07 | Vessel position → port | `VoyagePlanner.position_to_port()`, or `origin_position_id` |
| T08 | Multi-leg + total | `VoyagePlanner.multi_leg()` → `voyage()` |
| T16 | Understand the searoute network | `scripts/t16_network_probe.py`, `docs/T16_network_findings.md` |
| T17 | Exclude passages | `excluded_passage` handling in `_compute_leg()`; capes via `gates.py` |
| T18 | Require passages | `required_passage` handling, `_order_required()` |
| T32 | Routing methodology document | `docs/T32_routing_methodology.md` (draft) |

## 3. How `searoute` works - the one idea you must have

searoute contains a pre-built **map of shipping lanes** as a graph: ~9,700 dots in the sea joined by ~16,000 lines. Asking
for a route means: *snap* your two coordinates to the nearest dots, then find the shortest chain of lines between them.
Consequences that shaped every design decision:

* It does **not** start at your exact coordinate - it starts at the nearest dot. Tocopilla's nearest dot is **114 nm**
  away. That gap is not in the distance. (We measure and report it.)
* It has **no concept of "go through Suez"**. A few lines are *labelled* ("panama", "suez"…) and you may *forbid* labelled
  lines. To force a passage we route A→passage→B ourselves and add the two distances (that is also how Cargill built the
  benchmark answers).
* Capes (Cape Horn, Good Hope) have **no labelled lines at all**. They can be forced like any passage (route through the
  point). To *forbid* one we draw a **gate** - a line down the cape's meridian from the cape to the pole - and block every
  network line that crosses it in a private copy of the map (`gates.py`). A route cannot get from one ocean to the other
  round the cape without crossing that line. Without a cape exclusion the normal map is used.
* If everything is forbidden it quietly returns **0 nm** instead of an error - dangerous, so we catch it.

## 4. File-by-file

| File | Role |
|---|---|
| `voyage_planner/config.py` | All constants/decisions in one place: version `0.1.0`, passage→tag table, thresholds (10 nm snap warning = Member 1's T03 trigger, 50 nm cape detection) |
| `voyage_planner/errors.py` | `VoyagePlannerError` with the 7 spec error codes; `.to_dict()` is the exact JSON error body |
| `voyage_planner/gates.py` | Cape exclusion: builds a "gate" along a cape's meridian and a private network copy with the crossing edges blocked |
| `voyage_planner/geo.py` | Haversine distance and point-to-line distance (used to see if a route passes near a cape) |
| `voyage_planner/data.py` | Reads the Excel workbook. Cleans the oddities (numbers stored as text, `" "` blanks), builds the lookup by id / UN-LOCODE / name / alias (also accepts the team's decided aliases: GIGIB for Gibraltar, CNSGH for Shanghai, Manzanillo for PAMIT), and loads Member 1's T02/T03 review flags from `data/port_review.json` - flags only, supplied IDs and coordinates are never changed |
| `voyage_planner/backend.py` | The **only** file that talks to searoute. Adds: no-path detection, snap measurement, caching, a thread lock, coordinate validation |
| `voyage_planner/engine.py` | The service: parsing/validation, leg planning, required/excluded passages, aggregation, building the response, and `compare()` (spec section 7) |
| `voyage_planner/gates.py` | Cape exclusion: builds a private copy of the network with the lines that round a cape blocked |
| `app.py` | Streamlit app: port-to-port, multi-leg, position-to-port; exclusion selector for all six passages; highlighted exclusion routes |
| `voyage_planner/benchmarks.py` | Turns each benchmark row into a request and compares with Cargill's expected value |
| `scripts/run_benchmarks.py` | Produces `results/benchmark_results.md/json` (evidence for the validation report) |
| `scripts/run_comparisons.py` | T20: Panama vs Cape Horn and Suez vs Cape of Good Hope from real calculations -> `results/t20_comparisons.md` |
| `scripts/build_port_review.py` | Rebuilds `data/port_review.json` from Member 1's results |
| `scripts/demo.py` | Prints example calls; good for rehearsing the midterm/final demo |
| `scripts/t16_network_probe.py` | Re-creates the T16 evidence |
| `tests/test_engine.py` | 117 tests: data, benchmarks, spec shapes, errors, passages, capes, concurrency, Member 1 review flags, comparison |
| `tests/test_ui.py` | 24 tests that click through the real app (AppTest): exclusion selector, highlighting, Calculate then Compare, errors, exports |
| `member1_review/` | Member 1's reviewed T02/T03/T13 scripts, tests and results, kept as supplied |

## 5. Trace of one request

`planner.port_to_port("USHOU", "CLTOQ", required_passage="PANAMA")`

1. **`route()`** → `_check_request` (is it a dict? version OK?).
2. **`_parse_leg`** → `_resolve_endpoint` looks up "USHOU" (Houston 29.73, −95.0) and "CLTOQ" (Tocopilla −22.09, −70.2);
   `_normalise_passages` turns `"PANAMA"` into `["PANAMA"]` and checks it exists.
3. **`_compute_leg`** builds the chain `Houston → Panama Canal point (9.08, −79.68) → Tocopilla`.
4. For each pair it calls **`backend.shortest_leg()`** → searoute. Results: 1,534.6 nm + 2,059.7 nm.
5. Segment distances are rounded and summed → **3,594.3 nm**; the two polylines are joined into one GeoJSON line.
6. Checks & labels: tags crossed = `panama` → `passages_used: ["PANAMA"]`; Tocopilla snaps 114.2 nm → warning;
   unconstrained route computed for comparison (3,594.3 - Panama is already shortest).
7. Response assembled in the spec's shape + `routing_points`, `assumptions`, `warnings`, `calculation_version`, engine info.

Same request with `excluded_passage="PANAMA"` instead: step 4 passes `exclude_tags=["panama"]`, searoute finds the route round
the south of South America (9,773 nm).

## 6. Things you can say confidently in the team

* "All 10 benchmarks pass, max deviation 0.4 nm - but that is expected because Cargill generated them with the same library."
* "Capes can be required (waypoint) or excluded (a meridian gate blocks every line that rounds them); canals are excluded by blocking labelled lines."
* "Tocopilla is 114 nm from the nearest network node, so BM_005/BM_006 distances to Tocopilla may be understated by up to
  roughly that much (only on the access leg; well inside the ±250 nm tolerance)."
* "Member 1's reviewed T03 shows all 29 ports route, but eight start more than 10 nm from the network; the approach points are still unapproved. The engine warns on each of those routes."
* "Any of the six canals, straits and capes can be excluded in the app; the route that honours an exclusion is highlighted red on yellow."

## 7. Run it

```bash
pip install -r requirements.txt           # searoute==1.6.0, openpyxl, pytest (+ streamlit, pandas, folium for the app)
python3 scripts/run_benchmarks.py          # 10/10 table
python3 scripts/demo.py                    # guided tour
python3 -m pytest -q                       # 148 tests (117 engine, 24 app, 7 Member 1)
python3 scripts/run_comparisons.py         # T20 comparisons
streamlit run app.py                       # the app (VOYAGE_API_URL=local runs the engine in-process)
```

```python
from voyage_planner import VoyagePlanner
p = VoyagePlanner()
p.port_to_port("NLRTM", "ZADUR", required_passage="SUEZ")["distance_nm"]      # 7943.3
p.position_to_port(10.0, 114.0, "SGSIN")["distance_nm"]                       # 720.8
p.multi_leg(["SGSIN", "HKHKG", "LKCMB", "ZADUR"])["total_distance_nm"]        # 8271.0
p.handle_route({"origin_port_id": "XX", "destination_port_id": "SGSIN"})      # {'status': 'error', 'error_code': 'PORT_NOT_FOUND', ...}
```

## 8. The app (`app.py`) and the exclusion controls

* **Exclusion selector.** `load_passages()` reads the Passage Reference tab; one multiselect offers all six passages. The chosen
  IDs (sorted, upper-case) go into `excluded_passage` on every request made by `api_route()`. Capes work because the engine
  blocks them with a gate (section 5 of T32); the app needs no special case.
* **Highlighting.** `draw_route()` draws a route with exclusions as a yellow halo under a thick red line; without exclusions it
  is the normal blue line. `add_excluded_markers()` puts red markers on the excluded passage points and
  `add_exclusion_legend()` adds the legend. `show_route_notes()` prints which passages the route really uses and any engine
  warnings (such as the 114 nm Tocopilla snap).
* **Compare Routes** (all modes) calls the engine twice - no exclusions, then your exclusions - and shows both, the difference,
  and a "Passages used" column; the restricted route is the highlighted one.
* **Where results come from.** Default: the hosted API (`VOYAGE_API_URL`, as in PR #3). `VOYAGE_API_URL=local`: the same engine
  in-process. Either way the app only formats what the engine returns; it never calculates a distance itself (other than
  dividing by speed for sailing time).
