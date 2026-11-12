# Member 1: reviewed work and next steps

Reviewed on 11 November 2026. Original uploads have not been edited. These are revised checks based on your existing scripts, not the supplied reference service.

## What the review found

### T02: identifier screening works, but is not full port validation

The supplied workbook contains 29 ports, with no duplicated project port IDs or UN/LOCODE values. Both uploaded workbooks have the same SHA-256 checksum. The updated BM_006 is present: Cape Horn required, Panama excluded, 9,973 nm expected, tolerance 250 nm.

28 of 29 supplied identifiers occur in your UN/LOCODE CSVs. Three records require particular attention:

| Project ID | Finding | Handoff action |
|---|---|---|
| GIIBZ | No matching reference record. GIGIB is the Gibraltar record. | Keep GIIBZ as the supplied project key; document GIGIB as the proposed official-code mapping. |
| CNSHA | Reference name is Shanghai Hongqiao International Apt, function `---4----`; this is not a maritime port record. | Review the intended city/terminal. CNSGH (Shanghai) and CNSHG (Shanghai Pt) appear in the references; do not select or move coordinates automatically. |
| PAMIT | Reference name is Manzanillo, while the supplied workbook says Colon, with Cristobal/Colon aliases. | Reconcile regional versus terminal scope before declaring this an accurate name/code match. |

The revised T02 script also checks coordinate ranges, duplicate keys, country prefixes and maritime function codes. Where UN/LOCODE coordinates exist, it records their distance from the supplied port point. These are descriptive differences: UN/LOCODE points are not authoritative approach positions. Some records have no coordinates. The release of the uploaded CSV files cannot be established from their filenames; retain your original download release/date if available. The files decode correctly as UTF-8; unconditional Latin-1 decoding in the original script corrupts some names.

