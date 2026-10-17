import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { Activity, ArrowRight, BarChart3, BookOpen, ChevronRight, CircleHelp, Download, FileCheck2, FlaskConical, LayoutDashboard, Leaf, Menu, RotateCcw, ShieldAlert, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import { analyzeTrial, compareCriteria, getPopulations, getVariables } from './simulationService'
import { changedRules, emptyWorkspace, reviewedRules, validDraft, workspaceReducer } from './workspace'
import { exampleProtocol } from './exampleProtocol'
import type { CompareResult, PopulationCatalog, PopulationChoice, ReviewDecision, Rule, SimulationResult, VariableMeta } from './scenarioTypes'
import type { Workspace } from './workspace'

type Tab = 'overview' | 'analysis' | 'scenario' | 'review'
const tabs = [
  { id: 'overview' as const, name: 'Trial & population', icon: LayoutDashboard },
  { id: 'analysis' as const, name: 'Eligibility analysis', icon: BarChart3 },
  { id: 'scenario' as const, name: 'Scenario analysis', icon: SlidersHorizontal },
  { id: 'review' as const, name: 'Researcher review', icon: FileCheck2 },
]
const readable = (text: string) => text.replaceAll('_', ' ')
const count = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toLocaleString()
const pct = (value: number | null) => value === null ? 'Unavailable' : `${value.toFixed(2)}%`
function ruleValue(rule: Rule) { return rule.operator === 'between' ? `${rule.value}–${rule.value_max} ${rule.unit ?? ''}` : `${rule.operator ?? 'Unmodeled'} ${rule.value ?? ''} ${rule.unit ?? ''}` }
function Badge({ children, kind = 'sage' }: { children: React.ReactNode; kind?: 'sage' | 'amber' | 'gray' }) { return <span className={`badge ${kind}`}>{children}</span> }
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section> }
function Stat({ label, value, sub }: { label: string; value: string; sub: string }) { return <Card className="stat"><span className="stat-label">{label}</span><strong>{value}</strong><p>{sub}</p></Card> }
function Warnings({ items }: { items: string[] }) { return items.length ? <div className="notice notice-list" role="status"><CircleHelp size={18} /><ul>{[...new Set(items)].map(item => <li key={item}>{item}</li>)}</ul></div> : null }

function Summary({ result }: { result: SimulationResult }) {
  return <><div className="stat-grid impact-stats">
    <Stat label="Synthetic patients" value={count(result.population_n)} sub={result.cohort.label} />
    <Stat label="Known passing" value={count(result.eligible_n)} sub={`${pct(result.eligible_pct)} · all substantive checks`} />
    <Stat label="Excluded" value={count(result.excluded_n)} sub="At least one known rule failure" />
    <Stat label="Unknown" value={count(result.unknown_n)} sub="Missing fields or unmodeled requirements" />
  </div>{result.unmodeled_rule_ids.length > 0 && <div className="notice"><CircleHelp size={17} /><span>{count(result.modeled_eligible_n)} pass the available modeled checks; other protocol requirements remain unmodeled. This is not confirmed protocol eligibility.</span></div>}
  <div className="cohort-line"><Badge kind={result.complete ? 'sage' : 'amber'}>{result.complete ? 'Checks fully evaluated' : 'Incomplete / approximate'}</Badge><span>Rule coverage: {pct(result.coverage_pct)}</span><code>{result.cohort.id}</code></div></>
}

