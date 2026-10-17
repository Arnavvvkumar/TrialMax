"""Cross-endpoint identity, three-state counts and review on both population modes."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.cohorts import compare_population, population_catalog, simulate_population
from app.models import PopulationChoice, Rule

TEXT = "Inclusion Criteria:\n* Age >=50 years\n* ECOG <=1\n* ANC >=1.5 x10^9/L\nExclusion Criteria:\n* Brain metastases"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 10000)
    with TestClient(__import__('app.main', fromlist=['app']).app) as client:
        yield client


@pytest.mark.parametrize("mode", ["fixed", "generated"])
def test_analysis_simulation_and_unchanged_comparison_match(client, mode):
    option = next(p for p in client.get('/api/populations').json()['options'] if p['mode'] == mode)
    population = {"mode": mode, "size": 500, "seed": 42, "version": option['version']}
    analysis = client.post('/api/analyze', json={"eligibility_text": TEXT, "use_llm": False, "population": population})
    assert analysis.status_code == 200
    body = analysis.json()
    population['cohort_id'] = body['simulation']['cohort']['id']
    simulation = client.post('/api/simulate', json={"rules": body['rules'], "population": population})
    comparison = client.post('/api/compare', json={"baseline_rules": body['rules'], "proposed_rules": body['rules'], "population": population})
    assert simulation.status_code == comparison.status_code == 200
    result = comparison.json()
    assert simulation.json() == body['simulation'] == result['baseline'] == result['proposed']
    assert result['eligible_change_n'] == result['newly_eligible_n'] == result['newly_excluded_n'] == 0
    assert result['cohort']['id'] == population['cohort_id']
    assert sum(result['transitions'].values()) == 500


def test_generated_identity_changes_with_seed_size_or_mode():
    rules = [Rule(id='A', kind='inclusion', text='Age >=50', variable='age', operator='>=', value=50, simulatable=True)]
    outcomes = [simulate_population(rules, p) for p in [PopulationChoice(), PopulationChoice(mode='generated', size=500, seed=42), PopulationChoice(mode='generated', size=500, seed=43), PopulationChoice(mode='generated', size=501, seed=42)]]
    assert len({r.cohort.id for r in outcomes}) == 4
    for result in outcomes:
        assert result.eligible_n + result.excluded_n + result.unknown_n == result.population_n
        assert result.funnel[-1].remaining_n == result.eligible_n


@pytest.mark.parametrize("selection", [{"mode": "fixed", "version": "old"}, {"mode": "generated", "cohort_id": "fixed:wrong"}, {"mode": "fixed", "size": -1}, {"mode": "generated", "seed": -1}])
def test_invalid_or_stale_cohort_is_rejected(client, selection):
    response = client.post('/api/simulate', json={"rules": [], "population": selection})
    assert response.status_code == 422


@pytest.mark.parametrize("mode", ['fixed', 'generated'])
def test_admin_and_permission_do_not_make_clinical_results_unknown(mode):
    clinical = Rule(id='A', kind='inclusion', text='Age >=18', variable='age', operator='>=', value=18, simulatable=True)
    extras = [Rule(id='B', kind='inclusion', text='Consent', category='administrative'), Rule(id='C', kind='inclusion', text='Permission', category='permission')]
    choice = PopulationChoice(mode=mode, size=500)
    baseline = simulate_population([clinical], choice)
    result = simulate_population([clinical, *extras], choice)
    assert (result.eligible_n, result.excluded_n, result.unknown_n) == (baseline.eligible_n, baseline.excluded_n, baseline.unknown_n)
    assert result.coverage_pct == 100
    assert result.not_applicable_rule_ids == ['B', 'C']


def test_missing_variable_is_unknown_and_not_simulated():
    rule = Rule(id='A', kind='exclusion', text='HIV', variable='hiv', operator='present', simulatable=True)
    result = simulate_population([rule], PopulationChoice())
    assert result.eligible_n is None and result.unknown_n == 500 and result.excluded_n == 0
    assert result.unmodeled_rule_ids == ['A'] and result.impacts[0].unknown_n == 500


def test_numeric_safety_changes_and_reasons_for_review():
    old = Rule(id='A', kind='inclusion', text='ANC >=1.5', variable='anc', operator='>=', value=1.5, unit='10^9/L', purpose='safety', simulatable=True)
    result = compare_population([old], [old.model_copy(update={'value': 1.0})], PopulationChoice())
    assert result.safety_review_rule_ids == ['A']
    assert result.changes[0].change == 'relaxed'
    assert result.newly_excluded_n == 0
    assert '1.5' in result.baseline.funnel[-1].label
    assert ' 1 ' in result.proposed.funnel[-1].label
    assert '1.5' not in result.proposed.funnel[-1].label


def test_fixed_biomarker_is_distinct_from_kidney_function():
    option = population_catalog()['options'][0]
    assert 'egfr_mutation_positive' in option['available_variables'] and 'egfr' in option['available_variables']
    rule = Rule(id='G', kind='inclusion', text='EGFR mutation positive', variable='egfr_mutation_positive', operator='present', simulatable=True)
    result = simulate_population([rule], PopulationChoice())
    assert result.eligible_n == 136 and result.excluded_n == 341 and result.unknown_n == 23
    generated = simulate_population([rule], PopulationChoice(mode='generated', size=500))
    assert generated.eligible_n is None and generated.unknown_n == 500


def test_generated_patient_preview_is_bounded_but_totals_use_all_records():
    rule = Rule(id='A', kind='inclusion', text='Age >=50', variable='age', operator='>=', value=50, simulatable=True)
    result = simulate_population([rule], PopulationChoice(mode='generated', size=5000))
    assert len(result.patient_results) <= 100 and not result.patient_results_complete
    assert result.eligible_n + result.excluded_n + result.unknown_n == 5000
