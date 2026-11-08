# Project 7: Voyage Planner

## Project synopsis

Voyage planning requires reliable maritime distance calculations between a vessel’s position, loading ports, discharge ports, bunker ports, and intermediate stops. Straight-line distance is unsuitable because ships must follow navigable waters and may need to use or avoid canals, capes, straits, and other routing points.

This project will develop a transparent academic prototype that calculates and visualises maritime routes using public port information and one approved open-source maritime-routing network. The system will cover a defined selection of ports and benchmark routes rather than attempting global commercial coverage.

Users will be able to select origin and destination ports, enter a synthetic vessel position, add intermediate stops or waypoints, and compare selected route alternatives. The system will calculate distance for each voyage leg and the total voyage distance in nautical miles. It will display route geometry on a map and provide assumptions, warnings, and data limitations.

The routing engine will be available through a lightweight user interface and a documented function or API. An Orchestrator Agent may call this service, but it must use the deterministic routing result rather than inventing or estimating maritime distances.

## System responsibilities

The project has three connected components:

1. **`searoute` routing engine** — receives coordinates and calculates the underlying sea route, distance, and route geometry.
2. **Student-built Voyage Planner API** — receives ports, coordinates, intermediate stops, and passage preferences; calls `searoute`; calculates multi-leg totals; and returns a structured result containing distances, route geometry, assumptions, and warnings.
3. **Student-built Orchestrator Agent** — interprets a user’s natural-language voyage request, converts it into an API request, calls the Voyage Planner API, and explains the returned result. The agent must not calculate or guess maritime distances itself.

The intended flow is:

```text
User request → Orchestrator Agent → Voyage Planner API → searoute → voyage result
```

## Required capabilities

- Port-to-port routing.
- Synthetic vessel-position-to-port routing.
- Multi-leg itineraries.
- Selected canal, cape, and strait alternatives.
- Distance by leg and total distance in nautical miles.
- Route visualisation.
- Structured results containing route, assumptions, warnings, and version information.
- Public benchmark testing.
- A callable function or API.

## Example voyage request

For example, a user may request a voyage from Houston to Tocopilla via the Panama Canal, followed by Tocopilla to Durban via Cape Horn. The Voyage Planner will calculate the distance for each voyage leg and the total voyage distance, display the selected routes on a map, identify the passages used, and return the assumptions, warnings, and calculation version. An Orchestrator Agent can call the Voyage Planner API to obtain these results rather than estimating the distances itself.


