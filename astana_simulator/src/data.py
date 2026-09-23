"""Synthetic case data transcribed from docs/dataset-source.md.

Amounts in the source are converted at 1 unit = 10,000,000 KZT.
No values describe the actual current state of Astana.
"""

from dataclasses import dataclass

BUDGET = 1_000_000_000
UNIT = 10_000_000
HORIZON = 8
MODEL_VERSION = "1.0.0"


@dataclass(frozen=True)
class Sector:
    key: str
    label: str
    short: str
    indicators: tuple[str, str]
    color: str
    description: str


SECTORS = (
    Sector("transport", "Транспорт", "Транспорт", ("T1", "T2"), "#3D81CF", "Дороги, остановки и общественный транспорт"),
    Sector("green", "Озеленение", "Озеленение", ("E1", "E2"), "#219E7D", "Зеленые зоны и качество воздуха"),
    Sector("social", "Социальная инфраструктура", "Соцсфера", ("S1", "S2"), "#9773CD", "Школы, детские сады и поликлиники"),
    Sector("safety", "Безопасность", "Безопасность", ("B1", "B2"), "#DAA03E", "Безопасные улицы и дорожное движение"),
    Sector("services", "Городской сервис", "Сервисы", ("C1", "C2"), "#DE7B66", "Надежность ЖКХ и обращения жителей"),
)
SECTOR_BY_KEY = {s.key: s for s in SECTORS}
INDICATOR_NAMES = {
    "T1": "Разгрузка дорог", "T2": "Доступность общественного транспорта",
    "E1": "Озеленение", "E2": "Качество воздуха",
    "S1": "Школы и детсады", "S2": "Поликлиники и первичная медпомощь",
    "B1": "Безопасность улиц", "B2": "Безопасность дорожного движения",
    "C1": "Надежность ЖКХ", "C2": "Скорость решения обращений",
}
WEIGHTS = dict(zip(INDICATOR_NAMES, (.10, .10, .09, .11, .11, .11, .09, .09, .10, .10)))
POPULATION = {"Есиль": .27, "Алматы": .24, "Сарыарка": .20, "Байконур": .13, "Нура": .16}
_ROWS = (
    (45, 62, 68, 72, 48, 55, 78, 60, 75, 70),
    (40, 75, 50, 55, 60, 65, 62, 52, 50, 60),
    (50, 70, 42, 40, 62, 68, 58, 55, 45, 55),
    (52, 68, 55, 50, 58, 60, 52, 58, 55, 58),
    (55, 40, 45, 65, 38, 35, 55, 50, 60, 50),
)
BASE = {name: dict(zip(INDICATOR_NAMES, row)) for name, row in zip(POPULATION, _ROWS)}
PROFILES = {
    "Есиль": "Пробки на мостах и переполненные школы.",
    "Алматы": "Износ коммунальных сетей и транспортная нагрузка.",
    "Сарыарка": "Слабое озеленение и низкое качество воздуха.",
    "Байконур": "Умеренные показатели; внимание к безопасности улиц.",
    "Нура": "Дефицит социальной инфраструктуры и общественного транспорта.",
}


@dataclass(frozen=True)
class Measure:
    id: str
    sector: str
    name: str
    scope: str
    units: int
    lag: int
    effects: tuple[tuple[str, float], ...]

    @property
    def cost(self) -> int:
        return self.units * UNIT


MEASURES = (
    Measure("M1", "transport", "Выделенные полосы для автобусов", "district", 18, 2, (("T1", 6), ("T2", 9))),
    Measure("M2", "transport", "Умные светофоры", "city", 22, 2, (("T1", 4), ("B2", 3))),
    Measure("M3", "transport", "Линия ЛРТ / расширение", "district", 30, 4, (("T1", 16), ("T2", 20), ("E2", 4))),
    Measure("M4", "green", "Парк / сквер", "district", 15, 2, (("E1", 12), ("E2", 3), ("B1", 2))),
    Measure("M5", "green", "Перевод частного сектора на чистое топливо", "district", 25, 3, (("E2", 14), ("C1", 4))),
    Measure("M6", "green", "Озеленение и ветрозащитные полосы", "city", 20, 4, (("E1", 5), ("E2", 3))),
    Measure("M7", "social", "Школа + детсад", "district", 24, 3, (("S1", 16),)),
    Measure("M8", "social", "Центр семейного здоровья / поликлиника", "district", 20, 3, (("S2", 14),)),
    Measure("M9", "social", "Дворовые спорт-хабы", "district", 10, 1, (("S1", 3), ("S2", 3), ("B1", 3))),
    Measure("M10", "safety", "Освещение и камеры Safe City", "district", 12, 1, (("B1", 12), ("B2", 2))),
    Measure("M11", "safety", "Безопасные переходы и школьные зоны", "district", 10, 1, (("B2", 12), ("T1", -2))),
    Measure("M12", "services", "Цифровая платформа обращений", "city", 14, 1, (("C2", 5),)),
    Measure("M13", "services", "Модернизация тепло- и водосетей", "district", 28, 4, (("C1", 18), ("E2", 2))),
    Measure("M14", "services", "Аварийные бригады ЖКХ и оповещение", "city", 16, 1, (("C1", 5), ("C2", 2))),
)
MEASURE_BY_ID = {m.id: m for m in MEASURES}
SYNERGIES = (("M1", "M2", "T1", 2), ("M10", "M12", "B1", 2), ("M5", "M6", "E2", 2))
