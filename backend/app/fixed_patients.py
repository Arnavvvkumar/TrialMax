"""Evaluation of eligibility rules against the checked-in synthetic patient cohort."""
from __future__ import annotations

import json
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

from .models import (
    CriterionResult, ExcludedPatient, FunnelStep, PatientResult, Rule, RuleImpact,
    RuleOverlap, SimulationResult, ensure_unique_ids,
)
from .simulate import _pct, _threshold
from .variables import VARIABLES

DATA_PATH = Path(__file__).resolve().parents[2] / "frontend" / "synthetic_data" / "patients.json"
Status = Literal["pass", "fail", "unknown"]

_FIELD_MAP = {
    "age_years": ("age", 1.0),
    "ecog_score": ("ecog", 1.0),
    "hemoglobin_g_dl": ("hemoglobin", 1.0),
    "anc_cells_ul": ("anc", 0.001),
    "platelets_cells_ul": ("platelets", 0.001),
    "egfr_kidney_ml_min_1_73m2": ("egfr", 1.0),
    "ast_u_l": ("ast", 1.0),
    "alt_u_l": ("alt", 1.0),
    "prior_systemic_therapy_lines": ("prior_systemic_lines", 1.0),
    "brain_metastases": ("brain_mets", 1.0),
    "active_infection": ("active_infection", 1.0),
}


def normalize_patients(raw: Any) -> tuple[dict[str, Any], ...]:
    """Normalize local JSON or Chalk feature rows to the simulator's variable names."""
    patients = raw.get("patients") if isinstance(raw, dict) else raw
    if not isinstance(patients, list) or not patients:
        raise ValueError("Fixed patient data must contain a non-empty 'patients' list.")
    cleaned: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, patient in enumerate(patients):
        if not isinstance(patient, dict) or patient.get("patient_id", patient.get("id")) in (None, ""):
            raise ValueError(f"Fixed patient at index {index} must be an object with a patient_id.")
        patient_id = str(patient.get("patient_id", patient.get("id")))
        if patient_id in ids:
            raise ValueError(f"Fixed patient data has duplicate id {patient_id!r}.")
        ids.add(patient_id)
        normalized: dict[str, Any] = {"id": patient_id}
        for source, (target, factor) in _FIELD_MAP.items():
            value = patient.get(source)
            normalized[target] = value * factor if isinstance(value, (int, float)) and not isinstance(value, bool) else value
        sex = patient.get("sex_at_birth")
        normalized["female"] = True if sex == "female" else False if sex == "male" else None
        cleaned.append(normalized)
    return tuple(cleaned)


