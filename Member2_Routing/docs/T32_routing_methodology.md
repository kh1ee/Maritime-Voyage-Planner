# T32 - Routing methodology (v2, 11 Nov 2026, for review by Members 1 and 3)

Owner: Member 2 · Applies to: calculation_version **0.1.0**, searoute-py **1.6.0**, Python 3.9+.

## 1. Purpose and scope

The engine returns the maritime distance, route geometry, passages used, assumptions and warnings for:
port → port, vessel position → port, and multi-leg itineraries, optionally constrained to **require** or **exclude**
canals/straits/capes. It covers the 29 supplied ports, 6 passage reference points and 6 synthetic positions, and
returns results in the format of `API_SPECIFICATION.md`. It is an academic prototype, not for navigation.

## 2. Pipeline (one request)

```
request (dict)
  1  validate                      version, types, ids, coordinate ranges, passages          -> typed error or continue
  2  resolve locations             port (id / UN/LOCODE / name / alias), position id, or coordinates
  3  plan the leg                  [origin] + [required passages, ordered] or [user waypoints] + [destination]
  4  route each segment            searoute shortest path, excluded passages blocked           (cached, locked)
  5  check                         path exists? no excluded tag crossed? snap distances?
  6  aggregate                     segment distances rounded to 0.1 nm and summed; polylines joined
  7  describe                      passages_used, routing_points, assumptions, warnings, versions, deterministic id
```

## 3. Algorithms and rules

**Shortest path.** searoute runs bidirectional Dijkstra on its 9,708-node ocean graph (edge weight = great-circle km,
converted to nautical miles). The engine does not alter the graph.

**Coordinates.** Everything is `[longitude, latitude]` when talking to searoute and in GeoJSON; the API objects use
`{"latitude", "longitude"}`. Ports are routed from their **approach point** (`approach_latitude/longitude`, currently
equal to the port coordinates), but displayed with their port coordinates.

**Snapping.** searoute moves each endpoint to the nearest graph node. The engine measures that gap and reports it; the gap
is not added to the distance (see §6). A warning is issued when the gap exceeds **10 nm** - Member 1's T03 review trigger, an
analyst's triage choice rather than a course tolerance. Eight of the 29 ports exceed it (§6.2).

