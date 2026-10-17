import type { AnalyzeResponse, ApiHealth, ChalkCheck, CompareResult, PopulationCatalog, PopulationChoice, Rule, SimulationResult, VariableMeta } from './scenarioTypes'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
// An optional application access token is visible to the browser. Never put a Chalk key here.
const API_TOKEN = import.meta.env.VITE_API_TOKEN

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(API_TOKEN ? { 'X-WT-Token': API_TOKEN } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(`API ${response.status}: ${typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail)}`)
  }
  return response.json() as Promise<T>
}

export function getPopulations(signal?: AbortSignal) { return request<PopulationCatalog>('/api/populations', undefined, signal) }
export function getHealth(signal?: AbortSignal) { return request<ApiHealth>('/api/health', undefined, signal) }
export function checkChalk(signal?: AbortSignal) { return request<ChalkCheck>('/api/chalk/check', {}, signal) }
export function getVariables(signal?: AbortSignal) { return request<Record<string, VariableMeta>>('/api/variables', undefined, signal) }
export function analyzeTrial(input: { nct_id?: string; eligibility_text?: string; use_llm: boolean }, population: PopulationChoice, signal?: AbortSignal) {
  return request<AnalyzeResponse>('/api/analyze', { ...input, population }, signal)
}
export function runSimulation(rules: Rule[], population: PopulationChoice, signal?: AbortSignal) {
  return request<SimulationResult>('/api/simulate', { rules, population }, signal)
}
export function compareCriteria(baseline_rules: Rule[], proposed_rules: Rule[], population: PopulationChoice, signal?: AbortSignal) {
  return request<CompareResult>('/api/compare', { baseline_rules, proposed_rules, population }, signal)
}
