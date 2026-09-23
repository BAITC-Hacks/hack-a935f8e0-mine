"""Interactive map-first Streamlit game for the Akim for 5 Hours."""

from __future__ import annotations

import os
import time

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium
from streamlit_lottie import st_lottie

from calculator import (
    BUDGET, DISTRICTS, HORIZON, INDICATORS, MEASURES, SYNERGIES, WEIGHTS,
    ValidationError, calculate_score, validate_decisions,
)

BASELINE_SCORE = 52.56
ASTANA_CENTER = (51.1271, 71.4328)
DISTRICT_CENTERS = {
    "Есиль": (51.184, 71.405), "Нура": (51.184, 71.530),
    "Сарыарка": (51.128, 71.355), "Байконур": (51.128, 71.475),
    "Алматы": (51.075, 71.420),
}
LOTTIE_URLS = {
    "eco": "https://raw.githubusercontent.com/xvrh/lottie-flutter/master/example/assets/lottiefiles/StreetByMorning.json",
    "traffic": "https://raw.githubusercontent.com/xvrh/lottie-flutter/master/example/assets/lottiefiles/socar_logo.json",
    "joy": "https://cdn.prod.website-files.com/5d829bf092d4644f5c42e0ea/5def871cca4d3b3d86d6ee1b_Success-Pack9-smooth.json",
}
MEASURE_MARKERS = {
    "M1": ("🚌", "bus", "blue"), "M2": ("🚦", "traffic-light", "orange"),
    "M3": ("🚈", "train", "darkblue"), "M4": ("🌳", "tree", "green"),
    "M5": ("🍃", "leaf", "lightgreen"), "M6": ("🌲", "tree", "green"),
    "M7": ("🏫", "graduation-cap", "cadetblue"), "M8": ("🏥", "hospital-o", "red"),
    "M9": ("⚽", "futbol-o", "darkgreen"), "M10": ("💡", "video-camera", "darkred"),
    "M11": ("🚸", "road", "orange"), "M12": ("📱", "mobile", "purple"),
    "M13": ("🚰", "tint", "blue"), "M14": ("🧰", "wrench", "darkpurple"),
}
INDICATOR_INFO = {
    "T1": ("🚦", "Трафик"), "T2": ("🚌", "Транспорт"),
    "E1": ("🌳", "Зелень"), "E2": ("💨", "Воздух"),
    "S1": ("🏫", "Школы"), "S2": ("🏥", "Больницы"),
    "B1": ("🚓", "Безопасность улиц"), "B2": ("🚸", "Безопасность дорог"),
    "C1": ("💧", "ЖКХ"), "C2": ("📬", "Обращения жителей"),
}
DISTRICT_ICONS = {"Есиль": "🏙️", "Алматы": "🏘️", "Сарыарка": "🌆", "Байконур": "🏗️", "Нура": "🌱"}
# Игровые приближения, не официальные административные границы. GeoJSON: [lon, lat].
DISTRICT_POLYGONS = {
    "Есиль": [[71.355, 51.145], [71.465, 51.145], [71.485, 51.205], [71.405, 51.235], [71.335, 51.205], [71.355, 51.145]],
    "Нура": [[71.465, 51.145], [71.555, 51.145], [71.585, 51.205], [71.515, 51.235], [71.485, 51.205], [71.465, 51.145]],
    "Сарыарка": [[71.305, 51.105], [71.405, 51.105], [71.425, 51.145], [71.355, 51.145], [71.315, 51.165], [71.305, 51.105]],
    "Байконур": [[71.405, 51.105], [71.505, 51.105], [71.525, 51.145], [71.465, 51.145], [71.425, 51.145], [71.405, 51.105]],
    "Алматы": [[71.365, 51.045], [71.475, 51.045], [71.505, 51.105], [71.405, 51.105], [71.345, 51.105], [71.365, 51.045]],
}
MEASURE_CARDS = {
    "M1": ("🚌", "Автобусные полосы", "Выделенные полосы для автобусов"),
    "M2": ("🚦", "Умные светофоры", "Адаптивно управляют потоками во всём городе"),
    "M3": ("🚈", "Построить ЛРТ", "Новая линия или расширение сети"),
    "M4": ("🌳", "Парк или сквер", "Новое зелёное общественное пространство"),
    "M5": ("🍃", "Чистое топливо", "Перевод частного сектора на чистое топливо"),
    "M6": ("🌲", "Зелёный пояс", "Озеленение и ветрозащитные полосы города"),
    "M7": ("🏫", "Модульная школа", "Школа и детский сад в районе"),
    "M8": ("🏥", "Семейная клиника", "Центр здоровья и первичной помощи"),
    "M9": ("⚽", "Спорт-хабы", "Спорт и активный отдых во дворах"),
    "M10": ("💡", "Камеры Safe City", "Освещение и камеры безопасности"),
    "M11": ("🚸", "Безопасные переходы", "Переходы и школьные зоны"),
    "M12": ("📱", "Цифровая платформа", "Единый сервис обращений жителей"),
    "M13": ("🚰", "Новые сети ЖКХ", "Модернизация тепловых и водных сетей"),
    "M14": ("🧰", "Аварийные бригады", "Бригады ЖКХ и раннее оповещение"),
}

