# T20 - alternative route comparisons

Calculated by `VoyagePlanner.compare()` (spec section 7). Units: nautical miles.

| Voyage | Option | Distance (nm) | Passages on route | Extra vs shortest (nm) |
|---|---|---:|---|---:|
| Houston to Tocopilla | Via Panama Canal | 3,594.3 | PANAMA | +0.0 |
| Houston to Tocopilla | Via Cape Horn | 9,972.6 | CAPE_HORN | +6,378.3 |
| | **Difference** | **6,378.3** | shortest: Via Panama Canal | |
| Rotterdam to Durban | Via Suez Canal | 7,943.3 | GIBRALTAR, SUEZ | +764.5 |
| Rotterdam to Durban | Via Cape of Good Hope | 7,178.8 | CAPE_GOOD_HOPE | +0.0 |
| | **Difference** | **764.5** | shortest: Via Cape of Good Hope | |

Rotterdam-Durban: the Cape of Good Hope route is *shorter* than the Suez route in this network, so excluding Suez does not lengthen the voyage (see docs/T32).
Limitation: distances come from the same searoute-py 1.6.0 network as the benchmark baseline; they show consistency, not independent accuracy.
