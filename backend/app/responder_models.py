"""Aggregate historical-trial evidence; separate from synthetic eligibility rules."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Direction = Literal['weaker_benefit', 'stronger_benefit', 'no_reliable_difference']


class Effect(BaseModel):
    hr: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p: float | None = None
    status: Literal['ok', 'unestimable'] = 'unestimable'


class ArmCounts(BaseModel):
    control_n: int
    treatment_n: int
    control_events: int
    treatment_events: int


class SubgroupEvidence(BaseModel):
    id: str
    label: str
    n: int
    missing_n: int
    subgroup: ArmCounts
    complement: ArmCounts
    hr_subgroup: Effect
    hr_complement: Effect
    interaction: Effect
    interaction_q: float | None = None
    bh_significant: bool = False
    underpowered: bool
    truth_label: Direction = 'no_reliable_difference'


class TrialEvidence(BaseModel):
    case_id: str
    trial_key: str
    trial_name: str
    treatment: str
    control: str
    endpoint: str
    variant: str
    n: int
    events: int
    overall: Effect
    subgroups: list[SubgroupEvidence]
    provenance: dict
    disclaimers: list[str]
    planted_subgroup: str | None = None
    planted_detectable: bool | None = None
    seed: int | None = None


class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    flag: str | None
    direction: Literal['weaker_benefit', 'stronger_benefit'] | None
    confidence: Literal['low', 'medium', 'high']
    rationale: str = Field(max_length=400)

    @model_validator(mode='after')
    def paired(self):
        if (self.flag is None) != (self.direction is None):
            raise ValueError('Flag and direction must both be null or both specified')
        return self


class AgentOutput(Suggestion):
    invalid: bool = False
    source: Literal['chalk', 'unavailable', 'invalid'] = 'chalk'
    raw_output: str = ''


class ResponderRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trial_key: Literal['colon', 'veteran', 'gbsg']
    variant: Literal['original'] = 'original'


class ResponderResponse(BaseModel):
    evidence: TrialEvidence
    suggestion: AgentOutput
    evaluations: dict
    disclaimers: list[str]
