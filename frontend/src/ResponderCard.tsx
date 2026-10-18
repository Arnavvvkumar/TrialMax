import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleHelp, MinusCircle, XCircle } from 'lucide-react'
import { getResponderEvidence } from './simulationService'
import { agentVerdict, effectLabel, evaluationHeadline, evidenceSuggestion, hostedResponderValidation, overallStat, PLOT_TICKS, plotPosition, priorProseAudit, responderMetrics, shortName, subgroupStatus } from './responder'
import type { Tone } from './responder'
import type { ResponderResponse, ResponderSubgroup } from './responderTypes'
import './responder.css'

const TONE_ICON = { sage: CheckCircle2, red: AlertTriangle, amber: CircleHelp, gray: MinusCircle }

function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const Icon = TONE_ICON[tone]
  return <span className={`badge ${tone}`}><Icon size={13} />{children}</span>
}

function Tile({ label, value, sub, chip }: { label: string; value: React.ReactNode; sub: string; chip?: React.ReactNode }) {
  return <section className="card responder-tile"><span className="stat-label">{label}</span><strong>{value}</strong><p>{sub}</p>{chip}</section>
}

// ---------------------------------------------------------------- difference chart

const pct = (value: number) => `${plotPosition(value)}%`

// One mark per group: the interaction ratio (group's HR ÷ everyone else's HR). Left of 1 = the drug
// works better in the group, right = worse. Only groups that survive multiplicity correction get color.
function DifferenceMark({ row, tone }: { row: ResponderSubgroup; tone: Tone }) {
  const { hr, ci_low, ci_high } = row.interaction
  if (hr === null || ci_low === null || ci_high === null || hr <= 0 || ci_low <= 0) return <span className="forest-missing">Not estimable</span>
  const tip = `Difference vs everyone else: ${effectLabel(row.interaction)} · in group HR ${effectLabel(row.hr_subgroup)} · everyone else HR ${effectLabel(row.hr_complement)} · BH q ${row.interaction_q?.toPrecision(2) ?? 'n/a'}`
  return <div className={`forest-mark diff ${tone}`} title={tip}>
    <i className="forest-range" style={{ left: pct(ci_low), width: `calc(${pct(ci_high)} - ${pct(ci_low)})` }} />
    {ci_low < 1 / 8 && <i className="forest-clip left">◀</i>}{ci_high > 8 && <i className="forest-clip right">▶</i>}
    <i className="forest-point" style={{ left: pct(hr) }} />
  </div>
}

function ForestChart({ rows }: { rows: ResponderSubgroup[] }) {
  return <div className="forest" role="img" aria-label="How much better or worse the drug works in each patient group than in everyone else">
    <div className="forest-row forest-head"><span /><div className="forest-zones"><span>◀ Works better in group</span><span>Works worse in group ▶</span></div><span /></div>
    {rows.map(row => { const status = subgroupStatus(row); return <div className={`forest-row ${status.tone === 'amber' ? 'is-faint' : ''}`} key={row.id}>
      <span className="forest-label" title={row.label}>{row.label}</span>
      <div className="forest-track"><i className="forest-null" /><DifferenceMark row={row} tone={status.tone} /></div>
      <Chip tone={status.tone}>{status.text}</Chip>
    </div> })}
    <div className="forest-row forest-axis"><span /><div className="forest-ticks">{PLOT_TICKS.map(tick => <span key={tick} style={{ left: pct(tick) }}>{tick === 1 ? 'Same' : tick}</span>)}</div><span /></div>
    <div className="forest-legend"><span><i className="key-diff" />Difference vs everyone else</span><span><i className="key-range" />Uncertainty range</span><span><i className="key-null" />Works the same</span><span className="forest-note">Colored only when reliable after correcting for testing many groups · hover a mark for numbers</span></div>
  </div>
}

// ---------------------------------------------------------------- AI report card

function Meter({ label, tally }: { label: string; tally: { passed: number; total: number } | null }) {
  if (!tally) return null
  return <div className="responder-meter"><span>{label}</span><div className="meter-track"><i style={{ width: `${100 * tally.passed / tally.total}%` }} /></div><b>{tally.passed}/{tally.total}</b></div>
}

function ReportCard({ evaluations }: { evaluations: ResponderResponse['evaluations'] }) {
  const head = evaluationHeadline(evaluations), hosted = hostedResponderValidation(evaluations)
  if (!evaluations.runs.length) return null
  return <section className="card">
    <div className="card-top"><h3>AI report card</h3><Chip tone={hosted ? 'sage' : 'amber'}>{hosted ? 'Graded in Chalk Evaluations' : 'Local scores only'}</Chip></div>
    <Meter label="Abstains on null cases" tally={head.abstained} />
    <Meter label="Numbers match input" tally={head.realNumbers} />
    <Meter label="Raw JSON parses" tally={head.validJson} />
    <Meter label="Approved explanation templates" tally={head.claimsVerified} />
    {head.noPlantedTargets && <div className="responder-meter is-untested"><span>Finds a hidden effect</span><div className="meter-track" /><b>Not tested yet</b></div>}
    <p className="muted">{evaluations.message}</p>
    <details><summary>Full evaluation table</summary>
      <p className="muted">{head.cases} historical cases × 2 prompt styles = {head.answers} answers. High-confidence abstention is not a subgroup overclaim. Planted recall counts only detectable, decision-eligible targets; N/A means none were available. Template match measures approved wording, not factual accuracy.</p>
      <div className="table-scroll"><table className="responder-scores"><thead><tr><th>Prompt / cases</th>{responderMetrics.map(([metric, label]) => <th key={metric}>{label}</th>)}</tr></thead><tbody>{evaluations.runs.map(run => <tr key={`${run.prompt_variant}-${run.variant}`}>
        <td>{run.prompt_variant} / {run.variant} (n={run.n}){run.run_id && <small>Run: {run.run_id}</small>}</td>{responderMetrics.map(([metric]) => <td key={metric}>{run.scores[metric] == null ? 'N/A' : `${(100 * run.scores[metric]!).toFixed(1)}%`}<small>n={run.denominators[metric] ?? 0}</small></td>)}</tr>)}</tbody></table></div>
      {evaluations.claim_audit && <p className="muted">Explanation consistency audit: {priorProseAudit(evaluations.claim_audit.before)} New displayed explanations: {evaluations.claim_audit.guarded_after.contradiction_n} in {evaluations.claim_audit.guarded_after.n} displayed explanations ({evaluations.claim_audit.template_fallback_n} replaced by a verified template).</p>}
    </details>
  </section>
}

