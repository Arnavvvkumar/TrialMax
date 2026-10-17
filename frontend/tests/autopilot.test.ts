import test from 'node:test'
import assert from 'node:assert/strict'
import { planToEditActions } from '../src/autopilot.ts'
import { emptyWorkspace, workspaceReducer } from '../src/workspace.ts'
import type { AnalyzeResponse, AutopilotEdit, AutopilotResponse, Rule } from '../src/scenarioTypes.ts'

const age: Rule = { id: 'A', kind: 'inclusion', text: 'Age 18–65', clause: null, category: 'age', variable: 'age', operator: 'between', value: 18, value_max: 65, unit: 'years', simulatable: true, fidelity: 'exact', purpose: 'safety', findability: 'structured_field', safety_critical: false, parsed_by: 'rules', source: 'text', notes: [] }
const hemoglobin: Rule = { ...age, id: 'H', variable: 'hemoglobin', operator: '>=', value: 9, value_max: null, unit: 'g/dL' }
const edit: AutopilotEdit = { rule_id: 'A', variable: 'age', field: 'value_max', from: 65, to: 70, unit: 'years', marginal_gain: 12, cumulative_gain: 12, component_label: 'Age', review_flag: true, rationale: 'Clinical review required.' }
const suggestion: Pick<AutopilotResponse, 'cohort_id' | 'plan'> = { cohort_id: 'synthea:test', plan: [edit, { ...edit, rule_id: 'H', variable: 'hemoglobin', field: 'value', from: 9, to: 8, unit: 'g/dL' }] }

test('plan becomes only threshold-edit actions, preserving age lower bound and baseline', () => {
  const rules = [age, hemoglobin], before = structuredClone(rules)
  const actions = planToEditActions(suggestion, rules, suggestion.cohort_id)
  assert.deepEqual(actions, [{ type: 'edit', id: 'A', field: 'value_max', value: 70 }, { type: 'edit', id: 'H', field: 'value', value: 8 }])
  const analysis = { rules, simulation: { cohort: { id: suggestion.cohort_id } } } as AnalyzeResponse
  let state = workspaceReducer(emptyWorkspace('test'), { type: 'analyzed', context: 'test', result: analysis })
  for (const action of actions) state = workspaceReducer(state, action)
  assert.equal(state.draft[0].value, 18)
  assert.equal(state.draft[0].value_max, 70)
  assert.equal(state.draft[1].value, 8)
  assert.deepEqual(rules, before)
  assert.equal(state.comparison, null)
  assert.deepEqual(state.decisions, {})
})

test('rejects a stale cohort or threshold before any mutation', () => {
  assert.throws(() => planToEditActions(suggestion, [age, hemoglobin], 'other-cohort'), /cohort changed/)
  assert.throws(() => planToEditActions(suggestion, [{ ...age, value_max: 66 }, hemoglobin], suggestion.cohort_id), /no longer matches/)
  assert.equal(age.value_max, 65)
})

test('rejects missing, duplicated, critical, nonfinite and unit-changing edits', () => {
  for (const changed of [{ rule_id: 'UNKNOWN' }, { to: NaN }, { unit: 'months' }, { field: 'value', from: 18, to: 16 }]) {
    assert.throws(() => planToEditActions({ ...suggestion, plan: [{ ...edit, ...changed } as AutopilotEdit] }, [age], suggestion.cohort_id))
  }
  assert.throws(() => planToEditActions({ ...suggestion, plan: [edit, edit] }, [age], suggestion.cohort_id))
  assert.throws(() => planToEditActions({ ...suggestion, plan: [edit] }, [{ ...age, safety_critical: true }], suggestion.cohort_id))
})
