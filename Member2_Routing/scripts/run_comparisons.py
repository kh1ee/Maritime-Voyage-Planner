"""T20 route comparisons (API specification section 7) from real engine calculations.

    python3 scripts/run_comparisons.py

Houston -> Tocopilla: via Panama Canal vs via Cape Horn (Panama excluded).
Rotterdam -> Durban : via Suez Canal vs via Cape of Good Hope (Suez excluded).
Every distance is calculated by the engine; none is copied from the benchmark table.
Writes results/t20_comparisons.json and results/t20_comparisons.md.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from voyage_planner import VoyagePlanner  # noqa: E402

CASES = [("USHOU", "CLTOQ", "panama_vs_cape_horn", "Houston to Tocopilla"),
         ("NLRTM", "ZADUR", "suez_vs_cape_good_hope", "Rotterdam to Durban")]


def main() -> int:
    planner = VoyagePlanner()
    out, lines = [], ["# T20 - alternative route comparisons", "",
                      "Calculated by `VoyagePlanner.compare()` (spec section 7). Units: nautical miles.", "",
                      "| Voyage | Option | Distance (nm) | Passages on route | Extra vs shortest (nm) |",
                      "|---|---|---:|---|---:|"]
    for origin, dest, preset, title in CASES:
        r = planner.compare_standard_alternatives(origin, dest, preset)
        out.append({"voyage": title, "origin": origin, "destination": dest, "preset": preset,
                    "comparison": {k: v for k, v in r.items() if k != "options"},
                    "options": [{k: v for k, v in o.items() if k != "route_geometry"} for o in r["options"]]})
        for o in r["options"]:
            lines.append(f"| {title} | {o['route_name']} | {o['distance_nm']:,.1f} | "
                         f"{', '.join(o['passages_used']) or '-'} | {o['extra_distance_vs_shortest_nm']:+,.1f} |")
        lines.append(f"| | **Difference** | **{r['distance_difference_nm']:,.1f}** | shortest: {r['shortest_option']} | |")
    lines += ["", "Rotterdam-Durban: the Cape of Good Hope route is *shorter* than the Suez route in this network, "
              "so excluding Suez does not lengthen the voyage (see docs/T32).",
              "Limitation: distances come from the same searoute-py 1.6.0 network as the benchmark baseline; "
              "they show consistency, not independent accuracy."]
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "t20_comparisons.json"), "w") as fh:
        json.dump({"engine": planner.backend.engine_info(), "comparisons": out}, fh, indent=2)
    with open(os.path.join(ROOT, "results", "t20_comparisons.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
