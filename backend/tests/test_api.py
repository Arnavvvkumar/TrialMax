"""API-level checks (no network: only endpoints that do not call ClinicalTrials.gov)."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)

GOOD = {"id": "I1", "kind": "inclusion", "text": "ECOG <= 1", "variable": "ecog", "operator": "<=",
        "value": 1, "simulatable": True}


def post(path, body, **kw):
    return client.post(path, json=body, **kw)


def test_simulate_ok():
    # GOOD is an ECOG rule; Synthea has no ECOG, so use the fixed cohort, which does.
    r = post("/api/simulate", {"rules": [GOOD], "population": {"mode": "fixed"}})
    assert r.status_code == 200 and r.json()["eligible_pct"] is not None


@pytest.mark.parametrize("change", [
    {"variable": "anc", "operator": "present", "value": None},
    {"variable": "age", "operator": "between", "value": 18},
])
def test_simulate_rejects_invalid_rules(change):
    assert post("/api/simulate", {"rules": [{**GOOD, **change}]}).status_code == 422


def test_negative_seed_is_422():
    assert post("/api/simulate", {"rules": [GOOD], "seed": -1}).status_code == 422


def test_duplicate_ids_are_422():
    assert post("/api/simulate", {"rules": [GOOD, GOOD]}).status_code == 422
    assert post("/api/compare", {"baseline_rules": [GOOD], "proposed_rules": [GOOD, GOOD]}).status_code == 422


def test_oversized_rule_list_is_422():
    rules = [{**GOOD, "id": f"R{i}"} for i in range(201)]
    assert post("/api/simulate", {"rules": rules}).status_code == 422


def test_analyze_unmodeled_text_has_no_estimate_and_warns():
    r = post("/api/analyze", {"eligibility_text": "Inclusion Criteria:\n* Some unusual requirement", "use_llm": False})
    body = r.json()
    assert r.status_code == 200
    assert body["simulation"]["eligible_pct"] is None and body["warnings"]


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    assert post("/api/simulate", {"rules": [GOOD]}).status_code == 401
    ok = post("/api/simulate", {"rules": [GOOD]}, headers={"X-WT-Token": "secret-token"})
    assert ok.status_code == 200
    assert client.get("/api/health").status_code == 200


def test_body_size_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 100)
    assert post("/api/simulate", {"rules": [GOOD]}).status_code == 413
