import type { EligibilityCriterion, SimulationResponse } from './scenarioTypes'

export const demoCriteria: EligibilityCriterion[] = [
  {
    id: 'E01',
    name: 'ECOG performance status',
    originalText: 'ECOG performance status of 0–1',
    editable: false,
    status: 'unsupported',
    considerations: ['Patient safety', 'Scientific validity'],
    safetyNote: 'Functional status can affect treatment tolerance and endpoint interpretation. This criterion is not editable in the demo.',
  },
  {
    id: 'E02',
    name: 'EGFR mutation requirement',
    originalText: 'Documented EGFR mutation positive',
    editable: false,
    status: 'unsupported',
    considerations: ['Scientific validity', 'Generalizability'],
    safetyNote: 'Biomarker changes can alter the study population and the treatment response being measured. This criterion is not editable in the demo.',
  },
  {
    id: 'E03',
    name: 'Age requirement',
    originalText: 'Age 18 to 70 years',
    parameterLabel: 'Maximum age',
    unit: 'years',
    value: 70,
    min: 50,
    max: 90,
    step: 1,
    editable: true,
    status: 'supported',
    considerations: ['Patient safety', 'Generalizability', 'Scientific validity'],
    safetyNote: 'Changing age limits may affect comorbidity burden, treatment tolerance, consent considerations, and whether results generalize to the intended population.',
  },
  {
    id: 'E04',
    name: 'Hemoglobin threshold',
    originalText: 'Hemoglobin ≥ 10 g/dL',
    parameterLabel: 'Minimum hemoglobin',
    unit: 'g/dL',
    value: 10,
    min: 8,
    max: 13,
    step: 0.5,
    editable: true,
    status: 'supported',
    considerations: ['Patient safety', 'Scientific validity'],
    safetyNote: 'Lower hemoglobin thresholds may increase anemia-related risk and affect treatment tolerance. A qualified clinician must review any change.',
  },
  {
    id: 'E05',
    name: 'Prior systemic therapy',
    originalText: 'No more than 2 prior lines of systemic therapy',
    editable: false,
    status: 'unsupported',
    considerations: ['Scientific validity', 'Generalizability'],
    safetyNote: 'Treatment history can change prognosis and response patterns. This criterion is not editable in the demo.',
  },
  {
    id: 'E06',
    name: 'Renal function',
    originalText: 'eGFR ≥ 45 mL/min/1.73 m²',
    parameterLabel: 'Minimum eGFR',
    unit: 'mL/min/1.73 m²',
    value: 45,
    min: 30,
    max: 60,
    step: 5,
    editable: true,
    status: 'supported',
    considerations: ['Patient safety', 'Scientific validity', 'Generalizability'],
    safetyNote: 'Renal function may affect drug clearance and toxicity. Relaxing this threshold requires pharmacology and clinical safety review.',
  },
]

const baseline = { total: 500, eligible: 28, excluded: 450, unknown: 22 }
const baseExclusions = [
  { criterionId: 'E01', criterionName: 'ECOG performance status', before: 168 },
  { criterionId: 'E02', criterionName: 'EGFR mutation requirement', before: 124 },
  { criterionId: 'E03', criterionName: 'Age requirement', before: 68 },
  { criterionId: 'E04', criterionName: 'Hemoglobin threshold', before: 54 },
  { criterionId: 'E05', criterionName: 'Prior systemic therapy', before: 36 },
  { criterionId: 'E06', criterionName: 'Renal function', before: 22 },
]

export function buildMockSimulation(criteria: EligibilityCriterion[]): SimulationResponse {
  const age = criteria.find((criterion) => criterion.id === 'E03')?.value ?? 70
  const hemoglobin = criteria.find((criterion) => criterion.id === 'E04')?.value ?? 10
  const egfr = criteria.find((criterion) => criterion.id === 'E06')?.value ?? 45
  const addedEligible = Math.max(0, Math.round((age - 70) * 1.8 + (10 - hemoglobin) * 8 + (45 - egfr) * 0.35))
  const eligible = Math.min(126, baseline.eligible + addedEligible)
  const excluded = baseline.excluded - addedEligible

  return {
    source: 'synthetic-mock',
    evaluatedAt: new Date().toISOString(),
    baseline,
    modified: { total: baseline.total, eligible, excluded, unknown: baseline.unknown },
    eligibilityPercentagePointChange: Number(((eligible / baseline.total - baseline.eligible / baseline.total) * 100).toFixed(1)),
    exclusionBreakdown: baseExclusions.map((item) => ({
      ...item,
      after: item.criterionId === 'E03' ? Math.max(0, item.before - Math.max(0, Math.round((age - 70) * 1.8))) : item.before,
    })),
    note: 'Synthetic demonstration only. These figures are not calculated from a real patient cohort and are not clinical evidence.',
  }
}
