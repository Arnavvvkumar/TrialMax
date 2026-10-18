"""Serve versioned, precomputed historical evidence separately from the active trial."""
import hashlib
import json

from .responder_agent import run_agent
from .responder_models import ResponderResponse, TrialEvidence
from .responder_truth import RCT_DIR
from . import config
from .responder_agent import SYSTEM


def read_cases():
    path = RCT_DIR/'ground_truth.jsonl'
    if not path.exists(): raise ValueError('Historical evidence snapshot is missing; run the responder ground-truth builder.')
    return [TrialEvidence.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def evaluation_summary():
    path = RCT_DIR/'chalk_runs.json'
    data = json.loads(path.read_text()) if path.exists() else {'status':'not_run','runs':[],'message':'No completed Chalk evaluation runs recorded.'}
    local = RCT_DIR/'local_eval_results.json'
    if data.get('status') != 'complete' and local.exists():
        data = {**json.loads(local.read_text()),'hosted_status':data.get('status'),'message':data.get('message','Hosted validation is pending.')}
    truth_path = RCT_DIR/'ground_truth.jsonl'
    current = hashlib.sha256(truth_path.read_bytes()).hexdigest() if truth_path.exists() else None
    if data.get('ground_truth_sha256') != current:
        return {'status':'stale','runs':[],'message':'Evaluation records do not match this ground-truth snapshot. Rerun evaluation.'}
    if data.get('model') != config.LLM_MODEL or data.get('prompt_sha256') != hashlib.sha256(SYSTEM.encode()).hexdigest():
        return {'status':'stale','runs':[],'message':'Evaluation records use a different model or prompt. Rerun evaluation.'}
    # The API needs summaries, not the full evaluation dataset or raw model outputs.
    return {key:value for key,value in data.items() if key != 'cases'}


def responder_evidence(trial_key: str) -> ResponderResponse:
    evidence = next((row for row in read_cases() if row.trial_key==trial_key and row.variant=='original'),None)
    if evidence is None: raise ValueError('Historical trial not found')
    csv = RCT_DIR/f'{trial_key}.csv'
    if hashlib.sha256(csv.read_bytes()).hexdigest() != evidence.provenance.get('sha256'):
        raise ValueError('Historical snapshot changed; rebuild ground truth before using this panel.')
    return ResponderResponse(evidence=evidence,suggestion=run_agent(evidence),evaluations=evaluation_summary(),disclaimers=evidence.disclaimers)