st.set_page_config(page_title="Аким на 5 часов · Ситуационный центр", page_icon="🗺️", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');
.stApp{background:radial-gradient(ellipse at 50% -15%,#203c50 0%,#111d29 48%,#080d14 100%);color:#eff4f5;font-family:'Nunito',sans-serif}
[data-testid="stHeader"]{background:transparent}h1,h2,h3,p,label{font-family:'Nunito',sans-serif!important}
.hero{background:linear-gradient(105deg,#1d394a,#1b3040 58%,#354729);border:1px solid #506d60;border-radius:19px;padding:18px 25px;margin:3px 0 15px;box-shadow:0 12px 35px #0006}
.kicker{color:#a9d88b;font-size:.72rem;font-weight:900;letter-spacing:.16em;text-transform:uppercase}
.hud{background:linear-gradient(150deg,#26394a,#192735);border:1px solid #486073;border-bottom:4px solid #b38b44;border-radius:15px;padding:10px 16px;min-height:91px;box-shadow:0 7px 15px #0004}
.hud-label{color:#b9cbd0;font-weight:900;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase}.hud-value{color:#fff2c6;font-size:1.7rem;font-weight:900;line-height:1.22}.hud-note{color:#a9bbc5;font-size:.77rem}
.side-card{background:linear-gradient(155deg,#253a48,#172631);border:1px solid #49606b;border-radius:13px;padding:12px;margin:8px 0;color:#f1f5eb}
.combo{background:linear-gradient(90deg,#594526,#382f25);border:1px solid #e5b84d;border-radius:12px;padding:12px 15px;color:#ffebaa;font-weight:900}
div.stButton>button{border-radius:10px;font-weight:900;border:1px solid #728d80}
div.stButton>button[kind="primary"]{background:linear-gradient(180deg,#86b853,#558d45);border:1px solid #b2d67d;color:#102013;min-height:2.8rem;box-shadow:0 4px 0 #385d34}
[data-testid="stExpander"]{background:#172530;border:1px solid #405763;border-radius:11px}
</style>
""", unsafe_allow_html=True)


def _initial_indicators() -> dict[str, dict[str, float]]:
    return {name: {code: float(value) for code, value in row["indicators"].items()} for name, row in DISTRICTS.items()}


def _apply_effects(decisions: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """Generate map values using the calculator's lag, synergy and clipping rules."""
    values = _initial_indicators()
    selected = {item["measure"]: item.get("district") for item in decisions}
    for measure_id, district in selected.items():
        measure = MEASURES[measure_id]
        factor = (HORIZON - measure["lag"]) / HORIZON
        targets = DISTRICTS if measure["type"] == "Город" else (district,)
        for target in targets:
            for indicator, effect in measure["effects"].items():
                values[target][indicator] += effect * factor
    for first, second, indicator, bonus in SYNERGIES:
        if first in selected and second in selected:
            values[selected[first]][indicator] += bonus
    return {name: {code: min(100.0, max(0.0, value)) for code, value in stats.items()} for name, stats in values.items()}


def _district_score(values: dict[str, float]) -> float:
    return sum(WEIGHTS[code] * values[code] for code in INDICATORS)


def _color(score: float) -> str:
    if score < 50:
        return "#e34b4b"
    if score <= 60:
        return "#e8ba48"
    return "#54bd78"


def _geojson(values: dict[str, dict[str, float]]) -> dict:
    features = []
    for district, ring in DISTRICT_POLYGONS.items():
        stats = values[district]
        score = _district_score(stats)
        issues = []
        for code, value in stats.items():
            if value < 40:
                if district == "Нура" and code == "S1":
                    issues.append(f"🚨 Нура: Проблема со школами! ({value:.0f})")
                else:
                    icon, label = INDICATOR_INFO[code]
                    issues.append(f"⚠️ {icon} {label}: {value:.0f}")
        if not issues:
            issues = ["Критических показателей нет"]
        features.append({
            "type": "Feature",
            "properties": {"district": district, "score": round(score, 1), "problems": "<br>".join(issues), "fill": _color(score)},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    return {"type": "FeatureCollection", "features": features}


def _render_map(values: dict[str, dict[str, float]], applied_decisions: list[dict[str, str]] | None = None) -> None:
    city_map = folium.Map(location=ASTANA_CENTER, zoom_start=11, tiles="CartoDB dark_matter", control_scale=True)
    folium.GeoJson(
        _geojson(values),
        name="Районы Астаны",
        style_function=lambda feature: {"fillColor": feature["properties"]["fill"], "color": "#f2f5f5", "weight": 2, "fillOpacity": 0.56},
        highlight_function=lambda feature: {"weight": 4, "color": "#ffffff", "fillOpacity": 0.78},
        tooltip=folium.GeoJsonTooltip(
            fields=["district", "score", "problems"],
            aliases=["Район", "QoL Score", "Слабые места"],
            localize=True, sticky=False, labels=True,
            style="background-color:#17232d;color:#f5f5f5;font-family:Nunito,sans-serif;font-size:13px;padding:10px;border:1px solid #81919a;border-radius:8px;",
        ),
    ).add_to(city_map)
    # City-wide initiatives receive one marker in each district; local measures
    # are pinned to the center of the district they affect.
    for decision in applied_decisions or []:
        measure_id = decision["measure"]
        emoji, fa_icon, color = MEASURE_MARKERS[measure_id]
        targets = [decision["district"]] if "district" in decision else list(DISTRICT_CENTERS)
        title = MEASURE_CARDS[measure_id][1]
        for district in targets:
            folium.Marker(
                location=DISTRICT_CENTERS[district],
                tooltip=f"{emoji} {title} · {district}",
                popup=f"{emoji} <b>{title}</b><br>{district}",
                icon=folium.Icon(color=color, icon=fa_icon, prefix="fa"),
            ).add_to(city_map)
    folium.Marker(
        ASTANA_CENTER, tooltip="Ситуационный центр · Астана",
        icon=folium.DivIcon(html="<div style='font-size:24px;filter:drop-shadow(0 1px 4px #000)'>🏛️</div>"),
    ).add_to(city_map)
    legend = """<div style="position:fixed;bottom:26px;left:26px;z-index:9999;background:#111d29ee;color:#f4f4f4;padding:11px 14px;border:1px solid #71808c;border-radius:9px;font:13px Nunito,sans-serif;box-shadow:0 2px 9px #0009">
    <b>Рейтинг района</b><br><span style="color:#ff6b65">■</span> Критично &lt; 50<br><span style="color:#f5cc56">■</span> Средне 50–60<br><span style="color:#68dc91">■</span> Хорошо &gt; 60</div>"""
    city_map.get_root().html.add_child(folium.Element(legend))
    st_folium(city_map, use_container_width=True, height=590, returned_objects=[], key="astana_map")


@st.cache_data(ttl=3600, show_spinner=False)
def _load_lottie_url(url: str) -> dict | None:
    """Fetch a public Lottie JSON asset; animation failures never block the game."""
    try:
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        animation = response.json()
        return animation if isinstance(animation, dict) and "layers" in animation else None
    except (requests.RequestException, ValueError):
        return None


def _live_reactions(before: dict[str, dict[str, float]], after: dict[str, dict[str, float]]) -> list[tuple[str, str, str]]:
    reactions = []
    for district in DISTRICTS:
        change = _district_score(after[district]) - _district_score(before[district])
        if change >= 0.05:
            if after[district]["S1"] > before[district]["S1"] and before[district]["S1"] < 50:
                message = f"👨‍👩‍👧 Жители {district} счастливы: новые школы уже в плане!"
                tone = "positive"
            elif after[district]["E2"] > before[district]["E2"]:
                message = f"🌿 Жители {district} чувствуют, что воздух стал чище."
                tone = "positive"
            elif after[district]["T1"] > before[district]["T1"] or after[district]["T2"] > before[district]["T2"]:
                message = f"🚌 Дороги {district} стали свободнее — жители быстрее добираются домой."
                tone = "positive"
            else:
                message = f"✨ Жители {district} замечают перемены к лучшему!"
                tone = "positive"
        elif change <= -0.05:
            if after[district]["E2"] < before[district]["E2"]:
                message = f"😷 {district} задыхается от смога!"
            else:
                message = f"🚧 Жители {district} заметили ухудшение городских условий."
            tone = "negative"
        else:
            continue
        reactions.append((district, message, tone))
    return reactions


def _show_motion_feedback(before: dict[str, dict[str, float]], after: dict[str, dict[str, float]], score_delta: float) -> None:
    eco_gain = sum(after[d][k] - before[d][k] for d in DISTRICTS for k in ("E1", "E2"))
    traffic_gain = sum(after[d][k] - before[d][k] for d in DISTRICTS for k in ("T1", "T2"))
    animations = []
    if eco_gain > 0.01:
        animations.append(("🌳 Город зеленеет", "eco"))
    if traffic_gain > 0.01:
        animations.append(("🚗 Движение становится свободнее", "traffic"))
    if score_delta > 0.05:
        animations.append(("🎉 Жители празднуют перемены", "joy"))
    if not animations:
        st.caption("В этот ход Lottie-анимаций нет: выбранные решения не повысили эти направления.")
        return
    columns = st.columns(len(animations))
    for column, (title, category) in zip(columns, animations):
        with column:
            st.markdown(f"**{title}**")
            animation = _load_lottie_url(LOTTIE_URLS[category])
            if animation:
                st_lottie(animation, height=150, key=f"motion_{category}_{st.session_state.simulation_number}")
            else:
                st.markdown("🌱　🚗　🎉")
                st.caption("Анимация недоступна; игровой результат сохранён.")


def _add_decision(measure_id: str, district: str | None) -> tuple[bool, str]:
    decisions = st.session_state.decisions
    if len(decisions) >= 5:
        return False, "Пять указов уже выбраны. Удали один, чтобы заменить его."
    if any(item["measure"] == measure_id for item in decisions):
        return False, "Каждый указ можно выбрать только один раз."
    cost = MEASURES[measure_id]["cost"]
    spent = sum(MEASURES[item["measure"]]["cost"] for item in decisions)
    if spent + cost > BUDGET:
        return False, "Виртуальный бюджет будет превышен. Выбери другую меру."
    direction = MEASURES[measure_id]["direction"]
    direction_count = sum(MEASURES[item["measure"]]["direction"] == direction for item in decisions)
    if direction_count >= 2:
        return False, f"Уже выбраны две меры направления «{direction}»."
    decision = {"measure": measure_id}
    if MEASURES[measure_id]["type"] == "Район":
        if district not in DISTRICTS:
            return False, "Укажи район для районного мероприятия."
        decision["district"] = district
    decisions.append(decision)
    st.session_state.decisions = decisions
    return True, "Указ добавлен в план городского совета."


def _advisor(decisions: list[dict[str, str]], score: float, values: dict[str, dict[str, float]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Задай OPENAI_API_KEY, чтобы получить разбор от GPT‑4o. Расчёт Score и карта работают без AI-советника."
    try:
        from openai import OpenAI
        selected = [f"{MEASURE_CARDS[item['measure']][1]} — {item.get('district', 'весь город')}" for item in decisions]
        deltas = {
            district: {code: round(value - DISTRICTS[district]["indicators"][code], 1) for code, value in row.items()}
            for district, row in values.items()
        }
        response = OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4o", temperature=0.4,
            messages=[
                {"role": "system", "content": "Ты советник акима в ситуационном центре. Кратко по-русски назови сильную сторону сценария, риск и одно улучшение. Не считай Score и не придумывай данные."},
                {"role": "user", "content": f"Итоговый Score {score:.2f}; решения: {selected}; изменения показателей: {deltas}."},
            ],
        )
        return response.choices[0].message.content or "Советник не вернул анализ."
    except Exception as error:
        return f"AI-советник временно недоступен ({type(error).__name__}). Расчёт выполнен."


def _typewriter(text: str):
    for character in text:
        yield character
        time.sleep(0.012)


if "decisions" not in st.session_state:
    st.session_state.decisions = []
if "simulated_values" not in st.session_state:
    st.session_state.simulated_values = _initial_indicators()
    st.session_state.score = BASELINE_SCORE
    st.session_state.has_simulated = False
    st.session_state.simulation_number = 0
if "simulation_number" not in st.session_state:
    st.session_state.simulation_number = 0
if st.session_state.get("has_simulated") and "previous_values" not in st.session_state:
    st.session_state.previous_values = _initial_indicators()
    st.session_state.previous_score = BASELINE_SCORE
    st.session_state.last_reactions = []
    st.session_state.synergy_active = False

st.markdown(
    '<div class="hero"><div class="kicker">Astana Innovations · ситуационный центр</div>'
    '<h1 style="margin:.2rem 0">🏛️ Аким на 5 часов</h1>'
    '<div style="color:#cad9d2">Город на ладони. Пять указов. Два года, чтобы изменить жизнь районов.</div></div>',
    unsafe_allow_html=True,
)

decisions = st.session_state.decisions
spent = sum(MEASURES[item["measure"]]["cost"] for item in decisions)
score = st.session_state.score if st.session_state.has_simulated else BASELINE_SCORE
budget_col, score_col, edict_col = st.columns([1.1, 1.25, 1])
with budget_col:
    st.markdown(
        f'<div class="hud"><div class="hud-label">💰 Казна города</div><div class="hud-value">{BUDGET-spent} 🪙</div>'
        f'<div class="hud-note">Потрачено {spent} из {BUDGET} монет</div></div>', unsafe_allow_html=True,
    )
with score_col:
    st.markdown(
        f'<div class="hud"><div class="hud-label">⭐ Рейтинг одобрения жителей</div><div class="hud-value">{score:.2f}</div>'
        f'<div class="hud-note">{score-BASELINE_SCORE:+.2f} к базовому рейтингу</div></div>', unsafe_allow_html=True,
    )
with edict_col:
    st.markdown(
        f'<div class="hud"><div class="hud-label">📜 Доступно указов</div><div class="hud-value">{len(decisions)} / 5</div>'
        '<div class="hud-note">Уже принятых городских решений</div></div>', unsafe_allow_html=True,
    )
st.progress(spent / BUDGET, text=f"Бюджет · {spent} / {BUDGET} монет")

st.subheader("🗺️ Карта Астаны · ситуационный центр")
st.caption("Наведите курсор на район, чтобы увидеть QoL Score и критические проблемы. Границы на карте схематические.")
_render_map(
    st.session_state.simulated_values,
    decisions,
)

if st.session_state.has_simulated:
    st.subheader("📣 Live-реакции жителей")
    reactions = st.session_state.get("last_reactions", [])
    if reactions:
        reaction_columns = st.columns(min(3, len(reactions)))
        for index, (district_name, message, tone) in enumerate(reactions):
            with reaction_columns[index % len(reaction_columns)]:
                if tone == "positive":
                    st.success(message, icon="💚")
                else:
                    st.error(message, icon="🚨")
    else:
        st.info("Жители пока не заметили значимых перемен в этом сценарии.")
    with st.expander("✨ Посмотреть анимацию перемен", expanded=True):
        _show_motion_feedback(
            st.session_state.previous_values,
            st.session_state.simulated_values,
            st.session_state.score - st.session_state.previous_score,
        )

with st.sidebar:
    st.title("📜 Каталог указов")
    st.caption("Выбери инициативу, район и добавь её в городской план.")
    measure_id = st.selectbox(
        "Карточка мероприятия", list(MEASURES),
        format_func=lambda item: f"{MEASURE_CARDS[item][0]} {MEASURE_CARDS[item][1]} · {MEASURES[item]['cost']} 🪙",
    )
    measure = MEASURES[measure_id]
    icon, title, description = MEASURE_CARDS[measure_id]
    lag_factor = (HORIZON - measure["lag"]) / HORIZON
    effects = ", ".join(
        f"{INDICATOR_INFO[code][0]} {INDICATOR_INFO[code][1]} {amount*lag_factor:+g}"
        for code, amount in measure["effects"].items()
    )
    st.markdown(
        f'<div class="side-card"><b>{icon} Указ: {title}</b><br><span style="color:#b2c3c5">{description}</span><br><br>'
        f'💰 <b>{measure["cost"]} монет</b><br>⏳ Вступит в силу через {measure["lag"]} квартала<br>'
        f'<span style="color:#b2c3c5">Эффект после лага: {effects}</span></div>', unsafe_allow_html=True,
    )
    district = st.selectbox("Выбери район", list(DISTRICTS)) if measure["type"] == "Район" else None
    if measure["type"] == "Город":
        st.info("Городская инициатива действует во всех пяти районах.")
    if st.button("➕ Принять указ", type="primary", use_container_width=True):
        ok, message = _add_decision(measure_id, district)
        if ok:
            st.toast(message, icon="📜")
            st.rerun()
        else:
            st.error(message)

    st.divider()
    st.markdown("### Текущий план")
    if not decisions:
        st.caption("План пока пуст.")
    for index, item in enumerate(list(decisions)):
        measure_key = item["measure"]
        card_icon, card_name, _ = MEASURE_CARDS[measure_key]
        place = item.get("district", "Весь город")
        with st.container(border=True):
            st.markdown(f"**{card_icon} {card_name}**  \n{place} · {MEASURES[measure_key]['cost']} 🪙")
            if st.button("Убрать", key=f"remove_{index}", use_container_width=True):
                st.session_state.decisions.pop(index)
                st.rerun()
    st.progress(min(spent / BUDGET, 1.0), text=f"В казне осталось {BUDGET-spent} монет")

if len(decisions) != 5:
    validation_error = f"Нужно принять ещё {5-len(decisions)} указ(а/ов)."
else:
    try:
        validate_decisions(decisions)
        validation_error = None
    except ValidationError as error:
        validation_error = str(error)
if validation_error:
    st.warning(f"🧭 До симуляции: {validation_error}")

if st.button(
    "⚡ Симулировать два года · 8 кварталов", type="primary",
    use_container_width=True, disabled=bool(validation_error),
):
    with st.status("Ситуационный центр рассчитывает сценарий…", expanded=True) as status:
        st.write("Применяем лаги мероприятий и фиксированные синергии")
        previous_values = st.session_state.simulated_values
        previous_score = st.session_state.score
        score_result = calculate_score(decisions)
        values_result = _apply_effects(decisions)
        selected_ids = {item["measure"] for item in decisions}
        synergy_active = any(first in selected_ids and second in selected_ids for first, second, _, _ in SYNERGIES)
        st.write("Обновляем QoL Score и слои районов на карте")
        st.session_state.previous_values = previous_values
        st.session_state.previous_score = previous_score
        st.session_state.last_reactions = _live_reactions(previous_values, values_result)
        st.session_state.synergy_active = synergy_active
        st.session_state.score = score_result
        st.session_state.simulated_values = values_result
        st.session_state.has_simulated = True
        st.session_state.simulation_number += 1
        st.session_state.last_decisions = decisions.copy()
        st.session_state.advisor_text = None
        st.session_state.advisor_key = None
        status.update(label="Сценарий рассчитан · карта обновлена", state="complete", expanded=False)
    st.session_state.celebrate = True
    st.rerun()

if st.session_state.get("celebrate"):
    st.session_state.celebrate = False
    st.toast("Указы вступили в силу · город изменился!", icon="🏙️")
    if st.session_state.synergy_active or st.session_state.score > st.session_state.previous_score:
        st.balloons()

if st.session_state.has_simulated:
    st.subheader("🏆 Итог городского сценария")
    st.metric(
        "Рейтинг одобрения жителей", f"{st.session_state.score:.2f}",
        delta=f"{st.session_state.score-BASELINE_SCORE:+.2f} к базе 52.56",
    )
    selected_ids = {item["measure"] for item in st.session_state.last_decisions}
    combos = []
    for first, second, _, _ in SYNERGIES:
        if first in selected_ids and second in selected_ids:
            if (first, second) == ("M10", "M12"):
                combos.append("🌟 КОМБО: Безопасность усилена! · Камеры + Цифровая платформа")
            else:
                combos.append(f"🌟 КОМБО: {MEASURE_CARDS[first][1]} + {MEASURE_CARDS[second][1]}")
    if combos:
        st.markdown(f'<div class="combo">{"<br>".join(combos)}</div>', unsafe_allow_html=True)

    st.markdown("### 🧙 Советник акима")
    advisor_key = repr((st.session_state.last_decisions, round(st.session_state.score, 6)))
    if st.session_state.get("advisor_key") != advisor_key:
        with st.spinner("Советник изучает изменения районов…"):
            st.session_state.advisor_text = _advisor(
                st.session_state.last_decisions, st.session_state.score, st.session_state.simulated_values,
            )
            st.session_state.advisor_key = advisor_key
    if st.session_state.get("advisor_displayed_key") != advisor_key:
        st.write_stream(_typewriter(st.session_state.advisor_text))
        st.session_state.advisor_displayed_key = advisor_key
    else:
        st.markdown(st.session_state.advisor_text)

