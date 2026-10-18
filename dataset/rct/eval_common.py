"""Offline dataset construction and identical local/hosted scorer semantics. No network on import."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app import config
from app.responder_agent import aggregate_payload, run_agent, SYSTEM
from app.responder_evidence import read_cases
from app.responder_scoring import parsed_output, score_metric
from app.responder_claims import POLICY_VERSION, contradiction_errors, evidence_label

HERE = Path(__file__).resolve().parent
METRICS = ['correct_flag','no_overclaim','abstains_when_null','planted_recall','number_fidelity',
           'claim_consistency','raw_claim_consistency','legacy_claim_consistency']


def eval_rows(cases):
    rows = []
    for case in cases:
        reliable = sorted((s for s in case.subgroups if evidence_label(s.model_dump())=='weaker_benefit'),key=lambda s:(s.interaction_q,s.id))
        target = next((s for s in reliable if s.id==case.planted_subgroup),None) if case.planted_detectable else None
        reference = target or (reliable[0] if reliable else None)
        for prompt_variant in ['names_only','with_stats']:
            rows.append(dict(case_id=case.case_id,trial=case.trial_key,variant=case.variant,prompt_variant=prompt_variant,
              input_table=json.dumps(aggregate_payload(case,prompt_variant),ensure_ascii=False,sort_keys=True,allow_nan=False),
              truth_flag=reference.id if reference else None,truth_direction=reference.truth_label if reference else 'no_reliable_difference',
              truth_labels=json.dumps({s.id:evidence_label(s.model_dump()) for s in case.subgroups},sort_keys=True),
              any_significant=any(s.truth_label!='no_reliable_difference' for s in case.subgroups),
              planted=case.planted_subgroup is not None,planted_subgroup=case.planted_subgroup,
              planted_detectable=case.planted_detectable))
    return rows


def row_scores(row, output):
    kwargs = {k:row.get(k) for k in ['truth_flag','truth_direction','any_significant','variant','input_table',
              'planted_subgroup','planted_detectable','truth_labels']}
    scores = {name:score_metric(name,output,**kwargs) for name in METRICS if name not in ['raw_claim_consistency','legacy_claim_consistency']}
    scores['raw_claim_consistency'] = score_metric('claim_consistency',row.get('raw_agent_output',output),**kwargs)
    scores['legacy_claim_consistency'] = score_metric('claim_consistency',row.get('legacy_agent_output',output),
      input_table=row.get('legacy_input_table',row['input_table']))
    try:
        json.loads(row.get('raw_agent_output',output),parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        valid = True
    except (ValueError,TypeError): valid = False
    scores['json_valid'] = (float(valid),{'applicable':True})
    return scores


def group_summary(rows):
    summaries = []
    for prompt in ['names_only','with_stats']:
        for planted in [False,True]:
            group = [r for r in rows if r['prompt_variant']==prompt and r['planted']==planted]
            values = {m:[] for m in [*METRICS,'json_valid']}
            for row in group:
                for metric,(score,meta) in row_scores(row,row['agent_output']).items():
                    if meta.get('applicable') and score is not None: values[metric].append(score)
            summaries.append(dict(prompt_variant=prompt,variant='planted' if planted else 'originals',n=len(group),
              scores={k:sum(v)/len(v) if v else None for k,v in values.items()},
              denominators={k:len(v) for k,v in values.items()},
              detectable_planted_n=sum(r.get('planted_detectable') is True for r in group)))
    return summaries


def record_base():
    return dict(ground_truth_sha256=hashlib.sha256((HERE/'ground_truth.jsonl').read_bytes()).hexdigest(),
      model=config.LLM_MODEL,prompt_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(),
      policy_version=POLICY_VERSION,
      recorded_at=datetime.now(timezone.utc).isoformat(),
      limitations=['Exploratory statistical reference labels, not clinical truth; not protocol recommendations.',
        'Undetectable planted targets are retained. Strict planted recall alone cannot establish statistical sensitivity.',
        'No-significant-interaction does not establish equal treatment effects.',
        'Partly non-randomized treatment assignment: weaker evidence (GBSG).',
        'Underpowered groups retain statistical significance but their decision label is no reliable difference.',
        'Claim consistency verifies bounded templates and aggregate policy; it is not a general clinical fact checker.'])


def claim_audit(rows, legacy):
    def inspect(items, output_key, input_key):
        contradictions, unverified = [], []
        for row in items:
            output = parsed_output(row[output_key]); payload = json.loads(row[input_key])
            issues = contradiction_errors(output,payload) if output else ['invalid_output']
            entry = dict(case_id=row['case_id'],prompt_variant=row['prompt_variant'],reasons=issues)
            if issues: contradictions.append(entry)
            score,meta = score_metric('claim_consistency',row[output_key],input_table=row[input_key])
            if not score: unverified.append({**entry,'reasons':meta.get('claim_errors',['invalid_output'])})
        return dict(n=len(items),contradiction_n=len(contradictions),unverified_n=len(unverified),
                    contradictions=contradictions)
    return dict(policy_version=POLICY_VERSION,
      note='Legacy responses are rescored retrospectively; unverified free prose is not counted as a proven contradiction. Flag accuracy is not directly comparable after the underpower policy change.',
      before=inspect(legacy,'agent_output','input_table'),raw_after=inspect(rows,'raw_agent_output','input_table'),
      guarded_after=inspect(rows,'agent_output','input_table'),
      template_fallback_n=sum(row['guard_applied'] for row in rows))


def local_evaluation():
    cases = read_cases(); by_case = {case.case_id:case for case in cases}
    rows = eval_rows(cases)
    baseline_path = HERE/'local_eval_results.before_claims.json'
    legacy = json.loads(baseline_path.read_text())['cases'] if baseline_path.exists() else []
    legacy_by_key = {(row['case_id'],row['prompt_variant']):row for row in legacy}
    # Identical blind names-only inputs reuse one call, not truth/variant-specific answers.
    unique = {row['input_table']:row for row in rows}
    def evaluate(row):
        output = run_agent(by_case[row['case_id']],row['prompt_variant'])
        served = output.model_dump_json(include={'flag','direction','confidence','rationale','invalid'})
        raw = output.raw_output or served
        return row['input_table'],dict(agent_output=served,raw_agent_output=raw,
          guard_applied=output.used_template,claim_issues=json.dumps(output.claim_issues))
    with ThreadPoolExecutor(max_workers=3) as executor:
        outputs = dict(executor.map(evaluate,unique.values()))
    for row in rows:
        row.update(outputs[row['input_table']])
        previous = legacy_by_key.get((row['case_id'],row['prompt_variant']))
        row['legacy_agent_output'] = previous['agent_output'] if previous else row['raw_agent_output']
        row['legacy_input_table'] = previous['input_table'] if previous else row['input_table']
    result = {**record_base(),'status':'local_only','mode':'local_agent_local_scoring','runs':group_summary(rows),'cases':rows,
      'invalid_outputs':sum(parsed_output(r['agent_output']) is None for r in rows),
      'claim_audit':claim_audit(rows,legacy)}
    (HERE/'local_eval_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    (HERE/'claim_consistency_before_after.json').write_text(json.dumps(result['claim_audit'],indent=2)+'\n')
    return result


if __name__ == '__main__':
    result = local_evaluation()
    for group in result['runs']:
        print(group['prompt_variant'],group['variant'],group['scores'],flush=True)
