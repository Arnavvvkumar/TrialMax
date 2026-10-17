"""Synthetic adult oncology population used to estimate who passes each rule.

Every number here is a stated modeling assumption, not real-world data. Variables
are drawn independently (a simplification). Swap in Synthea- or NHANES-based
distributions later without changing the simulator.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

POPULATION_VERSION = "synthetic-oncology-v0"

PREVALENCE = {
    "brain_mets": 0.12,
    "hiv": 0.01,
    "hepatitis_b": 0.03,
    "hepatitis_c": 0.02,
    "prior_malignancy": 0.10,
    "autoimmune_active": 0.06,
    "cardiac_disease": 0.10,
    "thromboembolic_event_recent": 0.04,
    "uncontrolled_hypertension": 0.05,
    "active_infection": 0.04,
    "ibd": 0.01,
    "hepatic_impairment": 0.03,
    "interstitial_lung_disease": 0.02,
    "systemic_immunosuppression": 0.08,
    "recent_major_surgery": 0.05,
    "recent_live_vaccine": 0.01,
    "drug_hypersensitivity": 0.02,
    "myocarditis_history": 0.003,
    "prior_immunotherapy": 0.25,
}
ECOG_PROBS = [0.30, 0.40, 0.18, 0.09, 0.03]

ASSUMPTIONS = [
    f"Population '{POPULATION_VERSION}': synthetic adults with advanced cancer. Not real patients.",
    "Age ~ Normal(64, 11), limited to 18-95. Sex 50/50.",
    "ECOG 0/1/2/3/4 = 30/40/18/9/3%.",
    "Labs are log-normal around typical adult values (ANC 4.0, platelets 240, creatinine 0.9, "
    "bilirubin 0.6, AST 24, ALT 22); hemoglobin ~ Normal(12.0, 1.7). eGFR from CKD-EPI 2021.",
    "x ULN thresholds use ULN: bilirubin 1.2 mg/dL, AST/ALT 40 U/L, creatinine 1.2 mg/dL.",
    "Prior systemic lines ~ Poisson(1.2). Condition prevalences are rough planning assumptions.",
    "Variables are independent; real correlations (for example age and ECOG) are not modeled.",
    "Disease-defining criteria (diagnosis, stage, histology) are assumed met by everyone.",
]


def ckd_epi_2021(creatinine: np.ndarray, age: np.ndarray, female: np.ndarray) -> np.ndarray:
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = creatinine / kappa
    egfr = 142 * np.minimum(ratio, 1) ** alpha * np.maximum(ratio, 1) ** -1.200 * 0.9938 ** age
    return egfr * np.where(female, 1.012, 1.0)


def _generate(n: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    age = np.clip(np.round(rng.normal(64, 11, n)), 18, 95)
    female = rng.random(n) < 0.5
    creatinine = rng.lognormal(np.log(0.9), 0.30, n)
    pop: dict[str, np.ndarray] = {
        "age": age,
        "female": female,
        "ecog": rng.choice(5, size=n, p=ECOG_PROBS),
        "anc": rng.lognormal(np.log(4.0), 0.45, n),
        "platelets": rng.lognormal(np.log(240), 0.35, n),
        "hemoglobin": np.clip(rng.normal(12.0, 1.7, n), 5, 18),
        "creatinine": creatinine,
        "egfr": ckd_epi_2021(creatinine, age, female),
        "bilirubin": rng.lognormal(np.log(0.6), 0.5, n),
        "ast": rng.lognormal(np.log(24), 0.5, n),
        "alt": rng.lognormal(np.log(22), 0.55, n),
        "prior_systemic_lines": rng.poisson(1.2, n),
        "pregnant": female & (age < 50) & (rng.random(n) < 0.01),
    }
    for name, p in PREVALENCE.items():
        pop[name] = rng.random(n) < p
    return pop


@lru_cache(maxsize=8)
def generate_population(n: int, seed: int) -> dict[str, np.ndarray]:
    """Same (n, seed) always gives the same population, so comparisons are fair."""
    pop = _generate(n, seed)
    for arr in pop.values():
        arr.setflags(write=False)
    return pop
