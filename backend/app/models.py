"""Shared data shapes for the API. The frontend should mirror these."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .variables import validate_rule_semantics

Kind = Literal["inclusion", "exclusion"]
Category = Literal[
    "age", "sex", "performance_status", "lab", "condition", "prior_therapy", "pregnancy",
    "permission", "administrative", "conditional", "compound", "other",
]
Operator = Literal[">=", "<=", ">", "<", "==", "between", "present", "absent"]
Purpose = Literal[
    "safety", "predictive_enrichment", "prognostic_enrichment", "reduce_variability",
    "administrative", "unknown",
]
Findability = Literal[
    "coded_lab", "diagnosis_code", "structured_field", "chart_review", "patient_reported", "unknown",
]

MAX_RULES = 200
SEED_FIELD = Field(default=42, ge=0, le=2**32 - 1, description="Deprecated and ignored; use population.seed.")
POPULATION_FIELD = Field(default=10000, ge=100, le=200000, description="Deprecated and ignored; use population.size.")
NOT_APPLICABLE = ("administrative", "permission")


class PopulationChoice(BaseModel):
    """One population selection applies to both sides of a comparison."""
    model_config = {"extra": "forbid"}
    # synthea is the default; fixed and generated remain as API-only fallbacks.
    mode: Literal["synthea", "fixed", "generated"] = "synthea"
    size: int = Field(default=500, ge=100, le=200000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    version: Optional[str] = Field(default=None, max_length=80)
    cohort_id: Optional[str] = Field(default=None, max_length=160)


class CohortInfo(BaseModel):
    id: str
    mode: Literal["synthea", "fixed", "generated"]
    version: str
    label: str
    population_n: int
    seed: Optional[int]
    available_variables: list[str]


class Rule(BaseModel):
    """One eligibility criterion (or one part of it), as written and as the simulator reads it."""

    id: str = Field(min_length=1, max_length=40)
    kind: Kind
    text: str = Field(max_length=4000)
    clause: Optional[str] = Field(default=None, max_length=4000)  # the part of the text this rule came from
    category: Category = "other"
    variable: Optional[str] = None
    operator: Optional[Operator] = None
    value: Optional[float] = None
    value_max: Optional[float] = None
    unit: Optional[str] = None
    simulatable: bool = False
    fidelity: Literal["exact", "approximate"] = "exact"
    purpose: Purpose = "unknown"
    findability: Findability = "unknown"
    safety_critical: bool = False
    parsed_by: Literal["rules", "llm", "none"] = "none"
    source: Literal["text", "registry"] = "text"
    notes: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _check_semantics(self):
        if self.simulatable:
            validate_rule_semantics(self.variable, self.operator, self.value, self.value_max, self.unit)
        return self

    @property
    def not_applicable(self) -> bool:
        return self.category in NOT_APPLICABLE


def ensure_unique_ids(rules: list[Rule]) -> list[Rule]:
    seen, dupes = set(), set()
    for r in rules:
        (dupes if r.id in seen else seen).add(r.id)
    if dupes:
        raise ValueError(f"duplicate rule ids: {sorted(dupes)}")
    return rules


class TrialInfo(BaseModel):
    nct_id: Optional[str] = None
    title: Optional[str] = None
    phases: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    sponsor: Optional[str] = None
    status: Optional[str] = None
    enrollment: Optional[int] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    sex: Optional[str] = None
    eligibility_text: str = ""
    data_source: Literal["ctgov", "chalk", "manual"] = "ctgov"


class RuleImpact(BaseModel):
    rule_id: str
    simulated: bool
    fail_n: int = 0
    fail_pct: float = 0.0
    unique_fail_n: int = 0
    unique_fail_pct: float = 0.0
    pass_n: int = 0
    unknown_n: int = 0


class FunnelStep(BaseModel):
    rule_id: Optional[str]
    label: str
    remaining_n: int
    remaining_pct: float
    unknown_n: int = 0


class CriterionResult(BaseModel):
    rule_id: str
    status: Literal["pass", "fail", "unknown"]
    value: float | bool | None = None


class PatientResult(BaseModel):
    patient_id: str
    criteria: list[CriterionResult]
    overall_status: Literal["pass", "fail", "unknown"]
    modeled_status: Literal["pass", "fail", "unknown"] = "unknown"


class RuleOverlap(BaseModel):
    rule_a_id: str
    rule_b_id: str
    patient_n: int


class ExcludedPatient(BaseModel):
    patient_id: str | int
    failed_rule_ids: list[str]
    attributes: dict[str, float | int | bool]


class SimulationResult(BaseModel):
    cohort: CohortInfo
    population_n: int
    seed: int
    estimate_label: str = "Share of synthetic patients passing the modeled checks"
    eligible_n: Optional[int]
    eligible_pct: Optional[float]
    excluded_n: int
    unknown_n: int
    modeled_eligible_n: Optional[int]
    modeled_eligible_pct: Optional[float] = None
    modeled_unknown_n: int
    complete: bool
    coverage_pct: Optional[float]
    modeled_rule_ids: list[str]
    approximate_rule_ids: list[str]
    unmodeled_rule_ids: list[str]
    not_applicable_rule_ids: list[str]
    not_simulated_rule_ids: list[str]
    impacts: list[RuleImpact]
    funnel_basis: Literal["modeled_checks"] = "modeled_checks"
    funnel: list[FunnelStep]
    worst_rule_id: Optional[str]
    sample_excluded: list[ExcludedPatient]
    assumptions: list[str]
    patient_results: list[PatientResult] = Field(default_factory=list)
    rule_overlaps: list[RuleOverlap] = Field(default_factory=list)
    patient_results_complete: bool = False
    overlaps_truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    population: PopulationChoice = Field(default_factory=PopulationChoice)
    nct_id: Optional[str] = Field(default=None, max_length=20)
    eligibility_text: Optional[str] = Field(default=None, max_length=30000)
    source: Literal["auto", "ctgov", "chalk"] = "auto"
    use_llm: bool = True
    population_size: int = POPULATION_FIELD
    seed: int = SEED_FIELD


class AnalyzeResponse(BaseModel):
    trial: TrialInfo
    rules: list[Rule]
    simulation: SimulationResult
    llm_used: bool
    warnings: list[str]


class SimulateRequest(BaseModel):
    population: PopulationChoice = Field(default_factory=PopulationChoice)
    rules: list[Rule] = Field(max_length=MAX_RULES)
    # Legacy top-level settings are accepted for compatibility; population is authoritative.
    population_size: int = POPULATION_FIELD
    seed: int = SEED_FIELD

    @model_validator(mode="after")
    def _unique(self):
        ensure_unique_ids(self.rules)
        return self


class CompareRequest(BaseModel):
    population: PopulationChoice = Field(default_factory=PopulationChoice)
    baseline_rules: list[Rule] = Field(max_length=MAX_RULES)
    proposed_rules: list[Rule] = Field(max_length=MAX_RULES)
    population_size: int = POPULATION_FIELD
    seed: int = SEED_FIELD

    @model_validator(mode="after")
    def _unique(self):
        ensure_unique_ids(self.baseline_rules)
        ensure_unique_ids(self.proposed_rules)
        return self


class ScenarioReviewRequest(CompareRequest):
    """A cohort-aware deterministic comparison with optional Chalk provenance."""
    source: Literal["local", "chalk"] = "local"


class ScenarioReviewResponse(BaseModel):
    comparison: "CompareResult"
    data_source: str
    source_run_id: Optional[str] = None
    summary: str


class RareReachRequest(BaseModel):
    nct_id: str = Field(min_length=11, max_length=20)
    rules: list[Rule] = Field(default_factory=list, max_length=MAX_RULES)


class RecruitmentSite(BaseModel):
    name: str
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    historical_trial_count: int
    matching_nct_ids: list[str]
    source_urls: list[str]
    explanation: str


class RecruitmentStrategy(BaseModel):
    rule_id: str
    criterion: str
    safety_sensitive: bool
    option_a: str
    option_b: str


class RareReachResponse(BaseModel):
    trial: TrialInfo
    query_terms: list[str]
    orpha_code: Optional[str] = None
    orpha_status: str
    orpha_preferred_name: Optional[str] = None
    orpha_synonyms: list[str] = Field(default_factory=list)
    hospitals: list[RecruitmentSite]
    nord_url: str
    nord_candidate_url: Optional[str] = None
    strategies: list[RecruitmentStrategy]
    sources: list[dict[str, str]]
    warnings: list[str]


class RuleChange(BaseModel):
    rule_id: str
    change: Literal["added", "removed", "disabled", "enabled", "tightened", "relaxed", "mixed", "ambiguous"]
    safety_critical: bool


class CompareResult(BaseModel):
    cohort: CohortInfo
    baseline: SimulationResult
    proposed: SimulationResult
    eligible_change_n: Optional[int]
    eligible_change_pct_points: Optional[float]
    newly_eligible_n: Optional[int]
    newly_excluded_n: Optional[int]
    changes: list[RuleChange]
    changed_rule_ids: list[str]
    relaxed_safety_critical_rule_ids: list[str]
    review_safety_critical_rule_ids: list[str]
    safety_review_rule_ids: list[str] = Field(default_factory=list)
    modeled_eligible_change_n: Optional[int] = None
    modeled_eligible_change_pct_points: Optional[float] = None
    modeled_newly_eligible_n: Optional[int] = None
    modeled_newly_excluded_n: Optional[int] = None
    modeled_transitions: dict[str, int] = Field(default_factory=dict)
    transitions: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
