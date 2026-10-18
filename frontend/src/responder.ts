import type { ResponderEffect, ResponderResponse, ResponderSubgroup } from './responderTypes.ts'

export function subgroupEvidenceLabel(row: Pick<ResponderSubgroup,'underpowered'|'truth_label'>) {
  return row.underpowered ? 'no reliable difference' : row.truth_label.replaceAll('_', ' ')
}

export const responderMetrics = [
  ['correct_flag','Correct flag'], ['no_overclaim','No overclaim'], ['abstains_when_null','Null abstention'],
  ['planted_recall','Planted recall'], ['number_fidelity','Number fidelity'], ['json_valid','Raw JSON valid'],
  ['legacy_claim_consistency','Prior prose verified'], ['raw_claim_consistency','New AI prose verified'],
  ['claim_consistency','Displayed claims verified'],
] as const

export function effectLabel(effect: ResponderEffect) {
  return effect.hr === null || effect.ci_low === null || effect.ci_high === null ? 'Not estimable'
    : `${effect.hr.toFixed(2)} (95% CI ${effect.ci_low.toFixed(2)}–${effect.ci_high.toFixed(2)})`
}
export function forestInterval(effect: ResponderEffect) {
  if ([effect.hr, effect.ci_low, effect.ci_high].some(v => v === null || !Number.isFinite(v) || v <= 0)) return null
  const position = (value: number) => 100 * (Math.log10(Math.max(.1, Math.min(10, value))) + 1) / 2
  return { point: position(effect.hr!), left: position(effect.ci_low!), right: position(effect.ci_high!),
    clipped: effect.ci_low! < .1 || effect.ci_high! > 10 }
}
export function hostedResponderValidation(evaluations: ResponderResponse['evaluations']) {
  return evaluations.status === 'complete' && evaluations.runs.length === 4
    && evaluations.runs.every(run => Boolean(run.run_id) && Boolean(run.evaluation_id) && run.status?.includes('SUCCEEDED'))
}
export function evidenceSuggestion(data: ResponderResponse) {
  const suggestion = data.suggestion
  if (suggestion.invalid) return 'Agent unavailable or its output failed validation. No subgroup is flagged.'
  if (!suggestion.flag) return 'No subgroup flagged for efficacy-based exclusion.'
  const row = data.evidence.subgroups.find(r => r.id === suggestion.flag)
  if (!row) return 'Unknown subgroup returned; no suggestion is usable.'
  return suggestion.direction === 'weaker_benefit'
    ? `Flag for researcher review: ${row.label}. This is not a protocol-change recommendation.`
    : `Possible stronger benefit in ${row.label}; this is not an exclusion candidate.`
}
