"""Immutable catalogue edits; partial plans obey every rule except final count."""

from src.model import Decision, InvalidScenario, validate_decisions


def add_measure(plan: list[Decision], measure_id: str, district: str | None) -> list[Decision]:
    proposed = [*plan, Decision(measure_id, district)]
    errors = validate_decisions(proposed, require_five=False)
    if errors:
        raise InvalidScenario(errors)
    return proposed


def remove_measure(plan: list[Decision], measure_id: str) -> list[Decision]:
    return [decision for decision in plan if decision.measure_id != measure_id]


def move_measure(plan: list[Decision], measure_id: str, district: str) -> list[Decision]:
    if measure_id not in {d.measure_id for d in plan}:
        raise InvalidScenario(["Сначала добавьте мероприятие в план."])
    proposed = [Decision(d.measure_id, district) if d.measure_id == measure_id else d for d in plan]
    errors = validate_decisions(proposed, require_five=False)
    if errors:
        raise InvalidScenario(errors)
    return proposed
