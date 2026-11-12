# T16 - How `searoute-py` represents the maritime network (technical findings)

Owner: Member 2 · Evidence: `scripts/t16_network_probe.py` → `results/t16_probe_output.txt`
Library: searoute-py **1.6.0** (the version Cargill used for the benchmark baselines).

## 1. What the network is

* A graph ("Marnet") of **9,708 nodes and 15,970 edges**. Nodes are `(lon, lat)` points on water; edge weights are
  great-circle lengths. A route is the **shortest path (Dijkstra)** through that graph.
* Canals, straits and capes are **not special objects**. Some edges simply carry a text tag in `edge['passage']`.
  A "restriction" is a list of tags whose edges get infinite weight, so the router cannot use them.
* A request is `searoute([lon, lat], [lon, lat])` - **longitude first**. Each coordinate is *snapped* to the nearest
  graph node (k-d tree), the path is found between the two nodes, and that is what gets measured.

## 2. Which passages exist as tagged edges

| Project passage | searoute tag | Edges | Can it be **excluded**? | Evidence |
|---|---|---:|---|---|
| PANAMA | `panama` | 10 | **Yes** | Houston→Tocopilla 3,594 nm → 9,773 nm when blocked, no Panama edge in the path |
| SUEZ | `suez` | 5 | **Yes** | Singapore→Rotterdam 8,368 nm → 11,856 nm, goes round Africa |
| GIBRALTAR | `gibraltar` | 3 | **Yes** | Same detour (the Suez route needs Gibraltar) |
| MALACCA | `malacca` | 1 | **Yes** | Singapore→Rotterdam 8,368 nm → 9,106 nm via the Sunda Strait |
| CAPE_GOOD_HOPE | *(none)* | - | **Yes, via a gate** (see below) | Tag `south_africa` covers only 7 of the edges south of Africa; with it blocked, Rotterdam→Durban is 7,451 nm and still passes 41 nm from the Cape |
| CAPE_HORN | *(none)* | - | **Yes, via a gate** (see below) | Nearest tag `chili` is the Strait of Magellan + Beagle Channel + one Drake Passage edge; blocking it does not mean "avoid Cape Horn" (Houston→Tocopilla with Panama+chili blocked = 19,590 nm, round Africa!) |

Other tags present (not part of the six project passages): `babalmandab`, `bosporus`, `dardanelles`, `ormuz`, `sunda`,
`bering`, `northwest`, plus internal helper tags. `northwest` (Arctic) is blocked by default and we keep that.

**Design consequence.** Capes cannot be excluded by blocking a tag (evidence in the two rows above: blocking
`south_africa` still rounds the Cape; blocking `chili` sends Houston→Tocopilla round Africa). Instead the engine uses a
**gate** (`voyage_planner/gates.py`): the cape's meridian from its reference point south to the pole. Every route that
rounds the cape must cross it, so the engine copies the network, labels every edge crossing the gate (both directions -
searoute stores each edge as two separate records) and blocks that label. Without a cape exclusion the original network
is used unchanged. The Strait of Magellan and Beagle Channel lie north of the Cape Horn point, so they stay open.
Results: Rotterdam→Durban excluding the Cape of Good Hope = 7,943.3 nm via Suez (identical to BM_007); Houston→Tocopilla
excluding Panama and Cape Horn = 9,773.2 nm via Magellan. After every route the engine re-checks that the geometry does
not cross the gate.

## 3. There is no "must pass through X" feature

searoute can only *forbid* tagged edges. To **require** a passage the engine routes
`origin → passage reference point → destination` and adds the two legs. That is exactly how Cargill built the
baselines ("sum of routes through the waypoint"), and it reproduces them to within 0.4 nm.

Side effect: the passage reference point is snapped to the nearest node, which can be some way off
(Cape of Good Hope 29.9 nm - it snaps next to Cape Town; Malacca 36.7 nm). The route goes through that node. The
engine reports the snap distance in `routing_points` and warns above 10 nm (Member 1's T03 review trigger).

## 4. Behaviours that would silently give wrong answers (and how the engine handles them)

| # | searoute behaviour | Risk | Engine response |
|---|---|---|---|
| 1 | If restrictions make the destination unreachable it returns `length = 0` and an **empty geometry**, only a Python `warning` | A 0 nm voyage reported as a success | Detected, raised as `ROUTE_NOT_FOUND` (Port Said→Rotterdam with Gibraltar+Suez blocked) |
| 2 | Start/end are **snapped** to the nearest node and that gap is **not** in the distance | Distances too short for ports far from the network | Snap distance measured for every point, shown in `routing_points`, warning above 10 nm |
| 3 | `searoute()` stores the restriction list on a **global graph object** | Two parallel API requests with different exclusions overwrite each other. Reproduced: with the lock removed, a request excluding Panama returned a route through Panama | All searoute calls are serialised with a lock; the engine also verifies after every call that no excluded tag was crossed |
| 4 | Accepts out-of-range longitudes (e.g. 200°) | Garbage in, garbage out | Coordinates validated first → `INVALID_COORDINATES` |
| 5 | Same start and end node gives a 1-point line | Invalid GeoJSON `LineString` | Point duplicated; warning issued |

## 5. How far are our points from the network?

Every request point is moved to the nearest node. Largest gaps (full list in `results/t16_probe_output.txt`):

| Point | Gap (nm) | Note |
|---|---:|---|
| **Tocopilla (CLTOQ)** | **114.2** | Nearest node is ~2° north (Iquique area). Affects BM_005 and BM_006 |
| Richards Bay (ZARCB) | 51.0 | |
| Malacca passage point | 36.7 | |
| Callao (PECLL) | 32.4 | |
| Cape of Good Hope passage point | 29.9 | |
| POS_001 (BM_009 start) | 124.0 | Synthetic mid-sea position; distance to the network is not counted |

These gaps are **not** inside the reported distances. That matches Cargill's baseline (which the benchmarks were built
with) and the benchmark tolerances (100-300 nm) absorb them, but it should be stated in the validation write-up.

## 6. `append_orig_dest` - why it is `False`

Setting `append_orig_dest=True` adds a straight connector from the original coordinate to the snapped node.
Tested on all 10 benchmarks: `False` reproduces the baseline to within 0.4 nm; `True` adds 2-128 nm (BM_009: 721 → 848).
`False` is searoute's library default and what the baseline states it used (*"searoute-py 1.6.0 using the supplied port
and passage coordinates"*), so it is used here. The choice was made on that basis; it was not tuned per route.
(The straight connector can also cross land, so it is not a trustworthy distance either.)

## 7. Answering the T16 questions

* **How are canals represented?** As short chains of tagged edges (Panama 10, Suez 5). Excludable.
* **Capes?** Not represented - open-ocean edges only. Cape Horn / Good Hope exist only as our own waypoints; they are
  required by routing through the point and excluded with a gate.
* **Straits?** Gibraltar (3 edges) and Malacca (1 edge) are tagged and excludable.
* **What can the router do?** Shortest path avoiding tagged edges. Nothing else: no "required", no ordering.
