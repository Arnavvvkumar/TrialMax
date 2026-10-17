import { buildMockSimulation } from './mockSimulation'
import type { EligibilityCriterion, SimulationResponse } from './scenarioTypes'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')
const USE_BACKEND = import.meta.env.VITE_USE_BACKEND === 'true'
const API_TOKEN = import.meta.env.VITE_API_TOKEN

interface ApiRule {
  id: string
  kind: 'inclusion' | 'exclusion'
  text: string
  category: string
  variable?: string
  operator?: string
  value?: number
  value_max?: number
  unit?: string
  simulatable: boolean
  purpose: string
  findability: string
  safety_critical: boolean
}

interface ApiSimulationResult {
  population_n: number
  eligible_n: number | null
  eligible_pct: number | null
  impacts: Array<{ rule_id: string; simulated: boolean; fail_n: number; fail_pct: number }>
}

interface ApiCompareResult {
  baseline: ApiSimulationResult
  proposed: ApiSimulationResult
  eligible_change_pct_points: number | null
}

export interface TrialInfo {
  nct_id?: string
  title?: string
  phases: string[]
  conditions: string[]
  sponsor?: string
  status?: string
  enrollment?: number
  minimum_age?: string
  maximum_age?: string
  sex?: string
  eligibility_text: string
}

export interface AnalyzeResponse {
  trial: TrialInfo
  rules: ApiRule[]
  simulation: ApiSimulationResult
  llm_used: boolean
  warnings: string[]
}

function toApiRule(criterion: EligibilityCriterion): ApiRule {
  const common = {
    id: criterion.id,
    kind: 'inclusion' as const,
    text: criterion.originalText,
    category: 'other',
    simulatable: false,
    purpose: 'unknown',
    findability: 'unknown',
    safety_critical: criterion.considerations.includes('Patient safety'),
  }
  if (criterion.id === 'E03') return { ...common, category: 'age', variable: 'age', operator: 'between', value: 18, value_max: criterion.value, unit: 'years', simulatable: true, purpose: 'safety', findability: 'structured_field' }
  if (criterion.id === 'E04') return { ...common, category: 'lab', variable: 'hemoglobin', operator: '>=', value: criterion.value, unit: 'g/dL', simulatable: true, purpose: 'safety', findability: 'coded_lab' }
  if (criterion.id === 'E06') return { ...common, category: 'lab', variable: 'egfr', operator: '>=', value: criterion.value, unit: 'mL/min/1.73m2', simulatable: true, purpose: 'safety', findability: 'coded_lab' }
  return common
}

function toSummary(result: ApiSimulationResult) {
  const eligible = result.eligible_n ?? 0
  return { total: result.population_n, eligible, excluded: result.population_n - eligible, unknown: 0 }
}

function toResponse(compare: ApiCompareResult, criteria: EligibilityCriterion[]): SimulationResponse {
  const names = new Map(criteria.map((criterion) => [criterion.id, criterion.name]))
  return {
    source: 'backend',
    evaluatedAt: new Date().toISOString(),
    baseline: toSummary(compare.baseline),
    modified: toSummary(compare.proposed),
    eligibilityPercentagePointChange: compare.eligible_change_pct_points ?? 0,
    exclusionBreakdown: compare.proposed.impacts
      .filter((impact) => impact.simulated)
      .map((impact) => ({
        criterionId: impact.rule_id,
        criterionName: names.get(impact.rule_id) ?? impact.rule_id,
        before: compare.baseline.impacts.find((item) => item.rule_id === impact.rule_id)?.fail_n ?? 0,
        after: impact.fail_n,
      })),
    note: 'Calculated by the backend simulator using synthetic population generation. This is not clinical evidence.',
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(API_TOKEN ? { 'X-WT-Token': API_TOKEN } : {}) },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`API ${response.status}: ${detail || response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: API_TOKEN ? { 'X-WT-Token': API_TOKEN } : {},
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`API ${response.status}: ${detail || response.statusText}`)
  }
  return response.json() as Promise<T>
}

export function isBackendEnabled() {
  return USE_BACKEND
}

export async function getTrial(nctId: string): Promise<TrialInfo> {
  if (!USE_BACKEND) {
    return {
      nct_id: nctId,
      title: 'Targeted therapy in advanced non-small cell lung cancer',
      phases: ['Phase III'],
      conditions: ['Non-small cell lung cancer'],
      status: 'DEMO',
      enrollment: 500,
      eligibility_text: 'Synthetic demo protocol',
    }
  }
  return getJson<TrialInfo>(`/api/trials/${encodeURIComponent(nctId)}`)
}

export async function analyzeTrial(input: { nctId?: string; eligibilityText?: string }): Promise<AnalyzeResponse> {
  if (!USE_BACKEND) {
    return { trial: await getTrial(input.nctId ?? 'NCT-DEMO-001'), rules: [], simulation: { population_n: 500, eligible_n: 28, eligible_pct: 5.6, impacts: [] }, llm_used: false, warnings: ['Using local mock analysis data.'] }
  }
  return postJson<AnalyzeResponse>('/api/analyze', {
    nct_id: input.nctId,
    eligibility_text: input.eligibilityText,
    use_llm: true,
    population_size: 500,
    seed: 42,
  })
}

export async function runSimulation(criteria: EligibilityCriterion[]): Promise<SimulationResponse> {
  if (!USE_BACKEND) return buildMockSimulation(criteria)
  const result = await postJson<ApiSimulationResult>('/api/simulate', {
    rules: criteria.map(toApiRule),
    population_size: 500,
    seed: 42,
  })
  return toResponse({ baseline: result, proposed: result, eligible_change_pct_points: 0 }, criteria)
}

export async function compareCriteria(
  baseline: EligibilityCriterion[],
  modified: EligibilityCriterion[],
): Promise<SimulationResponse> {
  if (!USE_BACKEND) return buildMockSimulation(modified)
  const result = await postJson<ApiCompareResult>('/api/compare', {
    baseline_rules: baseline.map(toApiRule),
    proposed_rules: modified.map(toApiRule),
    population_size: 500,
    seed: 42,
  })
  return toResponse(result, modified)
}
