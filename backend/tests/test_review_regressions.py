"""Regression cases reproduced during the pre-push backend review. No network calls."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config, llm
from app.criteria import parse_criterion
from app.main import app
from app.models import Rule
from app.pipeline import MAX_RULES, parse_eligibility
from app.population import POPULATION_VERSION
from app.simulate import compare, fail_mask, simulate


@pytest.mark.parametrize("text", [
    "If age >=65 years, ECOG <=1",
    "For patients with liver metastases, AST <=5 x ULN",
    "In patients with renal impairment, creatinine <=1.5 mg/dL",
    "For patients with liver metastases, AST <=5 x ULN and must have ALT <=5 x ULN",
])
def test_numeric_subgroup_requirements_are_not_global_filters(text):
    rules = parse_criterion("I1", "inclusion", text)
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)
    assert any(r.category == "conditional" for r in rules)
    assert not simulate(rules, 100, 42).complete


@pytest.mark.parametrize("text", [
    "ANC >=1.5 x10^9/L and <10 x10^9/L",
    "ANC >=1.5 x10^9/L and ANC <10 x10^9/L",
    "ECOG <=2 and >=1",
    "Age 18 to 75 years and <65 years",
    "Age >=18 years or <=65 years",
])
def test_extra_numeric_bounds_are_not_silently_dropped(text):
    rules = parse_criterion("I1", "inclusion", text)
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)


@pytest.mark.parametrize("text", [
    "ANC >=1.5 x10^9/L and tumor must express PD-L1",
    "Tumor must express PD-L1 and ANC >=1.5 x10^9/L",
    "ANC >=1.5 x10^9/L and PD-L1 positive",
    "Age >=18 years and tumor must express PD-L1 and <=65 years",
])
def test_unknown_conjoined_requirements_remain_visible(text):
    rules = parse_criterion("I1", "inclusion", text)
    sim = simulate(rules, 100, 42)
    assert not sim.complete and sim.unmodeled_rule_ids
    assert any("PD-L1" in (r.clause or r.text) for r in rules if not r.simulatable)


@pytest.mark.parametrize("kind,text", [
    ("exclusion", "Patients who have HIV and are pregnant"),
    ("exclusion", "Patients with HIV and no active infection"),
    ("inclusion", "Age >=18 years; OR ECOG <=2"),
    ("inclusion", "Age >=18 years. Alternatively ECOG <=2"),
    ("inclusion", "Age >=18 years; OR agree to provide consent"),
    ("inclusion", "ANC >=1.5 x10^9/L or tumor must express PD-L1"),
    ("exclusion", "ANC <1.5 x10^9/L and tumor must express PD-L1"),
])
def test_clause_splitting_preserves_compound_semantics(kind, text):
    rules = parse_criterion("R", kind, text)
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)
    assert any(r.category == "compound" for r in rules)


def test_negated_immunotherapy_exclusion_excludes_unexposed_patients():
    rules = parse_criterion("E1", "exclusion", "Patients with no prior immunotherapy")
    assert len(rules) == 1
    assert rules[0].operator == "absent"
    pop = {"prior_immunotherapy": np.array([False, True])}
    assert fail_mask(rules[0], pop).tolist() == [True, False]


@pytest.mark.parametrize("text", [
    "History of grade 3 toxicity after prior immunotherapy",
    "Patients who progressed after prior immunotherapy",
    "Patients with intolerance to previous immunotherapy",
])
def test_treatment_outcomes_are_not_substituted_with_exposure(text):
    rules = parse_criterion("E1", "exclusion", text)
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)


@pytest.mark.parametrize("text", [
    "ANC >=1.5 x10^6/L",
    "Platelets >=100 x10^12/L",
    "Creatinine <=150 nmol/L",
    "Creatinine <=2 bananas",
    "eGFR >=60 mL/min",
    "Creatinine <=2 (bananas)",
])
def test_explicit_unsupported_units_are_never_inferred(text):
    rules = parse_criterion("I1", "inclusion", text)
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)
    assert any("not supported" in note for r in rules for note in r.notes)


def test_plain_uln_remains_a_multiple_not_an_absolute_unit():
    rule = parse_criterion("I1", "inclusion", "Creatinine <=1.5 ULN")[0]
    assert rule.simulatable and rule.unit == "x_uln" and rule.value == 1.5


def test_parenthesized_explicit_units_are_converted():
    rule = parse_criterion("I1", "inclusion", "Creatinine <=0.11 (mmol/L)")[0]
    assert rule.simulatable and rule.unit == "mg/dL"
    assert rule.value == pytest.approx(1.2443) and rule.fidelity == "exact"


def test_breastfeeding_is_not_substituted_with_pregnancy():
    rules = parse_criterion("E1", "exclusion", "Breastfeeding women")
    assert all(not r.simulatable and r.parsed_by == "rules" for r in rules)


def test_unknown_comparison_does_not_report_newly_eligible_patients():
    baseline = [Rule(id="I1", kind="inclusion", text="Age >=80 years", variable="age",
                     operator=">=", value=80, simulatable=True)]
    proposed = [Rule(id="I1", kind="inclusion", text="Must express an unmodeled biomarker")]
    for a, b in [(baseline, proposed), (proposed, baseline), ([], [])]:
        result = compare(a, b, 1000, 42)
        assert result.eligible_change_n is None
        assert result.newly_eligible_n is None and result.newly_excluded_n is None


def test_unmodeled_safety_edits_require_review():
    old = Rule(id="E1", kind="exclusion", text="Active infection restriction", safety_critical=True)
    new = old.model_copy(update={"text": "Active infection is allowed", "category": "permission"})
    result = compare([old], [new], 100, 42)
    assert result.changed_rule_ids == ["E1"]
    assert result.review_safety_critical_rule_ids == ["E1"]
    assert compare([old], [old], 100, 42).changed_rule_ids == []


def test_compare_api_returns_null_counts_and_safety_review_for_unknown_rules():
    old = {"id": "E1", "kind": "exclusion", "text": "Unmodeled safety restriction", "safety_critical": True}
    new = {**old, "text": "The restriction is removed", "category": "permission"}
    with TestClient(app) as client:
        response = client.post("/api/compare", json={
            "baseline_rules": [old], "proposed_rules": [new], "population_size": 100,
        })
    assert response.status_code == 200
    body = response.json()
    assert body["newly_eligible_n"] is None and body["newly_excluded_n"] is None
    assert body["review_safety_critical_rule_ids"] == ["E1"]


def oversized_protocol():
    return "Inclusion Criteria:\n" + "\n".join(
        ["* Age >=18 years"] * MAX_RULES + ["* No history of myocarditis"]
    )


def test_oversized_protocol_is_rejected_before_ai(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "classify", lambda rule: sent.append(rule))
    with pytest.raises(ValueError, match="limit"):
        parse_eligibility(oversized_protocol(), True)
    assert sent == []


def test_api_does_not_return_complete_results_for_truncated_protocol():
    with TestClient(app) as client:
        response = client.post("/api/analyze", json={
            "eligibility_text": oversized_protocol(), "use_llm": False, "population_size": 100,
        })
    assert response.status_code == 422 and "limit" in response.json()["detail"]


@pytest.mark.parametrize("chunked", [False, True])
def test_actual_body_bytes_are_limited(monkeypatch, chunked):
    body = json.dumps({"rules": [], "ignored_padding": "x" * 200}).encode()
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 100)
    content = iter([body[:50], body[50:]]) if chunked else body
    with TestClient(app) as client:
        response = client.post("/api/simulate", content=content,
                               headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_chunked_request_within_limit_is_accepted(monkeypatch):
    body = json.dumps({"rules": [], "population_size": 100}).encode()
    monkeypatch.setattr(config, "MAX_BODY_BYTES", len(body))
    with TestClient(app) as client:
        response = client.post("/api/simulate", content=iter([body[:10], body[10:]]),
                               headers={"Content-Type": "application/json"})
    assert response.status_code == 200


def test_population_version_identifies_the_new_generator():
    assert POPULATION_VERSION == "synthetic-oncology-v1"
    assert any(POPULATION_VERSION in assumption for assumption in simulate([], 100, 42).assumptions)
