import type { AnalyzeResponse, CompareResult, PopulationMode, ReviewDecision, Rule } from './scenarioTypes.ts'

export function defaultPopulationMode(source: 'nct' | 'text'): PopulationMode {
  return source === 'nct' ? 'generated' : 'fixed'
}

export interface Workspace {
  context: string; analysis: AnalyzeResponse | null; draft: Rule[]; comparison: CompareResult | null
  decisions: Record<string, ReviewDecision>
}
export function emptyWorkspace(context: string): Workspace { return { context, analysis: null, draft: [], comparison: null, decisions: {} } }
type Action = { type: 'reset'; context: string }
  | { type: 'analyzed'; context: string; result: AnalyzeResponse }
  | { type: 'edit'; id: string; value: number; field: 'value' | 'value_max' }
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
