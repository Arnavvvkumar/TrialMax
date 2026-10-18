"""Tiny hosted evaluation and remote gateway check; uses Chalk CLI login, never uploads local secrets."""
import json
import os
from pathlib import Path

import chalkcompute
from chalkcompute import EvaluationScorerResult


@chalkcompute.function(authenticated=True)
def responder_smoke_task(agent_output: str) -> str:
    return agent_output


@chalkcompute.function(authenticated=True)
def responder_smoke_score(output: str) -> EvaluationScorerResult:
    import json
    from chalkcompute import EvaluationScorerResult
    return EvaluationScorerResult(float(json.loads(output).get('ok') is True), {'probe':True})


@chalkcompute.function(authenticated=True)
def responder_gateway_probe(base_url: str, env_id: str, model: str) -> str:
    import json, os, urllib.request, urllib.error
    key = os.getenv('CHALK_ROUTER_API_KEY','')
    headers = {'Content-Type':'application/json','X-Chalk-Env-Id':env_id}
    if key: headers['Authorization'] = 'Bearer '+key
    request = urllib.request.Request(base_url.rstrip('/')+'/chat/completions',
      data=json.dumps({'model':model,'messages':[{'role':'user','content':'Reply OK.'}],'max_completion_tokens':32}).encode(),headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=10) as response:
            payload = json.load(response)
            success = bool(payload.get('choices'))
        return json.dumps({'gateway_callable':success,'status':200,'credential_available':bool(key)})
    except urllib.error.HTTPError as exc:
        return json.dumps({'gateway_callable':False,'status':exc.code,'credential_available':bool(key)})
    except Exception:
        return json.dumps({'gateway_callable':False,'status':None,'credential_available':bool(key)})


if __name__ == '__main__':
    import sys
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'backend'))
    from app import config
    from chalk.client import ChalkClient
    from chalk_transport import UploadTransport
    environment = os.environ.get('CHALK_ENVIRONMENT')
    if not environment: raise SystemExit('Set CHALK_ENVIRONMENT to the hosted-evaluation environment, separate from CHALK_ENV_ID.')
    client = ChalkClient(environment=environment)
    client.whoami()
    probe = json.loads(responder_gateway_probe.remote(base_url=config.CHALK_BASE_URL,env_id=config.CHALK_ENV_ID,model=config.LLM_MODEL))
    print('Remote gateway check:',probe,flush=True)
    record = dict(environment=environment,status='pending',gateway_probe=probe)
    try:
        datasets = chalkcompute.DatasetClient(chalk_client=client,http_client=UploadTransport())
        dataset = datasets.upload('responder-rct-smoke',[{'agent_output':'{"ok":true}'}],timeout=30)
        evaluation = chalkcompute.Evaluation.create('responder-rct-smoke',dataset=dataset,task=responder_smoke_task,
          scorers=[responder_smoke_score],chalk_client=client)
        run = evaluation.run(metadata={'purpose':'responder-preflight'}).wait(timeout=180,poll_interval=3)
        print('Tiny evaluation:',run.status,flush=True)
        record.update(evaluation_id=evaluation.id,run_id=run.id,status=str(run.status))
    except Exception as exc:
        record.update(status='failed',error_category=type(exc).__name__)
        print('Tiny evaluation failed:',type(exc).__name__,flush=True)
    (Path(__file__).parent/'chalk_probe.json').write_text(json.dumps(record,indent=2)+'\n')