function Results({ result, rules }: { result: SimulationResult; rules: Rule[] }) {
  const names = new Map(rules.map(rule => [rule.id, rule.simulatable ? `${rule.kind}: ${readable(rule.variable ?? '')} ${ruleValue(rule)}` : rule.clause || rule.text]))
  return <div className="results-stack"><Summary result={result} /><Warnings items={result.warnings} />
    <Card><div className="card-top"><div><h2>Attrition funnel</h2><p>Ordered checks; unknown patients stay separate from exclusions.</p></div></div>
      <div className="table-scroll"><table><thead><tr><th>Check</th><th>Known passing</th><th>Unknown</th><th>Excluded so far</th></tr></thead><tbody>{result.funnel.map(step => <tr key={step.rule_id ?? 'start'}><td><span className="funnel-label">{step.rule_id ?? 'Start'} · {step.label}</span><div className="funnel-track"><span style={{ width: `${100 * step.remaining_n / result.population_n}%` }} /></div></td><td>{count(step.remaining_n)}</td><td>{count(step.unknown_n)}</td><td>{count(result.population_n - step.remaining_n - step.unknown_n)}</td></tr>)}</tbody></table></div>
    </Card>
    <Card><div className="card-top"><div><h2>Per-rule impact</h2><p>Exclusions overlap. Unique failures do not imply confirmed eligibility if other checks are unknown.</p></div><Badge kind="amber">Most restrictive: {result.worst_rule_id ?? 'Unavailable'}</Badge></div>
      <div className="table-scroll"><table><thead><tr><th>Evaluated rule</th><th>Pass</th><th>Fail</th><th>Unknown</th><th>Unique fail</th></tr></thead><tbody>{result.impacts.map(impact => <tr key={impact.rule_id}><td><b>{impact.rule_id}</b> {names.get(impact.rule_id)}</td>{result.not_applicable_rule_ids.includes(impact.rule_id) ? <td colSpan={4}>Not applicable to patient simulation</td> : <><td>{impact.pass_n}</td><td>{impact.fail_n}</td><td>{impact.unknown_n}</td><td>{impact.unique_fail_n}</td></>}</tr>)}</tbody></table></div>
    </Card>
    <div className="impact-grid"><Card><h3>Overlapping exclusions</h3><p className="muted">{result.overlaps_truncated ? 'Pairs among the 20 rules with the largest exclusions.' : 'Patients failing both checks; these counts are not additive.'}</p>
      {result.rule_overlaps.length > 30 && <p className="muted">Showing 30 of {result.rule_overlaps.length} returned pairs.</p>}
      {result.rule_overlaps.length ? <div className="table-scroll"><table><thead><tr><th>Rules</th><th>Both fail</th></tr></thead><tbody>{result.rule_overlaps.slice(0, 30).map(pair => <tr key={`${pair.rule_a_id}-${pair.rule_b_id}`}><td>{pair.rule_a_id} + {pair.rule_b_id}</td><td>{pair.patient_n}</td></tr>)}</tbody></table></div> : <p className="empty-state">No overlapping failures.</p>}</Card>
      <Card><h3>Assumptions & provenance</h3><ul className="assumptions">{result.assumptions.map(text => <li key={text}>{text}</li>)}</ul></Card></div>
    <Card><h2>Patient-level explanations</h2><p className="muted">{result.patient_results_complete ? `All ${result.patient_results.length} patients returned.` : `A preview of ${result.patient_results.length} patients returned; totals use the full cohort.`} Showing the first 20 below.</p>
      {result.patient_results.slice(0, 20).map(patient => <details key={patient.patient_id} className="patient-row"><summary>{patient.patient_id} <Badge kind={patient.overall_status === 'pass' ? 'sage' : 'amber'}>{patient.overall_status}</Badge></summary>
        <div className="table-scroll"><table><thead><tr><th>Rule</th><th>Observed value</th><th>Check</th><th>Result</th></tr></thead><tbody>{patient.criteria.map(check => { const rule = rules.find(r => r.id === check.rule_id); return <tr key={check.rule_id}><td>{check.rule_id} · {names.get(check.rule_id)}</td><td>{check.value === null ? 'Missing / unavailable' : String(check.value)}</td><td>{rule ? ruleValue(rule) : '—'}</td><td>{rule && ['administrative', 'permission'].includes(rule.category) ? 'Not applicable' : check.status}</td></tr> })}</tbody></table></div>
      </details>)}
    </Card>
  </div>
}

