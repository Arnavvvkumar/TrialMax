import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import autopilot, cohorts, config
from app.autopilot import candidate_edits, run_autopilot
from app.cohorts import compare_population
from app.main import app
from app.models import AutopilotRequest, CohortInfo, PopulationChoice, Rule
from app.simulate import _critical, classify_change


def rule(rid='A', variable='age', op='between', value=18, value_max=65, **kw):
    return Rule(id=rid, kind=kw.pop('kind', 'inclusion'), text=rid, variable=variable, operator=op,
                value=value, value_max=value_max, simulatable=True, **kw)


def request(rules=None, **kwargs):
    return AutopilotRequest(rules=rules if rules is not None else [rule(), rule('H', 'hemoglobin', '>=', 10, None, unit='g/dL')],
                           population=PopulationChoice(mode='generated', size=1000, seed=42), **kwargs)


@pytest.mark.parametrize('variable,op,value,unit,expected', [
    ('ecog', '<=', 1, None, [2]), ('anc', '>=', 1.5, '10^9/L', [1]),
    ('platelets', '>=', 100, '10^9/L', [75]), ('hemoglobin', '>=', 9, 'g/dL', [8]),
    ('egfr', '>=', 60, 'mL/min/1.73m2', [45, 30]), ('crcl', '>=', 45, 'mL/min', [30]),
    ('bilirubin', '<=', 1.5, 'x_uln', [2]), ('bilirubin', '<=', 1.8, 'mg/dL', [2.4]),
    ('ast', '<=', 2.5, 'x_uln', [3]), ('alt', '<=', 100, 'U/L', [120]),
])
def test_candidates_are_exact_table_steps_and_preserve_units(variable, op, value, unit, expected):
    original = rule(variable=variable, op=op, value=value, value_max=None, unit=unit)
    candidates = candidate_edits(original)
    assert [c.after for c in candidates] == expected
    for c in candidates:
        assert c.rule.unit == unit and c.rule.kind == original.kind and c.rule.operator == original.operator
        assert classify_change(original, c.rule) == 'relaxed'
        assert Rule.model_validate(c.rule.model_dump()) == c.rule


def test_age_lower_bound_is_never_changed_and_unlisted_thresholds_are_not_guessed():
    assert candidate_edits(rule(op='>=', value=18, value_max=None)) == []
    assert candidate_edits(rule(variable='anc', op='>=', value=1.7, value_max=None)) == []
    assert candidate_edits(rule(variable='bilirubin', op='<=', value=1.5, value_max=None, unit='mg/dL')) == []
    for candidate in candidate_edits(rule()):
        assert candidate.field == 'value_max' and candidate.rule.value == 18
    inverted = rule(variable='anc', op='<', value=1.5, value_max=None, kind='exclusion')
    assert [c.after for c in candidate_edits(inverted)] == [1]


def test_every_comparison_preserves_all_rules_and_never_touches_critical_rules(monkeypatch):
    critical = [rule('CRIT', safety_critical=True)]
    for variable in ['pregnant', 'myocarditis_history', 'active_infection', 'hepatic_impairment', 'interstitial_lung_disease', 'drug_hypersensitivity']:
        critical.append(rule(variable, variable, 'present', None, None, kind='exclusion', safety_critical=False))
    original = request().rules + critical
    calls = []

    def checked(before, after, choice):
        assert [r.id for r in after] == [r.id for r in before]
        for old, new in zip(before, after):
            assert old.simulatable == new.simulatable
            if _critical(old):
                assert old.model_dump() == new.model_dump()
        result = compare_population(before, after, choice)
        assert not result.relaxed_safety_critical_rule_ids
        calls.append(result)
        return result

    monkeypatch.setattr(autopilot, 'compare_population', checked)
    result = run_autopilot(request(original))
    assert calls and result.simulation_count == 1 + 2 * len(calls)
    blocked = {r.id for r in critical}
    assert blocked == {r.rule_id for r in result.blocked_rules}
    assert not blocked & {e.rule_id for e in result.plan}
    assert all(candidate_edits(r) == [] for r in critical)


@pytest.mark.parametrize('rules', [None, [rule('I2', value_max=70),
                                        rule('REG-AGE-MAX', op='<=', value=70, value_max=None)]])
