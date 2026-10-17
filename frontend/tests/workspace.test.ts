import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyWorkspace, workspaceReducer, validDraft, reviewedRules } from '../src/workspace.ts'
import type { AnalyzeResponse, CompareResult, Rule, SimulationResult } from '../src/scenarioTypes.ts'

const rule: Rule = { id: 'I1', kind: 'inclusion', text: 'Age >=18 years', clause: null, category: 'age', variable: 'age', operator: '>=', value: 18, value_max: null, unit: 'years', simulatable: true, fidelity: 'exact', purpose: 'safety', findability: 'structured_field', safety_critical: false, parsed_by: 'rules', source: 'text', notes: ['Source preserved'] }
const cohort = { id: 'fixed:v1:hash', mode: 'fixed' as const, version: 'v1', label: 'Fixture', population_n: 500, seed: null, available_variables: ['age'] }
// These reducer tests only inspect rules and identity; numerical API contracts are tested in Python.
const simulation = { cohort } as SimulationResult
const analysis = { rules: [rule], simulation } as AnalyzeResponse
const decision = { decision: 'accepted' as const, reason: 'Reviewed for test', at: '2026-10-17T00:00:00Z' }
function loaded() { return workspaceReducer(emptyWorkspace('trial-A'), { type: 'analyzed', context: 'trial-A', result: analysis }) }
function compared() {
  const state = workspaceReducer(loaded(), { type: 'edit', id: 'I1', field: 'value', value: 21 })
  const result = { cohort, baseline: simulation, proposed: simulation, changed_rule_ids: ['I1'] } as CompareResult
  return workspaceReducer(state, { type: 'compared', context: 'trial-A', draft: state.draft, result })
}

test('editing preserves baseline, source, kind, operator and stable rule IDs', () => {
  const state = workspaceReducer(loaded(), { type: 'edit', id: 'I1', field: 'value', value: 21 })
  assert.equal(state.analysis!.rules[0].value, 18)
  assert.deepEqual(state.draft[0], { ...rule, value: 21 })
  assert.notEqual(state.draft, state.analysis!.rules)
})
test('late analysis for a previous trial or population is discarded', () => {
  const state = emptyWorkspace('trial-B-generated')
  assert.equal(workspaceReducer(state, { type: 'analyzed', context: 'trial-A', result: analysis }), state)
})
test('comparison for an old draft is discarded', () => {
  const state = compared()
  const edited = workspaceReducer(state, { type: 'edit', id: 'I1', field: 'value', value: 25 })
  assert.equal(workspaceReducer(edited, { type: 'compared', context: 'trial-A', draft: state.draft, result: state.comparison! }), edited)
})
test('comparison from a different cohort cannot overwrite results', () => {
  const state = compared()
  const wrong = { ...state.comparison!, cohort: { ...cohort, id: 'generated:v1:other' } }
  assert.equal(workspaceReducer(state, { type: 'compared', context: 'trial-A', draft: state.draft, result: wrong }), state)
})

test('both nested simulations must match the declared comparison cohort', () => {
  const state = compared()
  const mismatched = { ...simulation, cohort: { ...cohort, id: 'generated:other' } }
  const wrong = { ...state.comparison!, baseline: mismatched, proposed: mismatched }
  assert.equal(workspaceReducer(state, { type: 'compared', context: 'trial-A', draft: state.draft, result: wrong }), state)
})
test('editing clears comparison and all previous review decisions', () => {
  const state = workspaceReducer(compared(), { type: 'decide', id: 'I1', decision })
  const edited = workspaceReducer(state, { type: 'edit', id: 'I1', field: 'value', value: 22 })
  assert.equal(edited.comparison, null)
  assert.deepEqual(edited.decisions, {})
})
test('changing source or population clears baseline and draft together', () => {
  assert.deepEqual(workspaceReducer(compared(), { type: 'reset', context: 'generated' }), emptyWorkspace('generated'))
})
test('acceptance is explicit and never mutates the original baseline', () => {
  const initial = compared()
  assert.deepEqual(reviewedRules(initial), [rule])
  const state = workspaceReducer(initial, { type: 'decide', id: 'I1', decision })
  assert.equal(reviewedRules(state)[0].value, 21)
  assert.equal(state.analysis!.rules[0].value, 18)
  const rejected = workspaceReducer(state, { type: 'decide', id: 'I1', decision: { ...decision, decision: 'rejected' } })
  assert.equal(reviewedRules(rejected)[0].value, 18)
})
test('cannot record an acceptance without a current comparison', () => {
  const state = loaded()
  assert.equal(workspaceReducer(state, { type: 'decide', id: 'I1', decision }), state)
})
test('invalid or reversed thresholds cannot be submitted', () => {
  assert.equal(validDraft([{ ...rule, value: NaN }]), false)
  assert.equal(validDraft([{ ...rule, value: Infinity }]), false)
  assert.equal(validDraft([{ ...rule, operator: 'between', value: 65, value_max: 18 }]), false)
  assert.equal(validDraft([{ ...rule, operator: 'between', value: null, value_max: 75 }]), false)
  assert.equal(validDraft([rule]), true)
})
