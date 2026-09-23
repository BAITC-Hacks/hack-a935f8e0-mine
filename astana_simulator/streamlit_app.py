"""Run with: python -m streamlit run streamlit_app.py"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ai import generate_reports, load_providers
from src.data import (
    BASE, BUDGET, HORIZON, INDICATOR_NAMES, MEASURES, MEASURE_BY_ID,
    MODEL_VERSION, POPULATION, PROFILES, SECTORS, WEIGHTS,
)
from src.model import (
    BASELINE, EXAMPLE, Decision, Scenario, simulate_allocations,
    simulate_decisions, validate_allocations, validate_decisions,
)
from src.catalogue import initialize, load_example, remove_from_plan, render_catalogue, reset_plan
from src.map_view import render_map

ROOT = Path(__file__).resolve().parent
MILLION = 1_000_000
MODES = ["Каталог мероприятий", "Распределение бюджета"]
PRESETS = {
    "Баланс": (200, 200, 200, 200, 200),
    "Социальный фокус": (180, 120, 380, 160, 160),
    "Зеленый город": (180, 380, 180, 120, 140),
}
st.set_page_config(page_title="Аким на 5 часов · Astana Lab", page_icon="🏙️", layout="wide")
st.markdown(f"<style>{(ROOT / 'assets/catalogue.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def money(value: int) -> str:
    return f"{value:,.0f} ₸".replace(",", " ")


def number(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def set_preset(name: str) -> None:
    for sector, value in zip(SECTORS, PRESETS[name]):
        st.session_state[f"budget_{sector.key}"] = value


def metric_card(title: str, value: str, note: str, *, featured: bool = False) -> None:
    st.markdown(
        f'<div class="metric-box {"featured" if featured else ""}">'
        f'<div class="metric-title">{title}</div><div class="metric-value">{value}</div>'
        f'<div class="metric-note">{note}</div></div>', unsafe_allow_html=True,
    )


def chart_layout(fig: go.Figure, height: int = 305) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=5, r=22, t=12, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#657b85", size=11),
        legend=dict(orientation="h", y=1.15, x=0, font=dict(size=11)),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    return fig


def show_chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def sidebar(providers: list) -> tuple[str, dict, list[Decision], list[str]]:
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-icon">А</div>'
                    '<div>AKIM / ASTANA<small>ЛАБОРАТОРИЯ ГОРОДСКИХ РЕШЕНИЙ</small></div></div>',
                    unsafe_allow_html=True)
        mode = st.selectbox("Режим симуляции", MODES, key="mode")
        st.markdown('<div class="budget-label">Бюджет вашего города</div>'
                    '<div class="budget-number">1 000 <span>млн ₸</span></div>', unsafe_allow_html=True)
        st.caption("100 условных единиц · одинаковый старт для всех")
        budget_slot = st.empty()
        progress_slot = st.empty()
        allocations = {}
        decisions = []
        if mode == "Распределение бюджета":
            st.markdown('<div class="section-kicker">ВАШИ ПРИОРИТЕТЫ</div>', unsafe_allow_html=True)
            st.caption("5 направлений · суммы в млн ₸ · шаг 10 млн")
            saved = st.session_state.setdefault("budget_plan", {s.key: 200 for s in SECTORS})
            for sector in SECTORS:
                key = f"budget_{sector.key}"
                if key not in st.session_state:
                    st.session_state[key] = saved[sector.key]
                allocations[sector.key] = st.slider(
                    sector.label, min_value=0, max_value=1000, step=10,
                    key=key, format="%d млн ₸", help=sector.description,
                ) * MILLION
            st.session_state["budget_plan"] = {k: v // MILLION for k, v in allocations.items()}
            errors = validate_allocations(allocations)
            st.markdown('<div class="section-kicker">БЫСТРЫЙ СТАРТ</div>', unsafe_allow_html=True)
            for preset in PRESETS:
                st.button(preset, on_click=set_preset, args=(preset,), width="stretch", key=f"preset_{preset}")
        else:
            decisions = st.session_state["plan"]
            allocations = {s.key: 0 for s in SECTORS}
            for decision in decisions:
                m = MEASURE_BY_ID[decision.measure_id]
                allocations[m.sector] += m.cost
            errors = validate_decisions(decisions)
            st.markdown('<div class="section-kicker">ВАШ ПЛАН</div>'
                        f'<div class="plan-count">{len(decisions):02d}<span> / 05 решений</span></div>', unsafe_allow_html=True)
            if not decisions:
                st.markdown('<div class="empty-plan"><span>＋</span><strong>Город ждет ваших решений</strong>'
                            '<p>Добавьте мероприятия из каталога. Для районных мер выберите место на карте.</p></div>', unsafe_allow_html=True)
            for index, decision in enumerate(decisions):
                measure = MEASURE_BY_ID[decision.measure_id]
                details, remove = st.columns([5, 1], vertical_alignment="center")
                with details:
                    st.markdown(f'<div class="selected-item"><span>{index + 1:02d} / {measure.id}</span>'
                                f'<strong>{escape(measure.name)}</strong>'
                                f'<small>{decision.district or "Весь город"} · {measure.units} ед.</small></div>', unsafe_allow_html=True)
                with remove:
                    st.button("×", key=f"remove_{measure.id}", help=f"Убрать {measure.name}",
                              on_click=remove_from_plan, args=(measure.id,))
            directions = len({MEASURE_BY_ID[d.measure_id].sector for d in decisions})
            st.caption(f"Затронуто направлений: {directions} из 5")
            st.button("Загрузить пример", on_click=load_example, key="load_example", width="stretch")
            st.button("Сбросить план", on_click=reset_plan, key="reset_plan", width="stretch", disabled=not decisions)
        spent = sum(allocations.values())
        remaining = BUDGET - spent
        remainder_label = "Осталось" if remaining >= 0 else "Превышение"
        budget_slot.markdown(
            f'<div class="budget-note"><span>{remainder_label}</span>'
            f'<strong>{abs(remaining) // MILLION} млн ₸</strong></div>', unsafe_allow_html=True,
        )
        progress_slot.progress(min(spent / BUDGET, 1.0))
        st.divider()
        with st.expander("Подключение AI"):
            for provider in providers:
                st.caption(f"{'● Ключ задан' if provider.api_key else '○ Нет ключа'} · {provider.name}")
            st.caption("Ключ читается на сервере. Отчет запускается только по кнопке; запрос может быть платным.")
            st.code("OPENAI_API_KEY=…", language="dotenv")
            st.caption("После изменения .env перезапустите приложение. Переменная окружения имеет приоритет.")
        st.caption("План → расчет → AI-разбор. Синтетические данные HackAlem AI.")
    return mode, allocations, decisions, errors


def render_city_baseline() -> None:
    st.markdown('<div class="section-kicker">ПЕРЕД ПЕРВЫМ РЕШЕНИЕМ / ИСХОДНАЯ СИТУАЦИЯ</div>', unsafe_allow_html=True)
    st.subheader("Текущее состояние города и дефициты")
    st.caption(f"Учебный датасет до ваших решений · базовый Score {number(BASELINE.total)} / 100. "
               "Это синтетические показатели, а не оперативные сведения о реальной Астане.")

    def indicator_cell(row: dict, codes: tuple[str, ...]) -> str:
        code = min(codes, key=lambda key: row[key])
        value = row[code]
        level = "critical" if value < 40 else "deficit" if value < 50 else "stable"
        return (f'<td><span class="baseline-value {level}">{value:g}</span>'
                f'<small>{escape(INDICATOR_NAMES[code])}</small></td>')

    rows = []
    for name, row in BASE.items():
        rows.append(f'<tr><th scope="row">{escape(name)}</th>'
                    + indicator_cell(row, ("T1", "T2"))
                    + indicator_cell(row, ("E1",))
                    + indicator_cell(row, ("S1", "S2")) + '</tr>')
    st.markdown('<div class="baseline-table"><table><thead><tr><th>Район</th>'
                '<th>Транспорт</th><th>Зеленые зоны</th><th>Соцобъекты</th></tr></thead>'
                '<tbody>' + ''.join(rows) + '</tbody></table></div>', unsafe_allow_html=True)
    st.caption("Шкала 0–100: больше — лучше. В транспорте и соцсфере показан слабейший показатель. "
               "Ниже 40 — критично; 40–49 — дефицит для стартовой диагностики; от 50 — наблюдение. "
               "Порог 50 не меняет формулу Score.")
    with st.container(border=True, key="starting_advice"):
        st.markdown("**С чего начать акиму**")
        st.markdown(
            f"- **Нура — первый приоритет:** поликлиники {BASE['Нура']['S2']}, школы и детсады {BASE['Нура']['S1']}, "
            f"общественный транспорт {BASE['Нура']['T2']}. Рассмотрите M7/M8 и улучшение автобусного сообщения M1.\n"
            f"- **Есиль и Алматы — транспорт:** разгрузка дорог {BASE['Есиль']['T1']} и {BASE['Алматы']['T1']}. "
            f"Сравните M1 и городскую M2; в Есиле также обратите внимание на школы ({BASE['Есиль']['S1']}).\n"
            f"- **Сарыарка — зеленые зоны:** озеленение {BASE['Сарыарка']['E1']}, качество воздуха {BASE['Сарыарка']['E2']}. "
            "Сравните парк M4 и экологические меры M5/M6.\n"
            f"- **Байконур — наблюдение:** в этих трех направлениях нет значений ниже 50; "
            f"проверьте безопасность улиц ({BASE['Байконур']['B1']}) перед выбором M10."
        )
        st.caption("Это направления для сравнения, а не готовый набор: выберите ровно пять мер в пределах 1 млрд ₸ и проверьте совместимость. Начальные рекомендации не требуют API.")


def render_hero() -> None:
    st.markdown('<div class="topline"><span>HACKALEM AI / ГОРОДСКАЯ СИМУЛЯЦИЯ</span>'
                '<span class="live-tag">АСТАНА · 51° N / 71° E</span></div>'
                '<section class="editorial-hero"><div><div class="eyebrow">У ВАС ЕСТЬ ПЯТЬ РЕШЕНИЙ</div>'
                '<h1>Аким <em>на 5 часов.</em></h1>'
                '<p>Один бюджет. Пять районов. Каким станет ваш город?</p></div>'
                '<div class="hero-stamp"><strong>05</strong><span>РЕШЕНИЙ,<br>КОТОРЫЕ МЕНЯЮТ ГОРОД</span></div></section>', unsafe_allow_html=True)


def overview(scenario: Scenario, key_prefix: str = "overview") -> None:
    left, right = st.columns([1.3, 1], gap="large")
    with left, st.container(border=True):
        st.subheader("Куда направлен бюджет")
        st.caption("Ваши приоритеты в миллионах тенге")
        fig = go.Figure(go.Bar(
            x=[scenario.allocations[s.key] / MILLION for s in SECTORS],
            y=[s.short for s in SECTORS], orientation="h",
            marker_color=[s.color for s in SECTORS], width=.48,
            text=[f"{scenario.allocations[s.key] // MILLION} млн" for s in SECTORS],
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x} млн ₸<extra></extra>",
        ))
        largest = max(scenario.allocations.values()) / MILLION
        fig.update_xaxes(range=[0, max(largest * 1.28, 100)], showgrid=True, gridcolor="#E9EFF2",
                         zeroline=False, ticksuffix=" ")
        fig.update_yaxes(autorange="reversed", showgrid=False)
        show_chart(chart_layout(fig, 285), f"{key_prefix}_allocation_chart")
    with right, st.container(border=True):
        st.subheader("Что изменится")
        st.caption("Последствия текущего сценария по расчетной модели")
        best = max(SECTORS, key=lambda s: scenario.score.sectors[s.key] - BASELINE.sectors[s.key])
        gain = scenario.score.sectors[best.key] - BASELINE.sectors[best.key]
        weakest = scenario.score.weakest
        d_gain = scenario.score.district_scores[weakest] - BASELINE.district_scores[weakest]
        if gain > 0:
            title = f"{best.label}: +{number(gain)} пункта"
            detail = "Наибольшее улучшение среди пяти направлений относительно исходных данных."
        else:
            title, detail = "Изменений пока нет", "Средства не распределены. Передвиньте слайдеры, чтобы увидеть эффект."
        critical = scenario.score.critical
        insights = [
            (title, detail),
            (f"Фокус внимания — {weakest}",
             f"Самый низкий районный балл: {number(scenario.score.minimum)}. Изменение: {number(d_gain)} пункта."),
            (f"Критических показателей: {len(critical)}",
             "Каждое значение ниже 40 уменьшает итоговый Score на 1 балл."
             if critical else "Все показатели достигли порога 40. Это не означает отсутствия инфраструктурных рисков."),
        ]
        for title, detail in insights:
            st.markdown(f'<div class="insight"><strong>{escape(title)}</strong><p>{escape(detail)}</p></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Пять направлений · до и после")
        fig = go.Figure()
        fig.add_bar(name="Исходное состояние", x=[s.short for s in SECTORS],
                    y=[BASELINE.sectors[s.key] for s in SECTORS], marker_color="#D8E2E5")
        fig.add_bar(name="Ваш сценарий", x=[s.short for s in SECTORS],
                    y=[scenario.score.sectors[s.key] for s in SECTORS], marker_color="#188F80")
        fig.update_traces(hovertemplate="%{x}: %{y:.2f} / 100<extra>%{fullData.name}</extra>")
        fig.update_yaxes(range=[0, 100], gridcolor="#E9EFF2", title="Индекс, 0–100", zeroline=False)
        fig.update_layout(barmode="group", bargap=.5)
        show_chart(chart_layout(fig, 290), f"{key_prefix}_sector_comparison")
        st.caption("Индексы направлений взвешены по населению и весам показателей. Итоговый Score дополнительно учитывает слабейший район и критические значения.")


def districts(scenario: Scenario) -> None:
    st.subheader("Город состоит из районов")
    st.caption("Пять условных районов из датасета. Значение ниже 40 — критическое.")
    rows = [{
        "Район": d, "Доля населения": POPULATION[d], "До": BASELINE.district_scores[d],
        "После": scenario.score.district_scores[d],
        "Изменение": scenario.score.district_scores[d] - BASELINE.district_scores[d],
        "Критических": sum(v < 40 for v in scenario.indicators[d].values()),
    } for d in BASE]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "Доля населения": st.column_config.NumberColumn(format="percent"),
        "До": st.column_config.NumberColumn(format="%.2f"),
        "После": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.2f"),
        "Изменение": st.column_config.NumberColumn(format="%+.2f"),
    })
    district = st.selectbox("Рассмотреть район", list(BASE), index=4)
    st.caption(PROFILES[district])
    indicator_rows = [{
        "Код": k, "Показатель": INDICATOR_NAMES[k], "До": BASE[district][k],
        "После": scenario.indicators[district][k],
        "Изменение": scenario.indicators[district][k] - BASE[district][k],
        "Статус": "Ниже порога 40" if scenario.indicators[district][k] < 40 else "Порог 40 достигнут",
    } for k in INDICATOR_NAMES]
    st.dataframe(pd.DataFrame(indicator_rows), hide_index=True, width="stretch", column_config={
        "После": st.column_config.NumberColumn(format="%.2f"),
        "Изменение": st.column_config.NumberColumn(format="%+.2f"),
    })
    if scenario.synergies:
        st.success("Сработавшие синергии: " + "; ".join(scenario.synergies))
    if scenario.mode == "measures":
        with st.expander("Вклад мероприятий с учетом лагов"):
            for contribution in scenario.contributions:
                effects = ", ".join(f"{k} {v:+g}" for k, v in contribution["realized_effects"].items())
                st.write(f"**{contribution['id']} · {contribution['name']}** — {', '.join(contribution['districts'])}: {effects}")
            st.caption("Эффекты указаны до финального ограничения значений диапазоном 0–100. Синергии добавляются отдельно.")


def methodology(scenario: Scenario, is_preview: bool = False) -> None:
    st.subheader("Открытая модель расчета")
    st.write("AI объясняет готовый расчет. Балл воспроизводим и не зависит от текста ответа модели.")
    st.latex(r"D_d=\sum_k w_k I'_{dk},\quad D_{avg}=\sum_d pop_d D_d")
    st.latex(r"Score=\mathrm{clip}\left(0.7D_{avg}+0.3\min_d D_d-N_{crit},\ 0,\ 100\right)")
    st.write("70% — результат города, 30% — результат слабейшего района. Каждая пара «район × показатель» со значением строго ниже 40 отнимает 1 балл. Остаток бюджета бонуса не дает.")
    calculation_label = "Исходный расчет без действий" if is_preview else "Текущий расчет"
    st.info(f"{calculation_label}: 0,7 × {number(scenario.score.average, 4)} + "
            f"0,3 × {number(scenario.score.minimum, 4)} − {len(scenario.score.critical)} = "
            f"{number(scenario.score.total)}. Округление применяется только при отображении.")
    if scenario.mode == "allocation":
        st.markdown("**Как слайдеры меняют показатели**")
        st.latex(r"I'_{dk}=I_{dk}+(100-I_{dk})\cdot0.35\left(1-e^{-b_s/(B W_s)}\right)")
        st.write("bₛ — бюджет направления; B — 1 млрд ₸; Wₛ — сумма весов его двух показателей. "
                 "Программа действует на соответствующие показатели всех районов. При том же проценте "
                 "закрытого дефицита более слабые показатели получают больший абсолютный прирост. "
                 "Первые вложения дают больше эффекта, последующие — меньше. Нулевое финансирование не меняет показатели.")
        st.warning("Это авторская непрерывная модель для режима слайдеров. Коэффициент 0,35 — учебное допущение на горизонт двух лет; он не откалиброван на реальных данных. Лаги и синергии каталога применяются в режиме «5 мероприятий».")
    else:
        st.latex(r"I'_{dk}=\mathrm{clip}\left(I_{dk}+\sum_m effect_{mk}\frac{8-L_m}{8}+synergy_{dk},0,100\right)")
        st.write("Ровно пять уникальных мероприятий, не более двух в одном направлении. Район обязателен "
                 "для районных мер. Лаг уменьшает эффект; синергия фиксирована. M1/M3 несовместимы везде; "
                 "M4/M7 и M5/M13 несовместимы в одном районе. Порядок решений не влияет на результат.")
    st.dataframe(pd.DataFrame([
        {"Направление": s.label, "Показатели": ", ".join(s.indicators),
         "Вес": sum(WEIGHTS[k] for k in s.indicators)} for s in SECTORS
    ]), hide_index=True, width="stretch", column_config={"Вес": st.column_config.NumberColumn(format="percent")})
    with st.expander("Каталог: 14 мероприятий"):
        st.dataframe(pd.DataFrame([
            {"ID": m.id, "Мероприятие": m.name, "Масштаб": "Город" if m.scope == "city" else "Район",
             "Цена, млн ₸": m.cost // MILLION, "Лаг, кв.": m.lag,
             "Полные эффекты": ", ".join(f"{k} {v:+g}" for k, v in m.effects)} for m in MEASURES
        ]), hide_index=True, width="stretch")
    st.markdown("Источники: [условия кейса](https://docs.google.com/document/d/1oDZtYnBgbcn_Ii7vleP87hkARJ2HmbXl7Cw_rsCxqpo/edit) · "
                "[синтетический датасет и формула](https://docs.google.com/document/d/1Uc-GdGoKhDY-spu8V50-ZMm33t2CjYLP/edit).")
    st.caption(f"Версия модели {MODEL_VERSION}. Базовый Score: {number(BASELINE.total, 5)}. Сценарии двух режимов используют разные модели эффекта; сравнивайте их внутри одного режима.")


def ai_section(scenario: Scenario, providers: list) -> dict:
    st.markdown('<div class="section-kicker">02 — ЭКСПЕРТНЫЙ РАЗБОР</div>', unsafe_allow_html=True)
    st.subheader("AI-советник акима · OpenAI")
    st.caption("Урбанист объясняет сильные стороны, скрытые риски и компромиссы вашего сценария на основе расчета.")
    identity = scenario.fingerprint + "|" + "|".join(p.model for p in providers)
    stored = st.session_state.get("ai_run", {})
    reports = stored.get("reports", {}) if stored.get("identity") == identity else {}
    if stored and stored.get("identity") != identity:
        st.info("Сценарий изменен. Предыдущий AI-отчет скрыт; создайте новый для текущего бюджета.")
    pending = [p for p in providers if p.api_key and (p.name not in reports or not reports[p.name].ok)]
    complete = all(p.name in reports and reports[p.name].ok for p in providers)
    button_label = "AI-разбор готов" if complete else ("Повторить AI-разбор" if reports else "Получить AI-разбор")
    if st.button(button_label, type="primary", disabled=not pending, key="run_ai"):
        with st.status("OpenAI анализирует сценарий…", expanded=True) as status:
            st.write("Отправлен расчет текущего сценария. Ожидание — до 55 секунд.")
            received = asyncio.run(generate_reports(pending, scenario.payload()))
            reports = {**reports, **received}
            st.session_state["ai_run"] = {"identity": identity, "reports": reports}
            if all(report.ok for report in received.values()):
                status.update(label="AI-анализ завершен", state="complete", expanded=False)
            else:
                status.update(label="AI-отчет недоступен; расчет сохранен", state="error", expanded=False)
    if not any(p.api_key for p in providers):
        st.info("Для AI-отчета добавьте OPENAI_API_KEY в .env и перезапустите приложение. Расчетная модель уже работает.")
    for provider in providers:
        with st.container(border=True):
            st.markdown(f'<div class="provider"><strong>Эксперт-урбанист</strong><span>{provider.name}</span></div>', unsafe_allow_html=True)
            st.caption(provider.model)
            report = reports.get(provider.name)
            if report and report.ok:
                st.markdown(report.text, unsafe_allow_html=False)
                if report.warning:
                    st.warning(report.warning)
                st.caption(f"Ответ получен за {number(report.seconds, 1)} с · сценарий {scenario.fingerprint[:8]}")
            elif report:
                st.error(report.error)
            elif not provider.api_key:
                st.caption("Ключ не задан. Экспертный отчет появится после подключения API.")
            else:
                st.caption("Готов к запросу. Нажмите «Получить AI-разбор».")
    st.caption("AI-выводы могут содержать ошибки. Проверяйте их по расчетам во вкладке «Районы и результат». Пересчет страницы не отправляет запросы; повтор доступен после ошибки.")
    return reports


def main() -> None:
    initialize()
    providers = load_providers()
    mode, allocations, decisions, errors = sidebar(providers)
    render_city_baseline()
    render_hero()
    catalogue_mode = mode == "Каталог мероприятий"
    scenario = None
    if not errors:
        scenario = simulate_decisions(decisions) if catalogue_mode else simulate_allocations(allocations)
        st.session_state["current_fingerprint"] = scenario.fingerprint
    else:
        st.session_state.pop("current_fingerprint", None)
    notification = st.empty()
    if notice := st.session_state.pop("planner_notice", None):
        notification.info(notice)
        st.toast(notice)
    spent = sum(allocations.values())
    a, b, c = st.columns([1.25, 1, 1], gap="medium")
    with a:
        value = number(scenario.score.total) if scenario else "—"
        note = (f'<span class="delta">{scenario.score.total - BASELINE.total:+.2f}</span> к базе {number(BASELINE.total)}'
                if scenario else "Появится после проверки пяти решений" if catalogue_mode else "Расчет заблокирован: проверьте бюджет")
        metric_card("ASTANA QUALITY OF LIFE SCORE", f'{value} <small>/ 100</small>', note, featured=True)
    with b:
        metric_card("ИНВЕСТИЦИИ В ГОРОД", f'{spent // MILLION} <small>млн ₸</small>',
                    f"{spent / BUDGET:.0%} бюджета · {spent // 10_000_000} из 100 ед.")
    with c:
        if catalogue_mode:
            metric_card("ПРИНЯТО РЕШЕНИЙ", f'{len(decisions):02d} <small>/ 05</small>', "Горизонт эффекта — 8 кварталов")
        else:
            metric_card("КРИТИЧЕСКИЕ ПОКАЗАТЕЛИ", f'{len(scenario.score.critical) if scenario else "—"} <small>из 50</small>', "Порог — ниже 40 · в исходных данных: 2")
    if errors:
        for error in errors:
            if catalogue_mode and len(decisions) < 5 and error == "Нужно выбрать ровно 5 мероприятий.":
                st.info(f"Выбрано {len(decisions)} из 5 мероприятий. Карта показывает исходное состояние города.")
            else:
                st.error(error)
        if st.session_state.get("ai_run"):
            st.caption("Предыдущий AI-отчет скрыт: текущий план еще не прошел проверку.")
    baseline = Scenario("measures" if catalogue_mode else "allocation", {s.key: 0 for s in SECTORS}, [],
                        {d: dict(row) for d, row in BASE.items()}, BASELINE, [], [])
    tabs = st.tabs(
        ["Каталог мероприятий" if catalogue_mode else "Обзор сценария", "Карта Астаны", "Районы и результат", "Методика"],
        key="catalogue_tabs" if catalogue_mode else "allocation_tabs", on_change="rerun",
    )
    with tabs[0]:
        if catalogue_mode:
            render_catalogue()
        elif scenario:
            overview(scenario)
        else:
            st.warning("Расчет заблокирован. Уменьшите расходы в боковой панели.")
    with tabs[1]:
        render_map(scenario, catalogue_mode=catalogue_mode)
    with tabs[2]:
        if scenario:
            overview(scenario, key_prefix="results")
        else:
            st.caption("Исходные показатели. Прогноз появится после завершения допустимого плана.")
        districts(scenario or baseline)
    with tabs[3]:
        methodology(scenario or baseline, is_preview=scenario is None)
    st.divider()
    if scenario:
        reports = ai_section(scenario, providers)
        export = {
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "scenario_id": scenario.fingerprint, **scenario.payload(),
            "ai_reports": {name: asdict(report) for name, report in reports.items()},
        }
        st.download_button("Скачать сценарий и отчеты · JSON", json.dumps(export, ensure_ascii=False, indent=2),
                           file_name=f"astana-{scenario.fingerprint[:8]}.json", mime="application/json", key="export")
    else:
        st.subheader("Сначала план. Затем экспертный разбор.")
        st.caption("AI-анализ и экспорт доступны после проверки допустимого сценария.")
        st.button("Получить AI-разбор", disabled=True, type="primary", key="run_ai")
    st.markdown('<div class="footer"><span>AKIM / ASTANA · Аким на 5 часов</span>'
                '<span>Учебная симуляция · данные HackAlem AI</span></div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
