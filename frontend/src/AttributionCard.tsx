import type { Rule, SimulationResult } from './scenarioTypes'
import { compareAttributionRows, formatAttributionRows } from './attribution'
import './attribution.css'

const explainer = 'Each excluded patient counts once, split equally among every rule that excludes them, so the ranking does not depend on rule order.'
const caveat = 'Attribution of exclusions in a synthetic population; Trial Pathfinder attributed survival outcomes on real-world data.'

export function AttributionCard({ result, rules }: { result: SimulationResult; rules: Rule[] }) {
  const rows = formatAttributionRows(result, rules)
  const largest = rows[0]?.shapleyValue > 0 ? rows[0] : null
  return <section className="card attribution-card" aria-label="Order-independent impact (Shapley)">
    <div className="card-top"><div><h2>Order-independent impact (Shapley)</h2><p>{explainer}</p></div>
      {largest && <span className="badge amber">Largest impact: {largest.ruleId}</span>}
    </div>
    <p className="attribution-caveat">{caveat}</p>
    <p className="muted">{result.attribution_total_excluded ?? 'Unavailable'} known exclusions allocated. Fractional counts are exclusion credit, not additional patients who would qualify after an edit.</p>
    {!rows.length ? <p className="empty-state">{result.modeled_rule_ids.length ? 'Attribution is unavailable. Rerun the analysis with the current backend.' : 'No modeled rules are available for attribution.'}</p>
      : <>{!largest && <p className="muted">No known exclusions; every rule has zero attribution.</p>}<div className="attribution-rows">{rows.map(row => <div className="attribution-row" key={row.ruleId}>
        <div className="attribution-heading"><strong>{row.name}</strong><span>{row.patientLabel} ({row.shareLabel} of all exclusions)</span></div>
        <div className="attribution-track" role="img" aria-label={`${row.name}: ${row.shareLabel} of known exclusions`}><span style={{ width: `${Math.max(0, Math.min(100, row.sharePct))}%` }} /></div>
        <p>Only this rule: {row.uniqueN.toLocaleString()} · Total known failures: {row.totalFailN.toLocaleString()}</p>
        <p className="muted">Shares most with: {row.overlapLabel}</p>
      </div>)}</div></>}
  </section>
}

export function AttributionComparison({ baseline, proposed, baselineRules, proposedRules }: { baseline: SimulationResult; proposed: SimulationResult; baselineRules: Rule[]; proposedRules: Rule[] }) {
  const rows = compareAttributionRows(baseline, proposed, baselineRules, proposedRules)
  return <section className="card attribution-card" aria-label="Shapley attribution before and after">
    <div className="card-top"><div><h2>Shapley attribution before and after</h2><p>{explainer}</p></div></div>
    <p className="attribution-caveat">{caveat}</p>
    <p className="muted">Each share uses that scenario's own exclusion total: baseline {baseline.attribution_total_excluded ?? 'unavailable'}, draft {proposed.attribution_total_excluded ?? 'unavailable'}. A share can rise while its attributed count falls. These are baseline-versus-draft results, not acceptance decisions.</p>
    {rows.length ? <div className="table-scroll"><table className="attribution-table"><thead><tr><th>Rule</th><th>Baseline attribution / share</th><th>Draft attribution / share</th></tr></thead><tbody>{rows.map(row => <tr key={row.ruleId}>
      <td>{row.name}</td><td>{row.before ? `${row.before.patientLabel} · ${row.before.shareLabel}` : row.beforeMissing}</td>
      <td>{row.after ? `${row.after.patientLabel} · ${row.after.shareLabel}` : row.afterMissing}</td>
    </tr>)}</tbody></table></div> : <p className="empty-state">No attribution is available for this comparison.</p>}
  </section>
}
