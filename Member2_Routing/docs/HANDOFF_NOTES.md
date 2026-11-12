# Handoff notes from Member 2 (engine + exclusion controls) to the team

Date: 12 Nov 2026 · Engine version 0.1.0 · 10/10 benchmarks pass · 148 automated tests pass (117 engine, 24 app, 7 Member 1's validation tests)

What changed since the 9 Nov version: Member 1's reviewed T02/T03 results are now part of the package
(`member1_review/`, loaded as flags by `data/port_review.json`); `VoyagePlanner.compare()` implements API spec §7;
`app.py` is a Streamlit app with a canal/strait/cape exclusion selector and highlighted exclusion routes.

## To Member 3 (architecture, API, independent tests) - T04, T09, T14, T19, T23

**Calling the engine** (one shared instance, e.g. created at startup):

```python
from voyage_planner import VoyagePlanner
planner = VoyagePlanner()
planner.health()                       # GET /health
planner.handle_route(request_dict)     # POST /route   - never raises for client errors
planner.handle_voyage(request_dict)    # POST /voyage
planner.handle_compare(request_dict)   # NEW: spec section 7 comparison (optional endpoint, see below)
planner.list_ports(); planner.list_passages(); planner.list_positions()   # for dropdowns
```

* `handle_*` return either the success body or the spec error body (`{"status":"error","error_code":...}`).
  Suggested HTTP mapping: `PORT_NOT_FOUND` 404 · `ROUTE_NOT_FOUND` 422 · every other code 400.
* The engine is **thread-safe** (searoute shares global state; the backend serialises calls). Don't bypass `backend.py`.
* Responses are plain JSON-serialisable dicts. `route_id`/`voyage_id`/`comparison_id` are deterministic hashes of the request.
* Extra fields beyond the spec (all additive): `routing_points`, `distance_by_leg_nm`, `required_passage`,
  `excluded_passage`, `unconstrained_distance_nm`, `network_passages_traversed`, `routing_engine`, `location_type`.
* **Comparison (spec §7).** The spec gives a response shape but no endpoint, so none is required. If you want one, wrap
  `handle_compare`: body = a normal route request + `"options": [{"route_name", "required_passage"?, "excluded_passage"?}, ...]`
  (2-6 options). Response = `comparison_id`, `options[]` (each with `distance_nm`, `passages_used`, `route_geometry`),
  `distance_difference_nm` (longest minus shortest), `shortest_option`, `warnings`.
  Errors are the usual spec codes, prefixed with the option number.
* `excluded_passage` accepts a string or a list and works for all six passages (canals, straits, capes) - the app sends
  lists such as `["SUEZ", "CAPE_GOOD_HOPE"]`.
* **Deployment check needed:** I could not reach the hosted Render API from my environment. Please confirm the deployed
  copy runs this version of `voyage_planner/` (cape exclusion, `passages_used`, `unconstrained_distance_nm`).

**Please test independently (T19/T27):** that `passages_used` agrees with the geometry (Suez/Panama from tagged edges,
capes by 50 nm proximity - a heuristic, expect Cape Town false positive); that excluded passages are really absent;
required passages lie on the line; GeoJSON is `[lon, lat]`; line continuity at joins between sub-legs.
Known/intentional behaviours: capes are excluded with a meridian "gate" (test the geometry never crosses it); same-port requests
return 0 nm + warning; an unrecognised `calculation_version` is `INVALID_REQUEST`.

## To Member 4 (UI/maps/exports) - T10, T11, T21, T22, T24

`app.py` (package root) is the team's PR #3 Streamlit app with these changes, so you can diff/merge it:

1. **Exclusion selector (T21).** One multiselect, "Exclude canals, straits and capes", lists all six passages from the
   workbook's Passage Reference tab (Panama, Suez, Gibraltar, Malacca, Cape Horn, Cape of Good Hope). It replaces the old
   four-option dropdown. The selection is sent as `excluded_passage` and applies to Port-to-Port, Multi-Leg and Position-to-Port
   (Calculate and Compare). After a calculation the app lists the passages the route actually uses so the user knows what
   could be excluded.
2. **Highlighted routes (T22).** Any route calculated with an explicit exclusion is drawn as a thick red line on a yellow halo,
   with red markers on the excluded passage points ("EXCLUDED: Suez Canal") and a legend naming them; a warning box above
   the map states the exclusions and the passages actually used. In Compare, the restricted route is the highlighted one, the
   table gains a "Passages used" column, and a note appears if the exclusion did not change the route.
3. **Data warnings.** Engine warnings (e.g. "Tocopilla is 114.2 nm from the nearest routing-network node ... pending
   geographic review (T03)") appear in a "Route notes" expander.
4. Run: `streamlit run app.py`. Default is the hosted API (`VOYAGE_API_URL`, as in PR #3). `VOYAGE_API_URL=local` calls the engine
   in-process (no network; needs the `voyage_planner` folder beside `app.py`) - handy for demos and used by the tests.
5. Route lines start/end at the **network node**, not the port marker (`routing_points[*].snap_distance_nm`).
   Longitudes near the antimeridian can exceed 180 (e.g. 182.8); folium accepts this.
6. Not changed (still as in PR #3): one API call per button press, 30 s timeout per call (a sleeping Render instance can exceed
   it), unused `searoute`/`streamlit-folium` entries in the repo's requirements.txt.

## To Member 1 (data, benchmarks, comparison) - T02, T03, T13, T20, T26, T35

Thank you for the reviewed T02/T03 results - they are integrated, and the earlier "all connect without snapping errors"
conclusion is not used anywhere.

1. **T02.** Supplied IDs, names and coordinates are untouched (a test compares every port row with the workbook). The team
   decisions of 12 Nov are applied as **lookup aliases**, not renames:
   * `GIIBZ` and `GIGIB` are both accepted for Gibraltar (`GIIBZ` stays the project key);
   * `CNSGH` is an alias of `CNSHA` (the UN/LOCODE reference lists CNSHA as the Shanghai airport record; `CNSHA` stays the key);
   * `PAMIT` is treated as Manzanillo: the name/alias `Manzanillo` finds it (the workbook's Colon/Cristobal aliases still work).
   A route using any of these ports carries the decision as a line in `assumptions`, and `planner.list_ports()[i]["data_review"]`
   shows `identity_status: team_decision`, `accepted_aliases` and `known_as`. The workbook is not edited; if the team wants the
   workbook's `port_name` for PAMIT changed to Manzanillo, that is a Member 1 data change.
2. **T03.** The snap-warning threshold is now your 10 nm review trigger (was 25 nm). The eight ports above it (Tocopilla 114.2,
   Richards Bay 51.0, Callao 32.4, Valparaiso 18.8, Buenos Aires 17.2, Shanghai 17.2, Suez 15.2, Hong Kong 14.1) get a warning
   on every route that uses them, and `approach_approved` is false for all 29. A test asserts this list equals your table.
   Regenerate the flags after any re-run: `python3 scripts/build_port_review.py`.
   **Approach-point decision still needed from you and the team:** keep supplied points (what the benchmarks use) or adopt a
   separately versioned set. The engine uses whatever `approach_latitude/longitude` the workbook holds.
3. **T20.** Done in the engine as `compare()`; results from real calculations are in `results/t20_comparisons.md`
   (`python3 scripts/run_comparisons.py`): Houston→Tocopilla via Panama 3,594.3 nm vs via Cape Horn (Panama excluded) 9,972.6 nm,
   difference 6,378.3 nm; Rotterdam→Durban via Suez 7,943.3 nm vs via Cape of Good Hope 7,178.8 nm - the Cape route is
   **shorter** by 764.5 nm in this network (the unconstrained route already goes round the Cape, 7,018.4 nm).
   BM_006 is the updated definition (required CAPE_HORN, excluded PANAMA, 9,973 ±250); the engine gives 9,972.6.
4. **Validation write-up facts**: the baseline reproduces to ≤0.4 nm because it came from the same library; record searoute 1.6.0,
   `append_orig_dest=False`, default restriction `northwest`, and the coordinates in `results/benchmark_results.json`.
   BM_009 start (POS_001) is 124 nm from the network. Your T13 diagnostic (297.672 nm) matches the engine's BM_002 (297.7).
5. Your scripts, tests and results are kept unmodified in `member1_review/`; I re-ran T02, T03, T13 and `test_validation.py`
   against our workbook and they reproduce your results (only file paths and the order of a set-valued passage list differ).
6. T26: run the ten benchmarks against the deployed API once Member 3 confirms the deployment (`scripts/run_benchmarks.py`
   does this in-process today).

## Tracker note

`Voyage_Planner_Task_Tracker_4_Members_updated.xlsx` has Member 2's rows (T05-T08, T16-T18, T32) updated with what was
delivered and tested, and a note on T20/T21/T22. T01/T04 (Member 3) were not available, so the engine was built directly to
`API_SPECIFICATION.md`.
