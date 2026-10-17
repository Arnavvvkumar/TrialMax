"""Apply rules to the synthetic population: per-rule impact, funnel, coverage, and comparisons."""
from __future__ import annotations

import numpy as np

from .models import (
    CompareResult, ExcludedPatient, FunnelStep, Rule, RuleChange, RuleImpact, SimulationResult,
    ensure_unique_ids,
)
from .population import ASSUMPTIONS, POPULATION_VERSION, generate_population
from .variables import ULN, VARIABLES

SAMPLE_EXCLUDED = 25


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


def _masks(rules: list[Rule], pop: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    ensure_unique_ids(rules)
    out = {}
    for rule in rules:
        mask = fail_mask(rule, pop)
        if mask is not None:
            out[rule.id] = mask
    return out


def _eligible(masks: dict[str, np.ndarray], n: int) -> np.ndarray:
    any_fail = np.zeros(n, dtype=bool)
    for mask in masks.values():
        any_fail |= mask
    return ~any_fail


def simulate(rules: list[Rule], population_size: int = 10000, seed: int = 42) -> SimulationResult:
    pop = generate_population(population_size, seed)
    n = population_size
    masks = _masks(rules, pop)
    eligible = _eligible(masks, n)
    fail_count = np.zeros(n, dtype=np.int32)
    for mask in masks.values():
        fail_count += mask

    impacts = []
    funnel = [FunnelStep(rule_id=None, label="Synthetic population", remaining_n=n, remaining_pct=100.0)]
    remaining = np.ones(n, dtype=bool)
    for rule in rules:
        mask = masks.get(rule.id)
        if mask is None:
            impacts.append(RuleImpact(rule_id=rule.id, simulated=False))
            continue
        fail_n = int(mask.sum())
        unique_n = int((mask & (fail_count == 1)).sum())
        impacts.append(RuleImpact(rule_id=rule.id, simulated=True, fail_n=fail_n, fail_pct=_pct(fail_n, n),
                                  unique_fail_n=unique_n, unique_fail_pct=_pct(unique_n, n)))
        remaining &= ~mask
        left = int(remaining.sum())
        funnel.append(FunnelStep(rule_id=rule.id, label=(rule.clause or rule.text)[:80],
                                 remaining_n=left, remaining_pct=_pct(left, n)))

    modeled = [r.id for r in rules if r.id in masks]
    approximate = [r.id for r in rules if r.id in masks and r.fidelity == "approximate"]
    not_applicable = [r.id for r in rules if r.id not in masks and r.not_applicable]
    unmodeled = [r.id for r in rules if r.id not in masks and not r.not_applicable]
    substantive = len(modeled) + len(unmodeled)
    simulated_impacts = [i for i in impacts if i.simulated]
    worst = max(simulated_impacts, key=lambda i: (i.fail_n, i.unique_fail_n)).rule_id if simulated_impacts else None

    used_vars = sorted({r.variable for r in rules if r.id in masks and r.variable})
    sample = []
    for pid in np.flatnonzero(~eligible)[:SAMPLE_EXCLUDED] if masks else []:
        failed = [rid for rid, mask in masks.items() if mask[pid]]
        attrs = {}
        for var in used_vars:
            val = pop[var][pid]
            kind = VARIABLES.get(var, {}).get("type")
            attrs[var] = bool(val) if kind == "bool" else (int(val) if kind == "int" else round(float(val), 2))
        sample.append(ExcludedPatient(patient_id=int(pid), failed_rule_ids=failed, attributes=attrs))

    eligible_n = int(eligible.sum()) if modeled else None
    return SimulationResult(
        population_n=n, seed=seed,
        eligible_n=eligible_n, eligible_pct=_pct(eligible_n, n) if modeled else None,
        complete=bool(modeled) and not unmodeled and not approximate,
        coverage_pct=_pct(len(modeled), substantive) if substantive else None,
        modeled_rule_ids=modeled, approximate_rule_ids=approximate, unmodeled_rule_ids=unmodeled,
        not_applicable_rule_ids=not_applicable,
        not_simulated_rule_ids=[r.id for r in rules if r.id not in masks],
        impacts=impacts, funnel=funnel, worst_rule_id=worst,
        sample_excluded=sample, assumptions=ASSUMPTIONS,
        data_source="generated-synthetic", cohort_version=POPULATION_VERSION,
    )


def coverage_warnings(sim: SimulationResult) -> list[str]:
    """Plain-language caveats that must travel with every estimate."""
    warnings = []
    if sim.eligible_pct is None:
        warnings.append("No criteria could be modeled, so there is no eligibility estimate.")
        return warnings
    if sim.unmodeled_rule_ids:
        total = len(sim.modeled_rule_ids) + len(sim.unmodeled_rule_ids)
        warnings.append(f"{len(sim.unmodeled_rule_ids)} of {total} substantive criteria are not modeled. "
                        "The percentage counts only modeled checks; it does not estimate real-world eligibility.")
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
    pop = generate_population(population_size, seed)
    n = population_size
    base_result = simulate(baseline, population_size, seed)
    prop_result = simulate(proposed, population_size, seed)
    base_eligible = _eligible(_masks(baseline, pop), n)
    prop_eligible = _eligible(_masks(proposed, pop), n)

    old_by_id = {r.id: r for r in baseline}
    new_by_id = {r.id: r for r in proposed}
    changes: list[RuleChange] = []
    relaxed_critical, review_critical = [], []
    for rid in sorted(set(old_by_id) | set(new_by_id)):
        old, new = old_by_id.get(rid), new_by_id.get(rid)
        change = classify_change(old, new)
        if change == "none":
            continue
        critical = _critical(old) or _critical(new)
        changes.append(RuleChange(rule_id=rid, change=change, safety_critical=critical))
        if critical and change in _RELAXING:
            relaxed_critical.append(rid)
        elif critical and change == "ambiguous":
            review_critical.append(rid)

    both = base_result.eligible_n is not None and prop_result.eligible_n is not None
    return CompareResult(
        baseline=base_result, proposed=prop_result,
        eligible_change_n=(prop_result.eligible_n - base_result.eligible_n) if both else None,
        eligible_change_pct_points=round(prop_result.eligible_pct - base_result.eligible_pct, 2) if both else None,
        newly_eligible_n=int((prop_eligible & ~base_eligible).sum()) if both else None,
        newly_excluded_n=int((base_eligible & ~prop_eligible).sum()) if both else None,
        changes=changes, changed_rule_ids=[c.rule_id for c in changes],
        relaxed_safety_critical_rule_ids=relaxed_critical,
        review_safety_critical_rule_ids=review_critical,
    )
