"""Apply rules to the synthetic population: per-rule impact, funnel, coverage, and comparisons."""
from __future__ import annotations

import numpy as np

from .models import CompareResult, Rule, SimulationResult
from .variables import ULN, VARIABLES

def _threshold(rule: Rule, value: float) -> float:
    if rule.unit == "x_uln" and rule.variable in ULN:
        return value * ULN[rule.variable]
    return value


def condition_mask(rule: Rule, pop: dict[str, np.ndarray]) -> np.ndarray | None:
    """True where the rule's condition holds (before applying inclusion/exclusion)."""
    if not rule.simulatable or rule.variable not in pop or rule.operator is None:
        return None
    x = pop[rule.variable]
    op = rule.operator
    if op == "present":
        return x.astype(bool)
    if op == "absent":
        return ~x.astype(bool)
    v = _threshold(rule, rule.value)
    if op == ">=":
        return x >= v
    if op == "<=":
        return x <= v
    if op == ">":
        return x > v
    if op == "<":
        return x < v
    if op == "==":
        return x == v
    if op == "between":
        return (x >= v) & (x <= _threshold(rule, rule.value_max))
    return None


def fail_mask(rule: Rule, pop: dict[str, np.ndarray]) -> np.ndarray | None:
    """True where a patient is excluded by this rule."""
    cond = condition_mask(rule, pop)
    if cond is None:
        return None
    return ~cond if rule.kind == "inclusion" else cond


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 2) if total else 0.0


def simulate(rules: list[Rule], population_size: int = 10000, seed: int = 42) -> SimulationResult:
    """Compatibility helper for explicit generated-population callers."""
    from .cohorts import simulate_population
    from .models import PopulationChoice
    return simulate_population(rules, PopulationChoice(mode="generated", size=population_size, seed=seed))


def coverage_warnings(sim: SimulationResult) -> list[str]:
    """Plain-language caveats that must travel with every estimate."""
    warnings = []
    if sim.eligible_pct is None:
        warnings.append("No criteria could be modeled, so there is no eligibility estimate.")
        return warnings
    if sim.unmodeled_rule_ids:
        total = len(sim.modeled_rule_ids) + len(sim.unmodeled_rule_ids)
        warnings.append(f"{len(sim.unmodeled_rule_ids)} of {total} substantive criteria are not modeled. "
                        "Unsupported checks remain unknown. Passing available checks is reported separately "
                        "and does not establish protocol eligibility.")
    if sim.approximate_rule_ids:
        warnings.append(f"{len(sim.approximate_rule_ids)} modeled criteria are approximations "
                        "(qualifiers such as timing, severity or exceptions are simplified).")
    return warnings


# ---------------------------------------------------------------- comparing rule sets

def _direction(op: str, kind: str, old: float, new: float) -> str:
    """For a single threshold, does the edit admit more patients ('relaxed') or fewer ('tightened')?"""
    if new == old:
        return "none"
    if op == "==":
        return "ambiguous"
    raises_bar = op in (">=", ">")  # inclusion '>=': higher value admits fewer patients
    admits_more = (new < old) if raises_bar else (new > old)
    if kind == "exclusion":
        admits_more = not admits_more
    return "relaxed" if admits_more else "tightened"


def classify_change(old: Rule | None, new: Rule | None) -> str:
    """Structural classification of an edit. Does not depend on the sampled population."""
    if old is None:
        return "added"
    if new is None:
        return "removed"
    if old.simulatable and not new.simulatable:
        return "disabled"
    if not old.simulatable and new.simulatable:
        return "enabled"
    if not old.simulatable and not new.simulatable:
        # An unmodeled rule can still change a safety requirement. Its direction
        # cannot be inferred from simulation, so retain the edit for human review.
        return "none" if old.model_dump() == new.model_dump() else "ambiguous"
    if (old.kind, old.variable, old.unit, old.operator) != (new.kind, new.variable, new.unit, new.operator):
        return "ambiguous"
    if old.operator in ("present", "absent"):
        return "none"
    if old.operator == "between":
        lower = _direction(">=", old.kind, old.value, new.value)
        upper = _direction("<=", old.kind, old.value_max, new.value_max)
        moves = {lower, upper} - {"none"}
        if not moves:
            return "none"
        return moves.pop() if len(moves) == 1 else "mixed"
    return _direction(old.operator, old.kind, old.value, new.value)


_RELAXING = {"removed", "disabled", "relaxed", "mixed"}


def _critical(rule: Rule | None) -> bool:
    if rule is None:
        return False
    meta = VARIABLES.get(rule.variable or "")
    return rule.safety_critical or bool(meta and meta["safety_critical"])


def compare(baseline: list[Rule], proposed: list[Rule], population_size: int = 10000, seed: int = 42) -> CompareResult:
    """Compatibility helper; API callers use an explicit population choice."""
    from .cohorts import compare_population
    from .models import PopulationChoice
    return compare_population(baseline, proposed, PopulationChoice(mode="generated", size=population_size, seed=seed))
