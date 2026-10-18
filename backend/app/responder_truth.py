"""Prespecified, unadjusted Cox interaction reference labels; no AI or outcome predictions."""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .responder_models import ArmCounts, Effect, SubgroupEvidence, TrialEvidence

RCT_DIR = Path(__file__).resolve().parents[2] / 'dataset' / 'rct'
GBSG_WARNING = 'Partly non-randomized treatment assignment: weaker evidence.'
DISCLAIMERS = [
    'Old randomized trials used to validate the method; subgroup findings are exploratory; researcher decides.',
    'Statistical reference labels are not biological ground truth or recommendations to exclude patients.',
    'Efficacy evidence only; no assessment of treatment safety. No automatic protocol edits.',
    'Unadjusted proportional-hazards models assume proportional hazards; missing subgroup values are excluded from both subgroup arms and their complement.',
    'Benjamini-Hochberg correction at q = 0.10 is within each trial/variant; correlated subgroups, small samples and repeated exploration limit inference.',
]
TRIALS = {
    'colon': dict(name='Colon adjuvant chemotherapy', treatment='Lev+5FU', control='Obs', endpoint='Overall survival (death)',
                  citation='Moertel et al. NEJM 1990;322:352-358. doi:10.1056/NEJM199002083220602; R survival package colon data.',
                  publication_url='https://pubmed.ncbi.nlm.nih.gov/2300087/'),
    'veteran': dict(name="Veterans Administration lung cancer", treatment='Test regimen (trt=2)', control='Standard regimen (trt=1)', endpoint='Overall survival (death)',
                    citation='Kalbfleisch and Prentice (1980), The Statistical Analysis of Failure Time Data; R survival package veteran data.',
                    publication_url='https://vincentarelbundock.github.io/Rdatasets/doc/survival/veteran.html'),
    'gbsg': dict(name='German Breast Cancer Study Group', treatment='Hormonal therapy (hormon=1)', control='No hormonal therapy (hormon=0)', endpoint='Recurrence-free survival (recurrence or death)',
                 citation='Schumacher et al. JCO 1994;12:2086-2093. doi:10.1200/JCO.1994.12.10.2086; Royston and Altman BMC Med Res Methodol 2013;13:33; R survival package gbsg data.',
                 publication_url='https://pubmed.ncbi.nlm.nih.gov/7931478/'),
}
# id, display name, column, comparison, cutoff. No subgroup is selected using its p-value.
SPECS = {
    'colon': [('age_ge60','Age ≥60','age','ge',60), ('male','Male','sex','eq',1),
              ('node4','More than four positive nodes (node4)','node4','eq',1),
              ('obstruct','Obstruction','obstruct','eq',1), ('perfor','Perforation','perfor','eq',1),
              ('adhere','Adherence to nearby organs','adhere','eq',1),
              ('differ_well_moderate','Well/moderately differentiated vs poor','differ','in',[1,2]),
              ('extent_limited','Submucosa/muscle vs serosa/contiguous','extent','in',[1,2])],
    'veteran': [(f'cell_{c}',f'Cell type: {c} vs rest','celltype','eq',c) for c in ['squamous','smallcell','adeno','large']]
               + [('karno_ge60','Karnofsky ≥60','karno','ge',60), ('prior','Prior therapy','prior','gt',0), ('age_ge60','Age ≥60','age','ge',60)],
    'gbsg': [('age_ge50','Age ≥50','age','ge',50), ('meno','Postmenopausal','meno','eq',1),
             ('grade3','Grade 3','grade','eq',3), ('nodes_gt3','More than three positive nodes','nodes','gt',3),
             ('pgr_ge10','Progesterone receptor ≥10','pgr','ge',10), ('er_ge10','Estrogen receptor ≥10','er','ge',10),
             ('size_gt20','Tumor size >20 mm','size','gt',20)],
}


