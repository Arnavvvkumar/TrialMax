import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import config, responder_evidence as service
from app.main import app, heavy_request
from app.responder_agent import SYSTEM, safe_null
from app.responder_truth import RCT_DIR


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, 'run_agent', lambda _: safe_null('unavailable'))
    # Keep these endpoint tests independent of rate-limit counters in other suites.
    app.dependency_overrides[heavy_request] = lambda: None
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(heavy_request, None)


@pytest.mark.parametrize('body', [{}, {'trial_key':'../../.env'}, {'trial_key':'colon','variant':'planted:male'},
                                 {'trial_key':'colon','use_llm':False}])
def test_invalid_historical_request_is_422(client, body):
    assert client.post('/api/responder-evidence', json=body).status_code == 422


@pytest.mark.parametrize('key', ['colon', 'veteran', 'gbsg'])
def test_original_evidence_works_without_llm(client, key):
    response = client.post('/api/responder-evidence', json={'trial_key':key,'variant':'original'})
    assert response.status_code == 200
    body = response.json()
    assert body['evidence']['trial_key'] == key and body['evidence']['variant'] == 'original'
    assert body['evidence']['subgroups']
    assert body['suggestion']['flag'] is None and body['suggestion']['invalid']
    assert 'cases' not in body['evaluations']
    if key == 'gbsg': assert any('non-randomized' in d for d in body['disclaimers'])


def test_eval_summary_rejects_stale_ground_truth_or_model_and_omits_cases(monkeypatch, tmp_path):
    truth = (RCT_DIR/'ground_truth.jsonl').read_bytes()
    (tmp_path/'ground_truth.jsonl').write_bytes(truth)
    monkeypatch.setattr(service, 'RCT_DIR', tmp_path)
    record = dict(status='complete',runs=[],ground_truth_sha256='wrong',model=config.LLM_MODEL,
                  prompt_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(),cases=['raw output'])
    file = tmp_path/'chalk_runs.json'
    file.write_text(json.dumps(record))
    assert service.evaluation_summary()['status'] == 'stale'
    record['ground_truth_sha256'] = hashlib.sha256(truth).hexdigest()
    file.write_text(json.dumps(record))
    assert 'cases' not in service.evaluation_summary()
    record['model'] = 'different'
    file.write_text(json.dumps(record))
    assert service.evaluation_summary()['status'] == 'stale'


def test_incomplete_hosted_run_uses_labeled_local_fallback(monkeypatch, tmp_path):
    truth = (RCT_DIR/'ground_truth.jsonl').read_bytes()
    (tmp_path/'ground_truth.jsonl').write_bytes(truth)
    monkeypatch.setattr(service, 'RCT_DIR', tmp_path)
    (tmp_path/'chalk_runs.json').write_text(json.dumps(dict(status='incomplete',message='Hosted pending')))
    local = dict(status='local_only',runs=[],ground_truth_sha256=hashlib.sha256(truth).hexdigest(),
                 model=config.LLM_MODEL,prompt_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest())
    (tmp_path/'local_eval_results.json').write_text(json.dumps(local))
    summary = service.evaluation_summary()
    assert summary['status'] == 'local_only' and summary['hosted_status'] == 'incomplete'
