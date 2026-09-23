"""Editorial landing page and baseline summary, separate from scenario controls."""
import base64
from html import escape
from pathlib import Path

import streamlit as st

from src.model import BASELINE
from src.data import BASE, INDICATOR_NAMES, PROFILES

ROOT = Path(__file__).resolve().parents[1]


def render_district_briefing() -> None:
    cards = []
    for index, (name, values) in enumerate(BASE.items(), 1):
        code = min(("T1", "T2", "E1", "S1", "S2"), key=lambda k: values[k])
        value = values[code]
        status = "ПЕРВЫЙ ПРИОРИТЕТ" if value < 40 else "ЕСТЬ ДЕФИЦИТ" if value < 50 else "НАБЛЮДЕНИЕ"
        cards.append(f'<article class="district-brief {"urgent" if value < 40 else ""}">'
                     f'<div class="district-brief-index">0{index} <span>{status}</span></div>'
                     f'<h3>{escape(name)}</h3><p>{escape(PROFILES[name])}</p>'
                     f'<div class="district-brief-bottom"><strong>{value}<small> / 100</small></strong>'
                     f'<span>{escape(INDICATOR_NAMES[code])}</span></div></article>')
    st.markdown('<div class="district-brief-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def render_landing(reset_callback) -> None:
    with st.container(key="site_navigation"):
        brand, links, reset = st.columns([3, 4, 2], vertical_alignment="center")
        with brand:
            st.markdown('<div class="site-brand"><span>A</span><div>ASTANA<strong>INNOVATIONS</strong></div></div>', unsafe_allow_html=True)
        with links:
            st.markdown('<nav class="site-nav"><i></i> СИМУЛЯТОР ГОРОДА <span>/</span> HACKALEM AI</nav>', unsafe_allow_html=True)
        with reset:
            st.button("Сбросить сценарий ↻", on_click=reset_callback, key="reset_scenario", width="stretch")

    artwork = base64.b64encode((ROOT / "assets/city-hero.svg").read_bytes()).decode()
    whole, fraction = f"{BASELINE.total:.2f}".split(".")
    st.markdown(
        '<section class="city-hero"><div class="city-hero-copy">'
        '<div class="hero-index">01 <span>ВАШ ГОРОД. ВАШИ РЕШЕНИЯ.</span></div>'
        '<h1>Аким<br><em>на 5 часов</em></h1>'
        '<p>Пять решений. Один общий бюджет.<br>Как изменится качество жизни в Астане?</p>'
        '<a class="hero-cta" href="#scenario-builder" target="_self">СОБРАТЬ СЦЕНАРИЙ <span>↓</span></a>'
        '</div><div class="city-hero-art">'
        f'<img src="data:image/svg+xml;base64,{artwork}" alt="Стилизованная панорама Астаны в зеленых тонах"/>'
        '</div></section><div class="simulation-caption">СИМУЛЯЦИЯ 001 — 008 <span>●</span></div>'
        '<section class="baseline-strip" aria-label="Исходное состояние города">'
        '<div class="baseline-intro"><label>ТОЧКА ОТСЧЁТА</label><p>У города уже есть<br>свои вызовы.</p></div>'
        f'<div><label>ТЕКУЩИЙ SCORE</label><strong>{whole}<em>.{fraction}</em></strong>'
        '<small>из 100 · базовый сценарий</small></div>'
        '<div><label>БЮДЖЕТ ГОРОДА</label><strong>100<sub> ед.</sub></strong><small>одинаковый для всех команд</small></div>'
        '<div><label>РАЙОНЫ</label><strong>05</strong><small>условных районов Астаны</small></div>'
        '</section>', unsafe_allow_html=True,
    )
