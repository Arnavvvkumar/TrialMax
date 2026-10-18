import { useEffect, useState } from 'react'
import { compareCriteria } from './simulationService'
import { checkReviewCohort, reviewImpactRequest } from './reviewImpact'
import type { Workspace } from './workspace'
import type { CompareResult } from './scenarioTypes'

export function useReviewImpact(workspace: Workspace) {
  const request = reviewImpactRequest(workspace)
  const signature = JSON.stringify(request)
  const [attempt, setAttempt] = useState(0)
  const key = `${attempt}:${signature}`
  const [state, setState] = useState<{ key: string; result: CompareResult | null; error: string } | null>(null)
  useEffect(() => {
    if (!request) return
    const abort = new AbortController()
    compareCriteria(request.baseline, request.proposed, request.population, abort.signal)
      .then(result => {
        if (!abort.signal.aborted) setState({ key, result: checkReviewCohort(result, request.population.cohort_id!), error: '' })
      }).catch(cause => {
        if (!abort.signal.aborted) setState({ key, result: null, error: String(cause) })
      })
    return () => abort.abort()
  }, [key])
  // Never render a previous accepted set's numbers while its replacement is loading.
  const current = state?.key === key ? state : null
  return { result: current?.result ?? null, error: current?.error ?? '',
    pending: Boolean(request && !current), retry: () => setAttempt(value => value + 1) }
}
