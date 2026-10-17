"""One three-state evaluator shared by fixed and generated synthetic populations."""
from __future__ import annotations

from itertools import combinations

import numpy as np

from .models import (
    CohortInfo, CriterionResult, ExcludedPatient, FunnelStep, PatientResult, Rule,
    RuleImpact, RuleOverlap, SimulationResult, ensure_unique_ids,
)
from .simulate import _pct, condition_mask, coverage_warnings
from .variables import VARIABLES

PASS, FAIL, UNKNOWN = 0, 1, 2
STATUS_NAMES = ("pass", "fail", "unknown")


def _label(rule: Rule) -> str:
    if not rule.simulatable:
        return (rule.clause or rule.text)[:100]
    threshold = "" if rule.value is None else f" {rule.value:g}"
    if rule.operator == "between":
        threshold += f" and {rule.value_max:g}"
    return f"{rule.kind}: {VARIABLES[rule.variable]['label']} {rule.operator}{threshold} {rule.unit or ''}".strip()


def _column(raw: np.ndarray, boolean: bool) -> tuple[np.ndarray, np.ndarray]:
    if boolean:
        known = np.array([isinstance(v, (bool, np.bool_)) for v in raw], dtype=bool)
        return np.array([bool(v) if ok else False for v, ok in zip(raw, known)]), known
    if raw.dtype.kind in "iuf":
        return raw, np.isfinite(raw)
    known = np.array([isinstance(v, (int, float, np.number)) and not isinstance(v, (bool, np.bool_))
                      and np.isfinite(v) for v in raw], dtype=bool)
    return np.array([float(v) if ok else 0.0 for v, ok in zip(raw, known)]), known


