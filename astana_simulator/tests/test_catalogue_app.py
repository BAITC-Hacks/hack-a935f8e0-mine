import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.ai as ai
from src.ai import Provider

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.fixture(autouse=True)
def isolated_ai(monkeypatch):
    monkeypatch.setattr(ai, "load_providers", lambda: [Provider("OpenAI", ai.OPENAI_MODEL, "")])


def test_empty_catalogue_then_add_remove_and_reset():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert app.session_state["plan"] == []
    assert app.button(key="run_ai").disabled
    assert len(app.get("deck_gl_json_chart")) == 1
    app.button(key="add_M7").click().run()
    assert not app.exception
    assert app.session_state["plan"][0].district == "Нура"
    app.button(key="remove_M7").click().run()
    assert app.session_state["plan"] == []
    app.button(key="load_example").click().run()
    app.button(key="reset_plan").click().run()
    assert app.session_state["plan"] == []
    assert app.button(key="run_ai").disabled


def test_map_serialization_keeps_cyrillic_labels_and_literal_deck_options():
    app = AppTest.from_file(APP).run()
    chart = app.get("deck_gl_json_chart")[0].proto
    deck = json.loads(chart.json)
    polygons, labels = deck["layers"]
    assert polygons["lineWidthUnits"] == "pixels"
    assert labels["characterSet"] == "auto"
    assert labels["fontFamily"] == "Arial"
    assert labels["getTextAnchor"] == "middle"
    assert labels["getAlignmentBaseline"] == "center"
    assert len(labels["data"]) == 5
    assert "Нура" in [row["name"] for row in labels["data"]]
    assert json.loads(chart.tooltip)["text"] == "{tooltip}"


def test_focus_sets_new_targets_without_moving_existing_measures():
    app = AppTest.from_file(APP).run()
    app.button(key="add_M7").click().run()
    app.selectbox(key="district_picker").set_value("Алматы").run()
    assert not app.exception
    assert app.session_state["focused_district"] == "Алматы"
    assert app.selectbox(key="target_M8").value == "Алматы"
    assert app.session_state["plan"][0].district == "Нура"
    app.button(key="add_M8").click().run()
    assert app.session_state["plan"][1].district == "Алматы"


def test_map_assignment_recalculates_existing_plan():
    app = AppTest.from_file(APP).run()
    app.button(key="load_example").click().run()
    original = app.session_state["current_fingerprint"]
    app.selectbox(key="district_picker").set_value("Есиль").run()
    app.selectbox(key="move_measure").set_value("M7").run()
    app.button(key="apply_map_district").click().run()
    assert not app.exception
    assert app.session_state["current_fingerprint"] != original
    assert next(d for d in app.session_state["plan"] if d.measure_id == "M7").district == "Есиль"


def test_card_target_conflict_is_rejected_and_original_preserved():
    app = AppTest.from_file(APP).run()
    app.selectbox(key="target_M4").set_value("Есиль").run()
    app.button(key="add_M4").click().run()
    app.button(key="add_M7").click().run()
    app.selectbox(key="target_M7").set_value("Есиль").run()
    assert not app.exception
    assert app.selectbox(key="target_M7").value == "Нура"
    assert any("участок" in item.value for item in app.info)


def test_switching_modes_preserves_both_plans():
    app = AppTest.from_file(APP).run()
    app.button(key="add_M7").click().run()
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    app.slider(key="budget_transport").set_value(180).run()
    app.selectbox(key="mode").set_value("Каталог мероприятий").run()
    assert app.session_state["plan"][0].measure_id == "M7"
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    assert not app.exception
    assert app.slider(key="budget_transport").value == 180
