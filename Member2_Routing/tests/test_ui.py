"""End-to-end tests of the Streamlit app (app.py), driven with Streamlit's AppTest.

The app is run with VOYAGE_API_URL=local so it calls the engine in-process (no
network).  Each test clicks real widgets and reads the rendered metrics, tables,
warnings and the HTML of the folium map.
"""
import os
import sys

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("folium")
pytest.importorskip("pandas")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from voyage_planner import VoyagePlanner  # noqa: E402

APP = os.path.join(ROOT, "app.py")
HALO, RED = "ffd400", "d62728"          # highlight colours used by app.draw_route
ENGINE = VoyagePlanner()


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_URL", "local")


def new_app():
    at = AppTest.from_file(APP, default_timeout=240).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def pick(at, key, prefix):
    box = at.selectbox(key=key)
    box.select([o for o in box.options if o.startswith(prefix)][0])


def exclude(at, *ids):
    at.multiselect(key="excluded_passages").set_value(list(ids)).run()


def map_html(at):
    frames = at.get("iframe")
    return " ".join(getattr(f.proto, "srcdoc", "") or "" for f in frames)


def metric(at, label):
    return [m.value for m in at.metric if m.label == label]


def table(at):
    return [d.value.to_dict("list") for d in at.dataframe]


def port_to_port(at, origin, destination):
    pick(at, "origin", origin)
    pick(at, "destination", destination)
    at.run()


# ------------------------------------------------------------------ exclusion selector
def test_selector_offers_all_six_canals_straits_and_capes():
    at = new_app()
    options = at.multiselect(key="excluded_passages").options
    assert len(options) == 6
    text = " ".join(options)
    for name in ("Panama Canal", "Suez Canal", "Gibraltar", "Malacca", "Cape Horn", "Cape of Good Hope"):
        assert name in text
    assert sum("(cape)" in o for o in options) == 2 and sum("(canal)" in o for o in options) == 2
    assert at.multiselect(key="excluded_passages").value == []


# ------------------------------------------------------------------ port-to-port
def test_known_result_default_route_is_not_highlighted():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    at.button(key="calculate_port").click().run()
    assert not at.exception and not at.error
    assert metric(at, "Maritime Distance") == ["8,368.20 NM"]
    html = map_html(at)
    assert HALO not in html and "EXCLUDED:" not in html             # plain blue route
    assert any("Passages on this route" in c.value for c in at.caption)


def test_known_result_suez_and_panama_excluded_is_highlighted():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "SUEZ", "PANAMA")
    at.button(key="calculate_port").click().run()
    assert not at.exception and not at.error
    assert metric(at, "Maritime Distance") == ["11,856.30 NM"]
    assert any("Highlighted route" in w.value and "Suez Canal" in w.value and "Panama Canal" in w.value
               and "Cape of Good Hope" in w.value for w in at.warning)
    html = map_html(at)
    assert HALO in html and RED in html                              # halo + red line
    assert "EXCLUDED: Suez Canal" in html and "EXCLUDED: Panama Canal" in html
    assert "avoids: Panama Canal, Suez Canal" in html               # legend


@pytest.mark.parametrize("origin,dest,excluded,must_not_use", [
    ("SGSIN", "NLRTM", ["SUEZ"], "SUEZ"),
    ("SGSIN", "NLRTM", ["MALACCA"], "MALACCA"),
    ("SGSIN", "NLRTM", ["SUEZ", "CAPE_GOOD_HOPE"], "CAPE_GOOD_HOPE"),
    ("NLRTM", "ZADUR", ["CAPE_GOOD_HOPE"], "CAPE_GOOD_HOPE"),
    ("NLRTM", "EGSUZ", ["GIBRALTAR"], "GIBRALTAR"),
    ("USHOU", "CLTOQ", ["PANAMA"], "PANAMA"),
    ("USHOU", "CLTOQ", ["PANAMA", "CAPE_HORN"], "CAPE_HORN"),
])
def test_every_passage_can_be_excluded_and_ui_matches_engine(origin, dest, excluded, must_not_use):
    expected = ENGINE.handle_route({"origin_port_id": origin, "destination_port_id": dest,
                                    "excluded_passage": excluded})
    assert expected["status"] == "success" and must_not_use not in expected["passages_used"]
    names = {p["port_id"]: f"{p['port_name']} ({p['country']})" for p in ENGINE.list_ports()}
    at = new_app()
    at.selectbox(key="origin").select(names[origin])
    at.selectbox(key="destination").select(names[dest])
    exclude(at, *excluded)
    at.button(key="calculate_port").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert metric(at, "Maritime Distance") == [f"{expected['distance_nm']:,.2f} NM"]
    assert HALO in map_html(at)


