"""The Synthea cohort is the default population and never invents values Synthea does not simulate."""
import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.cohorts import SYNTHEA_PATH, population_catalog, simulate_population
from app.models import PopulationChoice, Rule

RAW = json.loads(SYNTHEA_PATH.read_text(encoding="utf-8"))
PATIENTS = RAW["patients"]
SYNTHEA = PopulationChoice(mode="synthea")


def rule(rid, variable, operator, value=None, kind="inclusion", **kw):
    return Rule(id=rid, kind=kind, text=f"{variable} {operator} {value}", variable=variable, operator=operator,
                value=value, simulatable=True, **kw)


def test_synthea_is_the_default_and_only_visible_population():
    catalog = population_catalog()
    assert catalog["default_mode"] == "synthea"
    assert [o["mode"] for o in catalog["options"] if o["visible"]] == ["synthea"]
    synthea = catalog["options"][0]
    assert synthea["cohort_id"].startswith("synthea:") and synthea["size"] == len(PATIENTS)
    assert PopulationChoice().mode == "synthea"


def test_records_are_synthetic_pseudonymous_and_unique():
    assert RAW["format"] == "clinova-synthea-cohort-v1" and RAW["metadata"]["source"].startswith("Synthea")
    ids = [p["patient_id"] for p in PATIENTS]
    assert len(ids) == len(set(ids)) and all(i.startswith("SYN-") for i in ids)
    assert all(p["synthetic"] is True for p in PATIENTS)
    # No names, addresses or other identifiers are copied from Synthea.
    forbidden = {"FIRST", "LAST", "SSN", "ADDRESS", "BIRTHDATE", "Id", "name", "address"}
    assert not forbidden & set().union(*(p.keys() for p in PATIENTS))
    assert all(40 <= p["age"] <= 90 for p in PATIENTS)


@pytest.mark.parametrize("variable", sorted(RAW["metadata"]["not_simulated"]))
def test_unsimulated_variables_are_always_unknown(variable):
    assert all(p.get(variable) is None for p in PATIENTS)
    assert variable not in population_catalog()["options"][0]["available_variables"]


def test_ecog_rule_is_not_checked_on_synthea():
    result = simulate_population([rule("E", "ecog", "<=", 1)], SYNTHEA)
    assert result.unmodeled_rule_ids == ["E"] and result.modeled_eligible_n is None
    assert result.unknown_n == result.population_n


def test_missing_labs_stay_unknown_and_counts_add_up():
    result = simulate_population([rule("H", "hemoglobin", ">=", 10, unit="g/dL")], SYNTHEA)
    missing = sum(p["hemoglobin"] is None for p in PATIENTS)
    failing = sum(p["hemoglobin"] is not None and p["hemoglobin"] < 10 for p in PATIENTS)
    assert result.impacts[0].unknown_n == missing and result.impacts[0].fail_n == failing
    assert result.modeled_eligible_n + result.excluded_n + result.modeled_unknown_n == result.population_n


def test_age_and_condition_rules_match_the_records():
    rules = [rule("A", "age", "<=", 65), rule("X", "cardiac_disease", "present", kind="exclusion")]
    result = simulate_population(rules, SYNTHEA)
    expected = sum(p["age"] <= 65 and not p["cardiac_disease"] for p in PATIENTS)
    assert result.modeled_eligible_n == expected and result.complete
    assert any("Synthea" in text for text in result.assumptions)


def test_stale_synthea_version_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 10000)
    with TestClient(__import__("app.main", fromlist=["app"]).app) as client:
        body = {"rules": [rule("A", "age", ">=", 50).model_dump()], "population": {"mode": "synthea", "version": "old"}}
        assert client.post("/api/simulate", json=body).status_code == 422
        ok = client.post("/api/simulate", json={**body, "population": {"mode": "synthea"}})
        assert ok.status_code == 200 and ok.json()["cohort"]["mode"] == "synthea"
