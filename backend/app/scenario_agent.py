"""Bounded scenario-review coordinator for Chalk-backed simulations.

It retrieves features and runs deterministic calculations. It does not make
clinical decisions or let a model alter rules.
"""
from __future__ import annotations

from . import config
from .feature_sources import ChalkFeatureSource, FeatureSourceError, LocalJsonFeatureSource
from .fixed_patients import simulate_patients
from .models import CompareResult, Rule, RuleChange, ScenarioReviewResponse
from .simulate import _RELAXING, _critical, classify_change


def _compare_fixed(baseline: list[Rule], proposed: list[Rule], batch) -> CompareResult:
    base = simulate_patients(baseline, batch.patients, data_source=batch.data_source,
                             cohort_version=batch.cohort_version, source_run_id=batch.source_run_id)
    prop = simulate_patients(proposed, batch.patients, data_source=batch.data_source,
                             cohort_version=batch.cohort_version, source_run_id=batch.source_run_id)
    old_by_id, new_by_id = {r.id: r for r in baseline}, {r.id: r for r in proposed}
    changes: list[RuleChange] = []
    relaxed, review = [], []
    for rule_id in sorted(set(old_by_id) | set(new_by_id)):
        old, new = old_by_id.get(rule_id), new_by_id.get(rule_id)
        change = classify_change(old, new)
        if change == "none":
            continue
        critical = _critical(old) or _critical(new)
        changes.append(RuleChange(rule_id=rule_id, change=change, safety_critical=critical))
        if critical and change in _RELAXING:
            relaxed.append(rule_id)
        elif critical and change == "ambiguous":
            review.append(rule_id)
    base_pass = {p.patient_id for p in base.patient_results if p.overall_status == "pass"}
    prop_pass = {p.patient_id for p in prop.patient_results if p.overall_status == "pass"}
    both = base.eligible_n is not None and prop.eligible_n is not None
    return CompareResult(
        baseline=base, proposed=prop,
        eligible_change_n=(prop.eligible_n - base.eligible_n) if both else None,
        eligible_change_pct_points=round(prop.eligible_pct - base.eligible_pct, 2) if both else None,
        newly_eligible_n=len(prop_pass - base_pass) if both else None,
        newly_excluded_n=len(base_pass - prop_pass) if both else None,
        changes=changes, changed_rule_ids=[change.rule_id for change in changes],
        relaxed_safety_critical_rule_ids=relaxed, review_safety_critical_rule_ids=review,
    )


def review_scenario(baseline: list[Rule], proposed: list[Rule], source: str = "local") -> ScenarioReviewResponse:
    """Fetch an audited cohort, compare scenarios, and return a factual summary."""
    fallback = None
    if source == "chalk":
        ids = [patient["id"] for patient in LocalJsonFeatureSource().fetch([]).patients]
        try:
            batch = ChalkFeatureSource(ids, branch=config.CHALK_FEATURE_BRANCH or None).fetch(baseline + proposed)
        except FeatureSourceError as exc:
            batch, fallback = LocalJsonFeatureSource().fetch(baseline + proposed), str(exc)
    else:
        batch = LocalJsonFeatureSource().fetch(baseline + proposed)
    comparison = _compare_fixed(baseline, proposed, batch)
    change = comparison.eligible_change_n
    summary = "No modeled eligibility estimate is available."
    if change is not None:
        summary = f"The proposed scenario changes modeled eligibility by {change:+d} synthetic patients."
    if comparison.review_safety_critical_rule_ids or comparison.relaxed_safety_critical_rule_ids:
        summary += " Safety-critical edits require human review."
    if fallback:
        summary += " Chalk was unavailable, so the local synthetic cohort was used."
        batch = batch.__class__(batch.patients, "local-json-fallback", batch.cohort_version, batch.source_run_id)
        comparison = _compare_fixed(baseline, proposed, batch)
    return ScenarioReviewResponse(comparison=comparison, data_source=batch.data_source,
                                  cohort_version=batch.cohort_version, source_run_id=batch.source_run_id,
                                  summary=summary)