function RuleEditor({ rule, original, metadata, available, onEdit }: { rule: Rule; original: Rule; metadata?: VariableMeta; available: boolean; onEdit: (field: 'value' | 'value_max', value: number) => void }) {
  const numeric = rule.simulatable && available && rule.value !== null && metadata?.type !== 'bool'
  const fields: ('value' | 'value_max')[] = rule.operator === 'between' ? ['value', 'value_max'] : ['value']
  return <Card className="editor-card"><div className="card-top"><h3>{rule.id} · {metadata?.label ?? readable(rule.category)}</h3><Badge kind={numeric ? 'sage' : 'gray'}>{numeric ? 'Threshold editable' : 'View only'}</Badge></div>
    <div className="selected-criterion"><p>{rule.clause ?? rule.text}</p></div><div className="rule-meta"><Badge kind="gray">{rule.kind}</Badge><Badge kind="gray">{readable(rule.purpose)}</Badge><Badge kind="gray">{readable(rule.findability)}</Badge><Badge kind={rule.fidelity === 'exact' ? 'sage' : 'amber'}>{rule.fidelity} · {rule.parsed_by}</Badge></div>
    {numeric ? <div className="numeric-fields">{fields.map(field => <label key={field}> {field === 'value_max' ? 'Upper bound' : rule.operator === 'between' ? 'Lower bound' : `Threshold (${rule.operator})`} · {rule.unit ?? 'score'}
      <input aria-label={`${rule.id} ${field}`} type="number" step={metadata?.type === 'int' || rule.variable === 'age' ? 1 : 'any'} value={rule[field] !== null && Number.isFinite(rule[field]) ? rule[field]! : ''} onChange={event => onEdit(field, event.target.value === '' ? Number.NaN : Number(event.target.value))} />
      <small>Original: {original[field]}</small></label>)}</div> : <div className="unsupported-box"><ShieldCheck size={18} /><span>{!rule.simulatable ? 'This requirement has no executable rule. It stays visible and is not silently dropped.' : !available ? 'This variable is unavailable in the selected cohort; its result stays unknown.' : 'This check is evaluated, but this editor only changes numeric thresholds.'}</span></div>}
    <div className="warning-box"><ShieldAlert size={18} /><div><strong>Researcher review required</strong><p>{metadata?.rationale ?? 'Purpose and findability are starting heuristics, not clinical judgments.'} Simulation does not establish treatment safety.</p></div></div>
    <ul className="assumptions">{rule.notes.map((note, index) => <li key={index}>{note}</li>)}</ul><details><summary>Original source text</summary><p className="source-text">{rule.text}</p><small>Source: {rule.source}</small></details>
  </Card>
}

function Comparison({ result }: { result: CompareResult }) {
  return <Card><div className="card-top"><div><h2>Baseline versus modified</h2><p>Same cohort, version and patient identities on both sides.</p></div><Badge kind="gray">{result.cohort.mode}</Badge></div>
    <div className="stat-grid"><Stat label="Known passing" value={`${count(result.baseline.eligible_n)} → ${count(result.proposed.eligible_n)}`} sub="All substantive checks" /><Stat label="Passing available checks" value={`${count(result.baseline.modeled_eligible_n)} → ${count(result.proposed.modeled_eligible_n)}`} sub="Other requirements may remain unmodeled" /><Stat label="Unknown" value={`${result.baseline.unknown_n} → ${result.proposed.unknown_n}`} sub="Not automatically excluded" /><Stat label="Rate change" value={result.eligible_change_pct_points === null ? 'Unavailable' : `${result.eligible_change_pct_points > 0 ? '+' : ''}${result.eligible_change_pct_points.toFixed(2)} pp`} sub="Synthetic check outcomes, not recruitment predictions" /></div>
    <p className="muted">Newly passing: {count(result.newly_eligible_n)} · Newly excluded: {count(result.newly_excluded_n)}</p>
    {result.safety_review_rule_ids.length > 0 && <div className="warning-box" role="status"><ShieldAlert size={20} /><div><strong>Safety-sensitive changes require review</strong><p>Rules: {result.safety_review_rule_ids.join(', ')}. A larger passing group does not establish an acceptable safety trade-off. No draft is automatically accepted.</p></div></div>}
  </Card>
}

