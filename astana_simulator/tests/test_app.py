from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.ai as ai
from src.ai import AIReport, Provider

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def allocation_app():
    app = AppTest.from_file(APP).run()
    return app.selectbox(key="mode").set_value("Распределение бюджета").run()


@pytest.fixture(autouse=True)
def isolated_ai(monkeypatch):
    # Tests must never consume user credits, even when .env contains real keys.
    monkeypatch.setattr(ai, "load_providers", lambda: [
        Provider("OpenAI", ai.OPENAI_MODEL, ""),
    ])


def test_app_starts_without_keys_and_has_five_sliders():
    app = allocation_app()
    assert not app.exception
    assert len(app.slider) == 5
    assert app.button(key="run_ai").disabled
    assert not app.error
    assert any("64,58" in m.value for m in app.markdown)


def test_overbudget_blocks_score_export_and_ai_then_recovers():
    app = allocation_app()
    app.slider(key="budget_transport").set_value(100).run()
    assert not app.exception
    assert any("превышен" in e.value for e in app.error)
    assert app.button(key="run_ai").disabled
    assert not app.get("download_button")
    assert "current_fingerprint" not in app.session_state
    app.slider(key="budget_transport").set_value(20).run()
    assert not app.error
    assert not app.exception


def test_zero_budget_is_a_valid_unchanged_scenario():
    app = allocation_app()
    for slider in app.slider:
        slider.set_value(0)
    app.run()
    assert not app.error
    assert any("52,56" in m.value for m in app.markdown)


def test_official_example_and_sixth_measure_blocked():
    app = AppTest.from_file(APP).run()
    app.button(key="load_example").click().run()
    assert not app.exception
    assert not app.error
    assert any("56,54" in m.value for m in app.markdown)
    assert app.button(key="add_M1").disabled
    app.button(key="remove_M7").click().run()
    assert len(app.session_state["plan"]) == 4
    assert app.button(key="run_ai").disabled


def test_ai_is_explicit_cached_and_invalidated_on_change(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, "load_providers", lambda: [
        Provider("OpenAI", ai.OPENAI_MODEL, "test"),
    ])

    async def reports(providers, payload):
        calls.append(payload)
        return {p.name: AIReport(p.name, p.model, text=f"Отчет {p.name} для сценария") for p in providers}

    monkeypatch.setattr(ai, "generate_reports", reports)
    app = allocation_app()
    assert calls == []
    app.button(key="run_ai").click().run()
    assert not app.exception
    assert len(calls) == 1
    assert any("Отчет OpenAI" in m.value for m in app.markdown)
    app.run()
    assert len(calls) == 1
    assert app.button(key="run_ai").disabled
    app.slider(key="budget_transport").set_value(19).run()
    assert not any("Отчет OpenAI" in m.value for m in app.markdown)
    assert any("Сценарий изменен" in e.value for e in app.info)
    assert not app.button(key="run_ai").disabled
    assert len(calls) == 1


def test_failed_openai_report_can_be_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, "load_providers", lambda: [
        Provider("OpenAI", ai.OPENAI_MODEL, "test"),
    ])

    async def reports(providers, payload):
        calls.append([p.name for p in providers])
        return {
            p.name: AIReport(p.name, p.model, text="Успешный отчет")
            if len(calls) > 1
            else AIReport(p.name, p.model, error="Сервис временно недоступен")
            for p in providers
        }

    monkeypatch.setattr(ai, "generate_reports", reports)
    app = allocation_app()
    app.button(key="run_ai").click().run()
    assert not app.exception
    assert any("временно недоступен" in e.value for e in app.error)
    app.button(key="run_ai").click().run()
    assert not app.exception
    assert calls == [["OpenAI"], ["OpenAI"]]
    assert not app.error


@pytest.mark.parametrize("entry", ["app.py", "streamlit_app.py"])
def test_landing_and_baseline_remain_independent_of_scenario(entry):
    app = AppTest.from_file(str(Path(APP).with_name(entry))).run()
    assert not app.exception
    assert any('<section class="city-hero">' in m.value for m in app.markdown)
    table = next(m.value for m in app.markdown if 'class="baseline-table"' in m.value)
    assert all(name in table for name in ("Есиль", "Алматы", "Сарыарка", "Байконур", "Нура"))
    assert 'critical">35' in table and 'deficit">42' in table
    assert any("С чего начать акиму" in m.value for m in app.markdown)
    app.button(key="load_example").click().run()
    assert table == next(m.value for m in app.markdown if 'class="baseline-table"' in m.value)


def test_hud_shows_100_coins_and_keeps_budget_scale():
    app = AppTest.from_file(APP).run()
    hud = next(m.value for m in app.markdown if '<div class="game-hud">' in m.value)
    assert 'Потрачено 0 из 100' in hud
    assert '52,56' in hud
    assert 'ед. доступно' in hud
    assert not app.sidebar.children
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    assert all(s.value == 20 and s.max == 100 and s.step == 1 for s in app.slider)
    app.slider(key="budget_transport").set_value(100).run()
    assert any("80 ед." in item.value for item in app.error)


def test_header_reset_clears_both_modes_and_reports():
    app = AppTest.from_file(APP).run()
    app.button(key="load_example").click().run()
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    app.slider(key="budget_transport").set_value(18).run()
    app.button(key="reset_scenario").click().run()
    assert not app.exception
    assert app.session_state["plan"] == []
    assert app.selectbox(key="mode").value == "Каталог мероприятий"
    assert "ai_run" not in app.session_state
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    assert all(s.value == 20 for s in app.slider)


def test_mode_switch_opens_planning_and_preserves_both_plans():
    app = AppTest.from_file(APP).run()
    app.button(key="add_M7").click().run()
    app.session_state["workspace_view"] = "Карта Астаны"
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    assert not app.exception
    assert app.session_state["workspace_view"] == "Планирование"
    app.slider(key="budget_transport").set_value(18).run()
    app.selectbox(key="mode").set_value("Каталог мероприятий").run()
    assert app.session_state["workspace_view"] == "Планирование"
    assert len([b for b in app.button if b.key and b.key.startswith("add_M")]) == 14
    assert app.session_state["plan"][0].measure_id == "M7"
    app.selectbox(key="mode").set_value("Распределение бюджета").run()
    assert app.slider(key="budget_transport").value == 18


def test_reference_hero_links_to_existing_constructor():
    app = AppTest.from_file(APP).run()
    html = "\n".join(m.value for m in app.markdown)
    assert 'href="#scenario-builder"' in html and 'id="scenario-builder"' in html
    assert '<strong>100<sub> ед.</sub>' in html
    assert '<strong>52<em>.56</em>' in html
    app.button(key="load_example").click().run()
    from src.model import simulate_decisions, EXAMPLE
    score = simulate_decisions(EXAMPLE).score
    formula = next(m.value for m in app.markdown if "средний районный балл" in m.value)
    assert f"{score.average:.2f}".replace(".", ",") in formula
    assert f"{score.minimum:.2f}".replace(".", ",") in formula