@lru_cache(maxsize=1)
def load_patients() -> tuple[dict[str, Any], ...]:
    """Load and normalize the frontend's fixed synthetic cohort."""
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Fixed patient data is missing: {DATA_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Fixed patient data is not valid JSON: {exc.msg}") from exc
    return normalize_patients(raw)


def evaluate_criterion(rule: Rule, patient: dict[str, Any]) -> Status:
    """Return pass/fail/unknown without treating an absent value as a failed criterion."""
    if not rule.simulatable or not rule.variable or not rule.operator:
        return "unknown"
    if rule.variable not in patient or patient[rule.variable] is None:
        return "unknown"
    value = patient[rule.variable]
    kind = VARIABLES.get(rule.variable, {}).get("type")
    try:
        if rule.operator == "present":
            if kind != "bool" or not isinstance(value, bool):
                return "unknown"
            condition = value
        elif rule.operator == "absent":
            if kind != "bool" or not isinstance(value, bool):
                return "unknown"
            condition = not value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return "unknown"
            threshold = _threshold(rule, rule.value)
            if rule.operator == ">=":
                condition = value >= threshold
            elif rule.operator == "<=":
                condition = value <= threshold
            elif rule.operator == ">":
                condition = value > threshold
            elif rule.operator == "<":
                condition = value < threshold
            elif rule.operator == "==":
                condition = value == threshold
            elif rule.operator == "between":
                condition = threshold <= value <= _threshold(rule, rule.value_max)
            else:
                return "unknown"
    except (TypeError, ValueError):
        return "unknown"
    passes = condition if rule.kind == "inclusion" else not condition
    return "pass" if passes else "fail"


def simulate_patients(rules: list[Rule], patients: tuple[dict[str, Any], ...], *, data_source: str,
                      cohort_version: str | None = "synthetic-v1", source_run_id: str | None = None) -> SimulationResult:
    """Evaluate rules against normalized patient records from any feature provider."""
    ensure_unique_ids(rules)
    outcomes: list[PatientResult] = []
    failures_by_rule: dict[str, set[str]] = {rule.id: set() for rule in rules}
    known_by_rule: dict[str, int] = {rule.id: 0 for rule in rules}

    for patient in patients:
        criteria = []
        for rule in rules:
            status = evaluate_criterion(rule, patient)
            criteria.append(CriterionResult(rule_id=rule.id, status=status))
            if status != "unknown":
                known_by_rule[rule.id] += 1
            if status == "fail":
                failures_by_rule[rule.id].add(patient["id"])
        statuses = [item.status for item in criteria]
        overall: Status = "fail" if "fail" in statuses else ("unknown" if "unknown" in statuses else "pass")
        outcomes.append(PatientResult(patient_id=patient["id"], criteria=criteria, overall_status=overall))

    n = len(patients)
    failed_by_patient = {
        outcome.patient_id: {item.rule_id for item in outcome.criteria if item.status == "fail"}
        for outcome in outcomes
    }
    impacts = []
    for rule in rules:
        failed = failures_by_rule[rule.id]
        unique = sum(len(failed_by_patient[patient_id]) == 1 for patient_id in failed)
        impacts.append(RuleImpact(
            rule_id=rule.id, simulated=rule.simulatable and known_by_rule[rule.id] > 0,
            fail_n=len(failed), fail_pct=_pct(len(failed), n), unique_fail_n=unique,
            unique_fail_pct=_pct(unique, n),
        ))

    funnel = [FunnelStep(rule_id=None, label="Fixed synthetic patients", remaining_n=n, remaining_pct=100.0)]
    failed_so_far: set[str] = set()
    unknown_so_far: set[str] = set()
    for rule in rules:
        for outcome in outcomes:
            status = next(item.status for item in outcome.criteria if item.rule_id == rule.id)
            if status == "fail":
                failed_so_far.add(outcome.patient_id)
            elif status == "unknown" and outcome.patient_id not in failed_so_far:
                unknown_so_far.add(outcome.patient_id)
        unknown_so_far -= failed_so_far
        remaining = n - len(failed_so_far) - len(unknown_so_far)
        funnel.append(FunnelStep(rule_id=rule.id, label=(rule.clause or rule.text)[:80],
                                 remaining_n=remaining, remaining_pct=_pct(remaining, n),
                                 unknown_n=len(unknown_so_far)))

    overlaps = [RuleOverlap(rule_a_id=left.id, rule_b_id=right.id,
                            patient_n=len(failures_by_rule[left.id] & failures_by_rule[right.id]))
                for left, right in combinations(rules, 2)
                if failures_by_rule[left.id] & failures_by_rule[right.id]]
    modeled = [rule.id for rule in rules if rule.simulatable]
    approximate = [rule.id for rule in rules if rule.simulatable and rule.fidelity == "approximate"]
    not_applicable = [rule.id for rule in rules if not rule.simulatable and rule.not_applicable]
    unmodeled = [rule.id for rule in rules if not rule.simulatable and not rule.not_applicable]
    substantive = len(modeled) + len(unmodeled)
    pass_n = sum(outcome.overall_status == "pass" for outcome in outcomes)
    sample = [ExcludedPatient(patient_id=outcome.patient_id,
                              failed_rule_ids=sorted(failed_by_patient[outcome.patient_id]), attributes={})
              for outcome in outcomes if outcome.overall_status == "fail"]
    worst = max(impacts, key=lambda impact: (impact.fail_n, impact.unique_fail_n)).rule_id if impacts else None
    return SimulationResult(
        population_n=n, seed=0, eligible_n=pass_n if modeled else None,
        eligible_pct=_pct(pass_n, n) if modeled else None,
        complete=bool(modeled) and not unmodeled and not approximate and all(
            outcome.overall_status != "unknown" for outcome in outcomes),
        coverage_pct=_pct(len(modeled), substantive) if substantive else None,
        modeled_rule_ids=modeled, approximate_rule_ids=approximate, unmodeled_rule_ids=unmodeled,
        not_applicable_rule_ids=not_applicable,
        not_simulated_rule_ids=[rule.id for rule in rules if not rule.simulatable],
        impacts=impacts, funnel=funnel, worst_rule_id=worst, sample_excluded=sample,
        assumptions=["Synthetic cohort only; not real patients."],
        patient_results=outcomes, rule_overlaps=overlaps,
        data_source=data_source, cohort_version=cohort_version, source_run_id=source_run_id,
    )


def simulate_fixed(rules: list[Rule]) -> SimulationResult:
    """Evaluate every rule against the checked-in fixed synthetic cohort."""
    return simulate_patients(rules, load_patients(), data_source="local-json")
