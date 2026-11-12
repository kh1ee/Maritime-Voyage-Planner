# Benchmark validation - routing engine 0.1.0

Routing library: searoute-py 1.6.0 (9708 nodes / 15970 edges), units: nautical miles, default restrictions: ['northwest'], endpoint snapping not added to distance.

| ID | Route | Constraints | Expected nm | Calculated nm | Diff | Tolerance | Result |
|---|---|---|---:|---:|---:|---:|---|
| BM_001 | Singapore to Hong Kong | - | 1,439 | 1,438.8 | -0.2 | ±100 | PASS |
| BM_002 | Rotterdam to Hamburg | - | 298 | 297.7 | -0.3 | ±100 | PASS |
| BM_003 | Singapore to Rotterdam | - | 8,368 | 8,368.2 | +0.2 | ±250 | PASS |
| BM_004 | Houston to Rotterdam | - | 5,041 | 5,041.2 | +0.2 | ±250 | PASS |
| BM_005 | Houston to Tocopilla via Panama | via PANAMA | 3,594 | 3,594.3 | +0.3 | ±250 | PASS |
| BM_006 | Houston to Tocopilla via Cape Horn | via CAPE_HORN, excl. PANAMA | 9,973 | 9,972.6 | -0.4 | ±250 | PASS |
| BM_007 | Rotterdam to Durban via Suez | via SUEZ | 7,943 | 7,943.3 | +0.3 | ±250 | PASS |
| BM_008 | Rotterdam to Durban via Cape | via CAPE_GOOD_HOPE | 7,179 | 7,178.8 | -0.2 | ±250 | PASS |
| BM_009 | Synthetic position to Singapore | - | 721 | 720.8 | -0.2 | ±150 | PASS |
| BM_010 | Multi-leg Asia-Africa voyage | - | 8,271 | 8,271.0 | +0.0 | ±300 | PASS |

**10/10 benchmarks within tolerance.**

Limitation: the expected values were generated with searoute-py 1.6.0 (same package as the engine), so agreement shows consistency with the baseline, not independent accuracy. BM_009 is a functional test.
