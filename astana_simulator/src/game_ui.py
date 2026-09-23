"""Presentation and explicit launch feedback; all numbers come from the model."""
from html import escape

import pandas as pd
import streamlit as st

from src.catalogue import focus_district, remove_from_plan
from src.data import BASE, BUDGET, UNIT, INDICATOR_NAMES, MEASURE_BY_ID, SYNERGIES
from src.geography import color_for
from src.model import BASELINE, simulate_decisions, validate_decisions

ICONS = {"transport": "🚎", "green": "🌳", "social": "🏫", "safety": "🛡️", "services": "⚡"}


def critical_problems(values):
    return [(INDICATOR_NAMES[k], v) for k, v in values.items() if v < 40]


def displayed_city(scenario):
    before = scenario is None or st.session_state.get("map_period") == "До"
    return (BASELINE, BASE) if before else (scenario.score, scenario.indicators)


def district_color(name, score, indicators):
    layer = st.session_state.get("map_layer", "score")
    value = {"score": score.district_scores[name],
             "gain": score.district_scores[name] - BASELINE.district_scores[name],
             "critical": len(critical_problems(indicators[name]))}[layer]
    return "rgb(" + ",".join(str(v) for v in color_for(value, layer)[:3]) + ")"


def render_header(reset):
    title, action = st.columns([4, 1], vertical_alignment="center")
    with title:
        st.markdown('<div class="game-brand"><span class="game-emblem">🏙️</span><div>'
                    '<small>ASTANA / CITY COMMAND</small><h1>Аким на 5 часов</h1>'
                    '<p>Ваш город. Пять указов. Одно будущее.</p></div></div>', unsafe_allow_html=True)
    with action:
        st.button("↻ Новый сценарий", key="reset_scenario", on_click=reset, width="stretch")


def render_hud(scenario, spent, count, catalogue_mode):
    score = scenario.score if scenario else BASELINE
    delta = score.total - BASELINE.total
    label = "Прогноз" if scenario else "Исходный рейтинг"
    if scenario and st.session_state.get("launched_fingerprint") == scenario.fingerprint:
        label = "Симуляция завершена"
    cells = [
        ("gold", "🪙 КАЗНА ГОРОДА", f"{(BUDGET-spent)/UNIT:g}", "монет доступно", f"Потрачено {spent/UNIT:g} из {BUDGET/UNIT:g}", spent / BUDGET),
        ("violet", "💜 ОДОБРЕНИЕ ЖИТЕЛЕЙ", f"{score.total:.2f}".replace(".", ","), "QoL Score / 100", f"{label} · {delta:+.2f} к базе", score.total / 100),
        ("cyan", "📜 ВАШИ УКАЗЫ" if catalogue_mode else "🎚️ НАПРАВЛЕНИЯ", str(count), "из 5 решений", "Не более двух в направлении" if catalogue_mode else "Дополнительная модель бюджета", count / 5),
        ("red" if score.critical else "cyan", "🚨 ГОРОДСКИЕ ВЫЗОВЫ", str(len(score.critical)), "критических показателей", "Порог < 40 · штраф учтён в Score", len(score.critical) / 50),
    ]
    html = '<div class="game-hud">'
    for tone, title, value, unit, note, progress in cells:
        html += (f'<article class="hud-tile {tone}"><div class="hud-label">{title}</div>'
                 f'<strong>{value}</strong><span class="hud-unit">{unit}</span><p>{note}</p>'
                 f'<div class="hud-track" role="progressbar" aria-label="{escape(title)}" aria-valuenow="{max(0,min(100,progress*100)):.0f}" aria-valuemin="0" aria-valuemax="100">'
                 f'<i style="width:{max(0,min(100,progress*100)):.1f}%"></i></div></article>')
    st.markdown(html + '</div>', unsafe_allow_html=True)
    st.caption("🪙 1 монета = 1 условная единица кейса. Одобрение — игровое название QoL Score, не опрос жителей.")


def launch_simulation():
    # Validate again at the action boundary; never trust the button's enabled state.
    plan = st.session_state["plan"]
    errors = validate_decisions(plan)
    if errors:
        st.session_state["planner_notice"] = " ".join(errors)
        return
    scenario = simulate_decisions(plan)
    seen = set(st.session_state.get("celebrated_scenarios", []))
    st.session_state["launched_fingerprint"] = scenario.fingerprint
    if scenario.fingerprint not in seen:
        seen.add(scenario.fingerprint)
        st.session_state["celebrated_scenarios"] = sorted(seen)
        st.session_state["launch_feedback"] = scenario.score.total


