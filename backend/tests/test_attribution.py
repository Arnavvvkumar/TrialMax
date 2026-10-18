from itertools import permutations
from pathlib import Path

import numpy as np
import pytest

from app import engine
from app.attribution import shapley_attribution
from app.cohorts import resolve
from app.criteria import parse_eligibility_rules
from app.models import PopulationChoice, Rule


def rule(rid, **kwargs):
    return Rule(id=rid, kind='inclusion', text=rid, variable='age', operator='>=', value=18,
                simulatable=True, **kwargs)


def attribute(f):
    rules = [rule(f'R{i}') for i in range(f.shape[1])]
    masks = {r.id: (f[:, i], np.zeros(len(f), dtype=bool)) for i, r in enumerate(rules)}
    return shapley_attribution(rules, masks, [r.id for r in rules])


@pytest.mark.parametrize('rule_n', range(2, 7))
def test_closed_form_matches_all_permutations(rule_n):
    for seed in range(3):
        f = np.random.default_rng(seed + rule_n * 10).random((13, rule_n)) < .4
        exact = np.zeros(rule_n)
        orderings = list(permutations(range(rule_n)))
        for order in orderings:
            excluded = np.zeros(len(f), dtype=bool)
            for i in order:
                exact[i] += np.count_nonzero(f[:, i] & ~excluded)
                excluded |= f[:, i]
        exact /= len(orderings)
        result = {a.rule_id: a.shapley_value for a in attribute(f)}
        np.testing.assert_allclose([result[f'R{i}'] for i in range(rule_n)], exact, rtol=0, atol=1e-9)


def test_efficiency_and_order_independence():
    rng = np.random.default_rng(42)
    f = rng.random((101, 12)) < .2
    rules = [rule(f'R{i}') for i in range(f.shape[1])]
    masks = {r.id: (f[:, i], np.zeros(len(f), dtype=bool)) for i, r in enumerate(rules)}
    expected = shapley_attribution(rules, masks, [r.id for r in rules])
    for _ in range(5):
        shuffled = [rules[i] for i in rng.permutation(len(rules))]
        assert shapley_attribution(shuffled, masks, [r.id for r in shuffled]) == expected
    assert sum(a.shapley_value for a in expected) == pytest.approx(np.any(f, axis=1).sum(), abs=1e-9)
    assert sum(a.shapley_share_pct for a in expected) == pytest.approx(100)


def test_identical_rules_split_credit_and_disjoint_rule_gets_full_count():
    f = np.array([[1, 1, 0, 0]] * 4 + [[0, 0, 1, 0]] * 2, dtype=bool)
    rows = attribute(f)
    assert [a.rule_id for a in rows] == ['R0', 'R1', 'R2', 'R3']
    assert [a.shapley_value for a in rows] == [2, 2, 2, 0]
    assert [a.unique_n for a in rows] == [0, 0, 2, 0]
    assert [a.total_fail_n for a in rows] == [4, 4, 2, 0]
    assert [(o.rule_id, o.patient_n) for o in rows[0].top_overlaps] == [('R1', 4)]
    assert rows[2].top_overlaps == []


def test_unknowns_never_fail_and_nonmodeled_or_nonapplicable_rules_receive_no_credit():
    rules = [Rule(id='A', kind='inclusion', text='ANC', variable='anc', operator='>=', value=1.5, simulatable=True),
             Rule(id='B', kind='inclusion', text='Platelets', variable='platelets', operator='>=', value=100, simulatable=True),
             rule('UNAVAILABLE'), rule('ADMIN', category='administrative'), rule('PERMISSION', category='permission'),
             Rule(id='UNSUPPORTED', kind='inclusion', text='Not understood')]
    columns = {'anc': np.array([1., None, 2., 1.]), 'platelets': np.array([None, 50., 150., 50.])}
    masks = engine.rule_masks(rules, columns)
    rows = shapley_attribution(rules, masks, ['A', 'B'])
    assert [a.rule_id for a in rows] == ['A', 'B']
    assert [a.shapley_value for a in rows] == [1.5, 1.5]
    assert [a.unique_n for a in rows] == [1, 1]
    assert [a.total_fail_n for a in rows] == [2, 2]
    # Even contradictory incoming masks cannot turn unknowns/admin items into failures.
    bad_masks = {r.id: (np.ones(4, dtype=bool), np.ones(4, dtype=bool)) for r in rules}
    assert all(a.shapley_value == 0 for a in shapley_attribution(rules, bad_masks, [r.id for r in rules]))
    assert {a.rule_id for a in shapley_attribution(rules, bad_masks, [r.id for r in rules])} == {'A', 'B', 'UNAVAILABLE'}


def test_empty_and_zero_exclusion_games_have_defined_results():
    assert shapley_attribution([], {}, []) == []
    assert shapley_attribution([rule('A')], {}, []) == []
    for patient_n in [0, 5]:
        rows = attribute(np.zeros((patient_n, 2), dtype=bool))
        assert len(rows) == 2
        assert all(a.shapley_value == a.shapley_share_pct == a.unique_n == a.total_fail_n == 0 for a in rows)
        assert all(a.top_overlaps == [] for a in rows)


def test_top_overlaps_use_all_rules_and_break_ties_by_id():
    rows = attribute(np.ones((9, 25), dtype=bool))  # not a multiple of 8; packed padding must not count
    last = next(a for a in rows if a.rule_id == 'R24')
    assert [(o.rule_id, o.patient_n) for o in last.top_overlaps] == [('R0', 9), ('R1', 9), ('R10', 9)]
    assert last.shapley_value == pytest.approx(9 / 25)


def test_overlap_counts_are_ranked_by_intersection_then_id():
    rows = attribute(np.array([[1, 1, 1, 0], [1, 1, 0, 1], [1, 1, 0, 0], [1, 0, 0, 0]], dtype=bool))
    first = next(a for a in rows if a.rule_id == 'R0')
    assert [(o.rule_id, o.patient_n) for o in first.top_overlaps] == [('R1', 3), ('R2', 1), ('R3', 1)]


def test_synthea_example_integration_preserves_all_existing_result_fields(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    text = (root / 'frontend/src/exampleProtocol.ts').read_text(encoding='utf-8').split('`')[1]
    rules, _ = parse_eligibility_rules(text)
    info, columns, ids, assumptions = resolve(PopulationChoice())
    result, overall, modeled = engine.evaluate(rules, columns, info, assumptions, ids)
    assert result.attributions
    assert {a.rule_id for a in result.attributions} == set(result.modeled_rule_ids)
    assert result.attribution_total_excluded == result.excluded_n > 0
    assert sum(a.shapley_value for a in result.attributions) == pytest.approx(result.attribution_total_excluded, abs=1e-9)
    assert sum(a.shapley_share_pct for a in result.attributions) == pytest.approx(100)
    reversed_result = engine.evaluate(list(reversed(rules)), columns, info, assumptions, ids)[0]
    assert reversed_result.attributions == result.attributions
    monkeypatch.setattr(engine, 'shapley_attribution', lambda *_: [])
    legacy, legacy_overall, legacy_modeled = engine.evaluate(rules, columns, info, assumptions, ids)
    additions = {'attributions', 'attribution_total_excluded'}
    assert result.model_dump(exclude=additions) == legacy.model_dump(exclude=additions)
    np.testing.assert_array_equal(overall, legacy_overall)
    np.testing.assert_array_equal(modeled, legacy_modeled)
