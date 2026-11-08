# Voyage Planner API Specification

## 1. Purpose

The Voyage Planner API calculates and returns transparent maritime route information for the selected public ports and synthetic vessel positions. It is an academic prototype and is not intended for navigation or operational decision-making.

## 2. Required endpoints

### `GET /health`

Confirms that the service is running.

Example response:

```json
{
  "status": "ok",
  "calculation_version": "0.1.0"
}
```

### `POST /route`

Calculates one route between an origin and destination.

### `POST /voyage`

Calculates a multi-leg voyage and returns each leg separately together with the total distance.

## 3. Single-route request

At least one origin and one destination are required. Each location may be a port ID or a coordinate pair.

```json
{
  "origin_port_id": "SGSIN",
  "destination_port_id": "NLRTM",
  "required_passage": null,
  "excluded_passage": null,
  "waypoints": [],
  "calculation_version": "0.1.0"
}
```

Coordinate-based example:

```json
{
  "origin_coordinates": {
    "latitude": 10.0,
    "longitude": 114.0
  },
  "destination_port_id": "SGSIN"
}
```

## 4. Multi-leg voyage request

```json
{
  "legs": [
    {
      "origin_port_id": "SGSIN",
      "destination_port_id": "HKHKG"
    },
    {
      "origin_port_id": "HKHKG",
      "destination_port_id": "LKCMB"
    },
    {
      "origin_port_id": "LKCMB",
      "destination_port_id": "ZADUR"
    }
  ],
  "calculation_version": "0.1.0"
}
```

## 5. Required response

```json
{
  "route_id": "route-001",
  "status": "success",
  "distance_nm": 8500.0,
  "origin": {
    "port_id": "SGSIN",
    "port_name": "Singapore",
    "latitude": 1.2644,
    "longitude": 103.8200
  },
  "destination": {
    "port_id": "NLRTM",
    "port_name": "Rotterdam",
    "latitude": 51.9500,
    "longitude": 4.1400
  },
  "routing_points": [],
  "passages_used": [],
  "route_geometry": {
    "type": "LineString",
    "coordinates": []
  },
  "assumptions": [
    "Port-level coordinates were used.",
    "Distance was calculated using the selected routing network."
  ],
  "warnings": [
    "Academic estimate; not for navigation."
  ],
  "calculation_version": "0.1.0"
}
```

Distances must be returned in nautical miles. Route geometry should use GeoJSON format where possible. GeoJSON coordinates must use `[longitude, latitude]` order.

## 6. Multi-leg response

```json
{
  "voyage_id": "voyage-001",
  "status": "success",
  "legs": [
    {
      "leg_number": 1,
      "origin_port_id": "SGSIN",
      "destination_port_id": "HKHKG",
      "distance_nm": 1200.0,
      "passages_used": [],
      "route_geometry": {
        "type": "LineString",
        "coordinates": []
      }
    }
  ],
  "total_distance_nm": 1200.0,
  "assumptions": [],
  "warnings": [
    "Academic estimate; not for navigation."
  ],
  "calculation_version": "0.1.0"
}
```

## 7. Alternative routes

Students should support route comparison for selected benchmark cases. A comparison response should include:

```json
{
  "comparison_id": "comparison-001",
  "options": [
    {
      "route_name": "Via Panama Canal",
      "required_passage": "PANAMA",
      "distance_nm": 0.0
    },
    {
      "route_name": "Via Cape Horn",
      "required_passage": "CAPE_HORN",
      "distance_nm": 0.0
    }
  ],
  "distance_difference_nm": 0.0,
  "warnings": []
}
```

## 8. Error responses

The API should return a clear error instead of silently producing a result.

```json
{
  "status": "error",
  "error_code": "PORT_NOT_FOUND",
  "message": "The supplied origin port ID was not found.",
  "warnings": []
}
```

Minimum error cases:

- `PORT_NOT_FOUND`
- `INVALID_COORDINATES`
- `MISSING_ORIGIN`
- `MISSING_DESTINATION`
- `ROUTE_NOT_FOUND`
- `INVALID_PASSAGE`
- `INVALID_REQUEST`

## 9. Implementation expectations

Students may use `searoute-py` or another approved routing engine internally, but the project API must provide a stable interface independent of the library’s internal function names. The calculation must be deterministic and must record its routing-data and software version.

## 10. Orchestrator Agent usage

An Orchestrator Agent should convert a natural-language request into the API request format, call the API, and explain the returned result. It must not estimate maritime distances itself. The agent should preserve and present the API’s assumptions, warnings, and calculation version.
