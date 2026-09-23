from copy import deepcopy
import math
import random

import pytest

from src.data import BASE, BUDGET, MEASURE_BY_ID, POPULATION, SECTORS, WEIGHTS
from src.model import (
    BASELINE, EXAMPLE, Decision, InvalidScenario, score_indicators,
    simulate_allocations, simulate_decisions, validate_decisions,
)


def allocations(amount=0):
    return {s.key: amount for s in SECTORS}


def test_source_baseline_and_reference_scenario():
    assert math.fsum(WEIGHTS.values()) == 1
    assert math.fsum(POPULATION.values()) == 1
    assert BASELINE.total == pytest.approx(52.55768)
    assert BASELINE.district_scores == pytest.approx({
        "Есиль": 62.99, "Алматы": 57.06, "Сарыарка": 54.65, "Байконур": 56.63, "Нура": 49.18,
    })
    result = simulate_decisions(EXAMPLE)
    assert result.spent == 950_000_000
    assert result.remaining == 50_000_000
    assert result.score.total == pytest.approx(56.54307)
    assert result.score.critical == []
    assert result.indicators["Нура"]["B1"] == 55 + 12 * 7 / 8 + 2
    assert result.indicators["Есиль"]["C2"] == 70 + 5 * 7 / 8


def test_order_independence_and_no_input_mutation():
    original = deepcopy(BASE)
    result = simulate_decisions(EXAMPLE)
    assert simulate_decisions(list(reversed(EXAMPLE))).fingerprint == result.fingerprint
    assert BASE == original


def test_zero_and_remaining_budget():
    assert simulate_allocations(allocations()).score.total == BASELINE.total
    partial = simulate_allocations(allocations(100_000_000))
    full = simulate_allocations(allocations(200_000_000))
    assert partial.remaining == 500_000_000
    assert partial.score.total < full.score.total
    assert full.remaining == 0


@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf"), True, "10", 0.5])
def test_reject_bad_budget_types(amount):
    plan = allocations()
    plan["transport"] = amount
    with pytest.raises(InvalidScenario):
        simulate_allocations(plan)


def test_budget_cannot_be_bypassed_at_model_boundary():
    plan = allocations(200_000_000)
    plan["transport"] += 1
    with pytest.raises(InvalidScenario, match="превышен"):
        simulate_allocations(plan)
    with pytest.raises(InvalidScenario):
        simulate_allocations({"transport": 0})


def test_different_allocations_change_score_and_have_diminishing_returns():
    first, second = allocations(), allocations()
    first["transport"] = BUDGET
    second["social"] = BUDGET
    assert simulate_allocations(first).score.total != simulate_allocations(second).score.total
    previous, deltas = BASE["Нура"]["T1"], []
    for amount in (100_000_000, 200_000_000, 300_000_000):
        plan = allocations()
        plan["transport"] = amount
        current = simulate_allocations(plan).indicators["Нура"]["T1"]
        deltas.append(current - previous)
        previous = current
    assert deltas[0] > deltas[1] > deltas[2] > 0


def test_random_valid_budgets_stay_bounded_and_monotone():
    rng = random.Random(7)
    for _ in range(100):
        # 0–100 chunks of 10m distributed over five sectors; retain spare budget.
        plan = allocations()
        for _ in range(rng.randrange(100)):
            plan[rng.choice(SECTORS).key] += 10_000_000
        result = simulate_allocations(plan)
        assert 0 <= result.score.total <= 100
        assert all(BASE[d][k] <= v <= 100 for d, row in result.indicators.items() for k, v in row.items())
        plan["transport"] += 10_000_000
        assert simulate_allocations(plan).score.total >= result.score.total


def test_critical_threshold_is_strict_and_score_is_clipped():
    values = {d: {k: 40 for k in WEIGHTS} for d in BASE}
    assert score_indicators(values).critical == []
    values["Нура"]["S1"] = 39.999
    assert len(score_indicators(values).critical) == 1
    assert score_indicators({d: {k: 0 for k in WEIGHTS} for d in BASE}).total == 0
    assert score_indicators({d: {k: 100 for k in WEIGHTS} for d in BASE}).total == 100


@pytest.mark.parametrize("plan,match", [
    (EXAMPLE[:4], "ровно 5"),
    ([*EXAMPLE[:4], EXAMPLE[0]], "Повторы"),
    ([Decision("M99"), *EXAMPLE[1:]], "каталога"),
    ([Decision("M7"), *EXAMPLE[1:]], "выберите район"),
    ([*EXAMPLE[:3], Decision("M12", "Нура"), EXAMPLE[4]], "не должно"),
    ([Decision("M7", "Нура"), Decision("M8", "Нура"), Decision("M9", "Нура"),
      Decision("M10", "Нура"), Decision("M12")], "Не более 2"),
    ([Decision("M1", "Нура"), Decision("M3", "Есиль"), Decision("M9", "Нура"),
      Decision("M10", "Нура"), Decision("M12")], "M1 и M3"),
    ([Decision("M4", "Нура"), Decision("M7", "Нура"), Decision("M9", "Нура"),
      Decision("M10", "Нура"), Decision("M12")], "участок"),
    ([Decision("M5", "Нура"), Decision("M13", "Нура"), Decision("M9", "Нура"),
      Decision("M10", "Нура"), Decision("M12")], "дублирование"),
    ([Decision("M3", "Нура"), Decision("M5", "Сарыарка"), Decision("M7", "Нура"),
      Decision("M10", "Нура"), Decision("M13", "Алматы")], "превышен"),
])
def test_invalid_catalog_scenarios_are_blocked(plan, match):
    with pytest.raises(InvalidScenario, match=match):
        simulate_decisions(plan)


def test_negative_effect_and_other_synergies():
    plan = [Decision("M1", "Есиль"), Decision("M2"), Decision("M5", "Сарыарка"),
            Decision("M6"), Decision("M11", "Нура")]
    assert sum(MEASURE_BY_ID[d.measure_id].cost for d in plan) <= BUDGET
    result = simulate_decisions(plan)
    assert result.indicators["Есиль"]["T1"] == 45 + 6 * .75 + 4 * .75 + 2
    assert result.indicators["Нура"]["T1"] == 55 + 4 * .75 - 2 * .875
    assert result.indicators["Сарыарка"]["E2"] == 40 + 14 * .625 + 3 * .5 + 2
    assert len(result.synergies) == 2


def test_district_conflicts_allow_different_districts():
    plan = [Decision("M4", "Есиль"), Decision("M7", "Нура"), Decision("M9", "Нура"),
            Decision("M10", "Нура"), Decision("M12")]
    assert validate_decisions(plan) == []
