import pytest

from src.model import Decision, EXAMPLE, InvalidScenario, simulate_decisions
from src.planner import add_measure, move_measure, remove_measure


def test_plan_edit_is_immutable_and_five_decisions_still_required():
    original = []
    plan = add_measure(original, "M7", "Нура")
    assert original == []
    assert plan == [Decision("M7", "Нура")]
    with pytest.raises(InvalidScenario, match="ровно 5"):
        simulate_decisions(plan)
    assert remove_measure(plan, "M7") == []
    assert len(plan) == 1


def test_cannot_add_sixth_duplicate_or_incompatible_measure():
    with pytest.raises(InvalidScenario, match="не более 5"):
        add_measure(EXAMPLE, "M1", "Нура")
    with pytest.raises(InvalidScenario, match="Повторы"):
        add_measure([Decision("M7", "Нура")], "M7", "Алматы")
    with pytest.raises(InvalidScenario, match="несовместимы"):
        add_measure([Decision("M1", "Нура")], "M3", "Алматы")


def test_move_changes_scenario_and_preserves_budget():
    before = simulate_decisions(EXAMPLE)
    moved = move_measure(EXAMPLE, "M7", "Есиль")
    after = simulate_decisions(moved)
    assert before.spent == after.spent
    assert before.fingerprint != after.fingerprint
    assert before.score.total != after.score.total
    assert EXAMPLE[0].district == "Нура"


def test_move_rejects_conflicts_city_measures_and_unknown_districts():
    plan = [Decision("M4", "Есиль"), Decision("M7", "Нура")]
    with pytest.raises(InvalidScenario, match="участок"):
        move_measure(plan, "M7", "Есиль")
    with pytest.raises(InvalidScenario, match="не должно"):
        move_measure([Decision("M12")], "M12", "Нура")
    with pytest.raises(InvalidScenario):
        move_measure(EXAMPLE, "M7", "Unknown")