function StatisticsTable({ rows }: { rows: ResponderSubgroup[] }) {
  return <div className="table-scroll"><table className="responder-scores"><thead><tr><th>Group</th><th>HR in group (95% CI)</th><th>HR everyone else (95% CI)</th><th>Interaction p</th><th>BH q</th><th>Events in group (treated / control)</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.id}><td>{row.label}</td><td>{effectLabel(row.hr_subgroup)}</td><td>{effectLabel(row.hr_complement)}</td>
      <td>{row.interaction.p?.toPrecision(3) ?? 'n/a'}</td><td>{row.interaction_q?.toPrecision(3) ?? 'n/a'}</td>
      <td>{row.subgroup.treatment_events} / {row.subgroup.control_events}{row.missing_n ? <small>{row.missing_n} missing</small> : null}</td></tr>)}</tbody></table></div>
}

// ---------------------------------------------------------------- page

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
  const overall = data && overallStat(data.evidence)
  const weaker = data?.evidence.subgroups.filter(row => row.truth_label === 'weaker_benefit').length ?? 0
  const verdict = data && agentVerdict(data)
  return <div className="results-stack responder-page">
    <section className="card responder-controls">
      <label>Historical trial<select aria-label="Historical responder trial" value={trial} onChange={event => setTrial(event.target.value)}>
        <option value="colon">Colon cancer · Lev+5FU vs observation</option><option value="veteran">Lung cancer · test vs standard regimen</option><option value="gbsg">Breast cancer · hormonal therapy</option>
      </select></label>
      <button className="btn primary" disabled={pending} onClick={load}>{pending ? 'Loading…' : 'Show evidence'}</button>
      <span className="badge gray">Past trials · separate from your loaded trial</span>
    </section>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {data && overall && verdict && <>
      {data.evidence.trial_key === 'gbsg' && <div className="warning-box"><AlertTriangle size={16} /><strong>Partly non-randomized: weaker evidence</strong></div>}
      <div className="responder-tiles">
        <Tile label="Overall effect" value={overall.value} sub={overall.caption} chip={<Chip tone={overall.tone}>{overall.verdict}</Chip>} />
        <Tile label="Groups that benefit less" value={`${weaker} / ${data.evidence.subgroups.length}`} sub="reliable after correction"
          chip={weaker ? <Chip tone="red">Review exclusion</Chip> : <Chip tone="sage">No reason to exclude</Chip>} />
        <Tile label="Chalk AI vs answer key" value={verdict === 'agrees' ? <CheckCircle2 size={34} className="ok" /> : verdict === 'disagrees' ? <XCircle size={34} className="bad" /> : <MinusCircle size={34} />}
          sub={evidenceSuggestion(data).replace(/\.$/, '')} chip={<Chip tone={verdict === 'agrees' ? 'sage' : verdict === 'disagrees' ? 'red' : 'gray'}>{verdict === 'agrees' ? 'Agrees' : verdict === 'disagrees' ? 'Disagrees' : 'Unavailable'}</Chip>} />
        <Tile label="Patients" value={data.evidence.n.toLocaleString()} sub={`${data.evidence.events.toLocaleString()} events · ${shortName(data.evidence.treatment)}`} />
      </div>
      <section className="card">
        <div className="card-top"><h3>Effect by patient group</h3><Chip tone="gray">{data.evidence.trial_name}</Chip></div>
        <ForestChart rows={data.evidence.subgroups} />
        <details><summary>Show statistics</summary><p className="muted">Benjamini–Hochberg q ≤ 0.10 counts as statistically significant. Groups with too few events are labeled “no reliable difference” for decisions even when significant. No difference does not prove equal effects.</p><StatisticsTable rows={data.evidence.subgroups} /></details>
      </section>
      <div className="responder-layout">
        <ReportCard evaluations={data.evaluations} />
        <section className="card responder-agent">
          <div className="card-top"><h3>Chalk AI answer</h3><Chip tone="amber">Confidence: {data.suggestion.confidence}</Chip></div>
          <p><b>{evidenceSuggestion(data)}</b></p>
          <details><summary>Why?</summary><p>{data.suggestion.rationale || 'No verified rationale available.'}</p>{data.suggestion.used_template && <p className="muted">The AI wording could not be confirmed, so a verified template explanation is shown.</p>}<p className="muted">Sees only the aggregate table, never the answer key or patient rows. Nothing is applied to the protocol.</p></details>
        </section>
      </div>
      <details className="dashboard-details"><summary>Sources and limitations</summary><div className="card"><p>{data.evidence.provenance.citation}</p>{data.evidence.provenance.publication_url && <a href={data.evidence.provenance.publication_url} target="_blank" rel="noreferrer">Trial source ↗</a>}<ul className="assumptions">{[...new Set([...data.disclaimers, ...(data.evaluations.limitations ?? [])])].map(text => <li key={text}>{text}</li>)}</ul></div></details>
    </>}
  </div>
}