def render_launch(scenario, errors, catalogue_mode):
    action, status = st.columns([1, 2], vertical_alignment="center")
    if catalogue_mode:
        with action:
            done = bool(scenario and st.session_state.get("launched_fingerprint") == scenario.fingerprint)
            st.button("✓ Симуляция завершена" if done else "▶ Запустить симуляцию", key="simulate",
                      type="primary", width="stretch", disabled=bool(errors) or done, on_click=launch_simulation)
        with status:
            st.caption("8 кварталов · расчёт по правилам кейса. До запуска показан живой прогноз." if scenario
                       else "Заполните пять слотов допустимыми указами. Сейчас карта показывает исходный город.")
    if "launch_feedback" in st.session_state:
        value = st.session_state.pop("launch_feedback")
        st.toast(f"Симуляция завершена · QoL {value:.2f} / 100", icon="🏙️")
        st.balloons()
    if scenario:
        delta = scenario.score.total - BASELINE.total
        movement = "↑ Рейтинг вырос" if delta > 0 else "↓ Рейтинг снизился" if delta < 0 else "→ Рейтинг не изменился"
        st.markdown(f'<div class="resident-feed">💬 <strong>{movement}: {delta:+.2f}</strong>'
                    f' · Критических показателей: {len(scenario.score.critical)}. Реакция по расчётной модели.</div>', unsafe_allow_html=True)
        chosen = {d["measure_id"]: d["district"] for d in scenario.decisions}
        for first, second, indicator, bonus in SYNERGIES:
            actual = f"{first} + {second}: {chosen.get(first)}, {indicator} +{bonus}"
            if actual in scenario.synergies:
                st.success(f"🌟 КОМБО: {MEASURE_BY_ID[first].name} + {MEASURE_BY_ID[second].name}. "
                           f"{chosen[first]} · {INDICATOR_NAMES[indicator]} +{bonus:g} пункта.")


def render_district_cards(scenario):
    score, indicators = displayed_city(scenario)
    st.markdown('<div class="section-kicker">РАЙОНЫ / ВЫБЕРИТЕ ЗОНУ УПРАВЛЕНИЯ</div>', unsafe_allow_html=True)
    with st.container(key="district_cards"):
        columns = st.columns(5, gap="small")
        for col, name in zip(columns, BASE):
            with col, st.container(border=True):
                color = district_color(name, score, indicators)
                st.markdown(f'<div class="district-mini" style="border-color:{color}"><span>{escape(name)}</span>'
                            f'<strong>{score.district_scores[name]:.2f}<small> / 100</small></strong></div>', unsafe_allow_html=True)
                for code, value in sorted(indicators[name].items(), key=lambda x: x[1])[:3]:
                    st.markdown(f'<div class="weak-stat {"critical-stat" if value < 40 else ""}">'
                                f'{"⚠ " if value < 40 else ""}{escape(INDICATOR_NAMES[code])}<b>{value:g}</b></div>', unsafe_allow_html=True)
                st.button("📍 Выбран" if name == st.session_state["focused_district"] else "Управлять →",
                          key=f"focus_{name}", on_click=focus_district, args=(name,), width="stretch")


def render_slots(plan):
    st.subheader("📜 Пять указов акима")
    st.caption("Соберите план. Удаление указа возвращает его стоимость в доступный бюджет.")
    with st.container(key="decree_slots"):
        columns = st.columns(5, gap="small")
        for i, col in enumerate(columns):
            with col, st.container(border=True):
                if i < len(plan):
                    decision = plan[i]
                    measure = MEASURE_BY_ID[decision.measure_id]
                    st.markdown(f'<div class="decree-slot filled"><small>СЛОТ {i+1:02d} / ПРИНЯТ</small>'
                                f'<span>{ICONS[measure.sector]}</span><strong>{escape(measure.name)}</strong>'
                                f'<p>{escape(decision.district or "Весь город")} · 🪙 {measure.units}</p></div>', unsafe_allow_html=True)
                    st.button("Убрать указ", key=f"remove_{measure.id}", on_click=remove_from_plan,
                              args=(measure.id,), width="stretch")
                else:
                    st.markdown(f'<div class="decree-slot"><small>СЛОТ {i+1:02d} / СВОБОДЕН</small>'
                                '<span>＋</span><strong>Ваше следующее решение</strong><p>Выберите указ в магазине</p></div>', unsafe_allow_html=True)


def district_details(name, indicators):
    with st.expander("📊 Детали района"):
        st.dataframe(pd.DataFrame([{"Показатель": INDICATOR_NAMES[k], "До": BASE[name][k],
                                    "Сейчас": v, "Изменение": v - BASE[name][k]}
                                   for k, v in indicators[name].items()]), hide_index=True, width="stretch")
