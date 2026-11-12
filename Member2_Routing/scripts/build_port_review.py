"""Build data/port_review.json from Member 1's T02 / T03 results (member1_review/results).

The file is *documentation + triage flags only*.  It never changes a supplied
project ID, coordinate or benchmark value.  Re-run it when Member 1 re-issues
their results:   python scripts/build_port_review.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "member1_review", "results")

# Team decisions on Member 1's T02 exceptions (12 Nov 2026).  The supplied project ID, name and
# coordinates are NOT changed; the decisions are lookup aliases plus a note in the responses.
IDENTITY_REVIEW = {
    "GIIBZ": {
        "status": "team_decision",
        "accepted_aliases": ["GIGIB"],
        "decision": "Both GIIBZ (supplied project ID) and GIGIB (UN/LOCODE record) are accepted for Gibraltar.",
        "note": "Gibraltar: both GIIBZ and GIGIB are accepted; GIIBZ remains the project key.",
    },
    "CNSHA": {
        "status": "team_decision",
        "accepted_aliases": ["CNSGH"],
        "decision": "CNSGH is accepted as an alias of CNSHA. The UN/LOCODE reference lists CNSHA as the Shanghai "
                    "Hongqiao airport record; the project keeps CNSHA as the Shanghai key.",
        "note": "Shanghai: CNSGH is accepted as an alias of CNSHA (the UN/LOCODE reference lists CNSHA as an airport record).",
    },
    "PAMIT": {
        "status": "team_decision",
        "accepted_aliases": ["Manzanillo"],
        "known_as": "Manzanillo",
        "decision": "PAMIT is treated as Manzanillo (the UN/LOCODE reference name); the workbook name Colon is kept "
                    "as a supplied alias.",
        "note": "PAMIT is treated as Manzanillo (UN/LOCODE reference name); the workbook's Colon/Cristobal aliases still work.",
    },
}


def main():
    t2 = json.load(open(os.path.join(RES, "t02.json")))
    t3 = json.load(open(os.path.join(RES, "t03.json")))
    snaps = {p["port_id"]: p for p in t3["ports"]}
    ports = {}
    for p in t2["ports"]:
        pid = p["port_id"]
        s = snaps[pid]
        ports[pid] = {
            "identifier_in_unlocode_reference": p["identifier_match"],
            "identity_review": IDENTITY_REVIEW.get(pid),
            "approach_snap_nm": s["origin_snap_nm"],
            "approach_snap_review": s["status"] == "REVIEW_SNAP",
            "approach_approved": bool(s["approach_approved"]),
        }
    out = {
        "source": "Member 1 review of 11 November 2026 (T02, T03)",
        "workbook_sha256_note": "workbook is byte-identical to data/voyage_planner_datasets.xlsx",
        "snap_review_trigger_nm": t3["review_snap_nm"],
        "snap_review_trigger_basis": t3["review_threshold_basis"],
        "searoute_version": t3["searoute_version"],
        "limitations": t3["limitations"],
        "t02_status": {"identifiers_matched": t2["matched_identifiers"] if "matched_identifiers" in t2 else None,
                       "needs_review": t2["ports_requiring_review"]},
        "ports": ports,
    }
    path = os.path.join(ROOT, "data", "port_review.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    flagged = [k for k, v in ports.items() if v["approach_snap_review"]]
    print("wrote", path, "| snap-review ports:", flagged, "| identity review:", list(IDENTITY_REVIEW))


if __name__ == "__main__":
    main()
