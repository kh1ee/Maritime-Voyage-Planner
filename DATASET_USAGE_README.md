# Voyage Planner dataset usage guide

Last updated: 27 October 2026. The workbook is voyage_planner_datasets.xlsx in this folder; the project brief takes precedence if anything here differs.

## Workbook

Open `voyage_planner_datasets.xlsx` (updated 27 October 2026). It contains five tabs:

1. **Port Reference** — origin, destination, and intermediate port information.
2. **Passage Reference** — canals, capes, and straits used for alternatives or constraints.
3. **Synthetic Positions** — fictional vessel coordinates for position-to-port tests.
4. **Benchmark Routes** — test scenarios used to validate the routing engine.
5. **Data Sources** — source, licence, version, and attribution tracking.

## Typical workflow

1. Load the Port Reference tab into the application.
2. Match a user’s port name or alias to `port_id` or `un_locode`.
3. Send the port coordinates to the selected maritime routing engine.
4. Use longitude first and latitude second when calling `searoute-py`: `[longitude, latitude]`.
5. Use the Passage Reference tab when a route must include or compare a canal, cape, or strait.
6. Use the Synthetic Positions tab to test a vessel-position-to-port request.
7. Use the Benchmark Routes tab to run short, long, canal, cape, and multi-leg tests.
8. Record the calculated distance, route geometry, routing points, assumptions, warnings, and calculation version.
9. Use the benchmark distances supplied by Cargill in expected_distance_nm (updated 27 Oct 2026). They are provisional model-derived baselines, not NGA Pub 151 values.

## Example request

```json
{
  "origin_port_id": "USHOU",
  "destination_port_id": "CLTOQ",
  "required_passage": "PANAMA",
  "intermediate_stops": [],
  "calculation_version": "0.1.0"
}
```

## Example multi-leg request

```json
{
  "legs": [
    {"origin_port_id": "SGSIN", "destination_port_id": "HKHKG"},
    {"origin_port_id": "HKHKG", "destination_port_id": "LKCMB"},
    {"origin_port_id": "LKCMB", "destination_port_id": "ZADUR"}
  ],
  "calculation_version": "0.1.0"
}
```

## Important coordinate rule

The CSV files list latitude and longitude as separate columns. The `searoute-py` function expects a coordinate pair in this order:

```text
[longitude, latitude]
```

## Suggested output structure

```json
{
  "route_id": "BM_005",
  "distance_by_leg_nm": [3594.0],
  "total_distance_nm": 3594.0,
  "required_passage": "PANAMA",
  "route_geometry": "GeoJSON LineString",
  "assumptions": ["Port-level approach points used"],
  "warnings": ["Academic estimate; not for navigation"],
  "calculation_version": "0.1.0"
}
```
