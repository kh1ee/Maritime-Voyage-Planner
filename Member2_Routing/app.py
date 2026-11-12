import json
import os

import streamlit as st
import pandas as pd
import folium
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pathlib import Path
from streamlit.components.v1 import html


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Maritime Voyage Planner",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Maritime Voyage Planner")


# ============================================================
# LOAD PORT DATASET
# ============================================================

DATASET_PATH = Path(__file__).resolve().parent / "data" / "voyage_planner_datasets.xlsx"

@st.cache_data
def load_ports():

    df = pd.read_excel(
        DATASET_PATH,
        sheet_name="Port Reference"
    )

    df = df[
        df["status"].astype(str).str.lower() == "active"
    ].copy()

    df = df.sort_values("port_name")

    return df


try:
    ports_df = load_ports()

except Exception as error:
    st.error(f"Failed to load port dataset: {error}")
    st.stop()


port_options = {
    f"{row['port_name']} ({row['country']})": row
    for _, row in ports_df.iterrows()
}

port_names = list(port_options.keys())


# ============================================================
# VOYAGE SETTINGS
# ============================================================

st.subheader("Voyage Settings")

speed = st.number_input(
    "Vessel Speed (knots)",
    min_value=0.1,
    max_value=50.0,
    value=15.0,
    step=0.5
)

@st.cache_data
def load_passages():
    df = pd.read_excel(DATASET_PATH, sheet_name="Passage Reference")
    df = df[df["status"].astype(str).str.lower() == "active"]
    return {
        str(row["passage_id"]).upper(): {
            "name": row["passage_name"],
            "type": str(row["passage_type"]).lower(),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        }
        for _, row in df.iterrows()
    }


passages = load_passages()
TYPE_LABEL = {"canal": "canal", "strait": "strait", "cape": "cape"}
passage_ids = sorted(
    passages,
    key=lambda pid: (["canal", "strait", "cape"].index(passages[pid]["type"])
                     if passages[pid]["type"] in TYPE_LABEL else 9, passages[pid]["name"]),
)


def passage_label(passage_id):
    info = passages[passage_id]
    return f"{info['name']} ({info['type']})"


def passage_names(passage_ids_list):
    return [passages[p]["name"] if p in passages else p for p in passage_ids_list]


# Any canal, strait or cape can be excluded.  Canals/straits are blocked on the
# routing network; capes are blocked with a meridian "gate" inside the engine.
selected_exclusions = st.multiselect(
    "Exclude canals, straits and capes",
    options=passage_ids,
    default=[],
    format_func=passage_label,
    help=(
        "Choose every passage the vessel must NOT use.  Leave empty for the "
        "automatic shortest route.  Routes with an explicit exclusion are "
        "highlighted on the map and in the results."
    ),
    key="excluded_passages",
)

restrictions = sorted(selected_exclusions)
if restrictions:
    st.info("Excluding: " + ", ".join(passage_names(restrictions)))
st.caption("The routing engine excludes the Northwest Passage by default.")


# ============================================================
# ROUTING FUNCTIONS
# ============================================================

def get_coordinates(port):

    return [
        float(port["approach_longitude"]),
        float(port["approach_latitude"])
    ]


@st.cache_resource
def local_engine():
    from voyage_planner import VoyagePlanner
    return VoyagePlanner()


def route_namespace(result):
    return SimpleNamespace(
        properties={"length": result["distance_nm"]},
        geometry=result["route_geometry"],
        passages_used=list(result.get("passages_used") or []),
        excluded=list(result.get("excluded_passage") or []),
        warnings=[w for w in result.get("warnings", []) if not w.startswith("Academic estimate")],
        unconstrained_nm=result.get("unconstrained_distance_nm"),
    )


