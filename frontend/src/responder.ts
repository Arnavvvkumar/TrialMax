import type { ResponderEffect, ResponderResponse, ResponderRun, ResponderSubgroup } from './responderTypes.ts'

export function subgroupEvidenceLabel(row: Pick<ResponderSubgroup,'underpowered'|'truth_label'>) {
  return row.underpowered ? 'no reliable difference' : row.truth_label.replaceAll('_', ' ')
}

export const responderMetrics = [
  ['correct_flag','Correct flag'], ['no_overclaim','No overclaim'], ['abstains_when_null','Null abstention'],
  ['planted_recall','Planted recall'], ['number_fidelity','Number fidelity'], ['json_valid','Raw JSON valid'],
  ['raw_claim_consistency','New AI template match'],
  ['claim_consistency','Displayed template match'],
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

// ---------------------------------------------------------------- at-a-glance summaries

export type Tone = 'sage' | 'amber' | 'gray' | 'red'
export type GroupStatus = { text: string; tone: Tone }

/** One short status per subgroup, from the precomputed statistical reference label. */
export function subgroupStatus(row: Pick<ResponderSubgroup, 'truth_label' | 'underpowered' | 'hr_subgroup'>): GroupStatus {
  if (row.hr_subgroup.status === 'unestimable') return { text: 'Not estimable', tone: 'gray' }
  // Underpowered groups never get a directional decision label, even when statistically significant.
  if (row.underpowered) return { text: 'Too few events', tone: 'amber' }
  if (row.truth_label === 'weaker_benefit') return { text: 'Benefits less', tone: 'red' }
  if (row.truth_label === 'stronger_benefit') return { text: 'Benefits more', tone: 'sage' }
  return { text: 'No clear difference', tone: 'gray' }
}

/** The answer the AI should give: the reliable weaker-benefit group with the smallest q, else none. */
export function expectedFlag(subgroups: ResponderSubgroup[]): string | null {
  const weaker = subgroups.filter(row => row.truth_label === 'weaker_benefit' && !row.underpowered)
    .sort((a, b) => (a.interaction_q ?? 1) - (b.interaction_q ?? 1) || a.id.localeCompare(b.id))
  return weaker[0]?.id ?? null
}

export const shortName = (text: string) => text.replace(/\s*\([^)]*\)/g, '').trim()
const outcome = (endpoint: string) => endpoint.match(/\(([^)]+)\)/)?.[1] ?? 'the outcome'

/** Overall effect as a signed % change in hazard; a direction is claimed only when the whole CI agrees. */
export function overallStat(evidence: Pick<ResponderResponse['evidence'], 'endpoint' | 'overall'>) {
  const { hr, ci_low, ci_high } = evidence.overall
  const caption = `hazard of ${outcome(evidence.endpoint)}`
  if (hr === null || ci_low === null || ci_high === null) return { value: 'n/a', caption, verdict: 'Not estimable', tone: 'gray' as Tone }
  const change = Math.round(100 * (hr - 1))
  const value = `${change > 0 ? '+' : change < 0 ? '−' : ''}${Math.abs(change)}%`
  if (ci_high < 1) return { value, caption, verdict: 'Lower hazard', tone: 'sage' as Tone }
  if (ci_low > 1) return { value, caption, verdict: 'Higher hazard', tone: 'red' as Tone }
  return { value, caption, verdict: 'No clear effect', tone: 'gray' as Tone }
}

export function agentVerdict(data: Pick<ResponderResponse, 'evidence' | 'suggestion'>): 'agrees' | 'disagrees' | 'unavailable' {
  if (data.suggestion.invalid) return 'unavailable'
  return data.suggestion.flag === expectedFlag(data.evidence.subgroups) ? 'agrees' : 'disagrees'
}

// Chart scale: log2 from 1/8 to 8, so HR 0.5 and 2 sit the same distance from "no effect".
export const PLOT_TICKS = [0.25, 0.5, 1, 2, 4]
export function plotPosition(value: number) {
  return 100 * (Math.log2(Math.max(1 / 8, Math.min(8, value))) + 3) / 6
}

type Tally = { passed: number; total: number }

/** Pooled counts for one metric across every run: score x denominator, so small groups are not overweighted. */
export function pooledMetric(runs: ResponderRun[], metric: string): Tally | null {
  let passed = 0, total = 0
  for (const run of runs) {
    const score = run.scores[metric], n = run.denominators[metric] ?? 0
    if (score == null || !n) continue
    passed += Math.round(score * n); total += n
  }
  return total ? { passed, total } : null
}

export function evaluationHeadline(evaluations: ResponderResponse['evaluations']) {
  const runs = evaluations.runs
  const cases = runs.filter(run => run.prompt_variant === runs[0]?.prompt_variant).reduce((sum, run) => sum + run.n, 0)
  return {
    cases, answers: runs.reduce((sum, run) => sum + run.n, 0),
    abstained: pooledMetric(runs, 'abstains_when_null'),
    realNumbers: pooledMetric(runs, 'number_fidelity'),
    validJson: pooledMetric(runs, 'json_valid'),
    claimsVerified: pooledMetric(runs, 'claim_consistency'),
    noPlantedTargets: runs.some(run => run.variant === 'planted') && runs.every(run => run.variant !== 'planted' || run.detectable_planted_n === 0),
  }
}


export function priorProseAudit(audit: NonNullable<ResponderResponse['evaluations']['claim_audit']>['before']) {
  return `${audit.contradiction_n} detected contradiction(s) in ${audit.n} prior responses. ${audit.n - audit.unverified_n}/${audit.n} matched approved templates; ${audit.unverified_n} did not. Failure to match a template does not by itself establish a contradiction.`
}