def evaluate(rules: list[Rule], columns: dict[str, np.ndarray], cohort: CohortInfo,
             assumptions: list[str], patient_ids: list[str] | None = None
             ) -> tuple[SimulationResult, np.ndarray, np.ndarray]:
    ensure_unique_ids(rules)
    n = cohort.population_n
    zero, all_unknown = np.zeros(n, dtype=bool), np.ones(n, dtype=bool)
    prepared: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    failures, unknowns, modeled = {}, {}, []
    fail_count = np.zeros(n, dtype=np.int16)
    any_unknown, modeled_unknown, modeled_failure = zero.copy(), zero.copy(), zero.copy()
    for rule in rules:
        missing = zero if rule.not_applicable else all_unknown
        failed = zero
        if rule.simulatable and rule.variable in columns and not rule.not_applicable:
            if rule.variable not in prepared:
                prepared[rule.variable] = _column(columns[rule.variable], VARIABLES[rule.variable]["type"] == "bool")
            values, known = prepared[rule.variable]
            cond = condition_mask(rule, {rule.variable: values})
            failed = known & (~cond if rule.kind == "inclusion" else cond)
            missing = ~known
            if known.any():
                modeled.append(rule.id)
                modeled_unknown |= missing
                modeled_failure |= failed
        failures[rule.id], unknowns[rule.id] = failed, missing
        fail_count += failed
        any_unknown |= missing

    states = np.where(fail_count > 0, FAIL, np.where(any_unknown, UNKNOWN, PASS)).astype(np.uint8)
    modeled_states = np.where(modeled_failure, FAIL, np.where(modeled_unknown, UNKNOWN, PASS)).astype(np.uint8)
    if not modeled:
        states[:] = UNKNOWN
        modeled_states[:] = UNKNOWN
    not_applicable = [r.id for r in rules if r.not_applicable]
    unmodeled = [r.id for r in rules if r.id not in modeled and not r.not_applicable]
    approximate = [r.id for r in rules if r.id in modeled and r.fidelity == "approximate"]
    impacts, funnel = [], [FunnelStep(rule_id=None, label=cohort.label, remaining_n=n, remaining_pct=100)]
    failed_so_far, unknown_so_far = zero.copy(), zero.copy()
    for rule in rules:
        failed, missing = failures[rule.id], unknowns[rule.id]
        fail_n = int(failed.sum())
        impacts.append(RuleImpact(
            rule_id=rule.id, simulated=rule.id in modeled, fail_n=fail_n, fail_pct=_pct(fail_n, n),
            unique_fail_n=int((failed & (fail_count == 1)).sum()),
            unique_fail_pct=_pct(int((failed & (fail_count == 1)).sum()), n),
            pass_n=0 if rule.not_applicable else int((~failed & ~missing).sum()),
            unknown_n=0 if rule.not_applicable else int(missing.sum()),
        ))
        if rule.not_applicable:
            continue
        failed_so_far |= failed
        unknown_so_far = (unknown_so_far | missing) & ~failed_so_far
        remaining = int((~failed_so_far & ~unknown_so_far).sum())
        funnel.append(FunnelStep(rule_id=rule.id, label=_label(rule),
                                 remaining_n=remaining, remaining_pct=_pct(remaining, n),
                                 unknown_n=int(unknown_so_far.sum())))

    ranked = sorted([i for i in impacts if i.simulated], key=lambda i: (-i.fail_n, -i.unique_fail_n, i.rule_id))
    overlap_ids = [i.rule_id for i in ranked[:20]]
    overlaps = [RuleOverlap(rule_a_id=a, rule_b_id=b, patient_n=int((failures[a] & failures[b]).sum()))
                for a, b in combinations(overlap_ids, 2) if (failures[a] & failures[b]).any()]
    preview = list(range(n)) if n <= 500 else sorted(set(
        np.flatnonzero(states == FAIL)[:40].tolist() + np.flatnonzero(states == UNKNOWN)[:40].tolist()
        + np.flatnonzero(states == PASS)[:20].tolist()))

    def patient_id(index):
        return patient_ids[index] if patient_ids is not None else f"GEN-{index + 1:06d}"

    def value_at(rule, index):
        if rule.variable not in prepared:
            return None
        values, known = prepared[rule.variable]
        return values[index].item() if known[index] else None

    patients = [PatientResult(patient_id=patient_id(index), overall_status=STATUS_NAMES[int(states[index])], criteria=[
        CriterionResult(rule_id=r.id, status="unknown" if r.not_applicable or unknowns[r.id][index]
                        else "fail" if failures[r.id][index] else "pass", value=value_at(r, index)) for r in rules
    ]) for index in preview]
    excluded = []
    for index in np.flatnonzero(states == FAIL)[:25]:
        attrs = {r.variable: value_at(r, index) for r in rules if value_at(r, index) is not None}
        excluded.append(ExcludedPatient(patient_id=patient_id(int(index)),
                        failed_rule_ids=[r.id for r in rules if failures[r.id][index]], attributes=attrs))
    pass_n = int((states == PASS).sum()) if modeled else None
    substantive = len(modeled) + len(unmodeled)
    result = SimulationResult(
        cohort=cohort, population_n=n, seed=cohort.seed or 0,
        estimate_label="Synthetic patients passing all substantive checks; unknowns kept separate",
        eligible_n=pass_n, eligible_pct=_pct(pass_n, n) if pass_n is not None else None,
        excluded_n=int((states == FAIL).sum()), unknown_n=int((states == UNKNOWN).sum()),
        modeled_eligible_n=int((modeled_states == PASS).sum()) if modeled else None,
        modeled_unknown_n=int((modeled_states == UNKNOWN).sum()),
        complete=bool(modeled) and not unmodeled and not approximate and not (states == UNKNOWN).any(),
        coverage_pct=_pct(len(modeled), substantive) if substantive else None,
        modeled_rule_ids=modeled, approximate_rule_ids=approximate, unmodeled_rule_ids=unmodeled,
        not_applicable_rule_ids=not_applicable, not_simulated_rule_ids=[r.id for r in rules if r.id not in modeled],
        impacts=impacts, funnel=funnel, worst_rule_id=ranked[0].rule_id if ranked else None,
        sample_excluded=excluded, assumptions=assumptions, patient_results=patients,
        patient_results_complete=len(preview) == n, rule_overlaps=overlaps, overlaps_truncated=len(ranked) > 20,
    )
    result.warnings = coverage_warnings(result)
    if result.unknown_n:
        result.warnings.append("Unknown includes missing patient fields and unsupported clinical requirements; it is not an exclusion.")
    return result, states, modeled_states
