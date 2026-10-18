import test from 'node:test'
import assert from 'node:assert/strict'
import { effectLabel, evidenceSuggestion, forestInterval, hostedResponderValidation } from '../src/responder.ts'
import type { ResponderEffect, ResponderResponse } from '../src/responderTypes.ts'

const effect = (hr: number | null, low: number | null, high: number | null): ResponderEffect => ({hr,ci_low:low,ci_high:high,p:null,status:'ok'})

test('forest intervals use a log scale centered on HR one and clip transparently', () => {
  const row = forestInterval(effect(1,.1,10))!
  assert.deepEqual(row, {point:50,left:0,right:100,clipped:false})
  assert.deepEqual(forestInterval(effect(1,.001,1000)), {...row,clipped:true})
  assert.equal(effectLabel(effect(.5,.2,.9)), '0.50 (95% CI 0.20–0.90)')
})

test('unestimable, zero and nonfinite effects never produce plot positions', () => {
  assert.equal(effectLabel(effect(null,null,null)), 'Not estimable')
  for (const value of [null,0,-1,NaN,Infinity]) assert.equal(forestInterval(effect(value,.2,.9)), null)
})

test('hosted validation requires four completed real run and evaluation IDs', () => {
  const runs = Array.from({length:4}, () => ({run_id:'run',evaluation_id:'eval',status:'EvaluationRunStatus.SUCCEEDED'})) as ResponderResponse['evaluations']['runs']
  assert.equal(hostedResponderValidation({status:'complete',runs}), true)
  assert.equal(hostedResponderValidation({status:'local_only',runs}), false)
  assert.equal(hostedResponderValidation({status:'complete',runs:runs.slice(1)}), false)
  assert.equal(hostedResponderValidation({status:'complete',runs:[{...runs[0],run_id:undefined},...runs.slice(1)]}), false)
})

test('agent display distinguishes abstention, invalid output and subgroup direction', () => {
  const data = {evidence:{subgroups:[{id:'A',label:'Older adults'}]},suggestion:{invalid:false,flag:null,direction:null}} as ResponderResponse
  assert.match(evidenceSuggestion(data), /No subgroup flagged/)
  data.suggestion.invalid = true
  assert.match(evidenceSuggestion(data), /failed validation/)
  data.suggestion.invalid = false; data.suggestion.flag = 'A'; data.suggestion.direction = 'weaker_benefit'
  assert.match(evidenceSuggestion(data), /not a protocol-change recommendation/)
  data.suggestion.direction = 'stronger_benefit'
  assert.match(evidenceSuggestion(data), /not an exclusion candidate/)
  data.suggestion.flag = 'UNKNOWN'
  assert.match(evidenceSuggestion(data), /no suggestion is usable/)
})
