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
    app.slider(key="budget_transport").set_value(1000).run()
    assert not app.exception
    assert any("превышен" in e.value for e in app.error)
    assert app.button(key="run_ai").disabled
    assert not app.get("download_button")
    assert "current_fingerprint" not in app.session_state
    app.slider(key="budget_transport").set_value(200).run()
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
    app.slider(key="budget_transport").set_value(190).run()
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
def test_city_baseline_is_first_and_independent_of_scenario(entry):
    app = AppTest.from_file(str(Path(APP).with_name(entry))).run()
    assert not app.exception
    assert app.subheader[0].value == "Текущее состояние города и дефициты"
    table = next(m.value for m in app.markdown if 'class="baseline-table"' in m.value)
    assert all(name in table for name in ("Есиль", "Алматы", "Сарыарка", "Байконур", "Нура"))
    assert 'critical">35' in table and 'deficit">42' in table
    assert any("С чего начать акиму" in m.value for m in app.markdown)
    app.button(key="load_example").click().run()
    assert table == next(m.value for m in app.markdown if 'class="baseline-table"' in m.value)
