import { useEffect, useRef, useState } from 'react'
import { getResponderEvidence } from './simulationService'
import { effectLabel, evidenceSuggestion, forestInterval, hostedResponderValidation } from './responder'
import type { ResponderEffect, ResponderResponse } from './responderTypes'
import './responder.css'

function Interval({ effect, tone }: { effect: ResponderEffect; tone: string }) {
  const interval = forestInterval(effect)
  return <div className={`responder-interval ${tone}`}><span>{tone === 'in' ? 'In subgroup' : 'Complement'}: {effectLabel(effect)}</span>
    {interval && <svg viewBox="0 0 100 12" role="img" aria-label={`${effectLabel(effect)}${interval.clipped ? '; confidence interval clipped to plot range' : ''}`}>
      <line x1="50" x2="50" y1="0" y2="12" className="responder-null" /><line x1={interval.left} x2={interval.right} y1="6" y2="6" />
      <line x1={interval.left} x2={interval.left} y1="3" y2="9" /><line x1={interval.right} x2={interval.right} y1="3" y2="9" /><circle cx={interval.point} cy="6" r="2" />
    </svg>}{interval?.clipped && <small>CI extends beyond plot range</small>}</div>
}

export function ResponderCard() {
  const [trial, setTrial] = useState('colon'), [data, setData] = useState<ResponderResponse | null>(null)
  const [pending, setPending] = useState(false), [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => { controller.current?.abort(); setData(null); setPending(false); setError(''); return () => controller.current?.abort() }, [trial])
  async function load() {
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort
    setPending(true); setError(''); setData(null)
    try {
      const result = await getResponderEvidence(trial, abort.signal)
      if (abort.signal.aborted) return
      if (result.evidence.trial_key !== trial || result.evidence.variant !== 'original') throw new Error('Historical case mismatch')
      setData(result)
    } catch (cause) { if (!abort.signal.aborted) setError(String(cause)) }
    finally { if (!abort.signal.aborted) setPending(false) }
  }
  const validated = data && hostedResponderValidation(data.evaluations)
  return <section className="card responder-card" aria-label="Responder evidence">
    <div className="card-top"><div><h2>{validated ? 'Responder evidence (validated method)' : 'Responder evidence (method validation pending)'}</h2>
      <p>Separate historical benchmark. These findings do not describe the loaded trial or the synthetic eligibility cohort.</p></div></div>
    <div className="responder-controls"><label>Historical trial<select aria-label="Historical responder trial" value={trial} onChange={event => setTrial(event.target.value)}>
      <option value="colon">Colon: Lev+5FU versus observation</option><option value="veteran">Veteran: test versus standard</option><option value="gbsg">GBSG: hormonal therapy (weaker evidence)</option>
    </select></label><button className="btn outline" disabled={pending} onClick={load}>{pending ? 'Reviewing aggregate evidence…' : 'Load responder evidence'}</button></div>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {data && <>
      <div className="warning-box"><div><strong>Exploratory efficacy evidence; researcher decides.</strong><p>Old trials, multiplicity-adjusted subgroup comparisons, no treatment-safety assessment. {validated ? 'Completed evaluation runs do not establish clinical validity.' : 'Hosted validation is not complete.'}</p>
        {data.evidence.trial_key === 'gbsg' && <strong>Partly non-randomized treatment assignment: weaker evidence.</strong>}</div></div>
      <p><b>{data.evidence.trial_name}</b> · {data.evidence.endpoint} · n={data.evidence.n} · events={data.evidence.events}</p>
      <p>{data.evidence.treatment} versus {data.evidence.control}. Overall HR: {effectLabel(data.evidence.overall)}.</p>
      <div className="responder-layout"><div><h3>Subgroup effects</h3><p className="muted">HRs compare treatment with control within each group. Use the interaction q-value to assess differences. Plot uses a log scale, 0.1–10; vertical line is HR=1.</p>
        {data.evidence.subgroups.map(row => <article className="responder-row" key={row.id}>
          <div className="responder-row-heading"><strong>{row.label}</strong><span className="badge gray">{row.truth_label.replaceAll('_', ' ')}</span>{row.underpowered && <span className="badge amber">Underpowered</span>}</div>
          <Interval effect={row.hr_subgroup} tone="in" /><Interval effect={row.hr_complement} tone="out" />
          <p className="muted">Interaction HR {effectLabel(row.interaction)} · p={row.interaction.p?.toPrecision(3) ?? 'unavailable'} · BH q={row.interaction_q?.toPrecision(3) ?? 'unavailable'}</p>
          <details><summary>Arm counts and missingness</summary><p>Subgroup: treated {row.subgroup.treatment_n} ({row.subgroup.treatment_events} events), control {row.subgroup.control_n} ({row.subgroup.control_events} events). Complement: treated {row.complement.treatment_n} ({row.complement.treatment_events} events), control {row.complement.control_n} ({row.complement.control_events} events). Missing subgroup values: {row.missing_n}.</p></details>
        </article>)}</div><aside className="responder-agent"><h3>Chalk-hosted agent suggestion</h3><p>{evidenceSuggestion(data)}</p><p>{data.suggestion.rationale || 'No validated rationale available.'}</p><span className="badge amber">Confidence: {data.suggestion.confidence}</span><p className="muted">Reference labels are deterministic statistical labels. The agent never receives these labels or patient-level rows. Nothing is applied to the protocol.</p></aside></div>
      <h3>{validated ? 'Chalk evaluation scores' : 'Evaluation status / local scores'}</h3>
      <p className="muted">Mode: {data.evaluations.mode ?? data.evaluations.status}. {data.evaluations.message}</p>
      <div className="table-scroll"><table className="responder-scores"><thead><tr><th>Prompt / cases</th><th>Correct flag</th><th>No overclaim</th><th>Null abstention</th><th>Planted recall</th><th>Number fidelity</th><th>JSON valid</th></tr></thead><tbody>{data.evaluations.runs.map(run => <tr key={`${run.prompt_variant}-${run.variant}`}>
        <td>{run.prompt_variant} / {run.variant} (n={run.n}){run.run_id && <small>Run: {run.run_id}</small>}</td>{['correct_flag','no_overclaim','abstains_when_null','planted_recall','number_fidelity','json_valid'].map(metric => <td key={metric}>{run.scores[metric] == null ? 'N/A' : `${(100 * run.scores[metric]!).toFixed(1)}%`}<small>n={run.denominators[metric] ?? 0}</small></td>)}</tr>)}</tbody></table></div>
      {data.evaluations.runs.some(run => run.variant === 'planted' && run.detectable_planted_n === 0) && <p className="warning-box">No detectable planted targets in this frozen snapshot. These scores cannot establish positive-case responder sensitivity or that statistics improved the agent.</p>}
      <details><summary>Sources and limitations</summary><p>{data.evidence.provenance.citation}</p>{data.evidence.provenance.publication_url && <a href={data.evidence.provenance.publication_url} target="_blank" rel="noreferrer">Trial source ↗</a>}<ul>{[...new Set([...data.disclaimers,...(data.evaluations.limitations ?? [])])].map(text => <li key={text}>{text}</li>)}</ul></details>
    </>}
  </section>
}
