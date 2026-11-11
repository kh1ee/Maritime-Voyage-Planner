"""Central constants for the routing engine (T05).

Everything that is a *decision* rather than a calculation lives here, so it can
be reviewed, documented (T32) and changed in one place.
"""
from __future__ import annotations

# Value required by API_SPECIFICATION.md (appears in every request/response).
CALCULATION_VERSION = "0.1.0"

# The searoute-py release Cargill used to generate the benchmark baselines.
EXPECTED_SEAROUTE_VERSION = "1.6.0"

# searoute blocks the Arctic "northwest" passage by default; we keep that
# default so results stay comparable with the Cargill baseline.
DEFAULT_RESTRICTION_TAGS = ("northwest",)

# Mean Earth radius expressed in nautical miles (1 nm = 1 minute of arc).
EARTH_RADIUS_NM = 3440.065

# Warn the user when a requested point is further than this from the nearest
# node of the searoute network (the distance to/from that node is NOT included
# in the reported distance - see docs/T32_routing_methodology.md).
SNAP_WARNING_NM = 25.0

# A route is reported as "using" a reference passage when its geometry passes
# within this distance of the passage reference point (or traverses a network
# edge tagged with that passage).
PASSAGE_DETECTION_NM = 50.0

# Required passages are tried in every order (n!) to find the shortest; cap n.
MAX_REQUIRED_PASSAGES = 4

# Safety cap on voyage size.
MAX_LEGS = 100

# Passage IDs (Passage Reference tab) -> tag used on the searoute network edges.
# Canals / straits that exist as *tagged edges* are excluded by blocking the tag.
# See docs/T16_network_findings.md for the evidence behind this table.
PASSAGE_TO_SEAROUTE_TAG = {
    "PANAMA": "panama",
    "SUEZ": "suez",
    "GIBRALTAR": "gibraltar",
    "MALACCA": "malacca",
}

# searoute edge tags -> project passage IDs (used to label passages_used).
TAG_TO_PASSAGE = {tag: pid for pid, tag in PASSAGE_TO_SEAROUTE_TAG.items()}

# Capes have no tagged edges in the network; they are excluded with a "gate"
# (see voyage_planner/gates.py).  Both capes in the dataset point south.
CAPE_GATE_PASSAGES = ("CAPE_HORN", "CAPE_GOOD_HOPE")

# Every passage in this list can be excluded.
EXCLUDABLE_PASSAGES = tuple(PASSAGE_TO_SEAROUTE_TAG) + CAPE_GATE_PASSAGES

STANDARD_WARNING = "Academic estimate; not for navigation."
