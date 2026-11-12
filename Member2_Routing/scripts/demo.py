"""Hands-on tour of the engine - prints a short summary of each call.

    python3 scripts/demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voyage_planner import VoyagePlanner, VoyagePlannerError        # noqa: E402

planner = VoyagePlanner()


def show(title, result):
    print(f"\n### {title}")
    if result.get("status") == "error":
        print("  ERROR:", json.dumps(result))
        return
    total = result.get("distance_nm", result.get("total_distance_nm"))
    print(f"  total: {total:,.1f} nm   passages: {result['passages_used']}")
    if "legs" in result:
        for leg in result["legs"]:
            o, d = leg["origin"], leg["destination"]
            print(f"    leg {leg['leg_number']}: {o['port_name'] or o['location_type']} -> "
                  f"{d['port_name'] or d['location_type']}: {leg['distance_nm']:,.1f} nm  {leg['passages_used']}")
    else:
        print("  by sub-leg:", result["distance_by_leg_nm"], "| unconstrained:", result["unconstrained_distance_nm"])
    for w in result["warnings"][1:]:
        print("  warning:", w)


print("GET /health ->", planner.health())

show("T06 port-to-port: Singapore -> Rotterdam", planner.port_to_port("SGSIN", "NLRTM"))
show("T06 by name/alias: Port of Santos -> Singapore", planner.port_to_port("Port of Santos", "Singapore"))
show("T07 position-to-port: POS_001 (South China Sea) -> Singapore",
     planner.route({"origin_position_id": "POS_001", "destination_port_id": "SGSIN"}))
show("T07 raw coordinates -> Singapore", planner.position_to_port(10.0, 114.0, "SGSIN"))
show("T08 multi-leg: Singapore > Hong Kong > Colombo > Durban",
     planner.multi_leg(["SGSIN", "HKHKG", "LKCMB", "ZADUR"]))
show("T18 required: Rotterdam -> Durban via Suez", planner.port_to_port("NLRTM", "ZADUR", required_passage="SUEZ"))
show("T18 required: Rotterdam -> Durban via Cape of Good Hope",
     planner.port_to_port("NLRTM", "ZADUR", required_passage="CAPE_GOOD_HOPE"))
show("T17 excluded: Houston -> Tocopilla, Panama excluded", planner.port_to_port("USHOU", "CLTOQ", excluded_passage="PANAMA"))
show("T17+T18 BM_006: Houston -> Tocopilla via Cape Horn, Panama excluded",
     planner.port_to_port("USHOU", "CLTOQ", required_passage="CAPE_HORN", excluded_passage="PANAMA"))
show("T17 excluded cape: Rotterdam -> Durban, Cape of Good Hope excluded (forces Suez)",
     planner.port_to_port("NLRTM", "ZADUR", excluded_passage="CAPE_GOOD_HOPE"))
show("T17 excluded cape: Houston -> Tocopilla, Panama + Cape Horn excluded (Strait of Magellan)",
     planner.port_to_port("USHOU", "CLTOQ", excluded_passage=["PANAMA", "CAPE_HORN"]))
show("Synopsis example: Houston > Tocopilla (Panama), Tocopilla > Durban (Cape Horn)",
     planner.multi_leg(["USHOU", "CLTOQ", "ZADUR"], required_passages=["PANAMA", "CAPE_HORN"]))

print("\n--- error handling (API spec section 8) ---")
for title, req in [
    ("unknown port", {"origin_port_id": "XXXXX", "destination_port_id": "SGSIN"}),
    ("missing destination", {"origin_port_id": "SGSIN"}),
    ("bad coordinates", {"origin_coordinates": {"latitude": 123, "longitude": 0}, "destination_port_id": "SGSIN"}),
    ("unknown passage", {"origin_port_id": "SGSIN", "destination_port_id": "NLRTM", "required_passage": "ATLANTIS"}),
    ("required = excluded", {"origin_port_id": "NLRTM", "destination_port_id": "ZADUR", "required_passage": "SUEZ", "excluded_passage": "SUEZ"}),
    ("no route exists", {"origin_port_id": "EGPSD", "destination_port_id": "NLRTM", "excluded_passage": ["GIBRALTAR", "SUEZ"]}),
]:
    print(f"{title:>26}: {json.dumps(planner.handle_route(req))[:150]}")
