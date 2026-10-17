import type { AutopilotResponse, Rule } from './scenarioTypes.ts'
import type { ThresholdEditAction } from './workspace.ts'

// Pure, atomic conversion: no API call, comparison, acceptance, or rule mutation.
export function planToEditActions(suggestion: Pick<AutopilotResponse, 'cohort_id' | 'plan'>, rules: Rule[], cohortId: string): ThresholdEditAction[] {
  if (suggestion.cohort_id !== cohortId) throw new Error('The cohort changed. Request a new Autopilot suggestion.')
  const byId = new Map(rules.map(rule => [rule.id, rule]))
  const seen = new Set<string>()
  return suggestion.plan.map(edit => {
    const rule = byId.get(edit.rule_id)
    if (!rule || seen.has(edit.rule_id) || !rule.simulatable || rule.safety_critical
        || rule.variable !== edit.variable || rule.unit !== edit.unit
        || !Number.isFinite(edit.from) || !Number.isFinite(edit.to)
        || !['value', 'value_max'].includes(edit.field) || rule[edit.field] !== edit.from
        || rule.operator === 'present' || rule.operator === 'absent'
        || (edit.field === 'value_max' ? rule.operator !== 'between' : rule.operator === 'between')) {
      throw new Error('The draft no longer matches this plan, or the plan contains an unsupported edit. Request a new suggestion.')
    }
    seen.add(edit.rule_id)
    return { type: 'edit', id: edit.rule_id, field: edit.field, value: edit.to }
  })
}
