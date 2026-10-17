// Tripwire: App.tsx is one very large file that several people edit, and a merge once silently
// restored a hard-coded fixed/generated dropdown, which made the UI ignore the Synthea population.
// If this fails after a merge, re-apply the population wiring in App.tsx (do not "take theirs").
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { defaultPopulationMode } from '../src/workspace.ts'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

test('population dropdown is built from the API catalog, not hard-coded', () => {
  assert.ok(app.includes('catalog?.options'), 'dropdown must list the options returned by /api/populations')
  assert.ok(!app.includes('<option value="fixed">'), 'hard-coded "fixed" option is back')
  assert.ok(!app.includes('<option value="generated">'), 'hard-coded "generated" option is back')
  assert.ok(!app.includes("as 'fixed' | 'generated'"), 'population mode must use the PopulationMode type')
})

test('fixed-size populations take size and seed from the catalog, not only mode === fixed', () => {
  assert.ok(app.includes("mode !== 'generated'"), 'size/seed/validity must treat every non-generated mode as catalog-defined')
  assert.ok(!app.includes("mode === 'fixed' || ("), 'populationValid regressed to the fixed-only check')
})

test('Synthea is the default population for every source', () => {
  assert.equal(defaultPopulationMode('nct'), 'synthea')
  assert.equal(defaultPopulationMode('text'), 'synthea')
})
