import type { ReactNode } from 'react'
import type { CompareResult } from './scenarioTypes'
import './scenarioReport.css'

interface Props {
  result: CompareResult
  comparison: ReactNode
  shapley: ReactNode
  fullResults: ReactNode
  onReview: () => void
}

const count = (value: number | null) => value == null ? 'Unavailable' : value.toLocaleString()

export function ScenarioReport({ result, comparison, shapley, fullResults, onReview }: Props) {
  const delta = result.modeled_eligible_change_pct_points
  return <section className="card scenario-report" aria-label="Saved draft comparison">
    <div className="card-top"><div><h2>Saved draft comparison</h2><p>Original protocol versus the current draft, on the same synthetic patients.</p></div><span className="badge gray">Compared draft</span></div>
    <p className="muted">Applying an Autopilot suggestion generates this report automatically. Manual edits need Compare draft. Searching alone does not change the draft.</p>
    <div className="scenario-report-summary">
      <div><span>Passing modeled checks</span><strong>{count(result.baseline.modeled_eligible_n)} → {count(result.proposed.modeled_eligible_n)}</strong></div>
      <div><span>Change</span><strong>{delta === null ? 'Unavailable' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)} pp`}</strong></div>
      <div><span>Newly passing</span><strong>{count(result.modeled_newly_eligible_n)}</strong></div>
    </div>
    <p className="muted">Excluded: {count(result.baseline.excluded_n)} → {count(result.proposed.excluded_n)} · Unknown on modeled checks: {count(result.baseline.modeled_unknown_n)} → {count(result.proposed.modeled_unknown_n)}. Unchecked requirements remain outside these counts.</p>
    {result.safety_review_rule_ids.length > 0 && <p className="scenario-report-safety" role="status">Safety-sensitive changes require review: {result.safety_review_rule_ids.join(', ')}. More passing patients does not establish safety.</p>}
    <div className="scenario-report-sections">
      {shapley}
      <details className="results-section"><summary>Full baseline versus draft comparison</summary>{comparison}</details>
      <details className="results-section"><summary>Full modified results, funnel and patient details</summary>{fullResults}</details>
    </div>
    <button className="btn primary" onClick={onReview}>Review proposed changes</button>
  </section>
}
