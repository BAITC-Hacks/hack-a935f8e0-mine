"""Streamlit UI for the Akim for 5 Hours city management game."""

from __future__ import annotations

import os
import time

import streamlit as st

from calculator import (
    BUDGET,
    DISTRICTS,
    HORIZON,
    INDICATORS,
    MEASURES,
    SYNERGIES,
    ValidationError,
    calculate_score,
    validate_decisions,
)


BASELINE_SCORE = 52.56
INDICATOR_LABELS = {
    "T1": "Разгрузка дорог", "T2": "Общественный транспорт",
    "E1": "Озеленение", "E2": "Качество воздуха",
    "S1": "Школы и детсады", "S2": "Медицинская помощь",
    "B1": "Безопасность улиц", "B2": "Безопасность движения",
    "C1": "Надёжность ЖКХ", "C2": "Обращения жителей",
}

st.set_page_config(page_title="Аким на 5 часов", page_icon="🏙️", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: radial-gradient(ellipse at 15% 0%, #18314a 0, #0c1422 42%, #080d16 100%); color: #edf4ff; }
    [data-testid="stHeader"] { background: rgba(8,13,22,.75); }
    [data-testid="stMetric"] { background: linear-gradient(145deg,#17263a,#111a29); border: 1px solid #2a405b; border-radius: 16px; padding: 16px 18px; }
    .district-card { background: linear-gradient(155deg,#17263a,#101a29); border: 1px solid #2a405b; border-radius: 16px; padding: 16px; min-height: 196px; margin-bottom: 12px; }
    .district-title { font-size: 1.15rem; font-weight: 750; margin-bottom: 4px; }
    .district-sub { color: #9db0c8; font-size: .83rem; margin-bottom: 12px; }
    .critical { background: #5a2028; color: #ffd9dc; border: 1px solid #ef626c; border-radius: 8px; padding: 7px 9px; margin: 5px 0 9px; font-weight: 700; font-size: .82rem; }
    .safe { color: #8ba2bc; font-size: .82rem; }
    .section-kicker { color: #5ed8cb; text-transform: uppercase; letter-spacing: .13em; font-size: .75rem; font-weight: 750; }
    div.stButton > button[kind="primary"] { min-height: 3.1rem; border-radius: 11px; font-weight: 750; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _decision_selections() -> list[dict[str, str]]:
    decisions: list[dict[str, str]] = []
    for slot in range(1, 6):
        measure_id = st.session_state.get(f"measure_{slot}", "")
        if not measure_id:
            continue
        measure = MEASURES[measure_id]
        decision = {"measure": measure_id}
        if measure["type"] == "Район":
            decision["district"] = st.session_state.get(f"district_{slot}", next(iter(DISTRICTS)))
        decisions.append(decision)
    return decisions


def _indicator_values(decisions: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    values = {
        district: {code: float(value) for code, value in record["indicators"].items()}
        for district, record in DISTRICTS.items()
    }
    selected = {item["measure"]: item.get("district") for item in decisions}
    for measure_id, district in selected.items():
        measure = MEASURES[measure_id]
        factor = (HORIZON - measure["lag"]) / HORIZON
        targets = DISTRICTS if measure["type"] == "Город" else (district,)
        for target in targets:
            for code, effect in measure["effects"].items():
                values[target][code] += effect * factor
    for first, second, code, bonus in SYNERGIES:
        if first in selected and second in selected:
            values[selected[first]][code] += bonus
    return {
        district: {code: min(100.0, max(0.0, value)) for code, value in stats.items()}
        for district, stats in values.items()
    }


def _render_districts(values: dict[str, dict[str, float]]) -> None:
    columns = st.columns(5)
    for column, (district, record) in zip(columns, DISTRICTS.items()):
        stats = values[district]
        critical = [(code, value) for code, value in stats.items() if value < 40]
        with column:
            st.markdown(f'<div class="district-card"><div class="district-title">{district}</div><div class="district-sub">Доля населения · {record["population"]:.0%}</div>', unsafe_allow_html=True)
            if critical:
                labels = ", ".join(f"{code} · {value:.0f}" for code, value in critical)
                st.markdown(f'<div class="critical">Критическое состояние!<br>{labels}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="safe">Критических показателей нет</div>', unsafe_allow_html=True)
            for code in INDICATORS:
                st.progress(int(round(stats[code])), text=f"{code} · {INDICATOR_LABELS[code]} · {stats[code]:.0f}")
            st.markdown("</div>", unsafe_allow_html=True)


def _ask_advisor(decisions: list[dict[str, str]], score: float, values: dict[str, dict[str, float]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Чтобы получить разбор от GPT‑4o, задайте `OPENAI_API_KEY` в окружении и перезапустите приложение. Расчёт Score работает независимо от AI-советника."
    try:
        from openai import OpenAI

        decision_text = [
            f"{item['measure']} ({MEASURES[item['measure']]['direction']}, {MEASURES[item['measure']]['cost']} ед.)"
            + (f" — {item['district']}" if "district" in item else " — весь город")
            for item in decisions
        ]
        changes = {
            district: {code: round(value - DISTRICTS[district]["indicators"][code], 1) for code, value in stats.items()}
            for district, stats in values.items()
        }
        response = OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            messages=[
                {"role": "system", "content": "Ты аналитик городской политики в симуляторе. Кратко, по-русски объясни сильную сторону сценария, риск и одно практическое улучшение. Используй только данные ниже, не пересчитывай Score и не выдумывай факты."},
                {"role": "user", "content": f"Итоговый Score: {score:.2f} (база {BASELINE_SCORE:.2f}). Решения: {decision_text}. Изменения показателей по районам: {changes}."},
            ],
        )
        return response.choices[0].message.content or "Советник не вернул текст анализа."
    except Exception as exc:  # Optional integration should not break the simulator.
        return f"AI-советник сейчас недоступен ({type(exc).__name__}). Основной расчёт сценария выполнен."


st.title("🏙️ Аким на 5 часов")
st.caption("Astana Innovations · симулятор управления городом · горизонт 2 года / 8 кварталов")

if "score" not in st.session_state:
    st.session_state.score = BASELINE_SCORE
    st.session_state.has_simulated = False

top_budget, top_score, top_round = st.columns([1, 1, 1])
selected_now = _decision_selections()
spent_now = sum(MEASURES[item["measure"]]["cost"] for item in selected_now)
top_budget.metric("Виртуальный бюджет", f"{max(0, BUDGET - spent_now)} / {BUDGET} ед.", delta=f"Выбрано на {spent_now} ед.", delta_color="off")
top_score.metric("Astana Quality of Life Score", f"{st.session_state.score:.2f}", delta=f"{st.session_state.score - BASELINE_SCORE:+.2f} к базе")
top_round.metric("Горизонт симуляции", "8 кварталов", delta="2 года", delta_color="off")

st.markdown('<div class="section-kicker">Карта города</div>', unsafe_allow_html=True)
district_data = _indicator_values(selected_now) if len(selected_now) == 5 else {
    district: record["indicators"] for district, record in DISTRICTS.items()
}
_render_districts(district_data)

st.markdown('<div class="section-kicker">План управления · выберите ровно 5 решений</div>', unsafe_allow_html=True)
selector_columns = st.columns(5)
measure_options = [""] + list(MEASURES)
for slot, column in enumerate(selector_columns, start=1):
    with column:
        st.markdown(f"**Решение {slot}**")
        measure_id = st.selectbox(
            "Мероприятие", measure_options,
            format_func=lambda value: "— выберите —" if not value else f"{value} · {MEASURES[value]['direction']} · {MEASURES[value]['cost']} ед.",
            key=f"measure_{slot}", label_visibility="collapsed",
        )
        if measure_id:
            measure = MEASURES[measure_id]
            st.caption(f"{measure['type']} · лаг {measure['lag']} кв.")
            if measure["type"] == "Район":
                st.selectbox("Район", list(DISTRICTS), key=f"district_{slot}")

decisions = _decision_selections()
spent = sum(MEASURES[item["measure"]]["cost"] for item in decisions)
st.progress(min(spent / BUDGET, 1.0), text=f"Использовано {spent} из {BUDGET} ед.")

try:
    validate_decisions(decisions)
    validation_message = None
except ValidationError as error:
    validation_message = str(error)

if validation_message:
    st.info(f"Для запуска симуляции: {validation_message}")

simulate = st.button("▶  Симулировать 2 года (8 кварталов)", type="primary", use_container_width=True, disabled=validation_message is not None)
if simulate:
    with st.status("Симулируем последствия решений…", expanded=True) as status:
        st.write("Применяем эффекты с учётом лагов и синергий")
        time.sleep(0.7)
        result_score = calculate_score(decisions)
        result_indicators = _indicator_values(decisions)
        st.write("Пересчитываем показатели районов и критические значения")
        time.sleep(0.4)
        st.session_state.score = result_score
        st.session_state.has_simulated = True
        st.session_state.last_decisions = decisions
        status.update(label="Симуляция завершена", state="complete", expanded=False)
    st.rerun()

if st.session_state.has_simulated:
    st.subheader("Результат сценария")
    delta = st.session_state.score - BASELINE_SCORE
    st.metric("Новый городской Score", f"{st.session_state.score:.2f}", delta=f"{delta:+.2f} к базовому 52.56")
    st.markdown("### AI-советник · GPT‑4o")
    advisor_key = repr((st.session_state.last_decisions, round(st.session_state.score, 6)))
    if st.session_state.get("advisor_key") != advisor_key:
        with st.spinner("Готовим аналитический разбор…"):
            st.session_state.advisor_text = _ask_advisor(
                st.session_state.last_decisions,
                st.session_state.score,
                _indicator_values(st.session_state.last_decisions),
            )
            st.session_state.advisor_key = advisor_key
    advice = st.session_state.advisor_text
    st.info(advice)

