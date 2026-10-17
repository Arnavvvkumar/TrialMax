"""Evaluation of eligibility rules against the checked-in synthetic patient cohort."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from .models import Rule, SimulationResult
from .simulate import _threshold
from .variables import VARIABLES

DATA_PATH = Path(os.getenv("WT_COHORT_PATH", str(Path(__file__).resolve().parents[2] / "frontend" / "synthetic_data" / "patients.json")))
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


@lru_cache(maxsize=1)
def load_patients() -> tuple[dict[str, Any], ...]:
    """Load and normalize the frontend's fixed synthetic cohort."""
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Fixed patient data is missing: {DATA_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Fixed patient data is not valid JSON: {exc.msg}") from exc
    patients = raw.get("patients") if isinstance(raw, dict) else raw
    if not isinstance(patients, list) or not patients:
        raise ValueError("Fixed patient data must contain a non-empty 'patients' list.")
    cleaned: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, patient in enumerate(patients):
        if not isinstance(patient, dict) or patient.get("patient_id", patient.get("id")) in (None, ""):
            raise ValueError(f"Fixed patient at index {index} must be an object with a patient_id.")
        if patient.get("synthetic") is not True:
            raise ValueError("The fixed cohort must contain explicitly labeled synthetic records only.")
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
        for source, target in (("egfr_mutation", "egfr_mutation_positive"), ("alk_rearrangement", "alk_positive")):
            status = patient.get(source)
            normalized[target] = True if status == "positive" else False if status == "negative" else None
        cleaned.append(normalized)
    return tuple(cleaned)


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


def simulate_fixed(rules: list[Rule]) -> SimulationResult:
    """Compatibility helper for the fixed cohort, using the shared evaluator."""
    from .cohorts import simulate_population
    from .models import PopulationChoice
    return simulate_population(rules, PopulationChoice(mode="fixed"))
