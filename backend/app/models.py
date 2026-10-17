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
SEED_FIELD = Field(default=42, ge=0, le=2**32 - 1)
POPULATION_FIELD = Field(default=10000, ge=100, le=200000)
NOT_APPLICABLE = ("administrative", "permission")


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


class RuleImpact(BaseModel):
    rule_id: str
    simulated: bool
    fail_n: int = 0
    fail_pct: float = 0.0
    unique_fail_n: int = 0
    unique_fail_pct: float = 0.0


class FunnelStep(BaseModel):
    rule_id: Optional[str]
    label: str
    remaining_n: int
    remaining_pct: float


class ExcludedPatient(BaseModel):
    patient_id: int
    failed_rule_ids: list[str]
    attributes: dict[str, float | int | bool]


class SimulationResult(BaseModel):
    population_n: int
    seed: int
    estimate_label: str = "Share of synthetic patients passing the modeled checks"
    eligible_n: Optional[int]
    eligible_pct: Optional[float]
    complete: bool
    coverage_pct: Optional[float]
    modeled_rule_ids: list[str]
    approximate_rule_ids: list[str]
    unmodeled_rule_ids: list[str]
    not_applicable_rule_ids: list[str]
    not_simulated_rule_ids: list[str]
    impacts: list[RuleImpact]
    funnel: list[FunnelStep]
    worst_rule_id: Optional[str]
    sample_excluded: list[ExcludedPatient]
    assumptions: list[str]


class AnalyzeRequest(BaseModel):
    nct_id: Optional[str] = Field(default=None, max_length=20)
    eligibility_text: Optional[str] = Field(default=None, max_length=30000)
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
    rules: list[Rule] = Field(max_length=MAX_RULES)
    population_size: int = POPULATION_FIELD
    seed: int = SEED_FIELD

    @model_validator(mode="after")
    def _unique(self):
        ensure_unique_ids(self.rules)
        return self


class CompareRequest(BaseModel):
    baseline_rules: list[Rule] = Field(max_length=MAX_RULES)
    proposed_rules: list[Rule] = Field(max_length=MAX_RULES)
    population_size: int = POPULATION_FIELD
    seed: int = SEED_FIELD

    @model_validator(mode="after")
    def _unique(self):
        ensure_unique_ids(self.baseline_rules)
        ensure_unique_ids(self.proposed_rules)
        return self


class RuleChange(BaseModel):
    rule_id: str
    change: Literal["added", "removed", "disabled", "enabled", "tightened", "relaxed", "mixed", "ambiguous"]
    safety_critical: bool


class CompareResult(BaseModel):
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
