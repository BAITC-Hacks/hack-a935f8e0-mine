"""Pure deterministic model. No UI, network, randomness, or intermediate rounding."""

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Integral

from src.data import (
    BASE, BUDGET, UNIT, HORIZON, INDICATOR_NAMES, MEASURE_BY_ID, MODEL_VERSION,
    POPULATION, SECTORS, SECTOR_BY_KEY, SYNERGIES, WEIGHTS,
)


class InvalidScenario(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(" ".join(errors))


@dataclass(frozen=True)
class Decision:
    measure_id: str
    district: str | None = None


@dataclass
class Score:
    total: float
    average: float
    minimum: float
    weakest: str
    district_scores: dict[str, float]
    critical: list[dict]
    sectors: dict[str, float]


@dataclass
class Scenario:
    mode: str
    allocations: dict[str, int]
    decisions: list[dict]
    indicators: dict[str, dict[str, float]]
    score: Score
    contributions: list[dict]
    synergies: list[str]

    @property
    def spent(self) -> int:
        return sum(self.allocations.values())

    @property
    def remaining(self) -> int:
        return BUDGET - self.spent

    def payload(self) -> dict:
        return {
            "model_version": MODEL_VERSION,
            "data_type": "Синтетический учебный датасет, не статистика реальной Астаны",
            "budget_kzt": BUDGET, "spent_kzt": self.spent, "remaining_kzt": self.remaining,
            "horizon_quarters": HORIZON,
            "mode_note": (
                "Непрерывная модель: I'=I+(100-I)*0.35*(1-exp(-b/(B*W))). "
                "Это авторская модель бюджетных программ, а не правила каталога мероприятий."
                if self.mode == "allocation" else "Строгие правила каталога мероприятий из датасета."
            ),
            "baseline": asdict(BASELINE),
            "indicator_names": INDICATOR_NAMES,
            "sector_names": {s.key: s.label for s in SECTORS},
            "baseline_indicators": BASE,
            "deltas": {
                "score": self.score.total - BASELINE.total,
                "districts": {d: self.score.district_scores[d] - BASELINE.district_scores[d] for d in BASE},
                "sectors": {s.key: self.score.sectors[s.key] - BASELINE.sectors[s.key] for s in SECTORS},
                "indicators": {d: {k: self.indicators[d][k] - BASE[d][k] for k in WEIGHTS} for d in BASE},
            },
            **asdict(self),
        }

    @property
    def fingerprint(self) -> str:
        serialized = json.dumps(self.payload(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def score_indicators(indicators: dict) -> Score:
    district_scores = {
        d: math.fsum(WEIGHTS[k] * indicators[d][k] for k in WEIGHTS) for d in BASE
    }
    average = math.fsum(POPULATION[d] * district_scores[d] for d in BASE)
    weakest = min(district_scores, key=district_scores.get)
    minimum = district_scores[weakest]
    critical = [
        {"district": d, "indicator": k, "value": v}
        for d, values in indicators.items() for k, v in values.items() if v < 40
    ]
    total = max(0.0, min(100.0, .7 * average + .3 * minimum - len(critical)))
    sectors = {
        s.key: math.fsum(
            POPULATION[d] * WEIGHTS[k] * indicators[d][k]
            for d in BASE for k in s.indicators
        ) / math.fsum(WEIGHTS[k] for k in s.indicators)
        for s in SECTORS
    }
    return Score(total, average, minimum, weakest, district_scores, critical, sectors)


BASELINE = score_indicators(BASE)


def validate_allocations(allocations: dict[str, int]) -> list[str]:
    if set(allocations) != set(SECTOR_BY_KEY):
        return ["Укажите бюджет для всех пяти направлений и только для них."]
    errors = []
    for key, amount in allocations.items():
        if isinstance(amount, bool) or not isinstance(amount, Integral) or amount < 0:
            errors.append(f"{SECTOR_BY_KEY[key].label}: требуется целая неотрицательная сумма в тенге.")
    if not errors and sum(allocations.values()) > BUDGET:
        excess = sum(allocations.values()) - BUDGET
        errors.append(f"Бюджет превышен на {excess / UNIT:g} ед. Уменьшите расходы.")
    return errors


def simulate_allocations(allocations: dict[str, int]) -> Scenario:
    errors = validate_allocations(allocations)
    if errors:
        raise InvalidScenario(errors)
    after = {d: dict(values) for d, values in BASE.items()}
    contributions = []
    for sector in SECTORS:
        weight = math.fsum(WEIGHTS[k] for k in sector.indicators)
        # At the sector's reference budget, close 22.12% of its remaining gap.
        fraction = .35 * -math.expm1(-allocations[sector.key] / (BUDGET * weight))
        for d in BASE:
            for k in sector.indicators:
                after[d][k] += (100 - BASE[d][k]) * fraction
        contributions.append({
            "sector": sector.key, "budget_kzt": allocations[sector.key],
            "gap_closed_fraction": fraction,
        })
    return Scenario("allocation", dict(allocations), [], after, score_indicators(after), contributions, [])


def validate_decisions(decisions: list[Decision], *, require_five: bool = True) -> list[str]:
    errors = []
    if require_five and len(decisions) != 5:
        errors.append("Нужно выбрать ровно 5 мероприятий.")
    elif len(decisions) > 5:
        errors.append("Можно выбрать не более 5 мероприятий.")
    ids = [d.measure_id for d in decisions]
    if len(set(ids)) != len(ids):
        errors.append("Повторы запрещены: каждое мероприятие можно выбрать только один раз.")
    if any(m not in MEASURE_BY_ID for m in ids):
        errors.append("Выберите мероприятие из каталога в каждой строке.")
        return errors
    counts = Counter(MEASURE_BY_ID[m].sector for m in ids)
    if any(n > 2 for n in counts.values()):
        errors.append("Не более 2 мероприятий из одного направления.")
    spent = sum(MEASURE_BY_ID[m].cost for m in ids)
    if spent > BUDGET:
        errors.append(f"Бюджет превышен на {(spent - BUDGET) / UNIT:g} ед.")
    for d in decisions:
        measure = MEASURE_BY_ID[d.measure_id]
        if measure.scope == "district" and d.district not in BASE:
            errors.append(f"{measure.id}: обязательно выберите район.")
        if measure.scope == "city" and d.district is not None:
            errors.append(f"{measure.id}: городское мероприятие не должно иметь район.")
    if "M1" in ids and "M3" in ids:
        errors.append("M1 и M3 несовместимы: выберите автобусные полосы или ЛРТ.")
    chosen = {d.measure_id: d.district for d in decisions}
    for first, second, reason in (("M4", "M7", "конфликт за участок"), ("M5", "M13", "дублирование программы")):
        if first in chosen and second in chosen and chosen[first] == chosen[second]:
            errors.append(f"{first} и {second} нельзя размещать в одном районе: {reason}.")
    return errors


def simulate_decisions(decisions: list[Decision]) -> Scenario:
    errors = validate_decisions(decisions)
    if errors:
        raise InvalidScenario(errors)
    # Canonical order makes effects and identity independent of selection order.
    decisions = sorted(decisions, key=lambda d: d.measure_id)
    after = {d: dict(values) for d, values in BASE.items()}
    allocations = {s.key: 0 for s in SECTORS}
    contributions, applied_synergies = [], []
    for decision in decisions:
        measure = MEASURE_BY_ID[decision.measure_id]
        allocations[measure.sector] += measure.cost
        targets = list(BASE) if measure.scope == "city" else [decision.district]
        factor = (HORIZON - measure.lag) / HORIZON
        changes = {k: value * factor for k, value in measure.effects}
        for d in targets:
            for k, delta in changes.items():
                after[d][k] += delta
        contributions.append({
            "id": measure.id, "name": measure.name, "cost_kzt": measure.cost,
            "districts": targets, "lag": measure.lag, "realized_effects": changes,
        })
    chosen = {d.measure_id: d.district for d in decisions}
    for first, second, indicator, bonus in SYNERGIES:
        if first in chosen and second in chosen:
            district = chosen[first]
            after[district][indicator] += bonus
            applied_synergies.append(f"{first} + {second}: {district}, {indicator} +{bonus}")
    # Clip after ALL effects, including negative ones and fixed synergies.
    after = {d: {k: max(0.0, min(100.0, v)) for k, v in row.items()} for d, row in after.items()}
    return Scenario("measures", allocations, [asdict(d) for d in decisions], after,
                    score_indicators(after), contributions, applied_synergies)


EXAMPLE = [Decision("M7", "Нура"), Decision("M8", "Нура"), Decision("M10", "Нура"),
           Decision("M12"), Decision("M5", "Сарыарка")]
