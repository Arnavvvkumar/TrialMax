"""A live readiness check must distinguish configuration, access failures and valid parser output."""
import json

import pytest

from app import config, llm


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(config, 'CHALK_ROUTER_API_KEY', 'private-test-key')
    monkeypatch.setattr(config, 'CHALK_ENV_ID', 'clkdcdaf84e')
    monkeypatch.setattr(config, 'LLM_MODEL', 'openai/gpt-6-sol')
    options = {}

    class Client:
        def with_options(self, **kwargs):
            options.update(kwargs)
            return self

    monkeypatch.setattr(llm, '_client', Client)
    return options


def test_live_check_validates_a_fresh_expected_rule(configured, monkeypatch):
    calls = []

    def call(kind, text, **kwargs):
        calls.append((kind, text, kwargs))
        return json.dumps({'simulatable': True, 'variable': 'age', 'operator': '>=', 'value': 18})

    monkeypatch.setattr(llm, 'call_model', call)
    result = llm.check_connection()
    assert result['status'] == 'ready'
    assert len(calls) == 1 and calls[0][2]['client']
    assert configured['max_retries'] == 0 and configured['timeout'] <= 15
    assert result['checked_at'] and result['elapsed_ms'] >= 0


@pytest.mark.parametrize('body', ['nonsense', '{"simulatable":false}', '{"simulatable":true,"variable":"age","operator":">=","value":21}'])
def test_valid_http_response_alone_is_not_parser_readiness(configured, monkeypatch, body):
    monkeypatch.setattr(llm, 'call_model', lambda *args, **kwargs: body)
    assert llm.check_connection()['status'] == 'invalid_output'


@pytest.mark.parametrize('http_status,expected', [(401, 'authentication_failed'), (403, 'permission_denied'), (429, 'rate_limited'), (503, 'provider_error')])
def test_gateway_errors_are_actionable_and_do_not_expose_provider_bodies(configured, monkeypatch, http_status, expected):
    def call(*args, **kwargs):
        exc = Exception('Provider body could echo private-test-key')
        exc.status_code = http_status
        raise exc

    monkeypatch.setattr(llm, 'call_model', call)
    result = llm.check_connection()
    assert result['status'] == expected and result['http_status'] == http_status
    assert 'private-test-key' not in json.dumps(result)


def test_missing_configuration_does_not_send_a_request(monkeypatch):
    monkeypatch.setattr(config, 'LLM_MODEL', '')
    monkeypatch.setattr(llm, '_client', lambda: pytest.fail('Should not call the gateway'))
    assert llm.check_connection()['status'] == 'not_configured'
