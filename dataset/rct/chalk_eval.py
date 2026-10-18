"""Four hosted responder evaluations. Authenticate with chalk login; set CHALK_ENVIRONMENT.

The remote probe uses ambient remote credentials only. Never upload the local router
key to the evaluation environment. Local aggregate-only inference is the fallback.
"""
import json
import os
from pathlib import Path

# Decorators deploy eagerly. Authenticate (or write the local fallback) before
# importing/declaring any hosted function when this file is run as a script.
if __name__ == '__main__' and not os.environ.get('CHALK_REMOTE_FUNCTION'):
    import sys
    from eval_common import local_evaluation
    if '--local-only' in sys.argv:
        local_evaluation()
        print('Mode: local agent + local scorers (no hosted validation claimed)')
        raise SystemExit(0)
    try:
        from chalk.client import ChalkClient
        environment = os.environ.get('CHALK_ENVIRONMENT')
        if not environment: raise ValueError('Missing hosted environment')
        ChalkClient(environment=environment).whoami()
    except Exception:
        local = local_evaluation()
        failure = {key:value for key,value in local.items() if key != 'cases'}
        failure.update(status='incomplete',message='Chalk authentication or environment missing. Run chalk login and set CHALK_ENVIRONMENT; local results are available.')
        (Path(__file__).resolve().parent/'chalk_runs.json').write_text(json.dumps(failure,indent=2)+'\n')
        print(failure['message'])
        raise SystemExit(1)

import chalkcompute
from chalkcompute import EvaluationScorerResult

HERE = Path(__file__).resolve().parent
# Package exactly the pure scorer source. No .env, credentials, patient CSVs or truth files.
SCORER_IMAGE = None
if not os.environ.get('CHALK_REMOTE_FUNCTION'):
    SCORER_IMAGE = (chalkcompute.Image.debian_slim('3.12').pip_install(['chalkcompute==2.13.7'])
        .add_local_file(str(HERE.parents[1]/'backend/app/responder_scoring.py'),'/opt/responder/responder_scoring.py',strategy='copy')
        .env({'PYTHONPATH':'/opt/responder'}))

# Build a remote agent only after a successful ambient-credential probe. Source
# files are explicitly listed; never package the repo, .env or CSVs.
REMOTE_MODE = False
AGENT_IMAGE = None
if not os.environ.get('CHALK_REMOTE_FUNCTION') and (HERE/'chalk_probe.json').exists():
    REMOTE_MODE = json.loads((HERE/'chalk_probe.json').read_text()).get('gateway_probe',{}).get('gateway_callable',False)
    if REMOTE_MODE:
        import sys
        sys.path.insert(0,str(HERE.parents[1]/'backend'))
        from app import config
        AGENT_IMAGE = chalkcompute.Image.debian_slim('3.12').pip_install(
            ['chalkcompute==2.13.7','openai','pydantic>=2,<3','python-dotenv'])
        for name in ['__init__','config','models','variables','llm','responder_models','responder_scoring','responder_agent']:
            AGENT_IMAGE = AGENT_IMAGE.add_local_file(str(HERE.parents[1]/f'backend/app/{name}.py'),f'/opt/responder/app/{name}.py',strategy='copy')
        AGENT_IMAGE = AGENT_IMAGE.env({'LLM_MODEL':config.LLM_MODEL,'CHALK_ENV_ID':config.CHALK_ENV_ID,
                                      'CHALK_BASE_URL':config.CHALK_BASE_URL,'WT_CACHE_DIR':'/tmp/responder-cache'})


if REMOTE_MODE or os.environ.get('CHALK_REMOTE_FUNCTION'):
    @chalkcompute.function(authenticated=True,image=AGENT_IMAGE)
    def responder_remote(input_table: str) -> str:
        import json
        import sys
        sys.path.insert(0,'/opt/responder')
        from app.responder_agent import run_payload
        output = run_payload(json.loads(input_table),use_cache=False)
        return output.raw_output if output.raw_output else output.model_dump_json(exclude={'raw_output','source'})


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def responder_passthrough(agent_output: str) -> str:
    return agent_output


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def correct_flag(output: str, truth_flag: str | None) -> EvaluationScorerResult:
    import sys
    sys.path.insert(0,'/opt/responder')
    from responder_scoring import score_metric
    from chalkcompute import EvaluationScorerResult
    score,metadata = score_metric('correct_flag',output,truth_flag=truth_flag)
    return EvaluationScorerResult(score,metadata)


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def no_overclaim(output: str, truth_flag: str | None, truth_labels: str) -> EvaluationScorerResult:
    import sys
    sys.path.insert(0,'/opt/responder')
    from responder_scoring import score_metric
    from chalkcompute import EvaluationScorerResult
    score,metadata = score_metric('no_overclaim',output,truth_flag=truth_flag,truth_labels=truth_labels)
    return EvaluationScorerResult(score,metadata)


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def abstains_when_null(output: str, any_significant: bool) -> list[EvaluationScorerResult]:
    import sys
    sys.path.insert(0,'/opt/responder')
    from responder_scoring import score_metric
    from chalkcompute import EvaluationScorerResult
    score,metadata = score_metric('abstains_when_null',output,any_significant=any_significant)
    return [] if score is None else [EvaluationScorerResult(score,metadata)]


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def planted_recall(output: str, variant: str, truth_flag: str | None, planted_detectable: bool | None) -> list[EvaluationScorerResult]:
    import sys
    sys.path.insert(0,'/opt/responder')
    from responder_scoring import score_metric
    from chalkcompute import EvaluationScorerResult
    score,metadata = score_metric('planted_recall',output,variant=variant,truth_flag=truth_flag,planted_detectable=planted_detectable)
    return [] if score is None else [EvaluationScorerResult(score,metadata)]


