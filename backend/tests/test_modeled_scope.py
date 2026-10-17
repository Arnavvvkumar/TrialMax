"""The exploratory headline/funnel must not imply full-protocol eligibility."""
import json
from pathlib import Path

import pytest

from app import config
from app.cohorts import compare_population, simulate_population, trial_population_warnings
from app.criteria import parse_eligibility_rules
from app.main import health
from app.models import AnalyzeRequest, PopulationChoice, Rule, TrialInfo


@pytest.mark.parametrize('mode', ['fixed', 'generated'])
@pytest.mark.parametrize('nct', ['NCT07223541', 'NCT06149286', 'NCT06165419'])
def test_real_fixture_funnel_counts_only_available_checks(mode, nct):
    fixture = json.loads((Path(__file__).parent / 'fixtures' / f'{nct}.json').read_text(encoding='utf-8'))
    text = fixture['protocolSection']['eligibilityModule']['eligibilityCriteria']
    rules, _ = parse_eligibility_rules(text)
    choice = PopulationChoice(mode=mode, size=10000)
    result = simulate_population(rules, choice)
    subset = simulate_population([r for r in rules if r.id in result.modeled_rule_ids], choice)
    assert result.unmodeled_rule_ids
    assert result.modeled_eligible_n == subset.eligible_n > 0
    assert result.funnel[-1].remaining_n == result.modeled_eligible_n
    assert result.funnel[-1].unknown_n == result.modeled_unknown_n
    assert [s.rule_id for s in result.funnel[1:]] == result.modeled_rule_ids
    assert result.modeled_eligible_n + result.modeled_unknown_n + result.excluded_n == result.population_n
    assert result.eligible_n == 0  # unresolved full protocol, deliberately not the headline


def age_rule(value=50):
    return Rule(id='A', kind='inclusion', text='Age >=50', variable='age', operator='>=', value=value, simulatable=True)


def test_first_unsupported_rule_does_not_empty_the_funnel_or_erase_patient_check_status():
    unsupported = Rule(id='U', kind='inclusion', text='An unsupported requirement')
    result = simulate_population([unsupported, age_rule()], PopulationChoice(mode='fixed'))
    assert [s.rule_id for s in result.funnel] == [None, 'A']
    for patient in result.patient_results:
        if patient.criteria[1].status == 'pass':
            assert patient.modeled_status == 'pass' and patient.overall_status == 'unknown'
    assert result.modeled_unknown_n > 0  # actual missing ages stay unknown


def test_only_unsupported_checks_produce_no_modeled_estimate():
    result = simulate_population([Rule(id='U', kind='inclusion', text='Unknown')], PopulationChoice(mode='fixed'))
    assert result.modeled_eligible_n is result.modeled_eligible_pct is None
    assert len(result.funnel) == 1 and result.modeled_unknown_n == 500


def test_modeled_comparison_shows_change_even_when_full_protocol_stays_unresolved():
    unsupported = Rule(id='U', kind='inclusion', text='Unknown biomarker subtype')
    result = compare_population([unsupported, age_rule(70)], [unsupported, age_rule(50)], PopulationChoice(mode='fixed'))
    assert result.eligible_change_n == 0 and result.newly_eligible_n == 0
    assert result.modeled_eligible_change_n > 0
    assert result.modeled_eligible_change_pct_points > 0
    assert result.modeled_newly_eligible_n == result.modeled_eligible_change_n
    assert result.modeled_newly_excluded_n == 0
    assert sum(result.modeled_transitions.values()) == 500


def test_registry_default_and_explicit_population_choice():
    # Synthea is the default population for registry lookups and pasted text alike.
    assert AnalyzeRequest(nct_id='NCT06165419').population.mode == 'synthea'
    assert AnalyzeRequest(eligibility_text='Age >=18').population.mode == 'synthea'
    assert AnalyzeRequest(nct_id='NCT06165419', population={'mode': 'fixed'}).population.mode == 'fixed'


@pytest.mark.parametrize('conditions', [['Renal Cell Carcinoma'], ['Lymphoma'], ['Spine Metastases'], []])
def test_fixed_cohort_warns_for_unconfirmed_nsclc_trial(conditions):
    warnings = trial_population_warnings(TrialInfo(nct_id='NCT06165419', conditions=conditions), 'fixed')
    assert len(warnings) == 1 and 'Population mismatch' in warnings[0]


def test_shared_disease_label_and_generated_cohort_do_not_claim_representativeness():
    trial = TrialInfo(nct_id='NCT06165419', conditions=['Non-Small Cell Lung Cancer'])
    assert 'shared disease label' in trial_population_warnings(trial, 'fixed')[0]
    assert 'not matched' in trial_population_warnings(trial, 'generated')[0]


def test_chalk_configuration_status_does_not_leak_key_or_claim_live_connectivity(monkeypatch):
    monkeypatch.setattr(config, 'CHALK_ROUTER_API_KEY', 'private-test-key')
    monkeypatch.setattr(config, 'CHALK_ENV_ID', 'environment')
    monkeypatch.setattr(config, 'LLM_MODEL', '')
    assert health()['llm_missing_configuration'] == ['LLM_MODEL']
    assert health()['llm_status'] == 'not_configured'
    monkeypatch.setattr(config, 'LLM_MODEL', 'test-model')
    assert health()['llm_status'] == 'configured_not_verified'
    assert 'private-test-key' not in json.dumps(health())
