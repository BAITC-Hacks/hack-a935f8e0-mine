"""Scenario validation and Astana Quality of Life Score calculation.

Decision format: ``{"measure": "M1", "district": "Есиль"}`` for
district measures, and ``{"measure": "M2"}`` for city-wide measures.
``id`` may be used instead of ``measure``. City measures must not specify a
district. ``validate_decisions`` returns True for valid input and raises
``ValidationError`` with a readable reason otherwise.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


BUDGET = 100
HORIZON = 8

INDICATORS = ("T1", "T2", "E1", "E2", "S1", "S2", "B1", "B2", "C1", "C2")
WEIGHTS = {
    "T1": 0.10, "T2": 0.10, "E1": 0.09, "E2": 0.11, "S1": 0.11,
    "S2": 0.11, "B1": 0.09, "B2": 0.09, "C1": 0.10, "C2": 0.10,
}

DISTRICTS = {
    "Есиль": {
        "population": 0.27,
        "indicators": dict(zip(INDICATORS, (45, 62, 68, 72, 48, 55, 78, 60, 75, 70))),
    },
    "Алматы": {
        "population": 0.24,
        "indicators": dict(zip(INDICATORS, (40, 75, 50, 55, 60, 65, 62, 52, 50, 60))),
    },
    "Сарыарка": {
        "population": 0.20,
        "indicators": dict(zip(INDICATORS, (50, 70, 42, 40, 62, 68, 58, 55, 45, 55))),
    },
    "Байконур": {
        "population": 0.13,
        "indicators": dict(zip(INDICATORS, (52, 68, 55, 50, 58, 60, 52, 58, 55, 58))),
    },
    "Нура": {
        "population": 0.16,
        "indicators": dict(zip(INDICATORS, (55, 40, 45, 65, 38, 35, 55, 50, 60, 50))),
    },
}

# Effects are full-horizon changes; the lag factor is applied at calculation time.
MEASURES = {
    "M1":  {"direction": "Транспорт", "type": "Район", "cost": 18, "lag": 2, "effects": {"T1": 6, "T2": 9}},
    "M2":  {"direction": "Транспорт", "type": "Город", "cost": 22, "lag": 2, "effects": {"T1": 4, "B2": 3}},
    "M3":  {"direction": "Транспорт", "type": "Район", "cost": 30, "lag": 4, "effects": {"T1": 16, "T2": 20, "E2": 4}},
    "M4":  {"direction": "Экология", "type": "Район", "cost": 15, "lag": 2, "effects": {"E1": 12, "E2": 3, "B1": 2}},
    "M5":  {"direction": "Экология", "type": "Район", "cost": 25, "lag": 3, "effects": {"E2": 14, "C1": 4}},
    "M6":  {"direction": "Экология", "type": "Город", "cost": 20, "lag": 4, "effects": {"E1": 5, "E2": 3}},
    "M7":  {"direction": "Соцсфера", "type": "Район", "cost": 24, "lag": 3, "effects": {"S1": 16}},
    "M8":  {"direction": "Соцсфера", "type": "Район", "cost": 20, "lag": 3, "effects": {"S2": 14}},
    "M9":  {"direction": "Соцсфера", "type": "Район", "cost": 10, "lag": 1, "effects": {"S1": 3, "S2": 3, "B1": 3}},
    "M10": {"direction": "Безопасность", "type": "Район", "cost": 12, "lag": 1, "effects": {"B1": 12, "B2": 2}},
    "M11": {"direction": "Безопасность", "type": "Район", "cost": 10, "lag": 1, "effects": {"B2": 12, "T1": -2}},
    "M12": {"direction": "Сервисы", "type": "Город", "cost": 14, "lag": 1, "effects": {"C2": 5}},
    "M13": {"direction": "Сервисы", "type": "Район", "cost": 28, "lag": 4, "effects": {"C1": 18, "E2": 2}},
    "M14": {"direction": "Сервисы", "type": "Город", "cost": 16, "lag": 1, "effects": {"C1": 5, "C2": 2}},
}

SYNERGIES = (
    ("M1", "M2", "T1", 2),
    ("M10", "M12", "B1", 2),
    ("M5", "M6", "E2", 2),
)


class ValidationError(ValueError):
    """Raised when a decision set violates the simulation rules."""


def _normalise_decisions(decisions: Sequence[Mapping[str, Any]]) -> list[tuple[str, str | None]]:
    if isinstance(decisions, (str, bytes, Mapping)) or not isinstance(decisions, Sequence):
        raise ValidationError("decisions must be a sequence of decision objects")

    normalized: list[tuple[str, str | None]] = []
    for index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, Mapping):
            raise ValidationError(f"Decision {index} must be an object with measure and optional district")
        measure_id = decision.get("measure", decision.get("id"))
        if not isinstance(measure_id, str) or measure_id not in MEASURES:
            raise ValidationError(f"Decision {index} has unknown measure {measure_id!r}; use M1–M14")
        district = decision.get("district", decision.get("район"))
        if district is not None and not isinstance(district, str):
            raise ValidationError(f"Decision {index} district must be a district name")
        normalized.append((measure_id, district))
    return normalized


def validate_decisions(decisions: Sequence[Mapping[str, Any]]) -> bool:
    """Validate a five-measure scenario; return True or raise ValidationError."""
    choices = _normalise_decisions(decisions)
    if len(choices) != 5:
        raise ValidationError(f"Exactly 5 decisions are required; received {len(choices)}")

    ids = [measure_id for measure_id, _ in choices]
    duplicates = [measure_id for measure_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValidationError(f"Repeated measures are not allowed: {', '.join(duplicates)}")

    total_cost = sum(MEASURES[measure_id]["cost"] for measure_id in ids)
    if total_cost > BUDGET:
        raise ValidationError(f"Budget exceeded: total cost is {total_cost}, limit is {BUDGET}")

    direction_counts = Counter(MEASURES[measure_id]["direction"] for measure_id in ids)
    over_limit = [direction for direction, count in direction_counts.items() if count > 2]
    if over_limit:
        direction = over_limit[0]
        raise ValidationError(f"At most 2 measures per direction; {direction} has {direction_counts[direction]}")

    by_id = dict(choices)
    for measure_id, district in choices:
        measure_type = MEASURES[measure_id]["type"]
        if measure_type == "Район":
            if district is None:
                raise ValidationError(f"{measure_id} is district-based; specify district")
            if district not in DISTRICTS:
                raise ValidationError(f"Unknown district {district!r} for {measure_id}")
        elif district is not None:
            raise ValidationError(f"{measure_id} is city-wide; omit district")

    if {"M1", "M3"}.issubset(ids):
        raise ValidationError("M1 and M3 are incompatible and cannot both be selected")
    for first, second, reason in (
        ("M4", "M7", "conflict over the same site"),
        ("M5", "M13", "duplicate program in the same district"),
    ):
        if first in by_id and second in by_id and by_id[first] == by_id[second]:
            raise ValidationError(f"{first} and {second} cannot be assigned to {by_id[first]} ({reason})")
    return True


def calculate_score(decisions: Sequence[Mapping[str, Any]]) -> float:
    """Return the scenario score, validating decisions before calculation."""
    validate_decisions(decisions)
    choices = _normalise_decisions(decisions)
    changes = {district: {indicator: 0.0 for indicator in INDICATORS} for district in DISTRICTS}
    selected = {measure_id: district for measure_id, district in choices}

    for measure_id, selected_district in choices:
        measure = MEASURES[measure_id]
        factor = (HORIZON - measure["lag"]) / HORIZON
        target_districts = DISTRICTS if measure["type"] == "Город" else (selected_district,)
        for district in target_districts:
            for indicator, effect in measure["effects"].items():
                changes[district][indicator] += effect * factor

    # Synergy bonuses are fixed and target the district of the first measure.
    for first, second, indicator, bonus in SYNERGIES:
        if first in selected and second in selected:
            district = selected[first]
            for indicator_code in (indicator,):
                changes[district][indicator_code] += bonus

    district_scores: dict[str, float] = {}
    critical_count = 0
    for district, data in DISTRICTS.items():
        score = 0.0
        for indicator in INDICATORS:
            value = min(100.0, max(0.0, data["indicators"][indicator] + changes[district][indicator]))
            score += WEIGHTS[indicator] * value
            critical_count += value < 40
        district_scores[district] = score

    average_score = sum(DISTRICTS[name]["population"] * score for name, score in district_scores.items())
    return 0.7 * average_score + 0.3 * min(district_scores.values()) - critical_count


__all__ = ["BUDGET", "DISTRICTS", "INDICATORS", "MEASURES", "SYNERGIES", "WEIGHTS", "ValidationError", "calculate_score", "validate_decisions"]