function Review({ workspace, decide }: { workspace: Workspace; decide: (id: string, decision: ReviewDecision) => void }) {
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const comparison = workspace.comparison
  if (!comparison || !workspace.analysis) return <Card><div className="empty-view"><FileCheck2 size={28} /><h2>Compare a draft first</h2><p>Researcher review uses the latest comparison for the current cohort.</p></div></Card>
  const allReviewed = comparison.changed_rule_ids.length > 0 && comparison.changed_rule_ids.every(id => workspace.decisions[id])
  function download() {
    const accepted = reviewedRules(workspace)
    const record = { trial: workspace.analysis!.trial, cohort: comparison!.cohort, baseline_rules: workspace.analysis!.rules,
      proposed_rules: workspace.draft, decisions: workspace.decisions, accepted_rules: accepted,
      accepted_rules_match_simulated_draft: JSON.stringify(accepted) === JSON.stringify(workspace.draft),
      comparison_of_proposed_draft: comparison, disclosure: 'Synthetic exploratory results. Local researcher review record; not an approved clinical protocol.' }
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'wind-tunnel-review.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <div className="results-stack"><Card><h2>Researcher review</h2><p className="muted">Decisions stay in this browser session. Acceptance records your review; it does not modify the original protocol or automatically apply changes.</p><code className="cohort-code">{comparison.cohort.id}</code></Card>
    {comparison.changes.map(change => { const old = workspace.analysis!.rules.find(r => r.id === change.rule_id)!; const next = workspace.draft.find(r => r.id === change.rule_id)!; const safety = comparison.safety_review_rule_ids.includes(change.rule_id); const decision = workspace.decisions[change.rule_id]; const reason = reasons[change.rule_id] ?? decision?.reason ?? ''; return <Card key={change.rule_id}>
      <div className="card-top"><h3>{change.rule_id} · {readable(change.change)}</h3><Badge kind={safety ? 'amber' : 'gray'}>{safety ? 'Safety review required' : 'Researcher review'}</Badge></div><p>{old.clause ?? old.text}</p><div className="redline"><del>{ruleValue(old)}</del><ArrowRight size={18} /><ins>{ruleValue(next)}</ins></div>
      <p className="muted">Purpose: {readable(old.purpose)} · Source: {old.source} · Interpretation: {old.parsed_by}, {old.fidelity}</p>{safety && <div className="warning-box"><ShieldAlert size={18} /><span>Do not infer safety from eligibility counts. Record a review rationale before accepting this change.</span></div>}
      <label className="review-reason">Review rationale {safety ? '(required for acceptance)' : '(optional)'}<textarea aria-label={`Review reason ${change.rule_id}`} value={reason} onChange={event => setReasons({ ...reasons, [change.rule_id]: event.target.value })} /></label>
      <div className="toolbar-actions"><button className="btn primary" disabled={safety && !reason.trim()} onClick={() => decide(change.rule_id, { decision: 'accepted', reason: reason.trim(), at: new Date().toISOString() })}>Accept draft change</button><button className="btn outline" onClick={() => decide(change.rule_id, { decision: 'rejected', reason: reason.trim(), at: new Date().toISOString() })}>Reject change</button>{decision && <Badge kind={decision.decision === 'accepted' ? 'sage' : 'gray'}>{decision.decision}</Badge>}</div>
    </Card> })}
    <Card><button className="btn primary" disabled={!allReviewed} onClick={download}><Download size={16} /> Download review record</button><p className="muted">Review every changed rule first. A mix of accepted and rejected changes needs a fresh simulation before its combined counts can be used.</p></Card>
  </div>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview'), [mobileOpen, setMobileOpen] = useState(false)
  const [inputMode, setInputMode] = useState<'nct' | 'text'>('nct'), [nctId, setNctId] = useState(''), [text, setText] = useState('')
  const [mode, setMode] = useState<'fixed' | 'generated'>('fixed'), [size, setSize] = useState(10000), [seed, setSeed] = useState(42), [useLlm, setUseLlm] = useState(false)
  const [catalog, setCatalog] = useState<PopulationCatalog | null>(null), [variables, setVariables] = useState<Record<string, VariableMeta>>({})
  const [catalogError, setCatalogError] = useState<string | null>(null), [error, setError] = useState<string | null>(null), [busy, setBusy] = useState<'analysis' | 'compare' | null>(null), [selectedId, setSelectedId] = useState('')
  const option = catalog?.options.find(item => item.mode === mode)
  const population = useMemo<PopulationChoice>(() => ({ mode, size: mode === 'fixed' ? option?.size ?? 500 : size, seed: mode === 'fixed' ? 0 : seed, version: option?.version, ...(option?.cohort_id ? { cohort_id: option.cohort_id } : {}) }), [mode, size, seed, option])
  const context = JSON.stringify([inputMode, nctId.trim().toUpperCase(), text, population, useLlm])
  const [workspace, dispatch] = useReducer(workspaceReducer, context, emptyWorkspace)
  const controller = useRef<AbortController | null>(null), sequence = useRef(0)
  function cancel() { sequence.current++; controller.current?.abort(); setBusy(null) }
  useEffect(() => {
    const abort = new AbortController()
    Promise.all([getPopulations(abort.signal), getVariables(abort.signal)]).then(([populations, metadata]) => { setCatalog(populations); setVariables(metadata); setCatalogError(null) }).catch(cause => { if (!abort.signal.aborted) setCatalogError(`Cannot reach the backend. Start FastAPI on port 8000. ${String(cause)}`) })
    return () => abort.abort()
  }, [])
  useEffect(() => { cancel(); dispatch({ type: 'reset', context }); setError(null) }, [context])
  useEffect(() => () => controller.current?.abort(), [])
  const analysis = workspace.analysis, baseline = analysis?.rules ?? [], changes = changedRules(baseline, workspace.draft)
  const selected = workspace.draft.find(r => r.id === selectedId) ?? workspace.draft[0]
  const populationValid = mode === 'fixed' || (Number.isInteger(size) && size >= 100 && size <= 200000 && Number.isInteger(seed) && seed >= 0 && seed <= 4294967295)
  const inputValid = inputMode === 'nct' ? /^NCT\d{8}$/.test(nctId.trim().toUpperCase()) : Boolean(text.trim()) && text.length <= 30000
  async function analyze() {
    cancel(); const requestId = sequence.current; const abort = new AbortController(); controller.current = abort
    dispatch({ type: 'reset', context }); setBusy('analysis'); setError(null)
    try {
      const result = await analyzeTrial({ ...(inputMode === 'nct' ? { nct_id: nctId.trim().toUpperCase() } : { eligibility_text: text }), use_llm: useLlm }, population, abort.signal)
      if (requestId !== sequence.current) return
      if (result.simulation.cohort.mode !== population.mode) throw new Error('Population mismatch. Reload and rerun the analysis.')
      dispatch({ type: 'analyzed', context, result }); setSelectedId(result.rules[0]?.id ?? ''); setTab('analysis')
    } catch (cause) { if (!abort.signal.aborted && requestId === sequence.current) setError(String(cause)) }
    finally { if (requestId === sequence.current) setBusy(null) }
  }
  async function compare() {
    if (!analysis) return
    cancel(); const requestId = sequence.current; const abort = new AbortController(); controller.current = abort
    const snapshot = structuredClone(workspace.draft); setBusy('compare'); setError(null)
    try {
      const result = await compareCriteria(baseline, snapshot, { ...population, cohort_id: analysis.simulation.cohort.id }, abort.signal)
      if (requestId !== sequence.current) return
      if (result.cohort.id !== analysis.simulation.cohort.id || result.baseline.cohort.id !== result.cohort.id || result.proposed.cohort.id !== result.cohort.id) throw new Error('Comparison returned a different cohort. Rerun the baseline.')
      dispatch({ type: 'compared', context, draft: snapshot, result })
    } catch (cause) { if (!abort.signal.aborted && requestId === sequence.current) setError(String(cause)) }
    finally { if (requestId === sequence.current) setBusy(null) }
  }
  function edit(field: 'value' | 'value_max', value: number) { if (selected) { cancel(); dispatch({ type: 'edit', id: selected.id, field, value }) } }
  const go = (next: Tab) => { setTab(next); setMobileOpen(false) }
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? 'shown' : ''}`}><div className="logo-wrap"><div className="logo-mark"><Leaf size={22} /></div><div><div className="logo-text">Wind Tunnel<span className="logo-period">.</span></div><div className="logo-sub">Clinical trial intelligence</div></div><button className="close-mobile" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={19} /></button></div><div className="workspace-label">WORKSPACE</div><nav className="nav">{tabs.map(item => <button key={item.id} className={`nav-item ${tab === item.id ? 'active' : ''}`} onClick={() => go(item.id)}><item.icon size={18} />{item.name}</button>)}</nav><div className="side-bottom"><div className="help-box"><BookOpen size={19} /><strong>Explore a synthetic example</strong><p>Use the real parser and engine without a registry request.</p><button onClick={() => { cancel(); setInputMode('text'); setText(exampleProtocol); go('overview') }}>Load example text <ArrowRight size={15} /></button></div><div className="side-footer"><ShieldCheck size={17} /> Public and synthetic data only</div></div></aside>
    <div className="mobile-shade" onClick={() => setMobileOpen(false)} style={{ display: mobileOpen ? 'block' : 'none' }} /><div className="main-area"><header className="topbar"><button className="menu-btn" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="crumb">Workspace <ChevronRight size={14} /> {tabs.find(item => item.id === tab)?.name}</div><span className="demo-pill"><FlaskConical size={15} /> {mode === 'fixed' ? 'Fixed synthetic cohort' : 'Generated exploration'}</span></header>
    <main className="content"><div className="eyebrow">CLINICAL TRIAL DESIGN / WORKSPACE</div><div className="page-heading"><div><h1>{tabs.find(item => item.id === tab)?.name}</h1><p>See the trade-offs of every eligibility rule before you lock the protocol.</p></div><Badge kind="gray">Synthetic only</Badge></div>
      {catalogError && <div className="error-notice" role="alert">{catalogError}<button className="btn outline" onClick={() => window.location.reload()}>Retry connection</button></div>}{error && <div className="error-notice" role="alert"><ShieldAlert size={18} />{error}</div>}
      <Card className="population-controls"><div><label htmlFor="population-mode">Population mode</label><select id="population-mode" value={mode} onChange={event => { cancel(); setMode(event.target.value as 'fixed' | 'generated') }}><option value="fixed">Fixed 500-patient NSCLC cohort</option><option value="generated">Generated oncology exploration</option></select></div>{mode === 'generated' && <><label>Population size<input aria-label="Population size" type="number" min={100} max={200000} value={size} onChange={event => { cancel(); setSize(Number(event.target.value)) }} /></label><label>Seed<input aria-label="Population seed" type="number" min={0} max={4294967295} value={seed} onChange={event => { cancel(); setSeed(Number(event.target.value)) }} /></label></>}<p>{mode === 'fixed' ? 'Same checked-in patient records, including missing values. Fictional NSCLC, not representative clinical data.' : 'Reproducible adults with assumed distributions. Changing size, seed or mode starts a new baseline.'} {option && <b>Version: {option.version}</b>}</p>{!populationValid && <span className="error-text">Use an integer size of 100–200,000 and a nonnegative 32-bit seed.</span>}</Card>
      {tab === 'overview' ? <div className="results-stack"><div className="hero"><div className="hero-copy"><div className="hero-chip"><Activity size={14} /> Explore protocol trade-offs</div><h2>Every criterion<br /><em>shapes your trial.</em></h2><p>Load public trial criteria, inspect the modeled checks, and compare a draft on exactly the same synthetic patients.</p></div><div className="hero-art" aria-hidden="true"><div className="ring r1" /><div className="ring r2" /><div className="orb"><Activity size={58} /></div></div></div><Card><div className="card-top"><h2>Trial source</h2><Badge kind="gray">No mock results</Badge></div><div className="toolbar-actions"><button className={`btn ${inputMode === 'nct' ? 'primary' : 'outline'}`} onClick={() => { cancel(); setInputMode('nct') }}>ClinicalTrials.gov ID</button><button className={`btn ${inputMode === 'text' ? 'primary' : 'outline'}`} onClick={() => { cancel(); setInputMode('text') }}>Paste eligibility text</button></div>
        {inputMode === 'nct' ? <label className="source-input">ClinicalTrials.gov identifier<input aria-label="ClinicalTrials.gov identifier" placeholder="NCT followed by 8 digits" value={nctId} onChange={event => { cancel(); setNctId(event.target.value) }} /></label> : <label className="source-input">Public eligibility text<textarea aria-label="Public eligibility text" maxLength={30000} rows={10} value={text} onChange={event => { cancel(); setText(event.target.value) }} /><small>{text === exampleProtocol ? 'Fictional example protocol. Not a real trial.' : `${text.length.toLocaleString()} / 30,000 characters · public protocol text only`}</small></label>}
        <label className="checkbox-label"><input type="checkbox" checked={useLlm} onChange={event => { cancel(); setUseLlm(event.target.checked) }} />Use Chalk AI fallback for unread criteria (may take up to the server time budget)</label><div className="toolbar-actions"><button className="btn primary" disabled={!catalog || !inputValid || !populationValid || Boolean(busy)} onClick={analyze}>{busy === 'analysis' ? 'Analyzing…' : 'Load and analyze'} <ArrowRight size={16} /></button>{busy && <button className="btn outline" onClick={cancel}>Cancel</button>}</div></Card></div> : !analysis ? <Card><div className="empty-view"><FlaskConical size={30} /><h2>Start with a trial or public eligibility text</h2><p>Changing the population or source clears the previous baseline and review decisions.</p><button className="btn primary" onClick={() => go('overview')}>Set up analysis <ArrowRight size={16} /></button></div></Card> : <>
        <div className="trial-heading"><h2>{analysis.trial.title ?? (text === exampleProtocol ? 'Fictional example protocol' : 'Pasted eligibility criteria')}</h2><span>{analysis.trial.nct_id ?? 'Public text input'} · {baseline.length} parsed rules</span>{analysis.trial.nct_id && <a href={`https://clinicaltrials.gov/study/${encodeURIComponent(analysis.trial.nct_id)}`} target="_blank" rel="noreferrer">Registry source ↗</a>}</div>
        <Warnings items={analysis.warnings} />
        {tab === 'analysis' && <><div className="toolbar-actions analysis-actions"><button className="btn primary" onClick={() => go('scenario')}>Edit a draft <ArrowRight size={16} /></button></div><Results result={analysis.simulation} rules={baseline} /></>}
        {tab === 'scenario' && <><div className="scenario-toolbar"><div><h2>Draft eligibility rules</h2><p>Original rules stay intact. Changes apply only to this exploratory draft.</p></div><div className="toolbar-actions"><button className="btn outline" disabled={!changes.length || Boolean(busy)} onClick={() => dispatch({ type: 'analyzed', context, result: analysis })}><RotateCcw size={15} />Reset draft</button><button className="btn primary" disabled={!changes.length || !validDraft(workspace.draft) || Boolean(busy)} onClick={compare}>{busy === 'compare' ? 'Comparing…' : 'Compare draft'}<ArrowRight size={16} /></button>{busy && <button className="btn outline" onClick={cancel}>Cancel</button>}</div></div>
          {!validDraft(workspace.draft) && <div className="error-notice">Enter finite numeric thresholds and keep upper bounds at least as large as lower bounds.</div>}
          <div className="scenario-grid connected-grid"><Card className="criteria-card"><div className="card-top"><h3>Parsed rules</h3><Badge kind="gray">{baseline.length}</Badge></div><div className="criteria-list">{workspace.draft.map(rule => <button key={rule.id} className={`criterion-item ${selected?.id === rule.id ? 'selected' : ''}`} onClick={() => setSelectedId(rule.id)}><span className="criterion-number">{rule.id}</span><span><strong>{variables[rule.variable ?? '']?.label ?? readable(rule.category)}</strong><small>{rule.clause ?? rule.text}</small></span><Badge kind={rule.simulatable && option?.available_variables.includes(rule.variable ?? '') ? 'sage' : 'gray'}>{rule.simulatable ? option?.available_variables.includes(rule.variable ?? '') ? 'Modeled' : 'Unavailable' : 'Unmodeled'}</Badge></button>)}</div></Card>{selected && <RuleEditor rule={selected} original={baseline.find(r => r.id === selected.id)!} metadata={variables[selected.variable ?? '']} available={Boolean(option?.available_variables.includes(selected.variable ?? ''))} onEdit={edit} />}</div>
          {workspace.comparison ? <div className="results-stack comparison-stack"><Comparison result={workspace.comparison} /><button className="btn primary" onClick={() => go('review')}>Review proposed changes <FileCheck2 size={16} /></button><Results result={workspace.comparison.proposed} rules={workspace.draft} /></div> : <div className="notice"><CircleHelp size={17} />{changes.length ? `${changes.length} edited rule(s). Compare the draft to update results.` : 'Select a supported numeric rule to explore a threshold change.'}</div>}
        </>}
        {tab === 'review' && <Review workspace={workspace} decide={(id, decision) => dispatch({ type: 'decide', id, decision })} />}
      </>}
    </main><footer className="footer"><div><Leaf size={15} /> Wind Tunnel · Qualified researchers make final decisions.</div><span>Synthetic estimates · Not clinical decision support</span></footer></div>
  </div>
}