Official corroboration, accessed 11 November 2026: [Gibraltar](https://service.unece.org/trade/locode/gi.htm), [China](https://service.unece.org/trade/locode/cn.htm), [Panama](https://service.unece.org/trade/locode/pa.htm). These corroborate the exceptions; the executable audit uses your supplied CSV files, not an unpinned live lookup.

### T03: route connectivity is demonstrated; approach approval is still pending

Your original script does not establish the conclusion in your results note. `searoute` returns a GeoJSON Feature, whereas the script looks for a `features` key. A false condition is ignored, and only exceptions enter the failure list. It can therefore report universal success without validating any geometry. Testing a point only 0.01 degrees away can also snap both ends to the same network node.

The revised check validates actual distant routes, nonempty LineString geometry, finite positive distance, and nautical-mile units. It records the distance between each supplied approach point and the returned network start, without appending input endpoints. Version: searoute 1.6.0, networkx/dijkstra, northwest passage excluded, no port substitution. Singapore is the destination anchor except for Singapore itself, which uses Rotterdam.

All 29 ports return valid network routes under this configuration. Eight exceed an analyst-selected **10 nm review trigger**:

| Port | Input-to-network distance (nm) |
|---|---:|
| Tocopilla | 114.179 |
| Richards Bay | 50.957 |
| Callao | 32.437 |
| Valparaiso | 18.781 |
| Buenos Aires | 17.229 |
| Shanghai | 17.204 |
| Suez | 15.234 |
| Hong Kong | 14.130 |

This trigger is a triage choice, not a course tolerance or proof that these coordinates are wrong. Shorter snaps do not establish approach safety either. No land mask, chart, bathymetry or draft check was performed. All `approach_approved` flags remain false pending geographic review. The raw library geometry can unwrap longitude beyond 180 degrees on date-line crossings; the diagnostic normalizes endpoints for distance measurements and retains the raw output for traceability.

Ask Member 2 to review these endpoints and the network resolution. Preserve supplied coordinates for benchmark acceptance runs. If the team adopts refined approach points, keep a separately versioned configuration and compare the impact without altering supplied targets.

Upstream behaviour: [searoute documentation](https://github.com/genthalili/searoute-py/blob/main/README.md), accessed 11 November 2026. Runtime version and settings are recorded in the results, since current online documentation can change.

### T13: the Rotterdam-Hamburg discrepancy now has a sourced explanation of scale

The direct-library diagnostic returns **297.672 nm**, compared with the supplied BM_002 target of **298 +/- 100 nm**. Absolute error against the required target is **0.328 nm**, so this diagnostic is within tolerance.

An independent source, **NGA Publication 151, 11th edition (2001), printed page 94**, Rotterdam entry, lists Hamburg at **307 nautical miles**. The calculated network distance is **9.328 nm shorter (3.04%)**. Publication 151's preface identifies nautical-mile units and central port reference positions. Its Rotterdam point is 51 degrees 54 minutes N, 4 degrees 28 minutes E, different from the workbook's 51.95 N, 4.14 E. Endpoint and route conventions can explain differences in general; this review does not isolate the cause of these particular 9.328 nm.

Source: [NGA Publication 151](https://msi.nga.mil/api/publications/download?key=16694076%2FSFH00000%2FPub151bk.pdf&type=view), accessed 11 November 2026. This independent spot-check is separate from the supplied model-derived acceptance target and must not replace it. The group's API has not been tested by this direct-library diagnostic. T13 has an initial sourced spot-check; a broader reference table can be expanded later.

## Your remaining work

| Task | Evidence now available | What remains |
|---|---|---|
| T02 | Per-port identifier, function and coordinate audit | Resolve/document the three identity exceptions and record CSV release provenance. |
| T03 | 29 successful route checks with measured snaps | Geographic review and documented disposition of approach points with Member 2. |
| T13 | Independently sourced Rotterdam-Hamburg check | Add other suitable published route references as useful. |
| T20 | Required comparisons identified in the API spec | Integrate with Member 2's constrained routing and Member 3's API. |
| T26 | Supplied targets and limitations identified | Run all ten supplied cases against the actual service, recording constraints, tolerances and geometry evidence. |
| T35 | Review findings and first spot-check | Combine final benchmark results with Member 3's tests and unresolved limitations. |
| T36 | Scope and evidence structure identified | Build slides from the implemented system and final results. |
| T38 | Existing inputs reviewed | Package the final code, versioned data/configuration and documentation from all members. |

For T20 compare Houston-Tocopilla via Panama versus Cape Horn (exclude Panama for the Cape Horn option), and Rotterdam-Durban via Suez versus Cape of Good Hope. The API spec defines a comparison response shape but no dedicated comparison endpoint. Agree on the integration with Member 3 instead of inventing a required endpoint. Use actual routing outputs to calculate differences; never substitute the benchmark targets as calculated distances.

The next essential inputs are the group's current routing/API code or repository, its run instructions, and any benchmark/test outputs already produced. No group routing/API implementation was included in these uploads; the `searoute-mcp` folder is the reference implementation.

## Reproduce the checks

Requirements: Python with `openpyxl`, `searoute==1.6.0` and its dependencies. These checks were run successfully using your existing environment at `/Users/brosman/Documents/Voyage_Planner/.venv/bin/python`.

Run from this `member1_work` directory using that Python (or your equivalent environment):

```sh
python T02_port_validation.py --workbook '/Users/brosman/Downloads/Prof Voyage Planner/voyage_planner_datasets.xlsx' --unlocode-dir /Users/brosman/Documents/Voyage_Planner
python T03_approach_validation.py --workbook '/Users/brosman/Downloads/Prof Voyage Planner/voyage_planner_datasets.xlsx'
python T13_rotterdam_hamburg.py --workbook '/Users/brosman/Downloads/Prof Voyage Planner/voyage_planner_datasets.xlsx'
python -m unittest discover -s . -p 'test_validation.py' -v
```

The scripts write JSON evidence under `results/`, without modifying source data. T02 and T03 print summaries; inspect the detailed statuses before accepting individual records. Successful script execution is not itself approval of the port data. T03's review trigger can be changed with `--review-snap-nm`; doing so changes only triage flags, not supplied points or distances.
