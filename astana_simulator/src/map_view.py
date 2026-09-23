"""Interactive OSM map; click events and the accessible picker share one focus."""

from html import escape

import pydeck as pdk
import streamlit as st

from src.catalogue import focus_district, focus_from_picker, move_to_focused
from src.data import BASE, INDICATOR_NAMES, MEASURE_BY_ID
from src.geography import LAYERS, district_from_event, load_boundaries, map_data
from src.model import BASELINE, Scenario
from src.game_ui import critical_problems, district_details, district_color


def select_on_map(key: str) -> None:
    if district := district_from_event(st.session_state.get(key, {})):
        focus_district(district)


def reset_view() -> None:
    st.session_state["map_revision"] = st.session_state.get("map_revision", 0) + 1


def render_map(scenario: Scenario | None, *, catalogue_mode: bool) -> None:
    st.subheader("🛰️ Ситуационный центр")
    map_column, details_column = st.columns([3, 1], gap="medium")
    focused = st.session_state["focused_district"]
    with map_column, st.container(border=True, key="map_panel"):
        a, b = st.columns([1.4, 1])
        with a:
            layer = st.selectbox("Слой карты", list(LAYERS), format_func=LAYERS.get, key="map_layer")
        with b:
            period = st.segmented_control("Период", ["До", "После"], default="После", key="map_period",
                                          disabled=scenario is None)
        before = period == "До" or scenario is None
        data, labels = map_data(scenario, layer=layer, focused=focused, before=before)
        for label in labels:
            orders = [MEASURE_BY_ID[d.measure_id] for d in st.session_state["plan"]
                      if catalogue_mode and (d.district is None or d.district == label["name"])]
            if orders:
                label["text"] += f"\nУказов: {len(orders)}"
                label["tooltip"] += "\nВ плане: " + "; ".join(m.name for m in orders)
            label["properties"] = {"name": label["name"], "tooltip": label["tooltip"]}
        show_streets = st.session_state.get("map_streets", True)
        deck = pdk.Deck(
            map_provider="carto" if show_streets else None,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" if show_streets else None,
            initial_view_state=pdk.ViewState(latitude=51.141, longitude=71.501, zoom=8.6, min_zoom=7, max_zoom=16, pitch=0),
            layers=[
                pdk.Layer("GeoJsonLayer", id="district-polygons", data=data, pickable=True,
                          stroked=True, filled=True, get_fill_color="properties.color",
                          get_line_color="properties.outline", get_line_width="properties.line_width",
                          line_width_units="'pixels'", auto_highlight=True, highlight_color=[244, 194, 103, 90]),
                pdk.Layer("TextLayer", id="district-labels", data=labels, pickable=True,
                          get_position="position", get_text="text", get_size=13,
                          get_color=[26, 52, 55], font_family="'Arial'", font_weight=600,
                          character_set="'auto'",
                          background=True, get_background_color=[255, 254, 249, 230],
                          background_padding=[8, 5], get_text_anchor="'middle'", get_alignment_baseline="'center'"),
            ],
            tooltip={"text": "{tooltip}", "style": {"backgroundColor": "#183f3c", "color": "white", "fontSize": "12px"}},
        )
        key = f"district_map_{st.session_state.get('map_revision', 0)}"
        st.pydeck_chart(deck, height=480, key=key, on_select=lambda: select_on_map(key), selection_mode="single-object")
        tools, streets = st.columns([1, 1])
        with tools:
            st.button("↺ Весь город", key="reset_map", on_click=reset_view, width="stretch")
        with streets:
            st.toggle("Подложка улиц", value=True, key="map_streets")
        legends = {
            "score": "Золотистый → зеленый: районный балл от 45 до 80+.",
            "gain": "Светлый → зеленый: прирост от 0 до 15+ пунктов.",
            "critical": "Терракотовый: есть показатели ниже 40. Зеленый: таких показателей нет.",
        }
        st.caption("Нажмите на район для управления. Колесо — масштаб; перетаскивание — перемещение.")
        st.caption(("Исходное состояние. " if before else "Результат сценария. ") + legends[layer])
    with details_column:
        st.session_state.setdefault("district_picker", focused)
        st.selectbox("Выбранный район", list(BASE), key="district_picker", on_change=focus_from_picker)
        score = BASELINE if before else scenario.score
        indicators = BASE if before else scenario.indicators
        value = score.district_scores[focused]
        change = value - BASELINE.district_scores[focused]
        color = district_color(focused, score, indicators)
        st.markdown(f'<div class="district-focus" style="border-top:4px solid {color}"><span>📍 ЗОНА УПРАВЛЕНИЯ</span><h3>{escape(focused)}</h3>'
                    f'<strong>{value:.2f}<small> / 100</small></strong>'
                    f'<p>{change:+.2f} к базе · {"до решений" if before else "после решений"}</p></div>', unsafe_allow_html=True)

        st.markdown("**Требует внимания**")
        for code, number in sorted(indicators[focused].items(), key=lambda item: item[1])[:2]:
            st.caption(f"{INDICATOR_NAMES[code]} · {number:.1f} / 100")
            st.progress(max(0, min(1, number / 100)))
        for problem, value in critical_problems(indicators[focused]):
            st.warning(f"⚠ {problem}: {value:g} < 40. Критический дефицит.")
        district_details(focused, indicators)
        if catalogue_mode:
            st.markdown(f"**Указы для района {focused}**")
            st.markdown('<a class="shop-link" href="#decree-shop" target="_self">Открыть магазин указов ↓</a>', unsafe_allow_html=True)
            st.caption("Район уже выбран для новых указов. Принятые решения сохраняют адресатов.")
            district_measures = [d.measure_id for d in st.session_state["plan"] if d.district is not None]
            if district_measures:
                measure_id = st.selectbox("Перенести выбранную меру", district_measures,
                                          format_func=lambda m: MEASURE_BY_ID[m].name, key="move_measure")
                st.button(f"Назначить район {focused}", key="apply_map_district", on_click=move_to_focused,
                          args=(measure_id,), width="stretch")
    metadata = load_boundaries()
    st.caption("Показаны только пять районов кейса. Границы OpenStreetMap, показатели — синтетические. Подложка улиц требует интернета; контуры сохранены локально.")
    st.markdown(f'<div class="map-attribution">География: <a href="https://www.openstreetmap.org/copyright" target="_blank">© OpenStreetMap contributors · ODbL</a>'
                f' · подложка © CARTO · снимок {metadata["retrieved_at_utc"][:10]}</div>', unsafe_allow_html=True)