def load_trial(key: str, directory: Path = RCT_DIR) -> pd.DataFrame:
    if key not in TRIALS:
        raise ValueError('Unknown historical trial key')
    raw = pd.read_csv(directory / f'{key}.csv')
    raw = raw.drop(columns=[c for c in raw.columns if c == 'rownames' or c.startswith('Unnamed:')])
    required = {s[2] for s in SPECS[key]} | ({'rx','etype','id','time','status'} if key == 'colon' else
                {'trt','time','status'} if key == 'veteran' else {'hormon','rfstime','status','pid'})
    if required - set(raw):
        raise ValueError(f'{key} is missing columns: {sorted(required-set(raw))}')
    if key == 'colon':
        raw = raw.loc[(raw.etype == 2) & raw.rx.isin(['Lev+5FU','Obs'])].copy()
        if raw.id.duplicated().any():
            raise ValueError('Colon must have exactly one death record per patient')
        raw['treatment'] = (raw.rx == 'Lev+5FU').astype(int)
    elif key == 'veteran':
        raw = raw.loc[raw.trt.isin([1,2])].copy(); raw['treatment'] = (raw.trt == 2).astype(int)
    else:
        raw = raw.loc[raw.hormon.isin([0,1])].copy(); raw['treatment'] = raw.hormon.astype(int)
        if raw.pid.duplicated().any():
            raise ValueError('GBSG contains duplicate patient IDs')
    raw['duration'] = pd.to_numeric(raw['rfstime' if key == 'gbsg' else 'time'], errors='coerce')
    raw['event'] = pd.to_numeric(raw.status, errors='coerce')
    if not ((raw.duration > 0) & np.isfinite(raw.duration) & raw.event.isin([0,1])).all():
        raise ValueError('Invalid or missing survival time/event; no silent outcome imputation')
    return raw.reset_index(drop=True)


def subgroup_masks(frame: pd.DataFrame, spec):
    _, _, column, operation, cutoff = spec
    values = frame[column]
    known = values.notna()
    if column == 'differ': known &= values.isin([1,2,3])
    if column == 'extent': known &= values.isin([1,2,3,4])
    if column == 'celltype': known &= values.isin(['squamous','smallcell','adeno','large'])
    condition = values.isin(cutoff) if operation == 'in' else getattr(values, {'ge':'ge','gt':'gt','eq':'eq'}[operation])(cutoff)
    return known & condition, known & ~condition, ~known


def counts(frame: pd.DataFrame) -> ArmCounts:
    return ArmCounts(control_n=int((frame.treatment == 0).sum()), treatment_n=int((frame.treatment == 1).sum()),
                     control_events=int(frame.loc[frame.treatment == 0,'event'].sum()),
                     treatment_events=int(frame.loc[frame.treatment == 1,'event'].sum()))


def cox(frame: pd.DataFrame, covariates=('treatment',), term='treatment') -> Effect:
    from lifelines import CoxPHFitter
    from lifelines.exceptions import ConvergenceError, ConvergenceWarning
    if len(frame) < 5 or frame.event.sum() < 2 or any(frame[c].nunique() < 2 for c in covariates):
        return Effect()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            model = CoxPHFitter(penalizer=0).fit(frame[['duration','event',*covariates]], duration_col='duration', event_col='event')
        row = model.summary.loc[term]
        numbers = [float(row[c]) for c in ['exp(coef)','exp(coef) lower 95%','exp(coef) upper 95%','p']]
        if not all(np.isfinite(numbers)) or min(numbers[:3]) <= 0:
            return Effect()
        return Effect(hr=numbers[0], ci_low=numbers[1], ci_high=numbers[2], p=numbers[3], status='ok')
    except (ConvergenceError, ConvergenceWarning, ValueError, np.linalg.LinAlgError, FloatingPointError):
        return Effect()


def bh_adjust(p_values: list[float | None]) -> list[float | None]:
    # Unestimable tests count as p=1 in the family; retain null in their output.
    p = np.array([v if v is not None else 1.0 for v in p_values])
    order = np.argsort(p, kind='stable'); ranked = p[order] * len(p) / np.arange(1,len(p)+1)
    adjusted = np.minimum(1, np.minimum.accumulate(ranked[::-1])[::-1])
    result = np.empty(len(p)); result[order] = adjusted
    return [float(result[i]) if v is not None else None for i,v in enumerate(p_values)]


