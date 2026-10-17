"""Generate a reproducible, fully synthetic oncology trial pre-screening cohort.
No real patient records, identities, or epidemiologic estimates are used.
Run: python3 generate_patients.py
"""
import csv
import json
import random
from pathlib import Path

SEED = 20261016
SIZE = 500
R = random.Random(SEED)
OUT = Path(__file__).resolve().parent

FIELDS = [
    'patient_id','synthetic','cohort','age_years','sex_at_birth','ecog_score',
    'egfr_mutation','alk_rearrangement','hemoglobin_g_dl','anc_cells_ul',
    'platelets_cells_ul','egfr_kidney_ml_min_1_73m2','ast_u_l','alt_u_l',
    'prior_systemic_therapy_lines','brain_metastases','active_infection',
    'data_version'
]

def missing(value, chance=0.06):
    return None if R.random() < chance else value

def maybe_lab(low, high, digits=0):
    n = R.uniform(low, high)
    return int(round(n)) if digits == 0 else round(n, digits)

def generate_one(i):
    # Purely invented distributions, tuned for interactive exclusion demos.
    # They are NOT clinical reference distributions or prevalence estimates.
    egfr = R.choices(['positive','negative','unknown'], weights=[26,68,6])[0]
    alk = R.choices(['positive','negative','unknown'], weights=[7,86,7])[0]
    return {
        'patient_id': f'SYN-{i:04d}',
        'synthetic': True,
        'cohort': 'FICTIONAL_NSCLC_PRE_SCREEN',
        'age_years': missing(R.randint(18, 85), .02),
        'sex_at_birth': R.choice(['female','male','unknown']),
        'ecog_score': missing(R.choices([0,1,2,3,4], weights=[15,38,27,15,5])[0], .05),
        'egfr_mutation': egfr,
        'alk_rearrangement': alk,
        'hemoglobin_g_dl': missing(maybe_lab(8.0,16.0,1)),
        'anc_cells_ul': missing(maybe_lab(700,6500)),
        'platelets_cells_ul': missing(maybe_lab(60000,400000)),
        'egfr_kidney_ml_min_1_73m2': missing(maybe_lab(25,120)),
        'ast_u_l': missing(maybe_lab(12,120)),
        'alt_u_l': missing(maybe_lab(12,140)),
        'prior_systemic_therapy_lines': missing(R.randint(0,4)),
        'brain_metastases': missing(R.choice([True,False])),
        'active_infection': missing(R.choices([True,False],weights=[12,88])[0]),
        'data_version': 'synthetic-v1'
    }

patients=[generate_one(i) for i in range(1,SIZE+1)]
with (OUT/'patients.json').open('w') as f:
    json.dump(patients, f, indent=2)
with (OUT/'patients.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    for p in patients:
        writer.writerow({k: '' if p[k] is None else p[k] for k in FIELDS})

# The demo uses a fixed subset of simple, explicitly illustrative criteria.
criteria = [
    {'id':'C1','field':'age_years','operator':'>=','value':18,'unit':'years','purpose':'minimum age','review_required':False},
    {'id':'C2','field':'ecog_score','operator':'<=','value':1,'unit':'ECOG','purpose':'performance status','review_required':True},
    {'id':'C3','field':'egfr_mutation','operator':'==','value':'positive','unit':None,'purpose':'biomarker enrichment','review_required':True},
    {'id':'C4','field':'anc_cells_ul','operator':'>=','value':1500,'unit':'cells/uL','purpose':'hematologic adequacy','review_required':True},
    {'id':'C5','field':'platelets_cells_ul','operator':'>=','value':100000,'unit':'cells/uL','purpose':'hematologic adequacy','review_required':True},
    {'id':'C6','field':'egfr_kidney_ml_min_1_73m2','operator':'>=','value':60,'unit':'mL/min/1.73m²','purpose':'renal function','review_required':True},
]
with (OUT/'demo_criteria.json').open('w') as f:
    json.dump({'trial_id':'SYNTHETIC-DEMO','not_real_protocol':True,'criteria':criteria},f,indent=2,ensure_ascii=False)

# Three-state evaluation, to avoid misclassifying missing data as pass.
def eval_criterion(patient, criterion):
    value = patient[criterion['field']]
    if value is None or value == 'unknown':
        return 'unknown'
    op,threshold=criterion['operator'], criterion['value']
    result={'==':lambda a,b:a==b,'>=':lambda a,b:a>=b,'<=':lambda a,b:a<=b}[op](value,threshold)
    return 'pass' if result else 'fail'

status_counts={'eligible':0,'excluded':0,'unknown':0}
per_criterion={c['id']:{'pass':0,'fail':0,'unknown':0} for c in criteria}
for patient in patients:
    outcomes=[eval_criterion(patient,c) for c in criteria]
    for c, result in zip(criteria,outcomes):
        per_criterion[c['id']][result] += 1
    status='excluded' if 'fail' in outcomes else 'unknown' if 'unknown' in outcomes else 'eligible'
    status_counts[status]+=1
with (OUT/'demo_validation.json').open('w') as f:
    json.dump({'seed':SEED,'population':SIZE,'patient_status_counts':status_counts,'per_criterion':per_criterion},f,indent=2)

assert len(patients)==SIZE
assert len(set(p['patient_id'] for p in patients))==SIZE
assert sum(status_counts.values())==SIZE
assert all(p['synthetic'] is True for p in patients)
print('Generated:',SIZE,'patients; statuses:',status_counts)
