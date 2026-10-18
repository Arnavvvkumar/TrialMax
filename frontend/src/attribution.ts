import type { Rule, SimulationResult } from './scenarioTypes.ts'

type AttributionInput = Pick<SimulationResult, 'modeled_rule_ids'> & Partial<Pick<SimulationResult, 'attributions' | 'attribution_total_excluded'>>
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const idOrder = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0

export function formatAttributionRows(result: AttributionInput | null | undefined, rules: Rule[]) {
  const modeled = new Set(result?.modeled_rule_ids ?? [])
  const byId = new Map(rules.map(rule => [rule.id, rule]))
  function name(id: string) {
    const rule = byId.get(id)
    return rule ? `${id} · ${rule.variable?.replaceAll('_', ' ') || rule.clause || rule.text}` : id
  }
  return [...(result?.attributions ?? [])].filter(item => modeled.has(item.rule_id))
    .sort((a, b) => b.shapley_value - a.shapley_value || idOrder(a.rule_id, b.rule_id))
    .map(item => {
      const overlaps = [...item.top_overlaps].sort((a, b) => b.patient_n - a.patient_n || idOrder(a.rule_id, b.rule_id)).slice(0, 3)
        .map(overlap => ({ ruleId: overlap.rule_id, name: name(overlap.rule_id), patientN: overlap.patient_n }))
      return {
        ruleId: item.rule_id, name: name(item.rule_id), shapleyValue: item.shapley_value,
        sharePct: item.shapley_share_pct, shareLabel: `${item.shapley_share_pct.toFixed(1)}%`,
        patientLabel: `≈ ${number.format(item.shapley_value)} patients`, uniqueN: item.unique_n, totalFailN: item.total_fail_n,
        overlaps, overlapLabel: overlaps.length ? overlaps.map(o => `${o.name} (${number.format(o.patientN)} patients)`).join('; ') : 'No shared known failures',
      }
    })
}

export function compareAttributionRows(baseline: AttributionInput, proposed: AttributionInput, baselineRules: Rule[], proposedRules: Rule[] = baselineRules) {
  const before = new Map(formatAttributionRows(baseline, baselineRules).map(row => [row.ruleId, row]))
  const after = new Map(formatAttributionRows(proposed, proposedRules).map(row => [row.ruleId, row]))
  return [...new Set([...before.keys(), ...after.keys()])].map(ruleId => ({
    ruleId, name: (after.get(ruleId) ?? before.get(ruleId))!.name,
    before: before.get(ruleId) ?? null, after: after.get(ruleId) ?? null,
    beforeMissing: baseline.modeled_rule_ids.includes(ruleId) ? 'Unavailable' : 'Not modeled',
    afterMissing: proposed.modeled_rule_ids.includes(ruleId) ? 'Unavailable' : 'Not modeled',
  })).sort((a, b) => Math.max(b.before?.shapleyValue ?? 0, b.after?.shapleyValue ?? 0)
    - Math.max(a.before?.shapleyValue ?? 0, a.after?.shapleyValue ?? 0) || idOrder(a.ruleId, b.ruleId))
}
