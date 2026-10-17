"""Explicit, versioned population selection for every analysis and comparison."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import numpy as np

from .engine import evaluate, PASS, FAIL, STATUS_NAMES
from .fixed_patients import load_patients
from .models import CohortInfo, CompareResult, PopulationChoice, Rule, RuleChange, TrialInfo
from .population import ASSUMPTIONS, POPULATION_VERSION, generate_population
from .simulate import classify_change, _critical, _RELAXING
from .variables import VARIABLES

FIXED_VERSION = "fixed-nsclc-v1"


def trial_population_warnings(trial: TrialInfo, mode: str) -> list[str]:
    if not trial.nct_id:
        return []
    if mode == "generated":
        return ["The generated adult oncology population is generic, not matched to this trial's disease, stage or treatment. "
                "Broader field coverage does not establish representativeness."]
    conditions = " ".join(trial.conditions).lower().replace("-", " ")
    if "nsclc" not in conditions and "non small cell lung" not in conditions:
        return ["Population mismatch: the fixed fictional NSCLC cohort is not verified as a disease match for this trial. "
                "Generated exploration offers broader field coverage, but neither population is validated for this trial."]
    return ["The fixed fictional NSCLC cohort is not matched to this trial's stage, biomarkers or treatment; "
            "a shared disease label does not establish representativeness."]


@lru_cache(maxsize=1)
def _fixed():
    patients = load_patients()
    digest = hashlib.sha256(json.dumps(patients, sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]
    fields = sorted(set().union(*(p.keys() for p in patients)) - {"id"})
    columns = {key: np.array([p.get(key) for p in patients], dtype=object) for key in fields}
    available = [key for key in fields if key in VARIABLES and any(p.get(key) is not None for p in patients)]
    info = CohortInfo(id=f"fixed:{FIXED_VERSION}:{digest}", mode="fixed", version=FIXED_VERSION,
                      label="Fixed fictional NSCLC cohort", population_n=len(patients), seed=None,
                      available_variables=available)
    return info, columns, [p["id"] for p in patients]


def resolve(choice: PopulationChoice):
    version = FIXED_VERSION if choice.mode == "fixed" else POPULATION_VERSION
    if choice.version is not None and choice.version != version:
        raise ValueError("Population version changed. Reload the population catalog and rerun the baseline.")
    if choice.mode == "fixed":
        info, columns, ids = _fixed()
        assumptions = [
            "Fixed 500-person fictional NSCLC pre-screen cohort. Entirely synthetic; not Synthea or real patients.",
            "Thresholds and distributions are illustrative. This cohort does not represent other trial populations.",
            "Missing fields remain unknown. Trial diagnosis, histology, stage and treatment safety are not validated.",
            "Dataset version and content fingerprint are recorded in the cohort ID.",
        ]
    else:
        key = f"{version}:{np.__version__}:{choice.size}:{choice.seed}"
        info = CohortInfo(id=f"generated:{key}", mode="generated", version=version,
                          label="Generated adult oncology exploration", population_n=choice.size, seed=choice.seed,
                          available_variables=sorted(set(VARIABLES) & set(generate_population(100, 0))))
        columns, ids = None, None
        assumptions = list(ASSUMPTIONS) + [f"Generator runtime: NumPy {np.__version__}. Cohorts from different modes are not comparable."]
    if choice.cohort_id is not None and choice.cohort_id != info.id:
        raise ValueError("Cohort ID does not match the requested population. Rerun the baseline for this cohort.")
    if columns is None:
        columns = generate_population(choice.size, choice.seed)
    return info, columns, ids, assumptions


def population_catalog():
    fixed, _, _ = _fixed()
    return {"default_mode": "fixed", "options": [
        {"mode": "fixed", "version": FIXED_VERSION, "label": fixed.label, "size": fixed.population_n,
         "seed": None, "cohort_id": fixed.id, "available_variables": fixed.available_variables},
        {"mode": "generated", "version": POPULATION_VERSION, "label": "Generated adult oncology exploration",
         "size": 10000, "seed": 42, "cohort_id": None,
         "available_variables": sorted(set(VARIABLES) & set(generate_population(100, 0)))},
    ]}


def simulate_population(rules: list[Rule], choice: PopulationChoice):
    info, columns, ids, assumptions = resolve(choice)
    return evaluate(rules, columns, info, assumptions, ids)[0]


def compare_population(baseline: list[Rule], proposed: list[Rule], choice: PopulationChoice) -> CompareResult:
    info, columns, ids, assumptions = resolve(choice)
    base, before, modeled_before = evaluate(baseline, columns, info, assumptions, ids)
    prop, after, modeled_after = evaluate(proposed, columns, info, assumptions, ids)
    old_by_id, new_by_id = {r.id: r for r in baseline}, {r.id: r for r in proposed}
    changes, relaxed, review, safety = [], [], [], []
    for rid in sorted(set(old_by_id) | set(new_by_id)):
        old, new = old_by_id.get(rid), new_by_id.get(rid)
        change = classify_change(old, new)
        if change == "none":
            continue
        critical = _critical(old) or _critical(new)
        changes.append(RuleChange(rule_id=rid, change=change, safety_critical=critical))
        if critical and change in _RELAXING:
            relaxed.append(rid)
        elif critical and change == "ambiguous":
            review.append(rid)
        if critical or any(r is not None and r.purpose == "safety" for r in (old, new)):
            safety.append(rid)
    both = base.eligible_n is not None and prop.eligible_n is not None
    modeled_both = base.modeled_eligible_n is not None and prop.modeled_eligible_n is not None
    transitions = {f"{a}_to_{b}": int(((before == i) & (after == j)).sum())
                   for i, a in enumerate(STATUS_NAMES) for j, b in enumerate(STATUS_NAMES)}
    return CompareResult(
        cohort=info, baseline=base, proposed=prop,
        eligible_change_n=prop.eligible_n - base.eligible_n if both else None,
        eligible_change_pct_points=round(prop.eligible_pct - base.eligible_pct, 2) if both else None,
        newly_eligible_n=int(((before != PASS) & (after == PASS)).sum()) if both else None,
        newly_excluded_n=int(((before != FAIL) & (after == FAIL)).sum()) if both else None,
        changes=changes, changed_rule_ids=[r.rule_id for r in changes],
        relaxed_safety_critical_rule_ids=relaxed, review_safety_critical_rule_ids=review,
        safety_review_rule_ids=safety, transitions=transitions,
        modeled_eligible_change_n=prop.modeled_eligible_n - base.modeled_eligible_n if modeled_both else None,
        modeled_eligible_change_pct_points=round(100 * (prop.modeled_eligible_n - base.modeled_eligible_n) / info.population_n, 2) if modeled_both else None,
        modeled_newly_eligible_n=int(((modeled_before != PASS) & (modeled_after == PASS)).sum()) if modeled_both else None,
        modeled_newly_excluded_n=int(((modeled_before != FAIL) & (modeled_after == FAIL)).sum()) if modeled_both else None,
        modeled_transitions={f"{a}_to_{b}": int(((modeled_before == i) & (modeled_after == j)).sum())
                             for i, a in enumerate(STATUS_NAMES) for j, b in enumerate(STATUS_NAMES)},
        warnings=list(dict.fromkeys(base.warnings + prop.warnings)),
    )
