import json
from unittest.mock import Mock

import pytest

from app import config, llm, responder_agent as agent
from app.responder_claims import claim_errors, contradiction_errors, evidence_label, significant, template_rationale
from app.responder_evidence import read_cases
from app.responder_scoring import score_metric


def veteran():
    return next(c for c in read_cases() if c.case_id=='veteran')


def suggestion(rationale, flag=None, direction=None):
    return dict(flag=flag,direction=direction,confidence='low',rationale=rationale)


@pytest.mark.parametrize('rationale',[
    'Treatment-by-subgroup interactions do not survive multiplicity correction. A researcher must decide.',
    'No interactions survive multiplicity correction; a researcher must decide.',
    'Nothing survives multiplicity correction; a researcher must decide.',
    'No subgroup is BH-significant; multiplicity considered; a researcher decides.',
])
def test_blanket_negative_is_rejected_even_when_significant_group_is_underpowered(rationale):
    payload = agent.aggregate_payload(veteran())
    errors = contradiction_errors(suggestion(rationale),payload)
    assert 'denied_existing_bh_significance' in errors
    assert score_metric('claim_consistency',json.dumps(suggestion(rationale)),input_table=json.dumps(payload))[0]==0


def test_verbatim_veteran_regression_is_corrected_and_raw_output_retained(monkeypatch,tmp_path):
    payload = agent.aggregate_payload(veteran())
    raw = json.dumps(suggestion('No subgroup warrants an efficacy-based exclusion: treatment-by-subgroup interactions do not survive multiplicity correction, and most subgroups are underpowered. Nominal stronger-benefit signals are not grounds for exclusion. A researcher must decide.'))
    monkeypatch.setattr(config,'CACHE_DIR',tmp_path)
    monkeypatch.setattr(config,'llm_configured',lambda:True)
    client=Mock(); client.with_options.return_value=client
    monkeypatch.setattr(llm,'_client',lambda:client)
    call=Mock(return_value=raw); monkeypatch.setattr(llm,'call_model',call)
    result=agent.run_agent(veteran())
    assert result.raw_output==raw and result.used_template
    assert 'denied_existing_bh_significance' in result.claim_issues
    assert 'every significant subgroup is underpowered' in result.rationale
    assert result.flag is None and result.confidence=='low'
    assert claim_errors(result.model_dump(),payload)==[]
    assert agent.run_agent(veteran())==result and call.call_count==1


@pytest.mark.parametrize('q,expected',[(.10,True),(.10001,False),(.099,True),(None,False),(float('nan'),False),(-.1,False)])
def test_cutoff_boundary(q,expected):
    assert significant({'q_value':q}) is expected


def test_underpowered_policy_and_direction_rejection():
    row=dict(id='A',label='Group A',q_value=.05,hr_in=.9,hr_out=.5,underpowered=False)
    assert evidence_label(row)=='weaker_benefit'
    payload=dict(prompt_variant='with_stats',subgroups=[row])
    wrong=suggestion(template_rationale(payload,'A','stronger_benefit'),'A','stronger_benefit')
    assert 'wrong_flag_direction' in claim_errors(wrong,payload)
    right=suggestion(template_rationale(payload,'A','weaker_benefit'),'A','weaker_benefit')
    assert claim_errors(right,payload)==[]
    row['underpowered']=True
    assert evidence_label(row)=='no_reliable_difference'
    assert 'flagged_underpowered_subgroup' in claim_errors(right,payload)


def test_wrong_named_direction_and_unrecognized_prose_fail_closed():
    row=dict(id='A',label='Group A',q_value=.05,hr_in=.9,hr_out=.5,underpowered=False)
    payload=dict(prompt_variant='with_stats',subgroups=[row])
    output=suggestion('Group A shows stronger benefit after multiplicity correction; a researcher decides.')
    assert 'wrong_named_subgroup_direction' in claim_errors(output,payload)
    output=suggestion('This beautiful treatment will cure everyone; multiplicity; researcher.')
    assert claim_errors(output,payload)==['unverified_free_prose']


def test_names_only_has_no_outcome_claim_and_never_flags():
    payload=agent.aggregate_payload(veteran(),'names_only')
    assert all(set(row)=={'id','label','n'} for row in payload['subgroups'])
    assert set(payload['rationale_options'])=={'abstain'}
    assert claim_errors(suggestion(template_rationale(payload)),payload)==[]
    output=suggestion('Multiplicity corrected; researcher decides.','cell_squamous','stronger_benefit')
    assert 'flag_without_effect_statistics' in claim_errors(output,payload)


def test_every_context_template_is_bounded_and_scores_consistently():
    for case in read_cases():
        for variant in ['names_only','with_stats']:
            payload=agent.aggregate_payload(case,variant)
            text=template_rationale(payload)
            assert len(text)<=400
            output=json.dumps(suggestion(text))
            score,meta=score_metric('claim_consistency',output,input_table=json.dumps(payload))
            assert score==1 and meta['claim_errors']==[]
