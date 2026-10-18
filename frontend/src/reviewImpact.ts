import { reviewedRules } from './workspace.ts'
import type { Workspace } from './workspace.ts'
import type { CompareResult, PopulationChoice } from './scenarioTypes.ts'

export function reviewImpactRequest(workspace: Workspace) {
  if (!workspace.analysis || !workspace.comparison) return null
  const cohort = workspace.comparison.cohort
  const population: PopulationChoice = { mode: cohort.mode, size: cohort.population_n,
    seed: cohort.seed ?? 0, version: cohort.version, cohort_id: cohort.id }
  return { baseline: workspace.analysis.rules, proposed: reviewedRules(workspace), population }
}

export function checkReviewCohort(result: CompareResult, cohortId: string) {
  if ([result.cohort.id, result.baseline.cohort.id, result.proposed.cohort.id].some(id => id !== cohortId)) {
    throw new Error('Reviewed comparison returned a different cohort. Rerun the baseline.')
  }
  return result
}
