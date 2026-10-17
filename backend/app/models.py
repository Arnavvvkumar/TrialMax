"""Shared data shapes for the API. The frontend should mirror these."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Kind = Literal["inclusion", "exclusion"]
Category = Literal[
    "age", "performance_status", "lab", "condition", "prior_therapy", "pregnancy",
    "permission", "administrative", "other",
]
Operator = Literal[">=", "<=", ">", "<", "==", "between", "present", "absent"]
Purpose = Literal[
    "safety", "predictive_enrichment", "prognostic_enrichment", "reduce_variability",
    "administrative", "unknown",
]
Findability = Literal[
    "coded_lab", "diagnosis_code", "structured_field", "chart_review", "patient_reported", "unknown",
]


class Rule(BaseModel):
    """One eligibility criterion, as written and as the simulator understands it."""

    id: str
    kind: Kind
    text: str
    category: Category = "other"
    variable: Optional[str] = None
    operator: Optional[Operator] = None
    value: Optional[float] = None
    value_max: Optional[float] = None
    unit: Optional[str] = None
    simulatable: bool = False
    purpose: Purpose = "unknown"
    findability: Findability = "unknown"
    safety_critical: bool = False
    parsed_by: Literal["rules", "llm", "none"] = "none"
    notes: list[str] = Field(default_factory=list)


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
    eligible_n: int
    eligible_pct: float
    impacts: list[RuleImpact]
    funnel: list[FunnelStep]
    worst_rule_id: Optional[str]
    not_simulated_rule_ids: list[str]
    sample_excluded: list[ExcludedPatient]
    assumptions: list[str]


class AnalyzeRequest(BaseModel):
    nct_id: Optional[str] = None
    eligibility_text: Optional[str] = Field(default=None, max_length=30000)
    use_llm: bool = True
    population_size: int = Field(default=10000, ge=100, le=200000)
    seed: int = 42


class AnalyzeResponse(BaseModel):
    trial: TrialInfo
    rules: list[Rule]
    simulation: SimulationResult
    llm_used: bool
    warnings: list[str]


class SimulateRequest(BaseModel):
    rules: list[Rule]
    population_size: int = Field(default=10000, ge=100, le=200000)
    seed: int = 42


class CompareRequest(BaseModel):
    baseline_rules: list[Rule]
    proposed_rules: list[Rule]
    population_size: int = Field(default=10000, ge=100, le=200000)
    seed: int = 42


class CompareResult(BaseModel):
    baseline: SimulationResult
    proposed: SimulationResult
    eligible_change_n: int
    eligible_change_pct_points: float
    newly_eligible_n: int
    newly_excluded_n: int
    changed_rule_ids: list[str]
    relaxed_safety_critical_rule_ids: list[str]