def test_reported_gains_and_maximum_match_independent_simulator_runs(rules):
    req = request(rules)
    result = run_autopilot(req)
    proposed = [r.model_dump() for r in req.rules]
    prior = 0
    for edit in result.plan:
        old = next(r for r in req.rules if r.id == edit.rule_id)
        assert any(c.field == edit.field and c.after == edit.to for c in candidate_edits(old))
        next(row for row in proposed if row['id'] == edit.rule_id)[edit.field] = edit.to
        comparison = compare_population(req.rules, [Rule.model_validate(row) for row in proposed], req.population)
        assert edit.cumulative_gain == comparison.modeled_eligible_change_n
        assert edit.marginal_gain == edit.cumulative_gain - prior
        assert edit.review_flag  # age and hemoglobin are safety-purpose defaults
        prior = edit.cumulative_gain
    upper = []
    for old in req.rules:
        candidates = candidate_edits(old)
        upper.append(max(candidates, key=lambda c: abs(c.after - c.before)).rule if candidates else old)
    assert result.max_achievable_gain == compare_population(req.rules, upper, req.population).modeled_eligible_change_n
    assert result.target_reached and prior >= result.target_gain


def test_deterministic_and_edit_limit_is_respected():
    req = request(max_edits=1)
    first, second = run_autopilot(req), run_autopilot(req)
    assert first.model_dump() == second.model_dump()
    assert len(first.plan) <= 1 and first.simulation_count <= 150


def test_returns_smallest_found_set_when_a_single_edit_reaches_target():
    result = run_autopilot(request([rule()], max_edits=5))
    assert result.target_reached and len(result.plan) == 1


def test_simulation_cap_reserves_budget_and_discloses_unexplored_alternatives(monkeypatch):
    monkeypatch.setattr(autopilot, 'MAX_SIMULATIONS', 25)
    rules = request().rules + [rule('C', 'crcl', '>=', 60, None), rule('E', 'ecog', '<=', 1, None),
                              rule('N', 'anc', '>=', 1.5, None), rule('G', 'egfr', '>=', 60, None)]
    result = run_autopilot(request(rules, max_edits=5, target_fraction=1))
    assert result.simulation_count == result.simulation_cap == 25
    assert any('budget' in warning for warning in result.warnings)


def test_nothing_relaxable_has_clear_empty_plan():
    result = run_autopilot(request([rule(op='>=', value=18, value_max=None)]))
    assert result.plan == [] and result.status == 'no_plan'
    assert 'No modeled, noncritical' in result.reason


def test_duplicate_age_limits_are_relaxed_together():
    req = request([rule('I2', value_max=70), rule('REG-AGE-MAX', op='<=', value=70, value_max=None)])
    result = run_autopilot(req)
    assert result.max_achievable_gain > 0
    assert result.target_reached and len(result.plan) == 2
    assert {edit.rule_id for edit in result.plan} == {'I2', 'REG-AGE-MAX'}
    assert result.plan[0].marginal_gain == 0
    assert result.plan[-1].cumulative_gain >= result.target_gain


def planted_population(monkeypatch, columns):
    """Keep the real evaluator/comparison, replacing only the test cohort resolver."""
    n = len(next(iter(columns.values())))
    info = CohortInfo(id='generated:planted', mode='generated', version='planted', label='Synthetic test cohort',
                      population_n=n, seed=42, available_variables=list(columns))
    def resolve(choice):
        assert choice.cohort_id in (None, info.id)
        return info, columns, None, ['Planted synthetic test data.']
    monkeypatch.setattr(autopilot, 'resolve', resolve)
    monkeypatch.setattr(cohorts, 'resolve', resolve)


def test_prefers_gentlest_step_that_reaches_target(monkeypatch):
    planted_population(monkeypatch, {'egfr': np.array([50.] * 60 + [35.] * 11 + [70.] * 29)})
    req = request([rule('G', 'egfr', '>=', 60, None, unit='mL/min/1.73m2')])
    result = run_autopilot(req)
    assert result.max_achievable_gain == 71 and result.target_gain == 57
    assert result.target_reached and len(result.plan) == 1
    assert result.plan[0].to == 45 and result.plan[0].cumulative_gain == 60


def test_duplicate_group_counts_each_rule_toward_edit_limit():
    req = request([rule('A', value_max=70), rule('B', value_max=70)], max_edits=1)
    result = run_autopilot(req)
    assert result.max_achievable_gain > 0 and result.plan == []
    assert not result.target_reached and 'edit and simulation limits' in result.reason


