import test from 'node:test'
import assert from 'node:assert/strict'
import { compareAttributionRows, formatAttributionRows } from '../src/attribution.ts'
import type { Rule, RuleAttribution } from '../src/scenarioTypes.ts'

const rules = [{ id: 'A', variable: 'hemoglobin' }, { id: 'B', variable: 'platelets' }, { id: 'C', variable: 'age' }] as Rule[]
const row = (id: string, value = 2.5, share = 50): RuleAttribution => ({ rule_id: id, shapley_value: value,
  shapley_share_pct: share, unique_n: 1, total_fail_n: 4, top_overlaps: [] })
const simulation = (attributions: RuleAttribution[], ids = attributions.map(a => a.rule_id)) => ({ attributions, modeled_rule_ids: ids })

test('formats Shapley credit, shares and named overlaps without changing source data', () => {
  const attribution = { ...row('A'), top_overlaps: [{ rule_id: 'B', patient_n: 3 }] }
  const source = simulation([attribution]); const before = JSON.stringify(source)
  const [formatted] = formatAttributionRows(source, rules)
  assert.equal(formatted.name, 'A · hemoglobin')
  assert.equal(formatted.patientLabel, '≈ 2.5 patients')
  assert.equal(formatted.shareLabel, '50.0%')
  assert.equal(formatted.uniqueN, 1)
  assert.equal(formatted.totalFailN, 4)
  assert.equal(formatted.overlapLabel, 'B · platelets (3 patients)')
  assert.equal(JSON.stringify(source), before)
})

test('sorts by Shapley then ID and keeps only modeled rows', () => {
  const rows = formatAttributionRows(simulation([row('B'), row('A'), row('C', 9)], ['A', 'B']), rules)
  assert.deepEqual(rows.map(r => r.ruleId), ['A', 'B'])
})

test('empty, no-modeled and old API responses have no fabricated attribution', () => {
  assert.deepEqual(formatAttributionRows(null, rules), [])
  assert.deepEqual(formatAttributionRows(undefined, rules), [])
  assert.deepEqual(formatAttributionRows({ modeled_rule_ids: ['A'] }, rules), [])
  assert.deepEqual(formatAttributionRows(simulation([], []), rules), [])
  assert.deepEqual(formatAttributionRows(simulation([row('A')], []), rules), [])
})

test('zero exclusions format as zero and no shared failures', () => {
  const [formatted] = formatAttributionRows(simulation([{ ...row('A', 0, 0), unique_n: 0, total_fail_n: 0 }]), rules)
  assert.equal(formatted.patientLabel, '≈ 0 patients')
  assert.equal(formatted.shareLabel, '0.0%')
  assert.equal(formatted.overlapLabel, 'No shared known failures')
})

test('top overlap names fall back to IDs and use count then ID order', () => {
  const overlaps = [{ rule_id: 'Z', patient_n: 2 }, { rule_id: 'Y', patient_n: 3 },
    { rule_id: 'X', patient_n: 2 }, { rule_id: 'W', patient_n: 1 }]
  const [formatted] = formatAttributionRows(simulation([{ ...row('A'), top_overlaps: overlaps }]), rules)
  assert.deepEqual(formatted.overlaps.map(o => o.ruleId), ['Y', 'X', 'Z'])
  assert.match(formatted.overlapLabel, /Y \(3 patients\)/)
})

test('comparison preserves each scenario share and distinguishes unmodeled from zero', () => {
  const rows = compareAttributionRows(simulation([row('A', 2.5, 50), row('B', 2.5, 50)]),
    simulation([row('A', 0, 0), row('C', 2, 100)]), rules)
  const a = rows.find(r => r.ruleId === 'A')!
  assert.equal(a.before?.sharePct, 50)
  assert.equal(a.after?.sharePct, 0)
  assert.equal(a.after?.patientLabel, '≈ 0 patients')
  const b = rows.find(r => r.ruleId === 'B')!
  assert.equal(b.after, null)
  assert.equal(b.afterMissing, 'Not modeled')
  assert.equal(rows.find(r => r.ruleId === 'C')!.before, null)
  assert.deepEqual(compareAttributionRows(simulation([]), simulation([]), rules), [])
})