def api_route(origin, destination, excluded_passages):
    payload = {**origin, **destination}
    if excluded_passages:
        payload["excluded_passage"] = [passage.upper() for passage in excluded_passages]
    api_url = os.environ.get(
        "VOYAGE_API_URL", "https://maritime-voyage-planner.onrender.com"
    ).rstrip("/")
    if api_url.lower() == "local":
        # VOYAGE_API_URL=local runs the engine in this process (no network);
        # needs the voyage_planner package next to app.py.
        result = local_engine().handle_route(payload)
        if result.get("status") == "error":
            raise ValueError(result.get("message", "Routing failed."))
        return route_namespace(result)
    request = Request(
        f"{api_url}/route",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            message = json.loads(error.read())["message"]
        except (ValueError, KeyError, TypeError):
            message = f"Routing API returned HTTP {error.code}."
        raise ValueError(message) from error
    except (URLError, TimeoutError) as error:
        raise ValueError("Could not reach the routing API. Please try again shortly.") from error

    return route_namespace(result)


def route_coordinates(role, point):
    longitude, latitude = map(float, point)
    return {f"{role}_coordinates": {"longitude": longitude, "latitude": latitude}}


def calculate_route(origin, destination):
    route = api_route(
        {"origin_port_id": str(origin["port_id"])},
        {"destination_port_id": str(destination["port_id"])},
        restrictions,
    )

    distance = float(route.properties["length"])

    duration_hours = distance / speed
    duration_days = duration_hours / 24

    return route, distance, duration_hours, duration_days


HIGHLIGHT_RED = "#d62728"
HIGHLIGHT_HALO = "#ffd400"


def draw_route(target_map, coords, excluded, tooltip, normal_color="blue", weight=4):
    """Draw a route.  A route with explicit exclusions gets a yellow halo under a
    thick red line, so it stands out from a plain automatic route."""
    if excluded:
        folium.PolyLine(coords, color=HIGHLIGHT_HALO, weight=weight + 8, opacity=0.6).add_to(target_map)
        folium.PolyLine(coords, color=HIGHLIGHT_RED, weight=weight + 1, opacity=0.95,
                        tooltip=f"{tooltip} — avoids {', '.join(passage_names(excluded))}").add_to(target_map)
    else:
        folium.PolyLine(coords, color=normal_color, weight=weight, opacity=0.85, tooltip=tooltip).add_to(target_map)


def add_excluded_markers(target_map, excluded):
    for pid in excluded:
        info = passages.get(pid)
        if info:
            folium.CircleMarker(
                [info["latitude"], info["longitude"]], radius=9, color=HIGHLIGHT_RED,
                fill=True, fill_color=HIGHLIGHT_RED, fill_opacity=0.8,
                tooltip=f"EXCLUDED: {info['name']}", popup=f"Excluded: {info['name']}",
            ).add_to(target_map)


def add_exclusion_legend(target_map, excluded):
    if not excluded:
        return
    html_block = (
        '<div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999; background: white;'
        ' border: 2px solid grey; border-radius: 6px; padding: 10px; font-size: 13px; color: black;">'
        f'<b>Highlighted route</b><br><span style="color:{HIGHLIGHT_RED};">━━━━━</span> '
        f'avoids: {", ".join(passage_names(excluded))}<br>'
        f'<span style="color:{HIGHLIGHT_RED};">●</span> excluded passage point</div>'
    )
    target_map.get_root().html.add_child(folium.Element(html_block))


def show_route_notes(routes, excluded):
    """Text shown under the metrics: what was excluded, what the route uses, data warnings."""
    used = []
    for route in routes:
        for pid in getattr(route, "passages_used", []):
            if pid not in used:
                used.append(pid)
    if excluded:
        st.warning(
            "Highlighted route — explicit exclusions: " + ", ".join(passage_names(excluded))
            + ". Passages on this route: " + (", ".join(passage_names(used)) or "none of the six reference passages") + "."
        )
    elif used:
        st.caption("Passages on this route: " + ", ".join(passage_names(used))
                   + ". Use the exclusion selector above to avoid any of them.")
    notes = []
    for route in routes:
        for warning in getattr(route, "warnings", []):
            if warning not in notes:
                notes.append(warning)
    if notes:
        with st.expander(f"Route notes ({len(notes)})"):
            for note in notes:
                st.write("• " + note)


def create_route_map(route, origin, destination):

    coordinates = [
        [lat, lon]
        for lon, lat in route.geometry["coordinates"]
    ]

    voyage_map = folium.Map(
        location=coordinates[0],
        zoom_start=3
    )

    draw_route(voyage_map, coordinates, restrictions, "Maritime Route")
    add_excluded_markers(voyage_map, restrictions)
    add_exclusion_legend(voyage_map, restrictions)

    folium.Marker(
        [
            float(origin["approach_latitude"]),
            float(origin["approach_longitude"])
        ],
        tooltip="Origin",
        popup=origin["port_name"],
        icon=folium.Icon(color="green")
    ).add_to(voyage_map)

    folium.Marker(
        [
            float(destination["approach_latitude"]),
            float(destination["approach_longitude"])
        ],
        tooltip="Destination",
        popup=destination["port_name"],
        icon=folium.Icon(color="purple")
    ).add_to(voyage_map)

    voyage_map.fit_bounds(coordinates)

    return voyage_map



# ============================================================
# ROUTE COMPARISON FUNCTIONS — STEP 6
# ============================================================

def calculate_comparison_route(start_coordinates, end_coordinates, restrictions_list):

    route = api_route(
        route_coordinates("origin", start_coordinates),
        route_coordinates("destination", end_coordinates),
        restrictions_list,
    )

    distance = float(route.properties["length"])

    if distance <= 0:
        raise ValueError("No valid maritime route was returned.")

    coordinates = [
        [lat, lon]
        for lon, lat in route.geometry["coordinates"]
    ]

    if not coordinates:
        raise ValueError("No route coordinates were returned.")

    return {
        "route": route,
        "distance": distance,
        "hours": distance / speed,
        "days": distance / speed / 24,
        "coordinates": coordinates
    }


def create_comparison_map(unrestricted_routes, restricted_routes, markers):

    all_coordinates = []

    first_location = markers[0]["location"]

    comparison_map = folium.Map(
        location=first_location,
        zoom_start=3,
        tiles="OpenStreetMap"
    )

    # Draw unrestricted routes — SOLID BLUE
    for index, route in enumerate(unrestricted_routes, start=1):

        folium.PolyLine(
            locations=route["coordinates"],
            color="blue",
            weight=4,
            opacity=0.85,
            tooltip=(
                f"Unrestricted Leg {index}: "
                f"{route['distance']:,.2f} NM"
            )
        ).add_to(comparison_map)

        all_coordinates.extend(route["coordinates"])

    # Draw restricted routes — SOLID RED
    for index, route in enumerate(restricted_routes, start=1):

        draw_route(
            comparison_map, route["coordinates"], restrictions,
            f"Restricted Leg {index}: {route['distance']:,.2f} NM",
        )

        all_coordinates.extend(route["coordinates"])

    # Add markers
    for marker in markers:

        folium.Marker(
            location=marker["location"],
            popup=marker["name"],
            tooltip=marker["name"],
            icon=folium.Icon(color=marker["color"])
        ).add_to(comparison_map)

        all_coordinates.append(marker["location"])

    # Add legend
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index: 9999;
        background-color: white;
        border: 2px solid grey;
        border-radius: 6px;
        padding: 12px;
        font-size: 13px;
        color: black;
    ">
        <b>Route Comparison</b><br><br>
        <span style="color: blue;">━━━━━</span>
        Unrestricted Route<br>
        <span style="color: #d62728;">━━━━━</span>
        Restricted Route (highlighted)<br>
        <span style="color: #d62728;">●</span>
        Excluded: EXCLUDED_NAMES
    </div>
    """.replace("EXCLUDED_NAMES", ", ".join(passage_names(restrictions)) or "none")

    comparison_map.get_root().html.add_child(
        folium.Element(legend_html)
    )
    add_excluded_markers(comparison_map, restrictions)

    comparison_map.fit_bounds(all_coordinates)

    return comparison_map


def display_comparison_results(unrestricted_routes, restricted_routes):

    unrestricted_distance = sum(
        route["distance"] for route in unrestricted_routes
    )

    restricted_distance = sum(
        route["distance"] for route in restricted_routes
    )

    unrestricted_days = unrestricted_distance / speed / 24
    restricted_days = restricted_distance / speed / 24

    def used_by(routes):
        names = []
        for item in routes:
            for pid in getattr(item["route"], "passages_used", []):
                if pid not in names:
                    names.append(pid)
        return ", ".join(passage_names(names)) or "—"

    comparison_df = pd.DataFrame([
        {
            "Route": "Unrestricted",
            "Distance (NM)": round(unrestricted_distance, 2),
            "Duration (Days)": round(unrestricted_days, 2),
            "Passages used": used_by(unrestricted_routes)
        },
        {
            "Route": "Restricted",
            "Distance (NM)": round(restricted_distance, 2),
            "Duration (Days)": round(restricted_days, 2),
            "Passages used": used_by(restricted_routes)
        },
        {
            "Route": "Difference",
            "Distance (NM)": round(
                restricted_distance - unrestricted_distance, 2
            ),
            "Duration (Days)": round(
                restricted_days - unrestricted_days, 2
            ),
            "Passages used": ""
        }
    ])

    st.subheader("Route Comparison")
    st.warning("Highlighted (restricted) route excludes: " + ", ".join(passage_names(restrictions)))
    if abs(restricted_distance - unrestricted_distance) < 0.05:
        st.info("The exclusions did not change the route: the unrestricted route does not use the excluded passage(s).")

    st.dataframe(
        comparison_df,
        use_container_width=True,
        hide_index=True
    )

    return unrestricted_distance, restricted_distance


# ============================================================

# ============================================================
# EXPORT FUNCTIONS — STEP 7
# ============================================================

def export_voyage_results(voyage_type, voyage_mode, rows, itinerary=None,
                          vessel_position=None):

    payload = {
        "voyage_type": voyage_type,
        "voyage_mode": voyage_mode,
        "vessel_speed_knots": float(speed),
        "passage_restrictions": list(restrictions),
        "itinerary": itinerary,
        "vessel_position": vessel_position,
        "results": rows
    }

    csv_rows = []

    for row in rows:
        csv_rows.append({
            "Voyage Type": voyage_type,
            "Voyage Mode": voyage_mode,
            "Vessel Speed (knots)": float(speed),
            "Passage Restrictions": ", ".join(restrictions),
            **row
        })

    csv_data = pd.DataFrame(csv_rows).to_csv(index=False)

    json_data = json.dumps(
        payload,
        indent=4,
        ensure_ascii=False
    )

    st.subheader("Export Voyage Results")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name=f"{voyage_type.lower().replace('-', '_')}_{voyage_mode.lower()}.csv",
            mime="text/csv",
            key=f"export_{voyage_type}_{voyage_mode}_csv"
        )

    with col2:
        st.download_button(
            "Download JSON",
            data=json_data,
            file_name=f"{voyage_type.lower().replace('-', '_')}_{voyage_mode.lower()}.json",
            mime="application/json",
            key=f"export_{voyage_type}_{voyage_mode}_json"
        )


# ============================================================
# VALIDATION FUNCTIONS — STEP 8A
# ============================================================

import math


def validate_coordinates(longitude, latitude):
    """Validate longitude and latitude values."""

    try:
        longitude = float(longitude)
        latitude = float(latitude)
    except (TypeError, ValueError):
        raise ValueError(
            "Longitude and latitude must be numeric values."
        )

    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError(
            "Longitude and latitude must be finite numbers."
        )

    if not -180 <= longitude <= 180:
        raise ValueError(
            "Longitude must be between -180 and 180 degrees."
        )

    if not -90 <= latitude <= 90:
        raise ValueError(
            "Latitude must be between -90 and 90 degrees."
        )

    return [longitude, latitude]


def validate_speed(vessel_speed):
    """Ensure vessel speed is valid."""

    try:
        vessel_speed = float(vessel_speed)
    except (TypeError, ValueError):
        raise ValueError(
            "Vessel speed must be a numeric value."
        )

    if not math.isfinite(vessel_speed) or vessel_speed <= 0:
        raise ValueError(
            "Vessel speed must be greater than zero."
        )

    return vessel_speed


def validate_route_result(route):
    """Check that the routing engine returned a usable route."""

    if route is None:
        raise ValueError(
            "The routing engine did not return a route."
        )

    if not hasattr(route, "properties"):
        raise ValueError(
            "The routing engine returned an invalid route."
        )

    distance = float(route.properties["length"])

    if not math.isfinite(distance) or distance <= 0:
        raise ValueError(
            "The calculated route distance must be greater than zero."
        )

    geometry = route.geometry

    if not geometry or not geometry.get("coordinates"):
        raise ValueError(
            "The routing engine returned no route coordinates."
        )

    coordinates = geometry["coordinates"]

    if len(coordinates) < 2:
        raise ValueError(
            "The calculated route contains insufficient coordinates."
        )

    for coordinate in coordinates:
        if len(coordinate) < 2:
            raise ValueError(
                "The route contains an invalid coordinate."
            )

        validate_coordinates(
            coordinate[0],
            coordinate[1]
        )

    return distance


def validate_itinerary(stops):
    """Validate a multi-leg voyage itinerary."""

    if len(stops) < 2:
        raise ValueError(
            "A multi-leg voyage requires at least two ports."
        )

    for index in range(len(stops) - 1):
        if stops[index] == stops[index + 1]:
            raise ValueError(
                "Consecutive duplicate ports are not allowed."
            )

    return True


# RESULTS PERSISTENCE — STEP 8B
# Retain a successful result only while its inputs remain unchanged.
def persisted_action(action_key, signature, clicked):
    state_key = f"persist_{action_key}"
    if clicked:
        st.session_state.pop(state_key, None)
        return True
    if state_key in st.session_state:
        if st.session_state[state_key] == signature:
            return True
        st.session_state.pop(state_key, None)
    return False

# APPLICATION TABS
# ============================================================

tab1, tab2, tab3 = st.tabs([
    "Port-to-Port",
    "Multi-Leg",
    "Position-to-Port"
])


# ============================================================
# TAB 1 — PORT-TO-PORT
# ============================================================

with tab1:

    st.header("Port-to-Port Voyage Planning")

    origin_name = st.selectbox(
        "Origin Port",
        port_names,
        key="origin"
    )

    destination_name = st.selectbox(
        "Destination Port",
        port_names,
        key="destination",
        index=min(1, len(port_names) - 1)
    )

    if persisted_action("calculate_port", (origin_name, destination_name, float(speed), tuple(restrictions)), st.button("Calculate Route", key="calculate_port")):

        try:

            if origin_name == destination_name:
                st.error(
                    "Origin and destination ports must be different."
                )

            else:

                origin = port_options[origin_name]
                destination = port_options[destination_name]

                route, distance, hours, days = calculate_route(
                    origin,
                    destination
                )

                st.session_state["persist_calculate_port"] = (origin_name, destination_name, float(speed), tuple(restrictions))
                st.success("Route calculated successfully!")

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "Maritime Distance",
                    f"{distance:,.2f} NM"
                )

                col2.metric(
                    "Sailing Time",
                    f"{hours:,.2f} hours"
                )

                col3.metric(
                    "Sailing Duration",
                    f"{days:,.2f} days"
                )

                show_route_notes([route], restrictions)

                voyage_map = create_route_map(
                    route,
                    origin,
                    destination
                )

                html(
                    voyage_map._repr_html_(),
                    height=550
                )


                export_voyage_results(
                    "Port-to-Port",
                    "Standard",
                    [{
                        "Origin": origin["port_name"],
                        "Destination": destination["port_name"],
                        "Distance (NM)": round(distance, 2),
                        "Duration (Hours)": round(hours, 2),
                        "Duration (Days)": round(days, 2)
                    }],
                    itinerary=[origin["port_name"], destination["port_name"]]
                )

        except Exception as error:
            # ERROR RECOVERY — STEP 8C.2
            st.session_state.pop("persist_calculate_port", None)

            st.error(f"Route calculation failed: {error}")



    # --------------------------------------------------------
    # PORT-TO-PORT ROUTE COMPARISON
    # --------------------------------------------------------

    if persisted_action("compare_port", (origin_name, destination_name, float(speed), tuple(restrictions)), st.button("Compare Routes", key="compare_port")):

        try:

            if not restrictions:
                st.warning(
                    "Select a passage restriction before comparing routes."
                )

            elif origin_name == destination_name:
                st.error(
                    "Origin and destination ports must be different."
                )

            else:

                origin = port_options[origin_name]
                destination = port_options[destination_name]

                start_coordinates = get_coordinates(origin)
                end_coordinates = get_coordinates(destination)

                unrestricted = calculate_comparison_route(
                    start_coordinates,
                    end_coordinates,
                    []
                )

                restricted = calculate_comparison_route(
                    start_coordinates,
                    end_coordinates,
                    restrictions
                )

                st.session_state["persist_compare_port"] = (origin_name, destination_name, float(speed), tuple(restrictions))
                st.success("Routes compared successfully!")

                display_comparison_results(
                    [unrestricted],
                    [restricted]
                )

                markers = [
                    {
                        "location": [
                            float(origin["approach_latitude"]),
                            float(origin["approach_longitude"])
                        ],
                        "name": origin["port_name"],
                        "color": "green"
                    },
                    {
                        "location": [
                            float(destination["approach_latitude"]),
                            float(destination["approach_longitude"])
                        ],
                        "name": destination["port_name"],
                        "color": "purple"
                    }
                ]

                comparison_map = create_comparison_map(
                    [unrestricted],
                    [restricted],
                    markers
                )

                html(
                    comparison_map._repr_html_(),
                    height=550
                )


                export_voyage_results(
                    "Port-to-Port",
                    "Comparison",
                    [
                        {
                            "Route": label,
                            "Origin": origin["port_name"],
                            "Destination": destination["port_name"],
                            "Distance (NM)": round(result["distance"], 2),
                            "Duration (Days)": round(result["days"], 2)
                        }
                        for label, result in [
                            ("Unrestricted", unrestricted),
                            ("Restricted", restricted)
                        ]
                    ],
                    itinerary=[origin["port_name"], destination["port_name"]]
                )

        except Exception as error:
            # ERROR RECOVERY — STEP 8C.2
            st.session_state.pop("persist_compare_port", None)

            st.error(f"Route comparison failed: {error}")


# ============================================================
# TAB 2 — MULTI-LEG
# ============================================================

with tab2:

    st.header("Multi-Leg Voyage Planning")

    st.write(
        "Select multiple ports to create a voyage itinerary."
    )

    # Initialize itinerary
    if "voyage_stops" not in st.session_state:
        st.session_state.voyage_stops = []

    # Port selection
    selected_stop = st.selectbox(
        "Select Port",
        port_names,
        key="multi_stop"
    )

    # Itinerary controls
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Add Stop", key="add_stop"):
            if (
                st.session_state.voyage_stops
                and st.session_state.voyage_stops[-1] == selected_stop
            ):
                st.warning("Consecutive duplicate ports are not allowed.")
            else:
                st.session_state.voyage_stops.append(selected_stop)

    with col2:
        if st.button("Remove Last Stop", key="remove_stop"):
            if st.session_state.voyage_stops:
                st.session_state.voyage_stops.pop()

    with col3:
        if st.button("Clear Itinerary", key="clear_stops"):
            st.session_state.voyage_stops = []

    # Display itinerary
    st.subheader("Current Itinerary")

    if st.session_state.voyage_stops:
        for index, port in enumerate(
            st.session_state.voyage_stops,
            start=1
        ):
            st.write(f"{index}. {port}")
    else:
        st.info("No ports added yet.")

    # Calculate multi-leg voyage
    if persisted_action("calculate_multi", (tuple(st.session_state.voyage_stops), float(speed), tuple(restrictions)), st.button(
        "Calculate Multi-Leg Voyage",
        key="calculate_multi"
    )):

        if len(st.session_state.voyage_stops) < 2:
            st.error("Please add at least two ports.")

        else:
            try:

                stops = st.session_state.voyage_stops
                validate_itinerary(stops)

                leg_results = []
                all_coordinates = []
                leg_routes = []

                total_distance = 0

                voyage_map = folium.Map(
                    location=[0, 0],
                    zoom_start=2
                )

                route_colors = [
                    "blue", "red", "green",
                    "purple", "orange", "darkblue"
                ]

                for i in range(len(stops) - 1):

                    origin = port_options[stops[i]]
                    destination = port_options[stops[i + 1]]

                    route, distance, hours, days = calculate_route(
                        origin,
                        destination
                    )

                    total_distance += distance

                    coordinates = [
                        [lat, lon]
                        for lon, lat in route.geometry["coordinates"]
                    ]

                    all_coordinates.extend(coordinates)

                    draw_route(
                        voyage_map, coordinates, restrictions,
                        f"Leg {i + 1}: {distance:,.2f} NM",
                        normal_color=route_colors[i % len(route_colors)],
                    )
                    leg_routes.append(route)

                    leg_results.append({
                        "Leg": i + 1,
                        "Origin": origin["port_name"],
                        "Destination": destination["port_name"],
                        "Distance (NM)": round(distance, 2),
                        "Duration (Days)": round(days, 2)
                    })

                # Add port markers
                for i, port_name in enumerate(stops):

                    port = port_options[port_name]

                    location = [
                        float(port["approach_latitude"]),
                        float(port["approach_longitude"])
                    ]

                    marker_color = (
                        "green" if i == 0
                        else "purple" if i == len(stops) - 1
                        else "blue"
                    )

                    folium.Marker(
                        location=location,
                        popup=f"Stop {i + 1}: {port['port_name']}",
                        icon=folium.Icon(color=marker_color)
                    ).add_to(voyage_map)

                add_excluded_markers(voyage_map, restrictions)
                add_exclusion_legend(voyage_map, restrictions)

                total_hours = total_distance / speed
                total_days = total_hours / 24

                st.session_state["persist_calculate_multi"] = (tuple(st.session_state.voyage_stops), float(speed), tuple(restrictions))
                st.success("Multi-leg voyage calculated successfully!")

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "Total Distance",
                    f"{total_distance:,.2f} NM"
                )

                col2.metric(
                    "Total Sailing Time",
                    f"{total_hours:,.2f} hours"
                )

                col3.metric(
                    "Total Sailing Duration",
                    f"{total_days:,.2f} days"
                )

                show_route_notes(leg_routes, restrictions)

                st.subheader("Leg-by-Leg Breakdown")

                st.dataframe(
                    pd.DataFrame(leg_results),
                    use_container_width=True
                )

                voyage_map.fit_bounds(all_coordinates)

                html(
                    voyage_map._repr_html_(),
                    height=550
                )


                export_voyage_results(
                    "Multi-Leg",
                    "Standard",
                    [
                        {
                            "Leg": row["Leg"],
                            "Origin": row["Origin"],
                            "Destination": row["Destination"],
                            "Distance (NM)": row["Distance (NM)"],
                            "Duration (Days)": row["Duration (Days)"]
                        }
                        for row in leg_results
                    ] + [{
                        "Leg": "TOTAL",
                        "Origin": stops[0],
                        "Destination": stops[-1],
                        "Distance (NM)": round(total_distance, 2),
                        "Duration (Days)": round(total_days, 2)
                    }],
                    itinerary=list(stops)
                )

            except Exception as error:
                # ERROR RECOVERY — STEP 8C.2
                st.session_state.pop("persist_calculate_multi", None)
                st.error(f"Multi-leg calculation failed: {error}")



    # --------------------------------------------------------
    # MULTI-LEG ROUTE COMPARISON
    # --------------------------------------------------------

    if persisted_action("compare_multi", (tuple(st.session_state.voyage_stops), float(speed), tuple(restrictions)), st.button("Compare Multi-Leg Routes", key="compare_multi")):

        if len(st.session_state.voyage_stops) < 2:

            st.error("Please add at least two ports.")

        elif not restrictions:

            st.warning(
                "Select a passage restriction before comparing routes."
            )

        else:

            try:

                stops = st.session_state.voyage_stops
                validate_itinerary(stops)

                unrestricted_routes = []
                restricted_routes = []
                markers = []
                leg_results = []

                for i in range(len(stops) - 1):

                    origin = port_options[stops[i]]
                    destination = port_options[stops[i + 1]]

                    start_coordinates = get_coordinates(origin)
                    end_coordinates = get_coordinates(destination)

                    unrestricted = calculate_comparison_route(
                        start_coordinates,
                        end_coordinates,
                        []
                    )

                    restricted = calculate_comparison_route(
                        start_coordinates,
                        end_coordinates,
                        restrictions
                    )

                    unrestricted_routes.append(unrestricted)
                    restricted_routes.append(restricted)

                    leg_results.append({
                        "Leg": i + 1,
                        "Origin": origin["port_name"],
                        "Destination": destination["port_name"],
                        "Unrestricted (NM)": round(
                            unrestricted["distance"], 2
                        ),
                        "Restricted (NM)": round(
                            restricted["distance"], 2
                        ),
                        "Difference (NM)": round(
                            restricted["distance"] - unrestricted["distance"],
                            2
                        )
                    })

                for i, port_name in enumerate(stops):

                    port = port_options[port_name]

                    markers.append({
                        "location": [
                            float(port["approach_latitude"]),
                            float(port["approach_longitude"])
                        ],
                        "name": f"Stop {i + 1}: {port['port_name']}",
                        "color": (
                            "green" if i == 0
                            else "purple" if i == len(stops) - 1
                            else "blue"
                        )
                    })

                st.session_state["persist_compare_multi"] = (tuple(st.session_state.voyage_stops), float(speed), tuple(restrictions))
                st.success("Multi-leg routes compared successfully!")

                st.subheader("Leg-by-Leg Comparison")

                st.dataframe(
                    pd.DataFrame(leg_results),
                    use_container_width=True,
                    hide_index=True
                )

                display_comparison_results(
                    unrestricted_routes,
                    restricted_routes
                )

                comparison_map = create_comparison_map(
                    unrestricted_routes,
                    restricted_routes,
                    markers
                )

                html(
                    comparison_map._repr_html_(),
                    height=550
                )


                export_voyage_results(
                    "Multi-Leg",
                    "Comparison",
                    [
                        {
                            "Leg": row["Leg"],
                            "Origin": row["Origin"],
                            "Destination": row["Destination"],
                            "Unrestricted (NM)": row["Unrestricted (NM)"],
                            "Restricted (NM)": row["Restricted (NM)"],
                            "Difference (NM)": row["Difference (NM)"]
                        }
                        for row in leg_results
                    ],
                    itinerary=list(stops)
                )

            except Exception as error:
                # ERROR RECOVERY — STEP 8C.2
                st.session_state.pop("persist_compare_multi", None)

                st.error(f"Multi-leg comparison failed: {error}")


# ============================================================
# TAB 3 — POSITION-TO-PORT
# ============================================================

with tab3:

    st.header("Position-to-Port Voyage Planning")

    st.write(
        "Enter the vessel's current coordinates and select "
        "a destination port."
    )

    # Vessel position inputs
    latitude = st.number_input(
        "Vessel Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=1.2903,
        format="%.4f",
        key="position_latitude"
    )

    longitude = st.number_input(
        "Vessel Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=103.8519,
        format="%.4f",
        key="position_longitude"
    )

    # Destination selection
    position_destination_name = st.selectbox(
        "Destination Port",
        port_names,
        key="position_destination"
    )

    if persisted_action("calculate_position", (float(latitude), float(longitude), position_destination_name, float(speed), tuple(restrictions)), st.button(
        "Calculate Position-to-Port Route",
        key="calculate_position"
    )):

        try:

            destination = port_options[
                position_destination_name
            ]

            vessel_coordinates = [float(longitude), float(latitude)]
            destination_coordinates = get_coordinates(destination)
            route = api_route(
                route_coordinates("origin", vessel_coordinates),
                {"destination_port_id": str(destination["port_id"])},
                restrictions,
            )

            distance = float(
                route.properties["length"]
            )

            if distance <= 0:
                raise ValueError(
                    "No valid maritime route was returned."
                )

            # Calculate sailing duration
            hours = distance / speed
            days = hours / 24

            st.session_state["persist_calculate_position"] = (float(latitude), float(longitude), position_destination_name, float(speed), tuple(restrictions))
            st.success(
                "Position-to-Port route calculated successfully!"
            )

            # Display results
            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Maritime Distance",
                f"{distance:,.2f} NM"
            )

            col2.metric(
                "Sailing Time",
                f"{hours:,.2f} hours"
            )

            col3.metric(
                "Sailing Duration",
                f"{days:,.2f} days"
            )

            # Create interactive map
            map_coordinates = [
                [lat, lon]
                for lon, lat in route.geometry["coordinates"]
            ]

            if not map_coordinates:
                raise ValueError(
                    "No route coordinates were returned."
                )

            voyage_map = folium.Map(
                location=[latitude, longitude],
                zoom_start=3
            )

            # Draw maritime route
            draw_route(voyage_map, map_coordinates, restrictions,
                       f"Maritime Distance: {distance:,.2f} NM")
            add_excluded_markers(voyage_map, restrictions)
            add_exclusion_legend(voyage_map, restrictions)
            show_route_notes([route], restrictions)

            # Vessel position marker
            folium.Marker(
                location=[latitude, longitude],
                popup="Current Vessel Position",
                tooltip="Vessel Position",
                icon=folium.Icon(color="green")
            ).add_to(voyage_map)

            # Destination marker
            destination_location = [
                float(destination["approach_latitude"]),
                float(destination["approach_longitude"])
            ]

            folium.Marker(
                location=destination_location,
                popup=destination["port_name"],
                tooltip="Destination Port",
                icon=folium.Icon(color="purple")
            ).add_to(voyage_map)

            # Fit map to route
            voyage_map.fit_bounds(
                map_coordinates
                + [[latitude, longitude]]
                + [destination_location]
            )

            html(
                voyage_map._repr_html_(),
                height=550
            )


            export_voyage_results(
                "Position-to-Port",
                "Standard",
                [{
                    "Destination": destination["port_name"],
                    "Distance (NM)": round(distance, 2),
                    "Duration (Hours)": round(hours, 2),
                    "Duration (Days)": round(days, 2)
                }],
                itinerary=[destination["port_name"]],
                vessel_position={
                    "latitude": float(latitude),
                    "longitude": float(longitude)
                }
            )

        except Exception as error:
            # ERROR RECOVERY — STEP 8C.2
            st.session_state.pop("persist_calculate_position", None)

            st.error(
                f"Position-to-Port calculation failed: {error}"
            )


    # --------------------------------------------------------
    # POSITION-TO-PORT ROUTE COMPARISON
    # --------------------------------------------------------

    if persisted_action("compare_position", (float(latitude), float(longitude), position_destination_name, float(speed), tuple(restrictions)), st.button("Compare Routes", key="compare_position")):

        try:

            if not restrictions:

                st.warning(
                    "Select a passage restriction before comparing routes."
                )

            else:

                destination = port_options[
                    position_destination_name
                ]

                start_coordinates = [
                    float(longitude),
                    float(latitude)
                ]

                end_coordinates = get_coordinates(destination)

                unrestricted = calculate_comparison_route(
                    start_coordinates,
                    end_coordinates,
                    []
                )

                restricted = calculate_comparison_route(
                    start_coordinates,
                    end_coordinates,
                    restrictions
                )

                st.session_state["persist_compare_position"] = (float(latitude), float(longitude), position_destination_name, float(speed), tuple(restrictions))
                st.success("Position-to-Port routes compared successfully!")

                display_comparison_results(
                    [unrestricted],
                    [restricted]
                )

                markers = [
                    {
                        "location": [
                            float(latitude),
                            float(longitude)
                        ],
                        "name": "Current Vessel Position",
                        "color": "green"
                    },
                    {
                        "location": [
                            float(destination["approach_latitude"]),
                            float(destination["approach_longitude"])
                        ],
                        "name": destination["port_name"],
                        "color": "purple"
                    }
                ]

                comparison_map = create_comparison_map(
                    [unrestricted],
                    [restricted],
                    markers
                )

                html(
                    comparison_map._repr_html_(),
                    height=550
                )


                export_voyage_results(
                    "Position-to-Port",
                    "Comparison",
                    [
                        {
                            "Route": label,
                            "Destination": destination["port_name"],
                            "Distance (NM)": round(result["distance"], 2),
                            "Duration (Days)": round(result["days"], 2)
                        }
                        for label, result in [
                            ("Unrestricted", unrestricted),
                            ("Restricted", restricted)
                        ]
                    ],
                    itinerary=[destination["port_name"]],
                    vessel_position={
                        "latitude": float(latitude),
                        "longitude": float(longitude)
                    }
                )

        except Exception as error:
            # ERROR RECOVERY — STEP 8C.2
            st.session_state.pop("persist_compare_position", None)

            st.error(
                f"Position-to-Port comparison failed: {error}"
            )