def test_three_duplicate_rules_work_even_when_pca_drops_constant_failures(monkeypatch):
    planted_population(monkeypatch, {'age': np.full(100, 73.)})
    req = request([rule(rid, value_max=70) for rid in ['A', 'B', 'C']], max_edits=3)
    result = run_autopilot(req)
    assert result.filters.redundancy_pairs == []  # all-failing columns have zero variance
    assert result.target_reached and len(result.plan) == 3
    assert [e.to for e in result.plan] == [75, 75, 75]
    assert [e.marginal_gain for e in result.plan] == [0, 0, 100]
    assert [e.cumulative_gain for e in result.plan] == [0, 0, 100]
    assert run_autopilot(req).model_dump() == result.model_dump()


def test_redundant_different_variables_can_recover_only_jointly(monkeypatch):
    planted_population(monkeypatch, {'anc': np.array([1.2] * 60 + [2.] * 40),
                                    'platelets': np.array([80.] * 60 + [120.] * 40)})
    req = request([rule('A', 'anc', '>=', 1.5, None), rule('P', 'platelets', '>=', 100, None)])
    result = run_autopilot(req)
    assert result.filters.redundancy_pairs[0].jaccard == 1
    assert result.target_reached and {e.rule_id for e in result.plan} == {'A', 'P'}
    assert [e.marginal_gain for e in result.plan] == [0, 60]
    proposed = list(req.rules)
    prior = 0
    for edit in result.plan:
        proposed = [next(c.rule for c in candidate_edits(r) if c.after == edit.to)
                    if r.id == edit.rule_id else r for r in proposed]
        comparison = compare_population(req.rules, proposed, req.population)
        assert not comparison.relaxed_safety_critical_rule_ids
        assert edit.cumulative_gain == comparison.modeled_eligible_change_n
        assert edit.marginal_gain == edit.cumulative_gain - prior
        prior = edit.cumulative_gain


def test_critical_duplicate_is_not_relaxed_as_part_of_group(monkeypatch):
    planted_population(monkeypatch, {'age': np.full(100, 73.)})
    req = request([rule('A', value_max=70), rule('LOCKED', value_max=70, safety_critical=True)])
    result = run_autopilot(req)
    assert result.max_achievable_gain == 0 and result.plan == []
    assert [r.rule_id for r in result.blocked_rules] == ['LOCKED']


def test_joint_plan_uses_gentlest_target_reaching_steps(monkeypatch):
    planted_population(monkeypatch, {'egfr': np.array([50.] * 60 + [35.] * 11 + [70.] * 29)})
    req = request([rule(rid, 'egfr', '>=', 60, None) for rid in ['A', 'B']])
    result = run_autopilot(req)
    assert result.target_reached and len(result.plan) == 2
    assert [e.to for e in result.plan] == [45, 45]
    assert [e.marginal_gain for e in result.plan] == [0, 60]


def test_fewer_rules_takes_priority_over_smaller_threshold_movements(monkeypatch):
    planted_population(monkeypatch, {'egfr': np.array([35.] * 50 + [70.] * 50),
                                    'age': np.array([68.] * 50 + [73.] * 50),
                                    'hemoglobin': np.array([10.5] * 50 + [9.5] * 50)})
    req = request([rule('G', 'egfr', '>=', 60, None), rule('A', value_max=70),
                   rule('H', 'hemoglobin', '>=', 10, None)], target_fraction=0.5)
    result = run_autopilot(req)
    # G=30 reaches the target in one edit; the gentler age/Hb pair requires two.
    assert result.target_reached and len(result.plan) == 1
    assert result.plan[0].rule_id == 'G' and result.plan[0].to == 30


@pytest.mark.parametrize('field,value', [('max_edits', 0), ('max_edits', 6), ('target_fraction', 0.49), ('target_fraction', 1.01)])
def test_api_rejects_invalid_search_limits(monkeypatch, field, value):
    monkeypatch.setattr(config, 'API_TOKEN', '')
    with TestClient(app) as client:
        response = client.post('/api/autopilot', json={'rules': [], field: value})
    assert response.status_code == 422


def test_api_false_llm_and_from_alias_work_with_default_synthea(monkeypatch):
    monkeypatch.setattr(config, 'API_TOKEN', '')
    monkeypatch.setattr(config, 'RATE_LIMIT_PER_MIN', 10000)
    with TestClient(app) as client:
        response = client.post('/api/autopilot', json={'rules': [rule().model_dump()], 'use_llm': False})
    assert response.status_code == 200
    body = response.json()
    assert body['cohort_id'].startswith('synthea:') and body['plan']
    assert body['plan'][0]['from'] == 65 and 'from_value' not in body['plan'][0]
    assert body['narration_source'] == 'template'
