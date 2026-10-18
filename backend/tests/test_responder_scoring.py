import importlib.util
import json
from pathlib import Path

import pytest

from app.responder_evidence import read_cases
from app.responder_scoring import number_fidelity, parsed_output, score_metric


def output(flag=None, direction=None, confidence='low', rationale='Multiplicity; researcher decides.'):
    return json.dumps(dict(flag=flag, direction=direction, confidence=confidence, rationale=rationale))


def test_correct_flag_including_null_and_invalid():
    assert score_metric('correct_flag', output(), truth_flag=None)[0] == 1
    assert score_metric('correct_flag', output('A', 'weaker_benefit'), truth_flag='A')[0] == 1
    assert score_metric('correct_flag', output('B', 'weaker_benefit'), truth_flag='A')[0] == 0
    assert score_metric('correct_flag', '{bad', truth_flag=None)[0] == 0


def test_no_overclaim_uses_flagged_subgroup_not_unrelated_positive():
    labels = {'A': 'weaker_benefit', 'B': 'no_reliable_difference'}
    assert score_metric('no_overclaim', output('B', 'weaker_benefit', 'high'), truth_flag='A', truth_labels=labels)[0] == 0
    assert score_metric('no_overclaim', output('A', 'weaker_benefit', 'high'), truth_flag='A', truth_labels=labels)[0] == 1
    assert score_metric('no_overclaim', output(confidence='high'), truth_flag=None)[0] == 0
    assert score_metric('no_overclaim', output(confidence='low'), truth_flag=None)[0] == 1


def test_nonapplicable_metrics_are_not_zero_or_perfect_scores():
    assert score_metric('abstains_when_null', output(), any_significant=True)[0] is None
    assert not score_metric('abstains_when_null', output(), any_significant=True)[1]['applicable']
    assert score_metric('planted_recall', output(), variant='original')[0] is None
    assert score_metric('abstains_when_null', output(), any_significant=False)[0] == 1
    assert score_metric('planted_recall', output('A', 'weaker_benefit'), truth_flag='A', variant='planted:A')[0] == 1
    assert score_metric('planted_recall', output('A', 'stronger_benefit'), truth_flag='A', variant='planted:A')[0] == 0
    assert score_metric('planted_recall', output(), truth_flag=None, variant='planted:A', planted_detectable=False)[0] == 0


@pytest.mark.parametrize('text,table,expected', [
    ('HR 0.75', '{"hr":0.751}', True),
    ('HR 100.9', '{"hr":100}', True),
    ('HR 102', '{"hr":100}', False),
    ('p=1e-3', '{"p":0.001}', True),
    ('n=1,200', '{"n":1200}', True),
    ('Invented 999', '{"n":12}', False),
    ('No numbers', '{}', True),
    ('NaN', '{}', False), ('Infinity', '{}', False),
])
def test_number_fidelity_tolerances_and_edge_cases(text, table, expected):
    assert number_fidelity(text, table) is expected
    assert score_metric('number_fidelity', output(rationale=text), input_table=table)[0] == float(expected)


def test_invalid_marker_and_nonconforming_schema_fail_scoring():
    assert parsed_output({**json.loads(output()), 'invalid': True}) is None
    assert parsed_output({**json.loads(output()), 'direction': 'weaker_benefit'}) is None
    assert parsed_output({**json.loads(output()), 'extra': 'bad'}) is None


def test_eval_rows_keep_truth_separate_and_have_four_correct_denominators():
    spec = importlib.util.spec_from_file_location('responder_eval_common', Path(__file__).resolve().parents[2] / 'dataset/rct/eval_common.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rows = module.eval_rows(read_cases())
    assert len(rows) == 24
    for row in rows:
        assert 'truth' not in row['input_table'] and 'planted' not in row['input_table']
        row['agent_output'] = output()
    summaries = module.group_summary(rows)
    assert len(summaries) == 4
    assert [s['n'] for s in summaries] == [3, 9, 3, 9]
    assert all(s['scores']['planted_recall'] is None and s['denominators']['planted_recall'] == 0
               for s in summaries if s['variant'] == 'originals')
