"""The supplied site's catalogue / filters / selected-plan interaction in Streamlit."""

from html import escape

import streamlit as st

from src.data import BASE, HORIZON, INDICATOR_NAMES, MEASURES, MEASURE_BY_ID, SECTORS, SECTOR_BY_KEY
from src.model import Decision, EXAMPLE, InvalidScenario, validate_decisions
from src.planner import add_measure, move_measure, remove_measure

NOTES = {
    "M1": "Снижает нагрузку на дороги и ускоряет общественный транспорт.",
    "M2": "Адаптивно управляет транспортными потоками во всех районах.",
    "M3": "Крупный инфраструктурный проект с более поздним эффектом.",
    "M4": "Добавляет зеленые зоны, улучшает воздух и безопасность.",
    "M5": "Снижает загрязнение от отопления и поддерживает надежность сетей.",
    "M6": "Городская программа озеленения с равномерным эффектом.",
    "M7": "Увеличивает доступность мест в школах и детских садах.",
    "M8": "Улучшает доступ жителей к первичной медицинской помощи.",
    "M9": "Быстрое улучшение сразу нескольких показателей района.",
    "M10": "Повышает безопасность улиц и дорожного движения.",
    "M11": "Снижает риск ДТП. Компромисс — небольшое замедление потока.",
    "M12": "Ускоряет обработку обращений жителей по всему городу.",
    "M13": "Долгосрочное снижение аварийности городской инфраструктуры.",
    "M14": "Быстрый городской эффект: надежность сетей и скорость реакции.",
}


def initialize() -> None:
    st.session_state.setdefault("plan", [])
    st.session_state.setdefault("focused_district", "Нура")
    st.session_state.setdefault("pending_targets", {})
    st.session_state.setdefault("catalogue_filter", "Все")


def focus_district(name: str) -> None:
    if name not in BASE:
        return
    st.session_state["focused_district"] = name
    st.session_state["district_picker"] = name
    selected = {d.measure_id for d in st.session_state.get("plan", [])}
    pending = dict(st.session_state.get("pending_targets", {}))
    for measure in MEASURES:
        if measure.scope == "district" and measure.id not in selected:
            pending[measure.id] = name
            st.session_state[f"target_{measure.id}"] = name
    st.session_state["pending_targets"] = pending


def focus_from_picker() -> None:
    focus_district(st.session_state["district_picker"])


def reset_plan() -> None:
    st.session_state["plan"] = []
    st.session_state["catalogue_filter"] = "Все"
    st.session_state.pop("ai_run", None)
    focus_district("Нура")


def load_example() -> None:
    st.session_state["plan"] = list(EXAMPLE)
    st.session_state.pop("ai_run", None)
    focus_district("Нура")
    for decision in EXAMPLE:
        if decision.district:
            st.session_state[f"target_{decision.measure_id}"] = decision.district


def remove_from_plan(measure_id: str) -> None:
    st.session_state["plan"] = remove_measure(st.session_state["plan"], measure_id)


def toggle_measure(measure_id: str) -> None:
    plan = st.session_state["plan"]
    if any(d.measure_id == measure_id for d in plan):
        remove_from_plan(measure_id)
        return
    measure = MEASURE_BY_ID[measure_id]
    district = st.session_state.get(f"target_{measure_id}", st.session_state["focused_district"]) if measure.scope == "district" else None
    try:
        st.session_state["plan"] = add_measure(plan, measure_id, district)
    except InvalidScenario as exc:
        st.session_state["planner_notice"] = str(exc)


def change_target(measure_id: str) -> None:
    name = st.session_state[f"target_{measure_id}"]
    selected = next((d for d in st.session_state["plan"] if d.measure_id == measure_id), None)
    if selected:
        try:
            st.session_state["plan"] = move_measure(st.session_state["plan"], measure_id, name)
        except InvalidScenario as exc:
            st.session_state[f"target_{measure_id}"] = selected.district
            st.session_state["planner_notice"] = str(exc)
    else:
        st.session_state["pending_targets"][measure_id] = name


def move_to_focused(measure_id: str) -> None:
    try:
        district = st.session_state["focused_district"]
        st.session_state["plan"] = move_measure(st.session_state["plan"], measure_id, district)
        st.session_state[f"target_{measure_id}"] = district
        st.session_state["planner_notice"] = f"{measure_id} перенесено в район {district}."
    except InvalidScenario as exc:
        st.session_state["planner_notice"] = str(exc)


