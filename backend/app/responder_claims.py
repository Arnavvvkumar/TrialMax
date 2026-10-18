"""Auditable aggregate-only evidence policy and bounded explanation verification.

Free prose is not assumed true merely because its numbers occur in a table.
Displayed explanations must match a context-checked template. Contradiction
patterns additionally identify specific errors in legacy/raw prose for the audit;
they are not a general natural-language or clinical-validity verifier.
"""
import math
import re

POLICY_VERSION = 'bh-010-powered-claims-v1'
BH_CUTOFF = .10
MULTIPLICITY_NOTE = 'Benjamini–Hochberg; statistically significant if q <= 0.10.'
UNDERPOWERED_NOTE = ('Underpowered subgroups are classified as no reliable difference, even when BH-significant. '
                     'This conservative evidence policy does not change their q-values or prove equal effects.')


def significant(row):
    q = row.get('q_value', row.get('interaction_q'))
    return isinstance(q, (int, float)) and not isinstance(q, bool) and math.isfinite(q) and 0 <= q <= BH_CUTOFF


def effect_direction(row):
    inside = row.get('hr_in', (row.get('hr_subgroup') or {}).get('hr'))
    outside = row.get('hr_out', (row.get('hr_complement') or {}).get('hr'))
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in [inside, outside]):
        return 'no_reliable_difference'
    return 'weaker_benefit' if inside > outside else 'stronger_benefit' if inside < outside else 'no_reliable_difference'


def evidence_label(row):
    return effect_direction(row) if significant(row) and not row.get('underpowered', True) else 'no_reliable_difference'


def template_rationale(payload, flag=None, direction=None):
    """Only asserts facts calculated from the supplied aggregates; <=400 chars."""
    if payload.get('prompt_variant') == 'names_only':
        return ('Effect statistics were not supplied, so multiplicity-adjusted subgroup differences cannot be assessed. '
                'No subgroup is flagged; a researcher must decide.')
    rows = payload.get('subgroups', [])
    sig = [r for r in rows if significant(r)]
    powered = [r for r in sig if not r.get('underpowered', True)]
    if flag is not None:
        relative = 'weaker' if direction == 'weaker_benefit' else 'stronger'
        return (f'The flagged subgroup meets the BH multiplicity cutoff (q <= 0.10), has {relative} relative benefit, '
                'and is not marked underpowered. This exploratory finding is not a protocol-change recommendation; a researcher must decide.')
    if not sig:
        return ('No interaction meets the BH multiplicity cutoff (q <= 0.10). '
                'No subgroup is flagged; this does not establish equal effects. A researcher must decide.')
    if not powered:
        return ('At least one interaction meets the BH multiplicity cutoff (q <= 0.10), but every significant subgroup is underpowered. '
                'The conservative evidence label is no reliable difference. No subgroup is flagged; a researcher must decide.')
    return ('At least one interaction meets the BH multiplicity cutoff (q <= 0.10). '
            'No subgroup is flagged; significant but underpowered groups remain no reliable difference under the conservative policy. '
            'This exploratory evidence requires a researcher to decide.')


def rationale_options(payload):
    options = {'abstain': template_rationale(payload)}
    if payload.get('prompt_variant') == 'with_stats':
        for direction in ['weaker_benefit', 'stronger_benefit']:
            if any(evidence_label(r) == direction for r in payload.get('subgroups', [])):
                options[direction] = template_rationale(payload, 'selected', direction)
    return options


def contradiction_errors(output, payload):
    """Specific contradiction detectors, separate from unverified free prose."""
    rows = payload.get('subgroups', [])
    by_id = {r['id']: r for r in rows}
    flag, direction = output.get('flag'), output.get('direction')
    text = output.get('rationale', '').lower()
    errors = []
    if flag is not None:
        row = by_id.get(flag)
        if row is None: errors.append('unknown_subgroup')
        elif payload.get('prompt_variant') != 'with_stats': errors.append('flag_without_effect_statistics')
        else:
            if row.get('underpowered', True): errors.append('flagged_underpowered_subgroup')
            if not significant(row): errors.append('flag_without_bh_significance')
            if direction != effect_direction(row): errors.append('wrong_flag_direction')
    if payload.get('prompt_variant') != 'with_stats':
        return errors
    # Match categorical claims about ALL interactions, not "no adequately powered
    # weaker-benefit group" or a statement specifically about exclusion candidates.
    for clause in re.split(r'(?<=[.;:])\s+', text):
        blanket_negative = any(re.search(pattern, clause) for pattern in [
            r'\b(?:interactions?|subgroups?)\b[^.;:]{0,55}\b(?:do(?:es)? not|don.t|fails? to)\s+surviv\w*[^.;:]{0,60}(?:multiplicity|correction|adjust)',
            r'\b(?:no|none|nothing|zero)\b[^.;:]{0,65}\b(?:interaction|subgroup)s?\b[^.;:]{0,55}\b(?:surviv\w*|(?:statistically|bh)[ -]significant)\b',
            r'\b(?:no|none|nothing|zero)\b[^.;:]{0,60}\bsurviv\w*[^.;:]{0,55}\b(?:multiplicity|correction|adjust)',
        ])
        qualified = re.search(r'\b(?:powered|reliable|weaker|stronger|exclusion|candidate)\b', clause)
        if blanket_negative and not qualified and any(significant(r) for r in rows):
            errors.append('denied_existing_bh_significance')
        # Recognize explicit subgroup-to-direction claims. Other prose still
        # fails the template allowlist below rather than being trusted silently.
        for row in rows:
            subject = re.escape(row['id'].lower())
            label = re.escape(row.get('label', '').lower())
            for word, claimed in [('weaker', 'weaker_benefit'), ('stronger', 'stronger_benefit')]:
                if re.search(rf'(?:\b{subject}\b|{label})\s+(?:has|shows|suggests|demonstrates|:|is associated with)\s+(?:a\s+)?{word}\s+(?:relative\s+)?benefit', clause):
                    if claimed != effect_direction(row): errors.append('wrong_named_subgroup_direction')
    return sorted(set(errors))


def claim_errors(output, payload):
    errors = contradiction_errors(output, payload)
    expected = template_rationale(payload, output.get('flag'), output.get('direction'))
    if output.get('rationale') != expected:
        errors.append('unverified_free_prose')
    return sorted(set(errors))
