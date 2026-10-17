from fastapi.testclient import TestClient

from app.feature_sources import ChalkFeatureSource, required_features
from app.main import app
from app.models import Rule
from app.scenario_agent import review_scenario


def rule(rule_id, variable, operator, value=None):
    return Rule(id=rule_id, kind="inclusion", text=rule_id, variable=variable, operator=operator,
                value=value, simulatable=True)


def test_chalk_source_requests_only_features_needed_by_validated_rules():
    assert required_features([rule("age", "age", ">=", 18)]) == ["patient.age_years", "patient.id"]


def test_chalk_source_normalizes_feature_rows_from_injected_client():
    class Result:
        data = {"patient.age_years": [70], "patient.hemoglobin_g_dl": [11.2]}
        query_id = "query-123"

    class Client:
        def query(self, **kwargs):
            assert kwargs["input"] == {"patient.id": ["SYN-0001"]}
            assert kwargs["output"] == ["patient.age_years", "patient.hemoglobin_g_dl", "patient.id"]
            return Result()

    batch = ChalkFeatureSource(["SYN-0001"], client=Client()).fetch([
        rule("age", "age", ">=", 18), rule("hb", "hemoglobin", ">=", 10),
    ])
    assert batch.data_source == "chalk" and batch.source_run_id == "query-123"
    assert batch.patients[0]["age"] == 70 and batch.patients[0]["hemoglobin"] == 11.2


def test_scenario_review_uses_fixed_cohort_and_returns_provenance():
    response = review_scenario([rule("age", "age", ">=", 70)], [rule("age", "age", ">=", 60)])
    assert response.data_source == "local-json"
    assert response.comparison.eligible_change_n > 0
    assert "synthetic patients" in response.summary


def test_scenario_review_endpoint_defaults_to_local_source():
    body = {"baseline_rules": [rule("age", "age", ">=", 70).model_dump()],
            "proposed_rules": [rule("age", "age", ">=", 60).model_dump()]}
    with TestClient(app) as client:
        response = client.post("/api/scenario-review", json=body)
    assert response.status_code == 200
    assert response.json()["data_source"] == "local-json"


def test_requested_chalk_source_falls_back_without_chalk_configuration():
    response = review_scenario([rule("age", "age", ">=", 70)], [rule("age", "age", ">=", 60)], "chalk")
    assert response.data_source == "local-json-fallback"
    assert "Chalk was unavailable" in response.summary