def test_same_origin_and_destination_is_rejected_cleanly():
    at = new_app()
    port_to_port(at, "Singapore", "Singapore")
    at.button(key="calculate_port").click().run()
    assert not at.exception and at.error and "different" in at.error[0].value


def test_compare_routes_table_and_highlight():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "SUEZ", "PANAMA")
    at.button(key="compare_port").click().run()
    assert not at.exception and not at.error
    df = table(at)[0]
    assert df["Route"] == ["Unrestricted", "Restricted", "Difference"]
    assert df["Distance (NM)"] == [8368.2, 11856.3, 3488.1]
    assert "Suez Canal" in df["Passages used"][0] and "Suez Canal" not in df["Passages used"][1]
    assert df["Passages used"][1] == "Cape of Good Hope"
    assert any("Highlighted (restricted) route excludes" in w.value for w in at.warning)
    html = map_html(at)
    assert HALO in html and "Restricted Route (highlighted)" in html and "EXCLUDED: Suez Canal" in html


def test_compare_without_exclusions_asks_for_one():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    at.button(key="compare_port").click().run()
    assert not at.exception and any("Select a passage restriction" in w.value for w in at.warning)


def test_compare_notes_when_exclusion_changes_nothing():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "PANAMA")                                   # Singapore-Rotterdam never uses Panama
    at.button(key="compare_port").click().run()
    assert table(at)[0]["Distance (NM)"][2] == 0.0
    assert any("did not change the route" in i.value for i in at.info)


# ------------------------------------------------------------------ position-to-port
def position_to_port(at, lat, lon, dest):
    at.number_input(key="position_latitude").set_value(lat)
    at.number_input(key="position_longitude").set_value(lon)
    pick(at, "position_destination", dest)
    at.run()


@pytest.mark.parametrize("excluded", [[], ["SUEZ", "PANAMA"]])
def test_known_result_position_to_rotterdam_is_2174_90_either_way(excluded):
    at = new_app()
    position_to_port(at, 35.0, -40.0, "Rotterdam")
    if excluded:
        exclude(at, *excluded)
    at.button(key="calculate_position").click().run()
    assert not at.exception and not at.error
    assert metric(at, "Maritime Distance") == ["2,174.90 NM"]
    assert (HALO in map_html(at)) == bool(excluded)


def test_position_calculate_then_compare_works():
    at = new_app()
    position_to_port(at, 1.2903, 103.8519, "Rotterdam")
    exclude(at, "SUEZ", "PANAMA")
    at.button(key="calculate_position").click().run()
    assert metric(at, "Maritime Distance") == ["11,856.30 NM"]
    at.button(key="compare_position").click().run()          # Calculate, then Compare
    assert not at.exception and not at.error
    assert table(at)[0]["Distance (NM)"] == [8368.2, 11856.3, 3488.1]
    assert metric(at, "Maritime Distance") == ["11,856.30 NM"]   # the Calculate result is still shown
    at.run()                                                  # a rerun (e.g. a download click) keeps results
    assert not at.exception and table(at)[0]["Distance (NM)"][1] == 11856.3


