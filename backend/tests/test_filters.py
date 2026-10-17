import numpy as np

from app.engine import rule_masks
from app.filters import hidden_filters
from app.models import Rule


def numeric(rid, variable):
    return Rule(id=rid, kind='inclusion', text=rid, variable=variable, operator='>=', value=1, simulatable=True)


def test_identical_rules_and_independent_rule_have_two_components():
    columns = {'anc': np.tile([0, 0, 1, 1], 25), 'platelets': np.tile([0, 0, 1, 1], 25),
               'ecog': np.tile([0, 1, 0, 1], 25)}
    result = hidden_filters([numeric('A', 'anc'), numeric('B', 'platelets'), numeric('C', 'ecog')], columns)
    assert len(result.components) == 2 and result.variance_target_reached
    first = result.components[0]
    assert np.isclose(first.loadings['A'], first.loadings['B'])
    assert abs(first.loadings['A']) > 0.7 and abs(first.loadings['C']) < 1e-8
    assert np.isclose(first.explained_variance_ratio, 2 / 3)
    assert np.isclose(result.explained_variance_total, 1)
    assert [(p.rule_a_id, p.rule_b_id, p.jaccard, p.both_fail_n) for p in result.redundancy_pairs] == [('A', 'B', 1, 50)]
    assert 'not a statistical test' in result.disclosure


def test_unknown_values_are_never_failures_and_constants_are_dropped():
    columns = {'anc': np.array([None, 0, 1, None], dtype=object), 'age': np.full(4, 40),
               'platelets': np.zeros(4), 'ecog': np.array([0, 1, 0, 1])}
    rules = [numeric('A', 'anc'), numeric('PASS', 'age'), numeric('FAIL', 'platelets'), numeric('C', 'ecog'),
             Rule(id='ADMIN', kind='inclusion', text='Consent', category='administrative')]
    failed, missing = rule_masks(rules, columns)['A']
    assert failed.tolist() == [False, True, False, False]
    assert missing.tolist() == [True, False, False, True]
    result = hidden_filters(rules, columns)
    assert set(result.included_rule_ids) == {'A', 'C'}
    assert set(result.dropped_rule_ids) == {'PASS', 'FAIL', 'ADMIN'}


def test_no_varying_columns_has_no_fabricated_components():
    result = hidden_filters([numeric('A', 'anc')], {'anc': np.ones(10)})
    assert result.components == [] and result.explained_variance_total == 0
    assert result.redundancy_pairs == []


def test_pca_sign_and_component_order_are_deterministic():
    columns = {'anc': np.tile([0, 0, 1, 1], 10), 'ecog': np.tile([0, 1, 0, 1], 10)}
    rules = [numeric('A', 'anc'), numeric('B', 'ecog')]
    assert hidden_filters(rules, columns).model_dump() == hidden_filters(list(reversed(rules)), columns).model_dump()
