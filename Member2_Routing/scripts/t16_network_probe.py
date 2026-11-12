"""T16 - evidence behind docs/T16_network_findings.md.

    python3 scripts/t16_network_probe.py  > results/t16_probe_output.txt

Prints facts about the searoute-py network that drive the engine's design:
passage-tagged edges, how far every port / passage point is from the nearest
network node, how exclusions behave, and what happens when no route exists.
"""
import collections
import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import searoute as sr                                         # noqa: E402
from searoute.searoute import get_graphs                       # noqa: E402

from voyage_planner import VoyagePlanner                       # noqa: E402
from voyage_planner.backend import SearouteBackend             # noqa: E402
from voyage_planner.geo import haversine_nm                    # noqa: E402

planner = VoyagePlanner()
M, _ = get_graphs(None, None, "networkx")
backend = SearouteBackend()

print("== 1. Network size and passage-tagged edges ==")
print(f"searoute-py {backend.version}: {M.number_of_nodes()} nodes, {M.number_of_edges()} edges")
tags = collections.Counter(d.get("passage") for _, _, d in M.edges(data=True) if d.get("passage"))
for tag, n in sorted(tags.items()):
    print(f"  edge tag {tag:<14} {n:>3} edges")

print("\n== 2. Distance from each requested point to the nearest network node (nm) ==")
print("(searoute silently starts/ends the route at that node; the distance is NOT in the result)")
rows = []
for p in planner.data.ports.values():
    node = M.kdtree.query([p.approach_longitude, p.approach_latitude])
    rows.append((haversine_nm((p.approach_longitude, p.approach_latitude), tuple(node)), "port", p.port_id, p.port_name))
for p in planner.data.passages.values():
    node = M.kdtree.query([p.longitude, p.latitude])
    rows.append((haversine_nm((p.longitude, p.latitude), tuple(node)), "passage", p.passage_id, p.passage_name))
for d, kind, ident, name in sorted(rows, reverse=True):
    flag = "  <-- above 25 nm warning threshold" if d > 25 else ""
    print(f"  {d:6.1f}  {kind:<8} {ident:<15} {name}{flag}")

print("\n== 3. Effect of blocking one tag (nautical miles) ==")
def dist(o, d, ex=()):
    a, b = planner.data.ports[o], planner.data.ports[d]
    r = backend.shortest_leg((a.approach_longitude, a.approach_latitude), (b.approach_longitude, b.approach_latitude), ex)
    return r.distance_nm, r.traversed_tags
cases = [("NLRTM", "ZADUR", ()), ("NLRTM", "ZADUR", ("suez",)), ("NLRTM", "ZADUR", ("south_africa",)),
         ("USHOU", "CLTOQ", ()), ("USHOU", "CLTOQ", ("panama",)), ("USHOU", "CLTOQ", ("panama", "chili")),
         ("SGSIN", "NLRTM", ()), ("SGSIN", "NLRTM", ("suez",)), ("SGSIN", "NLRTM", ("malacca",)),
         ("SGSIN", "NLRTM", ("gibraltar",)), ("SGSIN", "NLRTM", ("suez", "south_africa")),
         ("USNYC", "AUSYD", ("panama",))]
for o, d, ex in cases:
    n, t = dist(o, d, ex)
    print(f"  {o}->{d} blocked={str(list(ex) or '-'):<28} {n:9.1f} nm   tags crossed: {list(t)}")
print("  NOTE: blocking tag south_africa still rounds the Cape (7,451 nm), so capes are excluded with a meridian gate instead (voyage_planner/gates.py).")

print("\n== 4. What searoute does when the destination is unreachable ==")
a, b = planner.data.ports["EGPSD"], planner.data.ports["NLRTM"]
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    f = sr.searoute([a.longitude, a.latitude], [b.longitude, b.latitude], units="naut",
                    restrictions=["northwest", "gibraltar", "suez"])
print(f"  Port Said -> Rotterdam, gibraltar+suez blocked: length={f['properties']['length']}, "
      f"coordinates={f['geometry']['coordinates']}, python warning={[str(x.message)[:60] for x in w]}")
print("  => no exception: a naive caller would report a 0 nm voyage. The engine raises ROUTE_NOT_FOUND.")

print("\n== 5. Default behaviour that reproduces the Cargill baseline ==")
for flag in (False, True):
    tot = 0.0
    for o, d in (("SGSIN", "HKHKG"), ("USHOU", "NLRTM")):
        pa, pb = planner.data.ports[o], planner.data.ports[d]
        r = sr.searoute([pa.longitude, pa.latitude], [pb.longitude, pb.latitude], units="naut",
                        append_orig_dest=flag, restrictions=["northwest"])
        print(f"  append_orig_dest={flag!s:<5} {o}->{d}: {r['properties']['length']:.1f} nm")
print("  Baseline BM_001=1439, BM_004=5041 -> the library default (append_orig_dest=False) is what Cargill used.")