def test_position_compare_with_unused_canals_shows_zero_difference():
    at = new_app()
    position_to_port(at, 35.0, -40.0, "Rotterdam")
    exclude(at, "SUEZ", "PANAMA")
    at.button(key="calculate_position").click().run()
    at.button(key="compare_position").click().run()
    assert not at.exception and table(at)[0]["Distance (NM)"] == [2174.9, 2174.9, 0.0]
    assert any("did not change the route" in i.value for i in at.info)


# ------------------------------------------------------------------ multi-leg
def test_multi_leg_total_is_sum_of_legs_and_highlighted():
    at = new_app()
    for name in ("Singapore", "Rotterdam", "Durban"):
        pick(at, "multi_stop", name)
        at.button(key="add_stop").click().run()
    exclude(at, "SUEZ")
    at.button(key="calculate_multi").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    legs = [ENGINE.port_to_port(a, b, excluded_passage="SUEZ")["distance_nm"]
            for a, b in (("SGSIN", "NLRTM"), ("NLRTM", "ZADUR"))]
    assert metric(at, "Total Distance") == [f"{sum(legs):,.2f} NM"]
    assert HALO in map_html(at) and "EXCLUDED: Suez Canal" in map_html(at)


# ------------------------------------------------------------------ failure handling
def test_impossible_exclusions_show_a_message_not_a_traceback():
    # Port Said -> Rotterdam with Gibraltar and Suez blocked: the engine answers ROUTE_NOT_FOUND
    expected = ENGINE.handle_route({"origin_port_id": "EGPSD", "destination_port_id": "NLRTM",
                                    "excluded_passage": ["GIBRALTAR", "SUEZ"]})
    assert expected["error_code"] == "ROUTE_NOT_FOUND"
    at = new_app()
    port_to_port(at, "Port Said", "Rotterdam")
    exclude(at, "GIBRALTAR", "SUEZ")
    at.button(key="calculate_port").click().run()
    assert not at.exception
    assert at.error and expected["message"][:40] in at.error[0].value
    assert not metric(at, "Maritime Distance")                 # no distance is shown for a failed route


def test_excluding_everything_still_returns_the_engines_answer():
    """Four exclusions for Singapore-Rotterdam leave the long way round; the UI shows exactly the engine's figure."""
    expected = ENGINE.handle_route({"origin_port_id": "SGSIN", "destination_port_id": "NLRTM",
                                    "excluded_passage": ["SUEZ", "PANAMA", "CAPE_GOOD_HOPE", "CAPE_HORN"]})
    assert expected["status"] == "success" and expected["passages_used"] == []
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "SUEZ", "PANAMA", "CAPE_GOOD_HOPE", "CAPE_HORN")
    at.button(key="calculate_port").click().run()
    assert not at.exception and not at.error
    assert metric(at, "Maritime Distance") == [f"{expected['distance_nm']:,.2f} NM"]
    assert any("none of the six reference passages" in w.value for w in at.warning)


def test_unreachable_api_shows_clear_message(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_URL", "http://127.0.0.1:9")
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "SUEZ")
    at.button(key="calculate_port").click().run()
    assert not at.exception and at.error and "Could not reach the routing API" in at.error[0].value


def test_data_warnings_are_shown_for_flagged_port():
    at = new_app()
    port_to_port(at, "Houston", "Tocopilla")
    at.button(key="calculate_port").click().run()
    assert not at.exception
    notes = " ".join(e.label for e in at.expander)
    assert "Route notes" in notes
    assert "114.2 nm" in " ".join(m.value for m in at.markdown)


# ------------------------------------------------------------------ exports
def test_export_buttons_present_after_calculate_and_compare():
    at = new_app()
    port_to_port(at, "Singapore", "Rotterdam")
    exclude(at, "SUEZ")
    at.button(key="calculate_port").click().run()
    labels = [b.proto.label for b in at.get("download_button")]
    assert labels.count("Download CSV") == 1 and labels.count("Download JSON") == 1
    at.button(key="compare_port").click().run()
    assert [b.proto.label for b in at.get("download_button")].count("Download CSV") >= 1
