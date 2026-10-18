import test from 'node:test'
import assert from 'node:assert/strict'
import { agentVerdict, effectLabel, evaluationHeadline, evidenceSuggestion, expectedFlag, forestInterval, hostedResponderValidation, overallStat, plotPosition, pooledMetric, responderMetrics, subgroupEvidenceLabel, subgroupStatus } from '../src/responder.ts'
import type { ResponderEffect, ResponderResponse, ResponderRun, ResponderSubgroup } from '../src/responderTypes.ts'

const effect = (hr: number | null, low: number | null, high: number | null): ResponderEffect => ({hr,ci_low:low,ci_high:high,p:null,status:'ok'})
const group = (id: string, truth_label: ResponderSubgroup['truth_label'], interaction_q: number | null = null, underpowered = false) =>
  ({id, label: `Group ${id}`, truth_label, interaction_q, underpowered, hr_subgroup: effect(.7,.5,.9)}) as ResponderSubgroup

test('subgroup status names the reference label in plain language', () => {
  assert.deepEqual(subgroupStatus(group('A','weaker_benefit')), {text:'Benefits less',tone:'red'})
  assert.deepEqual(subgroupStatus(group('A','stronger_benefit',.05)), {text:'Benefits more',tone:'sage'})
  assert.deepEqual(subgroupStatus(group('A','stronger_benefit',.05,true)), {text:'Too few events',tone:'amber'})
  assert.deepEqual(subgroupStatus(group('A','weaker_benefit',.05,true)), {text:'Too few events',tone:'amber'})
  assert.deepEqual(subgroupStatus(group('A','no_reliable_difference',.4,true)), {text:'Too few events',tone:'amber'})
  assert.deepEqual(subgroupStatus(group('A','no_reliable_difference',.4)), {text:'No difference',tone:'gray'})
  assert.equal(subgroupStatus({...group('A','weaker_benefit'), hr_subgroup:{...effect(null,null,null),status:'unestimable'}}).text, 'Not estimable')
})

test('expected flag is the weaker-benefit group with the smallest q, never a stronger-benefit group', () => {
  assert.equal(expectedFlag([group('A','no_reliable_difference'), group('B','stronger_benefit',.01)]), null)
  assert.equal(expectedFlag([group('C','weaker_benefit',.08), group('B','weaker_benefit',.02), group('A','weaker_benefit',.02)]), 'A')
  assert.equal(expectedFlag([group('A','weaker_benefit',.01,true)]), null)
})

test('overall stat claims a direction only when the whole CI is on one side of HR 1', () => {
  const endpoint = 'Overall survival (death)'
  assert.deepEqual(overallStat({endpoint, overall:effect(.689,.546,.869)}), {value:'−31%', caption:'risk of death', verdict:'Helps', tone:'sage'})
  assert.deepEqual(overallStat({endpoint, overall:effect(1.02,.71,1.45)}), {value:'+2%', caption:'risk of death', verdict:'No clear effect', tone:'gray'})
  assert.equal(overallStat({endpoint, overall:effect(1.5,1.1,2)}).verdict, 'Harms')
  assert.equal(overallStat({endpoint:'Survival', overall:effect(null,null,null)}).caption, 'risk of the outcome')
})

test('agent verdict compares the AI with the reference answer', () => {
  const data = (subgroups: ResponderSubgroup[], flag: string | null, invalid = false) =>
    ({evidence:{subgroups}, suggestion:{flag, invalid}}) as unknown as ResponderResponse
  assert.equal(agentVerdict(data([group('A','no_reliable_difference')], null)), 'agrees')
  assert.equal(agentVerdict(data([group('A','weaker_benefit',.01)], 'A')), 'agrees')
  assert.equal(agentVerdict(data([group('A','no_reliable_difference')], 'A')), 'disagrees')
  assert.equal(agentVerdict(data([group('A','weaker_benefit',.01)], null)), 'disagrees')
  assert.equal(agentVerdict(data([], null, true)), 'unavailable')
})

test('chart scale is symmetric around HR 1 and clamps extremes', () => {
  assert.equal(plotPosition(1), 50)
  assert.equal(plotPosition(.5) + plotPosition(2), 100)
  assert.deepEqual([plotPosition(.001), plotPosition(1000)], [0, 100])
})

test('evaluation headline pools counts by denominator and discloses missing planted targets', () => {
  const run = (prompt_variant: string, variant: string, n: number, abstain: number | null, abstainN: number, detectable = 0) =>
    ({prompt_variant, variant, n, detectable_planted_n: detectable, scores:{abstains_when_null:abstain, number_fidelity:1}, denominators:{abstains_when_null:abstainN, number_fidelity:n}}) as ResponderRun
  const runs = [run('names_only','originals',3,1,3), run('names_only','planted',9,5/6,6), run('with_stats','originals',3,1,3), run('with_stats','planted',9,1,6)]
  assert.deepEqual(pooledMetric(runs, 'abstains_when_null'), {passed:17, total:18})
  assert.equal(pooledMetric(runs, 'missing_metric'), null)
  const head = evaluationHeadline({status:'complete', runs})
  assert.deepEqual([head.cases, head.answers, head.realNumbers, head.validJson, head.noPlantedTargets], [12, 24, {passed:24,total:24}, null, true])
  assert.equal(evaluationHeadline({status:'complete', runs: runs.map(r => ({...r, detectable_planted_n: 2}))}).noPlantedTargets, false)
})

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

test('underpowered subgroups always have the conservative decision label', () => {
  assert.equal(subgroupEvidenceLabel({underpowered:true,truth_label:'stronger_benefit'}),'no reliable difference')
  assert.equal(subgroupEvidenceLabel({underpowered:true,truth_label:'weaker_benefit'}),'no reliable difference')
  assert.equal(subgroupEvidenceLabel({underpowered:false,truth_label:'stronger_benefit'}),'stronger benefit')
})

test('claim metrics distinguish prior prose, raw AI output and displayed explanations', () => {
  assert.ok(responderMetrics.some(([metric])=>metric==='claim_consistency'))
  assert.ok(responderMetrics.some(([metric])=>metric==='raw_claim_consistency'))
  assert.ok(responderMetrics.some(([metric])=>metric==='legacy_claim_consistency'))
})
