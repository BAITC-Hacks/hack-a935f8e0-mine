import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.ai as ai
from src.ai import Provider
from src.data import BASE, MEASURE_BY_ID
from src.geography import color_for
from src.model import BASELINE, Decision, EXAMPLE, simulate_decisions, validate_decisions
from src.game_ui import critical_problems, launch_simulation

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def isolated_ai(monkeypatch):
    monkeypatch.setattr(ai, "load_providers", lambda: [Provider("OpenAI", ai.OPENAI_MODEL, "")])


def test_launch_requires_five_and_feedback_does_not_repeat():
    app = AppTest.from_file(APP).run()
    assert app.button(key="simulate").disabled
    assert not app.get("balloons") and not app.get("toast")
    app.button(key="load_example").click().run()
    assert not app.button(key="simulate").disabled
    assert not app.get("balloons")
    app.button(key="simulate").click().run()
    assert not app.exception
    assert app.session_state["launched_fingerprint"] == simulate_decisions(EXAMPLE).fingerprint
    assert len(app.get("balloons")) == 1 and len(app.get("toast")) == 1
    assert app.button(key="simulate").disabled
    app.run()
    assert not app.get("balloons") and not app.get("toast")
    app.button(key="focus_Есиль").click().run()
    assert not app.get("balloons") and not app.get("toast")
    app.button(key="remove_M7").click().run()
    assert app.button(key="simulate").disabled
    app.button(key="load_example").click().run()
    assert not app.get("balloons")


def test_district_cards_focus_shop_and_preserve_existing_targets():
    app = AppTest.from_file(APP).run()
    app.button(key="add_M7").click().run()
    app.button(key="focus_Алматы").click().run()
    assert app.selectbox(key="target_M7").value == "Нура"
    assert app.selectbox(key="target_M8").value == "Алматы"
    app.button(key="add_M8").click().run()
    app.button(key="add_M12").click().run()
    assert app.session_state["plan"] == [Decision("M7", "Нура"), Decision("M8", "Алматы"), Decision("M12")]
    hud = next(m.value for m in app.markdown if '<div class="game-hud">' in m.value)
    assert "Потрачено 58 из 100" in hud
    deck = json.loads(app.get("deck_gl_json_chart")[0].proto.json)
    labels = {x["name"]: x for x in deck["layers"][1]["data"]}
    assert "Указов: 2" in labels["Нура"]["text"]
    assert "Указов: 1" in labels["Есиль"]["text"]
    assert "Цифровая платформа" in labels["Есиль"]["tooltip"]
    app.button(key="remove_M12").click().run()
    hud = next(m.value for m in app.markdown if '<div class="game-hud">' in m.value)
    assert "Потрачено 44 из 100" in hud


def test_actual_critical_warnings_period_and_shared_colors():
    app = AppTest.from_file(APP).run()
    assert any("Школы и детсады: 38 < 40" in x.value for x in app.warning)
    app.button(key="load_example").click().run()
    assert not any("Критический дефицит" in x.value for x in app.warning)
    app.segmented_control(key="map_period").set_value("До").run()
    assert any("Школы и детсады: 38 < 40" in x.value for x in app.warning)
    card = next(m.value for m in app.markdown if 'class="district-mini"' in m.value and "Нура" in m.value)
    expected = "rgb(" + ",".join(map(str, color_for(BASELINE.district_scores["Нура"], "score")[:3])) + ")"
    assert expected in card
    assert critical_problems({"S1": 40}) == []


def test_combo_uses_real_bonus_and_disappears_with_incomplete_plan():
    app = AppTest.from_file(APP).run()
    app.button(key="load_example").click().run()
    combos = [x.value for x in app.success if "КОМБО" in x.value]
    assert len(combos) == 1
    assert "Нура · Безопасность улиц +2 пункта" in combos[0]
    app.button(key="remove_M12").click().run()
    assert not any("КОМБО" in x.value for x in app.success)


@pytest.mark.parametrize("plan", [
    EXAMPLE[:4], [Decision("M7", "Нура")] * 5,
    [Decision("M7", "Ошибка"), *EXAMPLE[1:]],
    [Decision("M3", "Есиль"), Decision("M13", "Нура"), Decision("M7", "Нура"), Decision("M8", "Нура"), Decision("M2")],
])
def test_launch_action_rechecks_exact_validator_errors(monkeypatch, plan):
    import src.game_ui as game
    state = {"plan": plan}
    monkeypatch.setattr(game.st, "session_state", state)
    launch_simulation()
    assert state["planner_notice"] == " ".join(validate_decisions(plan))
    assert "launched_fingerprint" not in state
    assert "launch_feedback" not in state


def test_card_titles_hide_ids_but_keep_real_negative_effect_and_lag():
    app = AppTest.from_file(APP).run()
    card = next(m.value for m in app.markdown if 'class="action-name"' in m.value and MEASURE_BY_ID["M11"].name in m.value)
    assert "M11" not in card and "лаг 1 кв." in card
    assert any("Разгрузка дорог -2" in m.value for m in app.markdown)
    assert any("Код: M11" in c.value for c in app.caption)


def test_realized_card_effects_come_from_calculator():
    app = AppTest.from_file(APP).run()
    app.button(key="load_example").click().run()
    app.button(key="remove_M10").click().run()
    app.button(key="add_M11").click().run()
    assert not app.exception
    assert any("Разгрузка дорог: -1.75 пункта" in m.value for m in app.markdown)
    assert not any("КОМБО" in x.value for x in app.success)
