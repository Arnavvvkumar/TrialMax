"""Bounded, deterministic scenario-review coordinator."""
from __future__ import annotations

from .cohorts import compare_population
from .models import PopulationChoice, Rule, ScenarioReviewResponse


def review_scenario(baseline: list[Rule], proposed: list[Rule], population: PopulationChoice,
                    source: str = "local") -> ScenarioReviewResponse:
    """Use main's cohort engine; Chalk never decides eligibility."""
    comparison = compare_population(baseline, proposed, population)
    data_source = "local-fixed-cohort" if population.mode == "fixed" else "generated-synthetic"
    summary = "No modeled eligibility estimate is available."
    if comparison.eligible_change_n is not None:
        summary = f"The proposed scenario changes modeled eligibility by {comparison.eligible_change_n:+d} synthetic patients."
    if comparison.safety_review_rule_ids:
        summary += " Safety-critical edits require human review."
    if source == "chalk":
        data_source += "-chalk-fallback"
        summary += " Chalk patient features are unavailable, so the selected synthetic cohort was used."
    return ScenarioReviewResponse(comparison=comparison, data_source=data_source, summary=summary)
