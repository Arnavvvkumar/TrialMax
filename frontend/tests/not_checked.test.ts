import test from 'node:test'
import assert from 'node:assert/strict'
import { notCheckedDetail } from '../src/workspace.ts'
import type { Rule } from '../src/scenarioTypes.ts'

const SENTENCE = 'Blood routine test: WBC>=3.5x10^9/L, absolute neutrophil count >=1.5x10^9/L, PLT>=75.0x10^9/L, HGB>=80g/L'
const base: Rule = { id: 'I6a', kind: 'inclusion', text: SENTENCE, clause: SENTENCE, category: 'lab', variable: null, operator: null,
  value: null, value_max: null, unit: null, simulatable: false, fidelity: 'exact', purpose: 'unknown', findability: 'unknown',
  safety_critical: false, parsed_by: 'rules', source: 'text', notes: [] }

test('a parsed rule with no population data names the exact check, not the whole sentence', () => {
  const anc = { ...base, variable: 'anc', operator: '>=' as const, value: 1.5, unit: '10^9/L', simulatable: true }
  const detail = notCheckedDetail(anc, { anc: { label: 'Absolute neutrophil count' } })
  assert.equal(detail.what, 'Absolute neutrophil count >= 1.5 10^9/L')
  assert.equal(detail.badge, 'No data in population')
})

test('an unmodeled part of a sentence shows only that part', () => {
  const wbc = { ...base, id: 'I6i', notes: ['Additional requirement is not modeled: wbc >=3.5 x10^9/l (no cohort field for this lab; not modeled)',
    'Part of criterion I6 that is not modeled.'] }
  const detail = notCheckedDetail(wbc)
  assert.ok(detail.what.startsWith('wbc >=3.5') && !detail.what.includes('Blood routine test'))
  assert.equal(detail.badge, 'Not modeled')
})

test('a word fragment is never shown instead of the sentence', () => {
  const nyha = { ...base, id: 'E5b', kind: 'exclusion' as const, clause: 'Class III or IV heart failure by New York Heart Association (NYHA) Functional Classification',
    notes: ['Additional requirement is not modeled: class iii', 'Part of criterion E5 that is not modeled.'] }
  assert.equal(notCheckedDetail(nyha).what, nyha.clause)
})

test('a rule with no specific part keeps its sentence and its own reason', () => {
  const gfr = { ...base, id: 'I6h', clause: 'Renal function: GFR >= 45 ml/min',
    notes: ['Unit mL/min is not supported for eGFR (CKD-EPI 2021).', 'Part of criterion I6 that is not modeled.'] }
  const detail = notCheckedDetail(gfr)
  assert.equal(detail.what, 'Renal function: GFR >= 45 ml/min')
  assert.equal(detail.reason, 'Unit mL/min is not supported for eGFR (CKD-EPI 2021).')
})