@chalkcompute.function(authenticated=True,image=SCORER_IMAGE)
def number_fidelity(output: str, input_table: str) -> EvaluationScorerResult:
    import sys
    sys.path.insert(0,'/opt/responder')
    from responder_scoring import score_metric
    from chalkcompute import EvaluationScorerResult
    score,metadata = score_metric('number_fidelity',output,input_table=input_table)
    return EvaluationScorerResult(score,metadata)


valid_json = chalkcompute.scorers.json_valid(name='json-valid',image=SCORER_IMAGE,authenticated=True)


def main():
    import argparse
    from chalk.client import ChalkClient
    from chalk_transport import UploadTransport
    from eval_common import local_evaluation, record_base
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-only',action='store_true')
    args = parser.parse_args()
    # Preserve a local audit even if auth, remote functions or storage are unavailable.
    local = local_evaluation()
    if args.local_only:
        print('Mode: local agent + local scorers (no hosted validation claimed)'); return
    record = {**record_base(),'status':'pending','mode':'local_agent_remote_scoring','runs':[]}
    stage = 'authentication'
    try:
        environment = os.environ.get('CHALK_ENVIRONMENT')
        if not environment: raise ValueError('CHALK_ENVIRONMENT is required for hosted evaluations')
        record['environment'] = environment
        client = ChalkClient(environment=environment); client.whoami()
        probe_path = HERE/'chalk_probe.json'
        if not probe_path.exists(): raise ValueError('Run chalk_probe.py before the full evaluation')
        probe = json.loads(probe_path.read_text())
        record['gateway_probe'] = probe.get('gateway_probe')
        if probe.get('environment') != environment or 'SUCCEEDED' not in probe.get('status',''):
            raise ValueError('Tiny hosted evaluation has not succeeded in this environment')
        task = responder_passthrough
        if REMOTE_MODE:
            task = responder_remote
            record['mode'] = 'remote_agent_remote_scoring'
            print('Mode: hosted aggregate-only agent and Chalk scorers; ambient remote gateway probe passed.',flush=True)
        else:
            print('Mode: local aggregate-only agent + hosted Chalk passthrough/scorers. Remote gateway had no ambient credentials.',flush=True)
        datasets = chalkcompute.DatasetClient(chalk_client=client,http_client=UploadTransport())
        for summary in local['runs']:
            group = [r for r in local['cases'] if r['prompt_variant']==summary['prompt_variant'] and r['planted']==(summary['variant']=='planted')]
            stage = 'dataset upload'
            dataset = datasets.upload('responder-rct-eval',group,timeout=30)
            name = f"responder-{summary['prompt_variant']}-{summary['variant']}"
            stage = 'evaluation creation'
            evaluation = chalkcompute.Evaluation.create(name,dataset=dataset,task=task,
              scorers=[correct_flag,no_overclaim,abstains_when_null,planted_recall,number_fidelity,valid_json],chalk_client=client)
            stage = 'evaluation run'
            run = evaluation.run(metadata={'prompt_variant':summary['prompt_variant'],'variant':summary['variant'],
              'mode':record['mode'],'ground_truth_sha256':record['ground_truth_sha256'],'model':record['model']})
            print('Started',name,run.id,flush=True)
            run = run.wait(timeout=240,poll_interval=3)
            # Read actual scorer outputs: never label local-only metrics as hosted results.
            stage = 'result read'
            scored = datasets.read(run.result_dataset,timeout=30).to_pylist()
            if any(value for row in scored for key,value in row.items() if key.endswith('_error')):
                raise RuntimeError('Hosted task/scorer errors; scores must not be reported as validated')
            scores,denominators = {},{}
            for index,metric in enumerate(['correct_flag','no_overclaim','abstains_when_null','planted_recall','number_fidelity','json_valid']):
                values = []
                for row in scored:
                    value = row.get(f'{metric}_value',row.get(f"{metric.replace('_','-')}_value",
                        row.get(f'scorer_{evaluation.scorers[index].id}')))
                    if isinstance(value,list): values.extend(float(v.get('score',v)) if isinstance(v,dict) else float(v) for v in value)
                    elif isinstance(value,dict): values.append(float(value.get('score')))
                    elif value is not None: values.append(float(value))
                scores[metric] = sum(values)/len(values) if values else None
                denominators[metric] = len(values)
            if not REMOTE_MODE and (denominators != summary['denominators'] or any(scores[m] != summary['scores'][m] for m in scores)):
                raise RuntimeError('Hosted and local scorer outputs disagree')
            item = {**summary,'scores':scores,'denominators':denominators,'evaluation_id':evaluation.id,'run_id':run.id,'status':str(run.status)}
            record['runs'].append(item)
            (HERE/'chalk_runs.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
            print(name,run.id,str(run.status),scores,flush=True)
        record['status'] = 'complete'
    except Exception as exc:
        record['status'] = 'incomplete'
        record['message'] = 'Hosted evaluation did not complete. Local results are available; no hosted validation claimed.'
        record['error_category'] = type(exc).__name__
        record['error_stage'] = stage
        import traceback
        record['error_locations'] = [f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(exc.__traceback__)]
        print('Hosted evaluation incomplete:',type(exc).__name__,stage, record['error_locations'], 'See local_eval_results.json; credentials and provider details are not logged.',flush=True)
    (HERE/'chalk_runs.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return 0 if record['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
