"""Patient-feature providers for deterministic scenario simulation.

The local provider is the demo fallback.  The Chalk provider deliberately only
retrieves the synthetic fields required by validated rules; it never decides
eligibility itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .fixed_patients import load_patients, normalize_patients
from .models import Rule


class FeatureSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeatureBatch:
    patients: tuple[dict[str, Any], ...]
    data_source: str
    cohort_version: str | None = "synthetic-v1"
    source_run_id: str | None = None


class PatientFeatureSource(Protocol):
    def fetch(self, rules: list[Rule]) -> FeatureBatch: ...


class LocalJsonFeatureSource:
    def fetch(self, rules: list[Rule]) -> FeatureBatch:
        return FeatureBatch(load_patients(), "local-json")


# Chalk feature names are intentionally separate from simulator variables.
FEATURES_BY_VARIABLE = {
    "age": "patient.age_years",
    "ecog": "patient.ecog_score",
    "hemoglobin": "patient.hemoglobin_g_dl",
    "anc": "patient.anc_cells_ul",
    "platelets": "patient.platelets_cells_ul",
    "egfr": "patient.egfr_kidney_ml_min_1_73m2",
    "ast": "patient.ast_u_l",
    "alt": "patient.alt_u_l",
    "prior_systemic_lines": "patient.prior_systemic_therapy_lines",
    "brain_mets": "patient.brain_metastases",
    "active_infection": "patient.active_infection",
    "female": "patient.sex_at_birth",
}


def required_features(rules: list[Rule]) -> list[str]:
    features = {"patient.id"}
    for rule in rules:
        if rule.simulatable and rule.variable in FEATURES_BY_VARIABLE:
            features.add(FEATURES_BY_VARIABLE[rule.variable])
    return sorted(features)


class ChalkFeatureSource:
    """Online Chalk adapter.

    The Chalk project should define the ``patient.*`` features above. A client
    can be injected for tests; in deployment chalkpy supplies ChalkClient.
    """

    def __init__(self, patient_ids: list[str], client: Any | None = None, branch: str | None = None):
        self.patient_ids = patient_ids
        self._client = client
        self.branch = branch

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from chalk.client import ChalkClient
        except ImportError as exc:
            raise FeatureSourceError("chalkpy is not installed; use the local source or install Chalk dependencies.") from exc
        return ChalkClient(branch=self.branch) if self.branch else ChalkClient()

    def fetch(self, rules: list[Rule]) -> FeatureBatch:
        client = self._get_client()
        outputs = required_features(rules)
        try:
            result = client.query(input={"patient.id": self.patient_ids}, output=outputs)
        except Exception as exc:
            raise FeatureSourceError(f"Chalk feature query failed: {exc}") from exc
        rows = _rows_from_query(result, self.patient_ids, outputs)
        run_id = getattr(result, "query_id", None) or getattr(result, "request_id", None)
        return FeatureBatch(normalize_patients(rows), "chalk", source_run_id=str(run_id) if run_id else None)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _rows_from_query(result: Any, patient_ids: list[str], outputs: list[str]) -> list[dict[str, Any]]:
    """Accept Chalk's mapping-shaped result and keep this boundary easy to test."""
    data = getattr(result, "data", result)
    if not isinstance(data, dict):
        raise FeatureSourceError("Chalk query returned an unsupported result shape.")
    rows = [{"patient_id": patient_id} for patient_id in patient_ids]
    for feature in outputs:
        values = _value(data.get(feature))
        if feature == "patient.id":
            continue
        if not isinstance(values, list) or len(values) != len(rows):
            raise FeatureSourceError(f"Chalk response did not return one value per patient for {feature}.")
        field = feature.removeprefix("patient.")
        for row, value in zip(rows, values):
            row[field] = _value(value)
    return rows