**Required passage (T18).** A required passage is a mandatory intermediate point: distance = d(origin→passage point) +
d(passage point→destination). With several required passages (max 4) all orders are tried and the **shortest total** is
kept (ties keep the user's order). Required passages are always listed in `passages_used`.

**Excluded passage (T17).** All six passages can be excluded, by two mechanisms:
* *Canals / straits with tagged edges* (PANAMA, SUEZ, GIBRALTAR, MALACCA): the tag is added to the router's restriction
  list, so those edges cost infinity.
* *Capes* (CAPE_HORN, CAPE_GOOD_HOPE) have no tagged edges, so a **gate** is used: the meridian of the cape's reference
  point from that point south to the pole. In a private copy of the network every edge crossing the gate is relabelled
  and blocked, so no route can round the cape. Magellan / Beagle stay open for Cape Horn. If no cape is excluded the
  original network is used unchanged.

A passage that is both required and excluded is `INVALID_REQUEST`. After every route the engine verifies that no excluded
tag was crossed and the geometry does not cross an excluded gate. An excluded passage is never listed in `passages_used`.

**Route comparison (spec §7, supports T20).** `compare()` takes one origin/destination and 2-6 *options*, each with its own
required/excluded passages. Every option is an ordinary `route()` calculation; the response gives each distance and the
longest-minus-shortest difference. Nothing is read from the benchmark table. The two T20 cases are in
`results/t20_comparisons.md`.

**Multi-leg (T08).** Each leg is routed independently (and may carry its own required/excluded passages);
`total_distance_nm` = sum of the leg distances. A voyage-level `excluded_passage` is a default for all legs.
Waypoints inside one `/route` call are visited in the order given and cannot be combined with `required_passage`
(use `/voyage` legs instead).

**Rounding.** Each segment is rounded to 0.1 nm, a leg is the sum of its rounded segments, a voyage is the sum of its
rounded legs, so displayed numbers always add up exactly.

**passages_used.** Canals/straits (Panama, Suez, Gibraltar, Malacca) come from the tagged edges the path crossed -
exact. Capes have no edges, so a cape counts as used when the path passes within **50 nm** of its reference point -
a heuristic (known false positive: any route ending at Cape Town, 27 nm from the Cape of Good Hope point).

**Determinism.** Same request + same data + same library version ⇒ identical response, including `route_id` /
`voyage_id` (a hash of the normalised request). Results are cached per (origin, destination, restrictions).

## 3b. User-facing exclusion controls (T21/T22, `app.py`)

The app offers one multiselect covering all six passages (2 canals, 2 straits, 2 capes) read from the Passage Reference tab.
The selection becomes `excluded_passage` on every route request in all three modes. A route calculated with an explicit
exclusion is drawn as a thick red line over a yellow halo, the excluded passage points are marked in red, and a legend and
warning box name the exclusions and the passages actually used. In Compare, the restricted route is the highlighted one.
The engine, not the app, decides what is possible: impossible combinations come back as `ROUTE_NOT_FOUND` and are shown as a
message (Port Said → Rotterdam with Gibraltar and Suez excluded).

## 4. Inputs accepted (superset of the specification)

| Field | Form | Notes |
|---|---|---|
| `origin_port_id`, `destination_port_id` | port id, UN/LOCODE, name or alias | case-insensitive |
| `origin_coordinates`, `destination_coordinates` | `{"latitude": n, "longitude": n}` | −90..90, −180..180 |
| `origin_position_id` | `POS_001`… | extension: synthetic positions by id |
| `required_passage`, `excluded_passage` | id, or list of ids; `null`/`""`/`" "` = none | case-insensitive |
| `waypoints` / `intermediate_stops` | list of port / passage / position ids or coordinate objects | |
| `legs` (voyage) | list of route-like objects | per-leg passage fields allowed |
| `calculation_version` | must be `"0.1.0"` if given | otherwise `INVALID_REQUEST` |

## 5. Outputs and error codes

Success responses follow spec §5/§6, plus extra fields: `routing_points` (what was routed, with snapped node and
snap distance), `distance_by_leg_nm`, `required_passage`, `excluded_passage`, `unconstrained_distance_nm`,
`network_passages_traversed`, `routing_engine` (library name/version/network size/config).

| Code | When |
|---|---|
| `PORT_NOT_FOUND` | unknown origin/destination/waypoint |
| `INVALID_COORDINATES` | not an object, missing key, non-number/NaN/bool, out of range |
| `MISSING_ORIGIN` / `MISSING_DESTINATION` | location absent |
| `INVALID_PASSAGE` | unknown passage id |
| `ROUTE_NOT_FOUND` | restrictions leave no path (searoute would return 0 nm silently) |
| `INVALID_REQUEST` | wrong types, id **and** coordinates both given, required = excluded, unsupported version, unknown position id, waypoints + required, empty legs |

## 6. Assumptions and limitations (state these in the report)

1. **Circular baseline.** Benchmarks were produced by searoute-py 1.6.0; passing shows consistency, not accuracy.
   Spot-check with NGA Pub. 151 (Member 1, T13/T26).
2. **Snapping gap not counted; approach points not yet approved.** Member 1's T03 (searoute 1.6.0, 29/29 ports route) finds eight
   ports whose supplied point is >10 nm from the network: Tocopilla 114.2, Richards Bay 51.0, Callao 32.4, Valparaiso 18.8,
   Buenos Aires 17.2, Shanghai 17.2, Suez 15.2, Hong Kong 14.1 nm; POS_001 is 124 nm. The engine warns on each route that uses
   them. The benchmark values match because the baseline ignores the gap too. No land mask, chart or draft check was done, so a
   short snap does not prove an approach is safe; `approach_approved` is false for every port. The earlier statement that all
   ports connect "without snapping errors" is withdrawn.
3. **Coarse network.** Ocean edges are straight great-circle chords between nodes; narrow channels and port approaches
   are generalised. Rotterdam–Hamburg 298 nm should be compared with Pub. 151 (T13).
4. **Cape handling.** Cape exclusion is a model (a meridian gate), not a navigational rule: a port on the far side of a
   cape is reached the long way round (Cape Town→Durban excluding the Cape of Good Hope = 11,794 nm via Suez).
   `passages_used` for capes is proximity-based (50 nm). The first request using a cape exclusion takes ~0.2 s extra to build the gated network copy.
5. **Passage points are waypoints, not transit models.** No canal transit times, tolls, draft/beam limits, piracy or
   weather. Requiring an unrelated passage (e.g. Panama for Singapore→Hong Kong) is allowed and just gives a long route;
   a warning appears when the constrained route is >50% longer.
6. **Order of several required passages** is chosen automatically (shortest total), not by real-world convention.
7. **One engine, one network.** No bunkering/ETA/speed logic (duration is not exposed).
8. **Port identity (Member 1's T02, team decisions of 12 Nov).** 28/29 supplied identifiers are in the UN/LOCODE reference. For the
   three exceptions the team decided: GIIBZ and GIGIB are both accepted for Gibraltar; CNSGH is an alias of CNSHA (the reference
   lists CNSHA as the Shanghai airport record); PAMIT is treated as Manzanillo. These are implemented as lookup aliases and a note
   in the response assumptions. Supplied IDs, names and coordinates are unchanged and benchmarks use them. The UN/LOCODE CSV
   release/date is not recorded (Member 1 to supply).
9. **Exclusion is a model.** Excluding the Cape of Good Hope can push a voyage onto another passage (e.g. Singapore → Rotterdam excluding Suez
   and the Cape = 15,511.1 nm via Panama). Excluding Rotterdam-Durban's Suez makes the voyage *shorter*, because the unconstrained
   route already uses the Cape.

## 7. Validation summary (10 Cargill benchmarks, `results/benchmark_results.md`)

All 10 pass; the largest deviation from the supplied value is 0.4 nm (tolerances 100-300 nm). BM_006 uses the 27 Oct
definition (required CAPE_HORN, excluded PANAMA, 9,973 ±250; engine 9,972.6). BM_009 is a functional test only. Reproduce with
`python3 scripts/run_benchmarks.py`. Test suite: `python3 -m pytest` - 148 tests (117 engine incl. Member 1's review flags and
comparison; 24 that drive the app; 7 from Member 1's validation module; including the known results Singapore → Rotterdam 8,368.2 / 11,856.3 nm with Suez and Panama
excluded and 35°N 40°W → Rotterdam 2,174.9 nm either way). Member 3 owns the independent passage/geometry tests (T19, T27).
What the tests do *not* show: independent accuracy (same-library baseline), the hosted API deployment, or real-browser rendering.

## 8. Reproducibility record

searoute-py 1.6.0 · network 9,708 nodes / 15,970 edges · units nm · default restriction `northwest` ·
`append_orig_dest=False` · workbook `voyage_planner_datasets.xlsx` (27 Oct 2026 copy, identical in both zips) ·
passage points = coordinates in the Passage Reference tab · port points = Port Reference approach coordinates.
