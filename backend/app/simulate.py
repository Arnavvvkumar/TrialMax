"""Apply rules to the synthetic population: per-rule impact, funnel, and why-excluded."""
from __future__ import annotations

import numpy as np

from .models import CompareResult, ExcludedPatient, FunnelStep, Rule, RuleImpact, SimulationResult
from .population import ASSUMPTIONS, generate_population
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
    if rule.value is None:
        return None
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
    if op == "between" and rule.value_max is not None:
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


def _eligible_mask(rules: list[Rule], pop: dict[str, np.ndarray], n: int) -> tuple[np.ndarray, dict]:
    masks = {}
    for rule in rules:
        mask = fail_mask(rule, pop)
        if mask is not None:
            masks[rule.id] = mask
    any_fail = np.zeros(n, dtype=bool)
    for mask in masks.values():
        any_fail |= mask
    return ~any_fail, masks


def simulate(rules: list[Rule], population_size: int = 10000, seed: int = 42) -> SimulationResult:
    pop = generate_population(population_size, seed)
    n = population_size
    eligible, masks = _eligible_mask(rules, pop, n)
    fail_count = np.zeros(n, dtype=np.int32)
    for mask in masks.values():
        fail_count += mask

    impacts, funnel = [], [FunnelStep(rule_id=None, label="Synthetic population", remaining_n=n, remaining_pct=100.0)]
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
        funnel.append(FunnelStep(rule_id=rule.id, label=rule.text[:80], remaining_n=left, remaining_pct=_pct(left, n)))

    simulated = [i for i in impacts if i.simulated]
    worst = max(simulated, key=lambda i: (i.fail_n, i.unique_fail_n)).rule_id if simulated else None

    used_vars = sorted({r.variable for r in rules if r.id in masks and r.variable})
    sample = []
    for pid in np.flatnonzero(~eligible)[:SAMPLE_EXCLUDED]:
        failed = [rid for rid, mask in masks.items() if mask[pid]]
        attrs = {}
        for var in used_vars:
            val = pop[var][pid]
            kind = VARIABLES.get(var, {}).get("type")
            attrs[var] = bool(val) if kind == "bool" else (int(val) if kind == "int" else round(float(val), 2))
        sample.append(ExcludedPatient(patient_id=int(pid), failed_rule_ids=failed, attributes=attrs))

    eligible_n = int(eligible.sum())
    return SimulationResult(
        population_n=n, seed=seed, eligible_n=eligible_n, eligible_pct=_pct(eligible_n, n),
        impacts=impacts, funnel=funnel, worst_rule_id=worst,
        not_simulated_rule_ids=[r.id for r in rules if r.id not in masks],
        sample_excluded=sample, assumptions=ASSUMPTIONS,
    )


def _rule_signature(rule: Rule) -> tuple:
    return (rule.kind, rule.variable, rule.operator, rule.value, rule.value_max, rule.unit, rule.simulatable)


def _is_relaxation(old: Rule | None, new: Rule | None, pop, n) -> bool:
    """A change is a relaxation if fewer patients fail under the new rule."""
    old_mask = fail_mask(old, pop) if old else None
    new_mask = fail_mask(new, pop) if new else None
    old_fail = int(old_mask.sum()) if old_mask is not None else 0
    new_fail = int(new_mask.sum()) if new_mask is not None else 0
    return new_fail < old_fail


def compare(baseline: list[Rule], proposed: list[Rule], population_size: int = 10000, seed: int = 42) -> CompareResult:
    pop = generate_population(population_size, seed)
    n = population_size
    base_result = simulate(baseline, population_size, seed)
    prop_result = simulate(proposed, population_size, seed)
    base_eligible, _ = _eligible_mask(baseline, pop, n)
    prop_eligible, _ = _eligible_mask(proposed, pop, n)

    old_by_id = {r.id: r for r in baseline}
    new_by_id = {r.id: r for r in proposed}
    changed, relaxed_critical = [], []
    for rid in sorted(set(old_by_id) | set(new_by_id)):
        old, new = old_by_id.get(rid), new_by_id.get(rid)
        if old is not None and new is not None and _rule_signature(old) == _rule_signature(new):
            continue
        changed.append(rid)
        critical = (old is not None and old.safety_critical) or (new is not None and new.safety_critical)
        if critical and _is_relaxation(old, new, pop, n):
            relaxed_critical.append(rid)

    return CompareResult(
        baseline=base_result, proposed=prop_result,
        eligible_change_n=prop_result.eligible_n - base_result.eligible_n,
        eligible_change_pct_points=round(prop_result.eligible_pct - base_result.eligible_pct, 2),
        newly_eligible_n=int((prop_eligible & ~base_eligible).sum()),
        newly_excluded_n=int((base_eligible & ~prop_eligible).sum()),
        changed_rule_ids=changed, relaxed_safety_critical_rule_ids=relaxed_critical,
    )