def render_catalogue(scenario=None) -> None:
    icons = {"transport": "🚎", "green": "🌳", "social": "🏫", "safety": "🛡️", "services": "⚡"}
    st.markdown('<div id="decree-shop" class="shop-title"><span>КОЛЛЕКЦИЯ / 14 УКАЗОВ</span><h2>🏛️ Магазин указов</h2></div>', unsafe_allow_html=True)
    st.info(f"📍 Управление: {st.session_state['focused_district']}. Район выбран на карте или карточке. "
            "Для каждого районного указа проверьте адресата перед применением.")
    filters = {"Все": None, **{s.short: s.key for s in SECTORS}}
    st.segmented_control("Направление", list(filters), key="catalogue_filter", selection_mode="single")
    active = filters.get(st.session_state.get("catalogue_filter"))
    selected = {d.measure_id: d for d in st.session_state["plan"]}
    contributions = {item["id"]: item for item in scenario.contributions} if scenario else {}
    shown = [m for m in MEASURES if active is None or m.sector == active]
    with st.container(key="decree_shop"):
        for start in range(0, len(shown), 3):
            columns = st.columns(3, gap="medium")
            for col, measure in zip(columns, shown[start:start+3]):
                sector = SECTOR_BY_KEY[measure.sector]
                is_selected = measure.id in selected
                with col, st.container(border=True, key=f"card_{measure.id}"):
                    st.markdown(
                        f'<div class="action-head {"selected-head" if is_selected else ""}">'
                        f'<span class="decree-icon">{icons[measure.sector]}</span><b>{escape(sector.short.upper())}</b>'
                        f'<span class="coin-price">🪙 {measure.units}</span></div>'
                        f'<div class="action-name">{escape(measure.name)}</div>'
                        f'<div class="action-desc">{"Один район" if measure.scope == "district" else "Весь город"} · '
                        f'лаг {measure.lag} кв. · горизонт {HORIZON} кв.</div>', unsafe_allow_html=True)
                    st.markdown('<div class="effect-row">' + ''.join(
                        f'<span class="effect {"negative" if value < 0 else ""}">{escape(INDICATOR_NAMES[k])} {value:+g}</span>'
                        for k, value in measure.effects) + '</div>', unsafe_allow_html=True)
                    target = None
                    if measure.scope == "district":
                        key = f"target_{measure.id}"
                        if key not in st.session_state:
                            st.session_state[key] = selected[measure.id].district if is_selected else st.session_state["pending_targets"].get(measure.id, st.session_state["focused_district"])
                        target = st.selectbox("📍 Район указа", list(BASE), key=key,
                                              on_change=change_target, args=(measure.id,))
                    else:
                        st.markdown('<div class="city-scope">🌐 Действует во всех пяти районах</div>', unsafe_allow_html=True)
                    with st.expander("Эффекты и детали"):
                        st.caption(f"Код: {measure.id} · стоимость: {measure.units} монет · лаг: {measure.lag} кв.")
                        st.caption("Плашки показывают полный эффект из каталога. Лаг, синергии и ограничение 0–100 учитываются калькулятором.")
                        if measure.id in contributions:
                            st.caption("Вклад из расчёта текущего плана с учётом лага, до синергий и ограничения шкалы:")
                            for code, value in contributions[measure.id]["realized_effects"].items():
                                st.write(f"{INDICATOR_NAMES[code]}: {value:+g} пункта")
                    errors = [] if is_selected else validate_decisions(
                        [*st.session_state["plan"], Decision(measure.id, target)], require_five=False)
                    st.button("✓ Принят · убрать" if is_selected else "＋ Применить указ", key=f"add_{measure.id}",
                              on_click=toggle_measure, args=(measure.id,), disabled=bool(errors),
                              help=" ".join(errors) if errors else None, width="stretch", type="primary" if is_selected else "secondary")
                    if errors:
                        st.caption("🔒 " + " ".join(errors))
    st.caption("Стоимость, эффекты и лаги — из каталога кейса. Технические ID сохранены в данных и подробностях.")
