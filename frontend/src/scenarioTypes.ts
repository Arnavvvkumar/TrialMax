export type CriterionCategory = 'Patient safety' | 'Scientific validity' | 'Generalizability'
export type CriterionStatus = 'supported' | 'unsupported'

export interface EligibilityCriterion {
  id: string
  name: string
  originalText: string
  parameterLabel?: string
  unit?: string
  value?: number
  min?: number
  max?: number
  step?: number
  editable: boolean
  status: CriterionStatus
  considerations: CriterionCategory[]
  safetyNote: string
}

export interface PatientPopulationSummary {
  total: number
  eligible: number
  excluded: number
  unknown: number
}

export interface CriterionExclusion {
  criterionId: string
  criterionName: string
  before: number
  after: number
}

export interface SimulationResponse {
  source: 'synthetic-mock' | 'backend'
  evaluatedAt: string
  dataSource?: string
  sourceRunId?: string
  baseline: PatientPopulationSummary
  modified: PatientPopulationSummary
  eligibilityPercentagePointChange: number
  exclusionBreakdown: CriterionExclusion[]
  note: string
}
