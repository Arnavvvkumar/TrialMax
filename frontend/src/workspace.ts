import type { AnalyzeResponse, CompareResult, PopulationMode, ReviewDecision, Rule } from './scenarioTypes.ts'

// Synthea is the default for every source; fixed and generated remain API-only fallbacks.
export function defaultPopulationMode(_source: 'nct' | 'text'): PopulationMode {
  return 'synthea'
}

export interface Workspace {
  context: string; analysis: AnalyzeResponse | null; draft: Rule[]; comparison: CompareResult | null
  decisions: Record<string, ReviewDecision>
}
export function emptyWorkspace(context: string): Workspace { return { context, analysis: null, draft: [], comparison: null, decisions: {} } }
export type ThresholdEditAction = { type: 'edit'; id: string; value: number; field: 'value' | 'value_max' }
type Action = { type: 'reset'; context: string }
  | { type: 'analyzed'; context: string; result: AnalyzeResponse }
  | ThresholdEditAction
  | { type: 'compared'; context: string; draft: Rule[]; result: CompareResult }
  | { type: 'decide'; id: string; decision: ReviewDecision }

export function workspaceReducer(state: Workspace, action: Action): Workspace {
  if (action.type === 'reset') return emptyWorkspace(action.context)
  if (action.type === 'analyzed') return action.context !== state.context ? state : {
    ...state, analysis: action.result, draft: structuredClone(action.result.rules), comparison: null, decisions: {},
  }
  if (action.type === 'edit') return {
    ...state, draft: state.draft.map(r => r.id === action.id ? { ...r, [action.field]: action.value } : r), comparison: null, decisions: {},
  }
  if (action.type === 'compared') {
    if (action.context !== state.context || JSON.stringify(action.draft) !== JSON.stringify(state.draft)
        || action.result.cohort.id !== state.analysis?.simulation.cohort.id
        || action.result.baseline.cohort.id !== action.result.cohort.id
        || action.result.proposed.cohort.id !== action.result.cohort.id) return state
    return { ...state, comparison: action.result, decisions: {} }
  }
  if (!state.comparison?.changed_rule_ids.includes(action.id)) return state
  return { ...state, decisions: { ...state.decisions, [action.id]: action.decision } }
}

export function changedRules(baseline: Rule[], draft: Rule[]) {
  const before = new Map(baseline.map(rule => [rule.id, rule]))
  return draft.filter(rule => JSON.stringify(before.get(rule.id)) !== JSON.stringify(rule))
}
export function validDraft(rules: Rule[]) {
  return rules.every(rule => !rule.simulatable || (rule.operator === 'present' || rule.operator === 'absent'
    ? rule.value === null && rule.value_max === null
    : rule.value !== null && Number.isFinite(rule.value) && (rule.operator === 'between'
      ? rule.value_max !== null && Number.isFinite(rule.value_max) && rule.value_max >= rule.value
      : rule.value_max === null)))
}
export function reviewedRules(state: Workspace) {
  const accepted = new Map(state.draft.filter(r => state.decisions[r.id]?.decision === 'accepted').map(r => [r.id, r]))
  return state.analysis?.rules.map(r => accepted.get(r.id) ?? r) ?? []
}

const SPECIFIC_PREFIX = 'Additional requirement is not modeled: '
const GENERIC_NOTE = /^Part of criterion .* that is not modeled\.$/

// Explains one "not checked" rule: the specific part that was not evaluated and why. Several rules can
// come from the same sentence, so repeating the whole sentence for each one hides what is different.
export function notCheckedDetail(rule: Rule, labels: Record<string, { label: string }> = {}) {
  if (rule.simulatable && rule.variable) {
    const threshold = rule.operator === 'between' ? `${rule.value}-${rule.value_max}` : `${rule.operator} ${rule.value ?? ''}`
    return {
      what: `${labels[rule.variable]?.label ?? rule.variable.replaceAll('_', ' ')} ${threshold} ${rule.unit ?? ''}`.replace(/\s+/g, ' ').trim(),
      reason: 'Understood, but the selected patient population has no data for this field.',
      badge: 'No data in population',
    }
  }
  // Use the specific leftover only when it is a real threshold (e.g. "wbc >=3.5 ..."); a bare word
  // fragment such as "class iii" is less clear than the original sentence.
  const specific = rule.notes.find(note => note.startsWith(SPECIFIC_PREFIX) && /(>=|<=|>|<)\s*\d/.test(note))
  const reason = rule.notes.find(note => note !== specific && !GENERIC_NOTE.test(note) && !note.startsWith(SPECIFIC_PREFIX))
  return {
    what: specific ? specific.slice(SPECIFIC_PREFIX.length) : (rule.clause || rule.text),
    reason: reason ?? 'The simulator cannot represent this requirement, so it needs researcher review.',
    badge: 'Not modeled',
  }
}