def analyze_frame(frame: pd.DataFrame, key: str, *, case_id=None, variant='original', specs=None,
                  planted_subgroup=None, seed=None, provenance=None) -> TrialEvidence:
    table = []
    for spec in specs if specs is not None else SPECS[key]:
        yes, no, missing = subgroup_masks(frame, spec)
        sub, rest = frame.loc[yes], frame.loc[no]
        a, b = counts(sub), counts(rest)
        design = frame.loc[~missing, ['duration','event','treatment']].copy()
        design['subgroup'] = yes.loc[~missing].astype(int)
        design['interaction'] = design.treatment * design.subgroup
        table.append(SubgroupEvidence(id=spec[0], label=spec[1], n=int(yes.sum()), missing_n=int(missing.sum()),
          subgroup=a, complement=b, hr_subgroup=cox(sub), hr_complement=cox(rest),
          interaction=cox(design, ('treatment','subgroup','interaction'), 'interaction'),
          underpowered=min(a.control_events,a.treatment_events,b.control_events,b.treatment_events) < 20))
    q_values = bh_adjust([r.interaction.p for r in table])
    for row, q in zip(table,q_values):
        row.interaction_q = q
        row.bh_significant = q is not None and q <= .10
        if row.bh_significant and row.hr_subgroup.hr is not None and row.hr_complement.hr is not None:
            if row.hr_subgroup.hr > row.hr_complement.hr: row.truth_label = 'weaker_benefit'
            elif row.hr_subgroup.hr < row.hr_complement.hr: row.truth_label = 'stronger_benefit'
    meta = TRIALS[key]
    disclaimers = list(DISCLAIMERS)
    if key == 'gbsg': disclaimers.append(GBSG_WARNING)
    if key == 'colon': disclaimers.append('R survival documents a nodes/node4 inconsistency; this analysis uses the supplied node4 flag, not a recomputed value.')
    detectable = None
    if planted_subgroup:
        target = next(r for r in table if r.id == planted_subgroup)
        detectable = target.truth_label == 'weaker_benefit'
        disclaimers.append('PLANTED diagnostic case: treated time/event pairs were replaced by control bootstrap pairs inside the named subgroup; it is not an observed trial result.')
        if not detectable: disclaimers.append('Planted, not detectable: the named subgroup did not meet the BH-adjusted weaker-benefit definition. No positive label was forced.')
    return TrialEvidence(case_id=case_id or key, trial_key=key, trial_name=meta['name'], treatment=meta['treatment'],
      control=meta['control'], endpoint=meta['endpoint'], variant=variant, n=len(frame), events=int(frame.event.sum()),
      overall=cox(frame), subgroups=table, provenance=provenance or {}, disclaimers=disclaimers,
      planted_subgroup=planted_subgroup, planted_detectable=detectable, seed=seed)


def plant(frame: pd.DataFrame, spec, seed: int) -> pd.DataFrame:
    yes, _, _ = subgroup_masks(frame, spec)
    controls = frame.loc[yes & (frame.treatment == 0), ['duration','event']]
    target = yes & (frame.treatment == 1)
    if controls.empty or not target.any():
        raise ValueError('Planted subgroup needs both treatment arms')
    draws = np.random.default_rng(seed).integers(0,len(controls),int(target.sum()))
    result = frame.copy(deep=True)
    result.loc[target,['duration','event']] = controls.iloc[draws].to_numpy()
    return result


def build_ground_truth(directory: Path = RCT_DIR, seed: int = 20261017) -> list[TrialEvidence]:
    result = []
    for trial_index,key in enumerate(TRIALS):
        frame = load_trial(key,directory)
        provenance = json.loads((directory/f'{key}.provenance.json').read_text())
        actual_hash = hashlib.sha256((directory/f'{key}.csv').read_bytes()).hexdigest()
        if actual_hash != provenance['sha256']: raise ValueError(f'{key} snapshot hash mismatch')
        result.append(analyze_frame(frame,key,provenance=provenance))
        # Three largest balanced prespecified groups, chosen by size alone, never p-values.
        candidates = sorted(SPECS[key],key=lambda s:(-min(int(subgroup_masks(frame,s)[0].sum()),int(subgroup_masks(frame,s)[1].sum())),s[0]))[:3]
        for k,spec in enumerate(candidates):
            planted_seed = seed + 100 * trial_index + k
            result.append(analyze_frame(plant(frame,spec,planted_seed),key,case_id=f'{key}:planted:{spec[0]}',
              variant=f'planted:{spec[0]}',planted_subgroup=spec[0],seed=planted_seed,provenance=provenance))
    (directory/'ground_truth.jsonl').write_text(''.join(row.model_dump_json()+'\n' for row in result),encoding='utf-8')
    return result


if __name__ == '__main__':
    rows = build_ground_truth()
    for row in rows:
        print(row.case_id, 'n=',row.n, 'planted_detectable=',row.planted_detectable)
