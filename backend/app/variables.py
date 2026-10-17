"""Variables the simulator understands, with trade-off defaults for each.

Purpose, findability and safety_critical are starting defaults that a researcher
can edit. They are heuristics, not clinical judgments.
"""
from __future__ import annotations

from typing import Literal, TypedDict

VarType = Literal["numeric", "bool", "int"]


class VariableMeta(TypedDict):
    label: str
    type: VarType
    unit: str | None
    purpose: str
    findability: str
    safety_critical: bool
    rationale: str


def _num(label, unit, rationale, purpose="safety", findability="coded_lab", critical=False) -> VariableMeta:
    return {"label": label, "type": "numeric", "unit": unit, "purpose": purpose,
            "findability": findability, "safety_critical": critical, "rationale": rationale}


def _flag(label, rationale, purpose="safety", findability="diagnosis_code", critical=False) -> VariableMeta:
    return {"label": label, "type": "bool", "unit": None, "purpose": purpose,
            "findability": findability, "safety_critical": critical, "rationale": rationale}


ORGAN = "Organ function needed to tolerate and clear the drug."

VARIABLES: dict[str, VariableMeta] = {
    "age": _num("Age", "years", "Adults only: consent and limited pediatric safety data.",
                findability="structured_field"),
    "ecog": {"label": "ECOG performance status", "type": "int", "unit": None, "purpose": "safety",
             "findability": "chart_review", "safety_critical": False,
             "rationale": "Fitness to tolerate treatment; also reduces variability in outcomes."},
    "anc": _num("Absolute neutrophil count", "10^9/L", ORGAN),
    "platelets": _num("Platelets", "10^9/L", ORGAN),
    "hemoglobin": _num("Hemoglobin", "g/dL", ORGAN),
    "creatinine": _num("Serum creatinine", "mg/dL", ORGAN),
    "egfr": _num("eGFR / creatinine clearance", "mL/min", ORGAN),
    "bilirubin": _num("Total bilirubin", "mg/dL", ORGAN),
    "ast": _num("AST", "U/L", ORGAN),
    "alt": _num("ALT", "U/L", ORGAN),
    "prior_systemic_lines": {"label": "Prior lines of systemic therapy", "type": "int", "unit": "lines",
                             "purpose": "predictive_enrichment", "findability": "chart_review",
                             "safety_critical": False,
                             "rationale": "Defines the treatment setting the drug is studied in."},
    "prior_immunotherapy": _flag("Prior immunotherapy",
                                 "Prior exposure may change response to an immune therapy.",
                                 purpose="predictive_enrichment", findability="structured_field"),
    "brain_mets": _flag("Brain / CNS metastases",
                        "CNS disease can confound neurological adverse events and survival."),
    "hiv": _flag("HIV infection", "Immune status and drug interactions; often acceptable when controlled."),
    "hepatitis_b": _flag("Hepatitis B infection", "Risk of reactivation; often acceptable when suppressed."),
    "hepatitis_c": _flag("Hepatitis C infection", "Liver safety; often acceptable when treated."),
    "prior_malignancy": _flag("Other / prior malignancy",
                              "A second cancer can confound efficacy and survival results.",
                              purpose="reduce_variability"),
    "autoimmune_active": _flag("Active autoimmune disease", "Immune therapies can flare autoimmune disease."),
    "cardiac_disease": _flag("Significant cardiac disease", "Cardiac safety under treatment."),
    "thromboembolic_event_recent": _flag("Recent arterial/venous thromboembolic event",
                                         "Bleeding and clotting risk."),
    "uncontrolled_hypertension": _flag("Uncontrolled hypertension", "Cardiovascular safety."),
    "active_infection": _flag("Active infection", "Infection can be worsened and confuses adverse events.",
                              findability="chart_review", critical=True),
    "ibd": _flag("Inflammatory bowel disease", "Risk of severe GI toxicity."),
    "hepatic_impairment": _flag("Moderate/severe hepatic impairment",
                                "Impaired drug metabolism; serious toxicity risk.", critical=True),
    "interstitial_lung_disease": _flag("Interstitial lung disease / pneumonitis",
                                       "Risk of life-threatening pneumonitis.", critical=True),
    "systemic_immunosuppression": _flag("Systemic steroids / immunosuppression",
                                        "Can blunt immune therapies and confound response.",
                                        findability="structured_field"),
    "recent_major_surgery": _flag("Recent major surgery", "Wound healing and bleeding risk.",
                                  findability="chart_review"),
    "recent_live_vaccine": _flag("Recent live vaccine", "Infection risk with immune-modulating drugs.",
                                 findability="structured_field"),
    "drug_hypersensitivity": _flag("Hypersensitivity to study drug", "Risk of severe allergic reaction.",
                                   findability="structured_field", critical=True),
    "myocarditis_history": _flag("History of myocarditis", "Risk of fatal immune-related myocarditis.",
                                 critical=True),
    "pregnant": _flag("Pregnant or breastfeeding", "Potential harm to a fetus or nursing infant.",
                      findability="coded_lab", critical=True),
}

# Reference upper limits of normal used to convert "x ULN" thresholds. Assumed values.
ULN = {"bilirubin": 1.2, "ast": 40.0, "alt": 40.0, "creatinine": 1.2}


def meta_for(variable: str | None) -> VariableMeta | None:
    return VARIABLES.get(variable) if variable else None
