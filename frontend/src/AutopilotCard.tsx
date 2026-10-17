import { useEffect, useRef, useState } from 'react'
import { LockKeyhole, Sparkles } from 'lucide-react'
import { suggestAutopilot } from './simulationService'
import { planToEditActions } from './autopilot'
import type { AutopilotResponse, PopulationChoice, Rule } from './scenarioTypes'
import type { ThresholdEditAction } from './workspace'
import './autopilot.css'

interface Props {
  rules: Rule[]; population: PopulationChoice; disabled: boolean; llmConfigured: boolean
  onApply: (actions: ThresholdEditAction[]) => void
}

export function AutopilotCard({ rules, population, disabled, llmConfigured, onApply }: Props) {
  const [maxEdits, setMaxEdits] = useState(3), [target, setTarget] = useState(80), [useLlm, setUseLlm] = useState(false)
  const [result, setResult] = useState<{ data: AutopilotResponse; signature: string } | null>(null)
  const [pending, setPending] = useState(false), [error, setError] = useState(''), [applied, setApplied] = useState(false)
  const controller = useRef<AbortController | null>(null), sequence = useRef(0)
  const signature = JSON.stringify({ rules, population, maxEdits, target, useLlm })
  const current = result?.signature === signature ? result.data : null
  useEffect(() => {
    sequence.current++; controller.current?.abort(); setPending(false); setResult(null); setError('')
    return () => { sequence.current++; controller.current?.abort() }
  }, [signature])
  const valid = Number.isInteger(maxEdits) && maxEdits >= 1 && maxEdits <= 5 && Number.isFinite(target) && target >= 50 && target <= 100
  async function suggest() {
    controller.current?.abort()
    const requestId = ++sequence.current, abort = new AbortController()
    controller.current = abort; setPending(true); setResult(null); setApplied(false); setError('')
    try {
      const data = await suggestAutopilot(rules, population, maxEdits, target / 100, useLlm, abort.signal)
      if (abort.signal.aborted || requestId !== sequence.current) return
      if (data.cohort_id !== population.cohort_id) throw new Error('Cohort mismatch. Rerun the baseline before requesting a suggestion.')
      setResult({ data, signature })
    } catch (cause) { if (!abort.signal.aborted && requestId === sequence.current) setError(String(cause)) }
    finally { if (requestId === sequence.current) setPending(false) }
  }
  function apply() {
    if (!current || !population.cohort_id) return
    try {
      const actions = planToEditActions(current, rules, population.cohort_id)
      onApply(actions); setApplied(true)
    } catch (cause) { setError(String(cause)) }
  }
  return <section className="card autopilot-card" aria-label="What-if Autopilot">
    <div className="card-top"><div><h2><Sparkles size={19} /> What-if Autopilot</h2><p>Search from the current draft for a small set of prespecified threshold edits. Every gain comes from the simulator.</p></div></div>
    <p className="autopilot-disclosure">{population.mode === 'synthea' ? 'Synthetic Synthea population.' : 'Synthetic exploration population.'} Suggestions require researcher and clinical review. “Safe” means critical-rule blocks passed; it does not establish treatment safety. PCA is exploratory.</p>
    <div className="autopilot-controls">
      <label>Maximum edits<select aria-label="Autopilot maximum edits" value={maxEdits} onChange={event => setMaxEdits(Number(event.target.value))}>{[1, 2, 3, 4, 5].map(n => <option value={n} key={n}>{n}</option>)}</select></label>
      <label>Target of table maximum (%)<input aria-label="Autopilot target percent" type="number" min={50} max={100} value={Number.isFinite(target) ? target : ''} onChange={event => setTarget(event.target.value === '' ? NaN : Number(event.target.value))} /></label>
      <label className="checkbox-label"><input type="checkbox" checked={useLlm} disabled={!llmConfigured} onChange={event => setUseLlm(event.target.checked)} />Optional Chalk narration</label>
    </div>
    <button className="btn primary" disabled={disabled || pending || !valid} onClick={suggest}>{pending ? 'Searching simulator scenarios…' : 'Suggest smallest safe change'}</button>
    {pending && <p className="muted" role="status">Bounded search on the same synthetic cohort; no edits are being applied.</p>}
    {error && <p className="error-notice" role="alert">{error}</p>}
    {applied && <p className="notice" role="status">Thresholds applied as a draft only. Click Compare draft, then review the proposed changes.</p>}
    {current && <div className="autopilot-results">
      <p>{current.summary}</p><p className="muted">Starting modeled passing: {current.baseline_modeled_eligible_n ?? 'Unavailable'} · All-rule table maximum gain: {current.max_achievable_gain} · Target gain: {current.target_gain} · Simulations: {current.simulation_count}/{current.simulation_cap}</p>
      <p className="muted">{current.reason}</p>
      <h3>Exploratory hidden filters</h3><p className="muted">{current.filters.disclosure}</p>
      {current.filters.components.length ? current.filters.components.map(filter => <div className="autopilot-filter" key={filter.component}>
        <div><span>{filter.label}</span><strong>{(100 * filter.explained_variance_ratio).toFixed(1)}% variance</strong></div>
        <div className="autopilot-bar"><span style={{ width: `${100 * filter.explained_variance_ratio}%` }} /></div>
      </div>) : <p className="muted">No varying known-failure patterns are available for PCA.</p>}
      {current.filters.redundancy_pairs.length > 0 && <details><summary>Overlapping failure patterns ({current.filters.redundancy_pairs.length} pairs)</summary><ul>{current.filters.redundancy_pairs.slice(0, 12).map(pair => <li key={`${pair.rule_a_id}-${pair.rule_b_id}`}>{pair.rule_a_id} / {pair.rule_b_id} · Jaccard {(pair.jaccard * 100).toFixed(1)}%. {pair.explanation}</li>)}</ul></details>}
      <h3>Proposed threshold edits</h3>
      {current.plan.length ? <ol className="autopilot-plan">{current.plan.map(edit => <li key={edit.rule_id}>
        <strong>{edit.rule_id} · {edit.variable.replaceAll('_', ' ')}</strong><p>{edit.field === 'value_max' ? 'Upper bound' : 'Threshold'}: <del>{edit.from}</del> → <ins>{edit.to}</ins> {edit.unit === 'x_uln' ? '× ULN' : edit.unit}</p>
        <p>+{edit.marginal_gain} passing modeled checks · cumulative +{edit.cumulative_gain}</p>
        <span className={`badge ${edit.review_flag ? 'amber' : 'gray'}`}>{edit.review_flag ? 'Clinical review required' : 'Researcher review required'}</span>
        <p className="muted">{edit.component_label}</p><p>{edit.rationale}</p>
      </li>)}</ol> : <p>No eligible suggestion. {current.reason}</p>}
      {current.plan.length > 0 && <button className="btn outline" disabled={disabled || pending} onClick={apply}>Apply as draft</button>}
      <h3>Blocked safety rules</h3>{current.blocked_rules.length ? <ul className="autopilot-blocked">{current.blocked_rules.map(rule => <li key={rule.rule_id}><LockKeyhole size={16} aria-label="Locked" /><span><b>{rule.rule_id} · {rule.label}</b> — {rule.reason}</span></li>)}</ul> : <p className="muted">No critical rules were identified in this input. Clinical review is still required.</p>}
      <details><summary>Other candidates considered</summary><ul>{current.also_considered.map((item, i) => <li key={i}>{item.rule_id}{item.to !== null ? ` → ${item.to}` : ''}{item.gain !== null ? ` (single-edit gain ${item.gain})` : ''}: {item.reason}</li>)}</ul></details>
      <details><summary>Assumptions and search limits</summary><ul>{[...current.assumptions, ...current.warnings].map((text, i) => <li key={i}>{text}</li>)}</ul></details>
    </div>}
  </section>
}
