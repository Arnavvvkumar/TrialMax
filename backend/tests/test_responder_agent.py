import json
from unittest.mock import Mock

import pytest

from app import config, llm, responder_agent as agent
from app.responder_evidence import read_cases


@pytest.fixture
def evidence():
    return read_cases()[0]


def response(**changes):
    return json.dumps(dict(flag=None, direction=None, confidence='low',
                          rationale='Multiplicity limits evidence; a researcher must decide.', **changes))


def test_payload_is_whitelisted_and_blind_to_reference_labels(evidence):
    evidence.planted_subgroup = 'SECRET_TARGET'
    evidence.provenance['patient_rows'] = [{'SECRET_PATIENT_ID': 1}]
    for variant in ['names_only', 'with_stats']:
        payload = agent.aggregate_payload(evidence, variant)
        encoded = json.dumps(payload)
        for forbidden in ['truth', 'planted', 'SECRET', 'patient_rows', 'case_id', 'any_significant']:
            assert forbidden not in encoded
        assert set(payload) == {'trial', 'treatment', 'control', 'endpoint', 'prompt_variant', 'evidence_note', 'subgroups'}
        if variant == 'names_only':
            assert all(set(row) == {'id', 'label', 'n'} for row in payload['subgroups'])
        else:
            assert all('q_value' in row and 'interaction_p' in row for row in payload['subgroups'])


def test_gbsg_evidence_warning_is_sent():
    case = next(c for c in read_cases() if c.trial_key == 'gbsg')
    assert 'non-randomized' in agent.aggregate_payload(case)['evidence_note']


@pytest.mark.parametrize('raw', [
    'not json', '```json\n{}\n```',
    '{"flag":null,"direction":null,"confidence":"low","rationale":"x","extra":true}',
    '{"flag":"unknown","direction":"weaker_benefit","confidence":"low","rationale":"Multiplicity; researcher decides."}',
    '{"flag":null,"direction":"weaker_benefit","confidence":"low","rationale":"Multiplicity; researcher decides."}',
    '{"flag":null,"direction":null,"confidence":"low","rationale":"HR is 98765; multiplicity; researcher decides."}',
    '{"flag":null,"direction":null,"confidence":"low","rationale":"No review needed."}',
])
def test_invalid_output_becomes_safe_null(monkeypatch, evidence, raw):
    monkeypatch.setattr(config, 'llm_configured', lambda: True)
    client = Mock(); client.with_options.return_value = client
    monkeypatch.setattr(llm, '_client', lambda: client)
    call = Mock(return_value=raw); monkeypatch.setattr(llm, 'call_model', call)
    result = agent.run_agent(evidence, use_cache=False)
    assert result.flag is result.direction is None
    assert result.confidence == 'low' and result.rationale == '' and result.invalid
    assert call.call_count == 1
    assert client.with_options.call_args.kwargs['max_retries'] == 0
    assert client.with_options.call_args.kwargs['timeout'] <= 15


def test_valid_output_is_cached_without_another_call(monkeypatch, tmp_path, evidence):
    monkeypatch.setattr(config, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(config, 'llm_configured', lambda: True)
    client = Mock(); client.with_options.return_value = client
    monkeypatch.setattr(llm, '_client', lambda: client)
    call = Mock(return_value=response()); monkeypatch.setattr(llm, 'call_model', call)
    first = agent.run_agent(evidence)
    assert first == agent.run_agent(evidence)
    assert not first.invalid and call.call_count == 1
    sent = call.call_args.kwargs
    assert sent['system_prompt'] == agent.SYSTEM
    assert json.loads(sent['user_prompt']) == agent.aggregate_payload(evidence)


def test_unavailable_or_timeout_is_safe(monkeypatch, evidence):
    monkeypatch.setattr(config, 'llm_configured', lambda: False)
    assert agent.run_agent(evidence, use_cache=False).source == 'unavailable'
    monkeypatch.setattr(config, 'llm_configured', lambda: True)
    monkeypatch.setattr(llm, '_client', Mock(side_effect=TimeoutError))
    result = agent.run_agent(evidence, use_cache=False)
    assert result.invalid and result.flag is None and result.rationale == ''


def test_valid_known_flag_and_bad_prompt_variant(evidence):
    raw = json.dumps(dict(flag=evidence.subgroups[0].id, direction='weaker_benefit', confidence='low',
                          rationale='Multiplicity considered; a researcher must decide.'))
    assert agent.validate_suggestion(raw, agent.aggregate_payload(evidence)).flag == evidence.subgroups[0].id
    with pytest.raises(ValueError): agent.aggregate_payload(evidence, 'truth')


def test_hosted_payload_path_drops_truth_and_nested_extra_keys(monkeypatch, evidence):
    payload = agent.aggregate_payload(evidence)
    payload['truth_flag'] = 'SECRET_TARGET'
    payload['subgroups'][0]['truth'] = 'SECRET_LABEL'
    payload['subgroups'][0]['subgroup']['patient_rows'] = ['SECRET_PATIENT']
    monkeypatch.setattr(config, 'llm_configured', lambda: True)
    client = Mock(); client.with_options.return_value = client
    monkeypatch.setattr(llm, '_client', lambda: client)
    call = Mock(return_value=response()); monkeypatch.setattr(llm, 'call_model', call)
    assert not agent.run_payload(payload, use_cache=False).invalid
    assert 'SECRET' not in call.call_args.kwargs['user_prompt']
    assert agent.run_payload({'prompt_variant':'unknown'}, use_cache=False).invalid
