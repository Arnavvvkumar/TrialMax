import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { checkReviewCohort, reviewImpactRequest } from '../src/reviewImpact.ts'
import type { Workspace } from '../src/workspace.ts'
import type { CompareResult, Rule } from '../src/scenarioTypes.ts'

function fixture(): Workspace {
  const rules = [{id:'ageText',value:18,value_max:80},{id:'ageRegistry',value:80},
    {id:'kidney',value:45}] as Rule[]
  const cohort = {id:'same-cohort',mode:'synthea',version:'test-v1',population_n:1000,seed:null}
  return {context:'test',analysis:{rules} as Workspace['analysis'],
    draft:rules.map(r => r.id==='kidney' ? {...r,value:30} : r.id==='ageText' ? {...r,value_max:85} : {...r,value:85}),
    comparison:{cohort} as CompareResult, decisions:{}}
}
const decision = (value: 'accepted'|'rejected') => ({decision:value,reason:'Reviewed',at:'now'})

test('review impact uses both accepted age edits and the original rejected kidney threshold', () => {
  const workspace=fixture()
  workspace.decisions={ageText:decision('accepted'),ageRegistry:decision('accepted'),kidney:decision('rejected')}
  const original=JSON.stringify(workspace)
  const request=reviewImpactRequest(workspace)!
  assert.equal(request.proposed[0].value_max,85)
  assert.equal(request.proposed[1].value,85)
  assert.equal(request.proposed[2].value,45)
  assert.deepEqual(request.population,{mode:'synthea',size:1000,seed:0,version:'test-v1',cohort_id:'same-cohort'})
  assert.equal(request.baseline[0].value_max,80)
  assert.equal(workspace.draft[2].value,30)
  assert.equal(JSON.stringify(workspace),original)
})

test('no accepted changes and all rejections compare against the original; pending edits are excluded', () => {
  const workspace=fixture()
  assert.deepEqual(reviewImpactRequest(workspace)!.proposed,workspace.analysis!.rules)
  workspace.decisions={ageText:decision('rejected'),kidney:decision('rejected')}
  assert.deepEqual(reviewImpactRequest(workspace)!.proposed,workspace.analysis!.rules)
  workspace.decisions.ageText=decision('accepted')
  const accepted=JSON.stringify(reviewImpactRequest(workspace))
  workspace.decisions.ageText=decision('rejected')
  assert.notEqual(JSON.stringify(reviewImpactRequest(workspace)),accepted)
  assert.equal(reviewImpactRequest({...workspace,comparison:null}),null)
})

test('review comparisons reject mismatched nested cohorts', () => {
  const same={cohort:{id:'same-cohort'}}
  const result={...same,baseline:same,proposed:same} as CompareResult
  assert.equal(checkReviewCohort(result,'same-cohort'),result)
  assert.throws(()=>checkReviewCohort({...result,proposed:{cohort:{id:'other'}}} as CompareResult,'same-cohort'))
})


test('PDF and review summary cannot regress to full-draft impact figures', () => {
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8')
  const review=app.slice(app.indexOf('function Review('),app.indexOf('export default function App()'))
  assert.ok(review.includes('useReviewImpact(workspace)'))
  assert.ok(!review.includes('comparison.proposed.'))
  assert.ok(!review.includes('comparison.modeled_newly_eligible_n'))
  const report=review.slice(review.indexOf('aria-label="TrialMax decision brief"'))
  assert.ok(report.includes('impact?.proposed.modeled_eligible_n'))
  assert.ok(report.includes('impact?.modeled_newly_eligible_n'))
  assert.ok(review.includes('disabled={!allReviewed || !impact || reviewedImpact.pending}'))
})
