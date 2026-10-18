"""Pure, portable evaluation metrics; importable in tests without Chalk or network."""
import json
import math
import re

try:  # Also shipped as two pure modules in the hosted scorer image.
    from .responder_claims import claim_errors
except ImportError:
    from responder_claims import claim_errors

NUMBER = re.compile(r'(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')


def parsed_output(raw):
    try:
        value = json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(value,dict) or value.get('invalid'):
            return None
        if not {'flag','direction','confidence','rationale'} <= set(value): return None
        if set(value) - {'flag','direction','confidence','rationale','invalid','source','raw_output','used_template','claim_issues'}:
            return None
        if value.get('flag') is not None and not isinstance(value['flag'],str): return None
        if value.get('confidence') not in ['low','medium','high']: return None
        if value.get('direction') not in [None,'weaker_benefit','stronger_benefit']: return None
        if (value.get('flag') is None) != (value.get('direction') is None): return None
        if not isinstance(value.get('rationale'),str) or len(value['rationale']) > 400: return None
        return value
    except (ValueError,TypeError):
        return None


def number_fidelity(rationale: str, input_table: str) -> bool:
    if re.search(r'\b(?:nan|infinity|inf)\b',rationale,re.I): return False
    clean = lambda text: re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',text)
    supplied = [float(n) for n in NUMBER.findall(clean(input_table))]
    return all(math.isfinite(float(n)) and any(abs(float(n)-given) <= max(.0100000001,.01*abs(given)) for given in supplied)
               for n in NUMBER.findall(clean(rationale)))


def score_metric(name, output, *, truth_flag=None, truth_direction='no_reliable_difference',
                 any_significant=False, variant='original', input_table='{}', planted_subgroup=None,
                 planted_detectable=None,truth_labels='{}'):
    parsed = parsed_output(output)
    metadata = {'applicable':True, 'invalid':parsed is None}
    if name == 'planted_recall' and not variant.startswith('planted:'):
        return None, {**metadata,'applicable':False,'reason':'Original case; exclude from recall denominator.'}
    if name == 'abstains_when_null' and any_significant:
        return None, {**metadata,'applicable':False,'reason':'Interaction present; exclude from null-abstention denominator.'}
    if parsed is None: return 0.0,metadata
    flag = parsed['flag']
    if name == 'correct_flag': value = flag == truth_flag
    elif name == 'no_overclaim':
        labels = json.loads(truth_labels) if isinstance(truth_labels,str) else truth_labels
        unreliable = truth_flag is None or (flag is not None and labels.get(flag,'no_reliable_difference')=='no_reliable_difference')
        value = not (parsed['confidence']=='high' and unreliable)
    elif name == 'abstains_when_null': value = flag is None
    elif name == 'planted_recall':
        target = truth_flag
        value = flag == target and parsed['direction']=='weaker_benefit'
        metadata['planted_detectable'] = planted_detectable
    elif name == 'number_fidelity': value = number_fidelity(parsed['rationale'],input_table)
    elif name == 'claim_consistency':
        try:
            payload = json.loads(input_table) if isinstance(input_table,str) else input_table
            errors = claim_errors(parsed,payload)
        except (ValueError,TypeError,KeyError): errors = ['invalid_input_table']
        metadata['claim_errors'] = errors
        value = not errors
    else: raise ValueError('Unknown responder metric')
    return float(value), metadata
