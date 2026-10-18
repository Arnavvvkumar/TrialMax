import type { AnalyzeResponse, ApiHealth, AutopilotResponse, CompareResult, PopulationCatalog, PopulationChoice, RareReachResponse, Rule, SimulationResult, VariableMeta } from './scenarioTypes'
import type { ResponderResponse } from './responderTypes'

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
export function getVariables(signal?: AbortSignal) { return request<Record<string, VariableMeta>>('/api/variables', undefined, signal) }
export function getResponderEvidence(trial_key: string, signal?: AbortSignal) { return request<ResponderResponse>('/api/responder-evidence', { trial_key, variant: 'original' }, signal) }
export function analyzeTrial(input: { nct_id?: string; eligibility_text?: string; use_llm: boolean }, population: PopulationChoice, signal?: AbortSignal) {
  return request<AnalyzeResponse>('/api/analyze', { ...input, population }, signal)
}
export function runSimulation(rules: Rule[], population: PopulationChoice, signal?: AbortSignal) {
  return request<SimulationResult>('/api/simulate', { rules, population }, signal)
}
export function compareCriteria(baseline_rules: Rule[], proposed_rules: Rule[], population: PopulationChoice, signal?: AbortSignal) {
  return request<CompareResult>('/api/compare', { baseline_rules, proposed_rules, population }, signal)
}
export function getRareReach(nct_id: string, rules: Rule[], signal?: AbortSignal) { return request<RareReachResponse>('/api/rare-reach', { nct_id, rules }, signal) }
export function suggestAutopilot(rules: Rule[], population: PopulationChoice, max_edits: number, target_fraction: number, use_llm: boolean, signal?: AbortSignal) {
  return request<AutopilotResponse>('/api/autopilot', { rules, population, max_edits, target_fraction, use_llm }, signal)
}
