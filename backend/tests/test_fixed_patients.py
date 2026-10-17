from fastapi.testclient import TestClient

from app.fixed_patients import simulate_fixed
from app.main import app
from app.models import Rule


def rule(rule_id, kind, variable, operator, value=None):
    return Rule(id=rule_id, kind=kind, text=rule_id, variable=variable, operator=operator,
                value=value, simulatable=True)


def test_fixed_cohort_returns_each_patient_and_three_way_criterion_status():
    result = simulate_fixed([
        rule("age", "inclusion", "age", ">=", 50),
        rule("hiv", "exclusion", "hiv", "present"),
    ])
    by_id = {patient.patient_id: patient for patient in result.patient_results}
    assert len(by_id) == 6
    assert by_id["P001"].criteria[0].status == "fail"
    assert by_id["P006"].criteria[1].status == "unknown"
    assert by_id["P006"].overall_status == "unknown"


def test_fixed_cohort_reports_funnel_and_pairwise_overlap():
    result = simulate_fixed([
        rule("age", "inclusion", "age", ">=", 60),
        rule("ecog", "inclusion", "ecog", "<=", 1),
        rule("brain", "exclusion", "brain_mets", "present"),
    ])
    assert result.funnel[0].remaining_n == 6
    assert result.funnel[-1].remaining_n == 1
    assert result.funnel[-1].unknown_n == 0
    overlaps = {(item.rule_a_id, item.rule_b_id): item.patient_n for item in result.rule_overlaps}
    assert overlaps[("age", "brain")] == 1


def test_simulate_endpoint_uses_fixed_cohort():
    with TestClient(app) as client:
        response = client.post("/api/simulate", json={"rules": [
            {"id": "age", "kind": "inclusion", "text": "Age >= 50", "variable": "age",
             "operator": ">=", "value": 50, "simulatable": True},
        ]})
    assert response.status_code == 200
    body = response.json()
    assert body["population_n"] == 6
    assert len(body["patient_results"]) == 6
