// Tripwire: App.tsx is one very large file that several people edit, and a merge once silently
// restored a hard-coded fixed/generated dropdown, which made the UI ignore the Synthea population.
// If this fails after a merge, re-apply the population wiring in App.tsx (do not "take theirs").
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { defaultPopulationMode } from '../src/workspace.ts'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

test('Responder evidence has its own tab that works without loading a trial', () => {
  assert.ok(app.includes("id: 'responder' as const"), 'sidebar tab for Responder evidence is missing')
  const responderBranch = app.indexOf("tab === 'responder' ?"), needsAnalysis = app.indexOf(': !analysis ?')
  assert.ok(responderBranch > -1 && responderBranch < needsAnalysis, 'Responder tab must render before the "load a trial first" gate')
})

test('historical responder tab hides the synthetic population controls and header badge', () => {
  assert.ok(app.includes("{tab !== 'responder' && <Card className=\"population-controls\">"))
  assert.ok(app.includes("{tab !== 'responder' && <span className=\"demo-pill\">"))
})

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
