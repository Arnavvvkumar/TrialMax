import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BarChart3, CheckCircle2, ChevronRight, CircleHelp, Download, FileCheck2, FlaskConical, Info, LayoutDashboard, Leaf, MapPinned, Menu, RotateCcw, ShieldAlert, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import { analyzeTrial, checkChalk, compareCriteria, getHealth, getPopulations, getRareReach, getVariables } from './simulationService'
import { changedRules, defaultPopulationMode, emptyWorkspace, notCheckedDetail, reviewedRules, validDraft, workspaceReducer } from './workspace'
import { exampleProtocol } from './exampleProtocol'
import type { ApiHealth, ChalkCheck, CompareResult, PopulationCatalog, PopulationChoice, PopulationMode, RareReachResponse, ReviewDecision, Rule, SimulationResult, VariableMeta } from './scenarioTypes'
import type { Workspace } from './workspace'

type Tab = 'overview' | 'analysis' | 'scenario' | 'rare' | 'review'
const tabs = [
  { id: 'overview' as const, name: 'Trial setup', icon: LayoutDashboard },
  { id: 'analysis' as const, name: 'Results', icon: BarChart3 },
  { id: 'scenario' as const, name: 'Scenario analysis', icon: SlidersHorizontal },
  { id: 'rare' as const, name: 'RareReach', icon: MapPinned },
  { id: 'review' as const, name: 'Review', icon: FileCheck2 },
]
const readable = (text: string) => text.replaceAll('_', ' ')
const count = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toLocaleString()
const pct = (value: number | null) => value === null ? 'Unavailable' : `${value.toFixed(2)}%`
function ruleValue(rule: Rule) { return rule.operator === 'between' ? `${rule.value}–${rule.value_max} ${rule.unit ?? ''}` : `${rule.operator ?? 'Unmodeled'} ${rule.value ?? ''} ${rule.unit ?? ''}` }
function Badge({ children, kind = 'sage' }: { children: React.ReactNode; kind?: 'sage' | 'amber' | 'gray' }) { return <span className={`badge ${kind}`}>{children}</span> }
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section> }
function Stat({ label, value, sub }: { label: string; value: string; sub: string }) { return <Card className="stat"><span className="stat-label">{label}</span><strong>{value}</strong><p>{sub}</p></Card> }
function Warnings({ items }: { items: string[] }) { return items.length ? <div className="notice notice-list" role="status"><CircleHelp size={18} /><ul>{[...new Set(items)].map(item => <li key={item}>{item}</li>)}</ul></div> : null }
function Evidence({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="evidence-drawer"><summary><Info size={14} />{title}</summary><div>{children}</div></details>
}
function PatientSpotlight({ result, rules, names }: { result: SimulationResult; rules: Rule[]; names: Map<string, string> }) {
  const patient = result.patient_results.find(item => item.modeled_status === 'fail' || item.modeled_status === 'unknown') ?? result.patient_results[0]
  if (!patient) return null
  const failed = patient.criteria.filter(check => check.status === 'fail')
  const unknown = patient.criteria.filter(check => check.status === 'unknown')
  return <Card className="patient-spotlight"><div className="card-top"><div><span className="eyebrow">ONE PATIENT, EXPLAINED</span><h2>{patient.patient_id}</h2></div><Badge kind={patient.modeled_status === 'pass' ? 'sage' : 'amber'}>{patient.modeled_status === 'unknown' ? 'Unknown' : patient.modeled_status === 'fail' ? 'Excluded' : 'Passes checks'}</Badge></div>
    <p className="spotlight-summary">{patient.modeled_status === 'fail' ? `This patient is excluded by ${failed.length} modeled ${failed.length === 1 ? 'criterion' : 'criteria'}.` : patient.modeled_status === 'unknown' ? 'This patient cannot be fully classified because required information is missing.' : 'This patient passes every modeled criterion.'}</p>
    <div className="spotlight-reasons">{failed.slice(0, 2).map(check => <div className="spotlight-reason" key={`${patient.patient_id}-${check.rule_id}`}><ShieldAlert size={16} /><div><b>{check.rule_id}</b><span>{names.get(check.rule_id) ?? 'Eligibility criterion'}</span><small>Observed value: {check.value === null ? 'Missing' : String(check.value)}</small></div></div>)}{unknown.slice(0, 2).map(check => <div className="spotlight-reason unknown" key={`${patient.patient_id}-${check.rule_id}`}><Info size={16} /><div><b>{check.rule_id}</b><span>{names.get(check.rule_id) ?? 'Eligibility criterion'}</span><small>Observed value: unavailable</small></div></div>)}</div>
    <Evidence title="See patient-level evidence"><div className="evidence-list">{patient.criteria.map(check => { const rule = rules.find(item => item.id === check.rule_id); return <div key={check.rule_id}><b>{check.rule_id}</b><span>{rule?.clause ?? rule?.text ?? 'Criterion'}</span><em>{check.status} · {check.value === null ? 'missing' : String(check.value)}</em></div> })}</div></Evidence>
  </Card>
}

function Summary({ result }: { result: SimulationResult }) {
  return <><div className="stat-grid impact-stats">
    <Stat label="Patients evaluated" value={count(result.population_n)} sub={result.cohort.label} />
    <Stat label="Passing modeled checks" value={count(result.modeled_eligible_n)} sub={`${pct(result.modeled_eligible_pct)} · available checks only`} />
    <Stat label="Excluded by checks" value={count(result.excluded_n)} sub="At least one modeled rule failure" />
    <Stat label="Unknown on modeled checks" value={count(result.modeled_unknown_n)} sub={result.modeled_rule_ids.length ? 'Missing values on the evaluated checks' : 'No modeled checks available'} />
  </div><div className="notice"><CircleHelp size={17} /><span>{result.unmodeled_rule_ids.length > 0 ? `${result.unmodeled_rule_ids.length} rules were not checked. ${count(result.unknown_n)} patients remain unresolved.` : 'All available rules are included.'} Review modeled results before making protocol decisions.</span></div>
  <div className="cohort-line"><Badge kind={result.complete ? 'sage' : 'amber'}>{result.complete ? 'Checks fully evaluated' : 'Incomplete / approximate'}</Badge><span>Rule coverage: {pct(result.coverage_pct)}</span><code>{result.cohort.id}</code></div></>
}

function Results({ result, rules, variables = {} }: { result: SimulationResult; rules: Rule[]; variables?: Record<string, VariableMeta> }) {
  const names = new Map(rules.map(rule => [rule.id, rule.simulatable ? `${rule.kind}: ${readable(rule.variable ?? '')} ${ruleValue(rule)}` : rule.clause || rule.text]))
  const rankedImpacts = [...result.impacts].sort((a, b) => b.fail_n - a.fail_n)
  return <div className="results-stack"><Summary result={result} /><Warnings items={result.warnings} />
    <Card><div className="card-top"><div><h2>Eligibility funnel</h2><p>{result.modeled_rule_ids.length} checks applied in protocol order.</p></div></div>
      {result.modeled_rule_ids.length ? <div className="funnel-dashboard">{result.funnel.map(step => <div className="funnel-step" key={step.rule_id ?? 'start'}><div className="funnel-step-heading"><strong>{step.rule_id ?? 'Start'}</strong><span>{step.label}</span><b>{count(step.remaining_n)} passing</b></div><div className="funnel-track"><span style={{ width: `${100 * step.remaining_n / result.population_n}%` }} /></div><div className="funnel-step-meta"><span>{pct(step.remaining_pct)} remaining</span><span>{count(step.unknown_n)} unknown</span><span>{count(result.population_n - step.remaining_n - step.unknown_n)} excluded</span></div></div>)}</div> : <p className="empty-state">No eligibility checks are available for this population.</p>}
    </Card>
    {result.unmodeled_rule_ids.length > 0 && <Card><h2>Not checked · {result.unmodeled_rule_ids.length} rules</h2><p className="muted">These requirements stay in the protocol and patient explanations, but are outside the headline and funnel. They need researcher review.</p><ul className="assumptions">{result.unmodeled_rule_ids.map(id => { const rule = rules.find(item => item.id === id); const detail = rule ? notCheckedDetail(rule, variables) : null; return <li key={id}><b>{id}</b> · {detail?.what ?? id} <Badge kind="gray">{detail?.badge ?? 'Not modeled'}</Badge>{detail && <><br /><small className="muted">{detail.reason}</small></>}</li> })}</ul></Card>}
    <Card><div className="card-top"><div><h2>Rule impact</h2><p>Rules ranked by patients excluded. Select a row for the detailed counts.</p></div><Badge kind="amber">Largest impact: {result.worst_rule_id ?? 'Unavailable'}</Badge></div>
      <div className="impact-dashboard">{rankedImpacts.map(impact => <details className="impact-row" key={impact.rule_id}><summary><span className="impact-rule"><strong>{impact.rule_id}</strong><span>{names.get(impact.rule_id)}</span></span>{result.not_applicable_rule_ids.includes(impact.rule_id) ? <Badge kind="gray">Not applicable</Badge> : <span className="impact-fail-count">{count(impact.fail_n)} fail</span>}</summary>{!result.not_applicable_rule_ids.includes(impact.rule_id) && <div className="impact-bar"><span style={{ width: `${Math.min(100, impact.fail_pct)}%` }} /></div>}<div className="impact-details"><span>Pass <b>{count(impact.pass_n)}</b></span><span>Fail <b>{count(impact.fail_n)}</b></span><span>Unknown <b>{count(impact.unknown_n)}</b></span><span>Unique fail <b>{count(impact.unique_fail_n)}</b></span></div></details>)}</div>
    </Card>
    <details className="dashboard-details"><summary>Additional analysis</summary><div className="impact-grid"><Card><h3>Overlapping exclusions</h3><p className="muted">{result.overlaps_truncated ? 'Pairs among the 20 rules with the largest exclusions.' : 'Patients failing both checks; these counts are not additive.'}</p>
      {result.rule_overlaps.length > 30 && <p className="muted">Showing 30 of {result.rule_overlaps.length} returned pairs.</p>}
      {result.rule_overlaps.length ? <div className="table-scroll"><table><thead><tr><th>Rules</th><th>Both fail</th></tr></thead><tbody>{result.rule_overlaps.slice(0, 30).map(pair => <tr key={`${pair.rule_a_id}-${pair.rule_b_id}`}><td>{pair.rule_a_id} + {pair.rule_b_id}</td><td>{pair.patient_n}</td></tr>)}</tbody></table></div> : <p className="empty-state">No overlapping failures.</p>}</Card>
      <Card><h3>Assumptions & provenance</h3><ul className="assumptions">{result.assumptions.map(text => <li key={text}>{text}</li>)}</ul></Card></div></details>
    <PatientSpotlight result={result} rules={rules} names={names} />
    <details className="dashboard-details"><summary>Patient-level details</summary><Card><h2>Patient explanations</h2><p className="muted">{result.patient_results_complete ? `All ${result.patient_results.length} patients returned.` : `Showing ${result.patient_results.length} patient records.`}</p>
      {result.patient_results.slice(0, 20).map(patient => <details key={patient.patient_id} className="patient-row"><summary>{patient.patient_id} <Badge kind={patient.modeled_status === 'pass' ? 'sage' : 'amber'}>Checks: {patient.modeled_status}</Badge><span>Full protocol: {patient.overall_status}</span></summary>
        <div className="table-scroll"><table><thead><tr><th>Rule</th><th>Observed value</th><th>Check</th><th>Result</th></tr></thead><tbody>{patient.criteria.map(check => { const rule = rules.find(r => r.id === check.rule_id); return <tr key={check.rule_id}><td>{check.rule_id} · {names.get(check.rule_id)}</td><td>{check.value === null ? 'Missing / unavailable' : String(check.value)}</td><td>{rule ? ruleValue(rule) : '—'}</td><td>{rule && ['administrative', 'permission'].includes(rule.category) ? 'Not applicable' : check.status}</td></tr> })}</tbody></table></div>
      </details>)}
    </Card></details>
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
    <div className="stat-grid"><Stat label="Passing modeled checks" value={`${count(result.baseline.modeled_eligible_n)} → ${count(result.proposed.modeled_eligible_n)}`} sub="Available checks only" /><Stat label="Excluded by checks" value={`${result.baseline.excluded_n} → ${result.proposed.excluded_n}`} sub="At least one modeled failure" /><Stat label="Unknown on modeled checks" value={`${result.baseline.modeled_unknown_n} → ${result.proposed.modeled_unknown_n}`} sub="Missing values, not exclusions" /><Stat label="Eligibility change" value={result.modeled_eligible_change_pct_points === null ? 'Unavailable' : `${result.modeled_eligible_change_pct_points > 0 ? '+' : ''}${result.modeled_eligible_change_pct_points.toFixed(2)} pp`} sub="Percentage-point change" /></div>
    <p className="muted">Newly passing modeled checks: {count(result.modeled_newly_eligible_n)} · Newly excluded by checks: {count(result.modeled_newly_excluded_n)}. Not-checked requirements remain outside these counts.</p>
    {result.safety_review_rule_ids.length > 0 && <div className="warning-box" role="status"><ShieldAlert size={20} /><div><strong>Safety-sensitive changes require review</strong><p>Rules: {result.safety_review_rule_ids.join(', ')}. A larger passing group does not establish an acceptable safety trade-off. No draft is automatically accepted.</p></div></div>}
  </Card>
}

function RareReach({ result, loading, onLoad }: { result: RareReachResponse | null; loading: boolean; onLoad: () => void }) {
  if (!result) return <Card><div className="empty-view"><MapPinned size={30} /><h2>Find public recruitment channels</h2><p>RareReach identifies public ClinicalTrials.gov site history and links to Orphanet and NORD research resources. It never accesses patient records or estimates patient volume.</p><button className="btn primary" disabled={loading} onClick={onLoad}>{loading ? 'Searching public sources…' : 'Research recruitment options'} <ArrowRight size={16} /></button></div></Card>
  return <div className="results-stack"><Warnings items={result.warnings} /><Card><div className="card-top"><div><h2>Rare-disease profile</h2><p>Terms from the public trial record: {result.query_terms.join(', ') || 'No condition available'}</p></div><Badge kind={result.orpha_status === 'matched' ? 'sage' : 'amber'}>Orphadata: {result.orpha_status}</Badge></div>{result.orpha_code ? <><p><b>ORPHAcode:</b> {result.orpha_code} · <b>Preferred term:</b> {result.orpha_preferred_name ?? 'Unavailable'}</p><p className="muted">Synonyms: {result.orpha_synonyms.length ? result.orpha_synonyms.join(', ') : 'None returned'}</p></> : <p className="muted">No ORPHAcode match is claimed for this trial condition.</p>}</Card><Card><div className="card-top"><div><h2>US public trial-site history</h2><p>United States sites only, ranked by matching public ClinicalTrials.gov records.</p></div><Badge kind="gray">{result.hospitals.length} sites</Badge></div>{result.hospitals.length ? <div className="table-scroll"><table><thead><tr><th>Hospital / site</th><th>Location</th><th>Historical records</th><th>Why shown</th></tr></thead><tbody>{result.hospitals.map(site => <tr key={`${site.name}-${site.city}`}><td><b>{site.name}</b></td><td>{[site.city, site.region, site.country].filter(Boolean).join(', ')}</td><td>{site.historical_trial_count}</td><td>{site.explanation} {site.source_urls.slice(0, 2).map(url => <a key={url} href={url} target="_blank" rel="noreferrer">Source ↗ </a>)}</td></tr>)}</tbody></table></div> : <p className="empty-state">No matching US sites were returned.</p>}</Card><Card><h2>Keep the criterion, widen outreach</h2>{result.strategies.map(item => <div className="strategy" key={item.rule_id}><b>{item.rule_id}</b><p>{item.criterion}</p><p><b>Recruitment strategy:</b> {item.outreach}</p>{item.safety_sensitive && <Badge kind="amber">Safety-sensitive · clinical review required</Badge>}</div>)}</Card><Card><h2>Patient-network research</h2><p>Use <a href={result.nord_url} target="_blank" rel="noreferrer">NORD ↗</a> to investigate relevant public advocacy organisations and registries. This does not imply registry access, endorsement, or a partnership.</p><p>Sources: {result.sources.map(source => <a key={source.name} href={source.url} target="_blank" rel="noreferrer">{source.name} ({source.access}) ↗ </a>)}</p></Card></div>
}

function Review({ workspace, decide }: { workspace: Workspace; decide: (id: string, decision: ReviewDecision) => void }) {
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const comparison = workspace.comparison
  if (!comparison || !workspace.analysis) return <Card><div className="empty-view"><FileCheck2 size={28} /><h2>Compare a draft first</h2><p>Researcher review uses the latest comparison for the current cohort.</p></div></Card>
  const allReviewed = comparison.changed_rule_ids.length > 0 && comparison.changed_rule_ids.every(id => workspace.decisions[id])
  const reviewedCount = comparison.changed_rule_ids.filter(id => workspace.decisions[id]).length
  function download() {
    const accepted = reviewedRules(workspace)
    const record = { trial: workspace.analysis!.trial, cohort: comparison!.cohort, baseline_rules: workspace.analysis!.rules,
      proposed_rules: workspace.draft, decisions: workspace.decisions, accepted_rules: accepted,
      accepted_rules_match_simulated_draft: JSON.stringify(accepted) === JSON.stringify(workspace.draft),
      comparison_of_proposed_draft: comparison, disclosure: 'Modeled results require qualified researcher review and are not an approved clinical protocol.' }
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'clinova-review.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const modeledDelta = comparison.modeled_eligible_change_pct_points
  return <div className="results-stack review-page"><Card className="review-hero"><div><span className="eyebrow">PROTOCOL CHANGE LEDGER</span><h2>Make each decision explicit.</h2><p>Review the modeled impact, record your rationale, and keep the original protocol unchanged.</p></div><div className="review-progress"><strong>{reviewedCount}/{comparison.changed_rule_ids.length}</strong><span>changes reviewed</span><div><i style={{ width: `${100 * reviewedCount / comparison.changed_rule_ids.length}%` }} /></div></div></Card>
    <div className="review-overview"><Card className="review-impact"><span className="stat-label">MODELED ELIGIBILITY</span><strong>{count(comparison.baseline.modeled_eligible_n)} <small>→</small> {count(comparison.proposed.modeled_eligible_n)}</strong><p>{modeledDelta === null ? 'Change unavailable' : `${modeledDelta > 0 ? '+' : ''}${modeledDelta.toFixed(2)} percentage points`}</p><Evidence title="How this was calculated"><p>Both versions were evaluated against the same cohort: <code>{comparison.cohort.id}</code>. This is a modeled estimate, not clinical evidence.</p></Evidence></Card><Card className="review-impact"><span className="stat-label">EXCLUDED PATIENTS</span><strong>{count(comparison.baseline.excluded_n)} <small>→</small> {count(comparison.proposed.excluded_n)}</strong><p>{count(comparison.modeled_newly_eligible_n)} newly passing modeled checks</p></Card><Card className="review-impact"><span className="stat-label">RESEARCHER STATUS</span><strong>{allReviewed ? 'Complete' : 'Pending'}</strong><p>{allReviewed ? 'Ready to export the review record' : 'Review every changed criterion below'}</p></Card></div>
    {comparison.safety_review_rule_ids.length > 0 && <div className="warning-box review-warning"><ShieldAlert size={19} /><div><strong>Safety-sensitive change detected</strong><p>Eligibility counts show population impact, not medical safety. A qualified researcher must review the safety, scientific validity, and generalizability trade-offs.</p></div></div>}
    <Card className="tradeoff-card"><div className="card-top"><div><h2>Trade-off scorecard</h2><p>Structured prompts for researcher judgment; these are not validated clinical scores.</p></div><Badge kind="amber">Review required</Badge></div><div className="tradeoff-grid"><div><span>Recruitment reach</span><b className="tradeoff-positive">Population impact</b><p>{modeledDelta !== null && modeledDelta > 0 ? 'More patients pass the modeled checks.' : 'No modeled increase in passing patients.'}</p></div><div><span>Patient safety</span><b className="tradeoff-review">Requires review</b><p>Check whether the changed threshold affects patient risk.</p></div><div><span>Scientific validity</span><b className="tradeoff-review">Requires review</b><p>Confirm the proposed population still answers the study question.</p></div><div><span>Generalizability</span><b className="tradeoff-review">Requires review</b><p>Consider whether the trial better reflects the intended population.</p></div></div></Card>
    <div className="review-ledger"><div className="section-header"><div><h2>Change ledger</h2><p>One decision per proposed criterion.</p></div><Badge kind="gray">{comparison.changed_rule_ids.length} proposed</Badge></div>
    {comparison.changes.map(change => { const old = workspace.analysis!.rules.find(r => r.id === change.rule_id)!; const next = workspace.draft.find(r => r.id === change.rule_id)!; const safety = comparison.safety_review_rule_ids.includes(change.rule_id); const decision = workspace.decisions[change.rule_id]; const reason = reasons[change.rule_id] ?? decision?.reason ?? ''; return <Card className={`ledger-card ${decision ? 'is-reviewed' : ''}`} key={change.rule_id}>
      <div className="ledger-heading"><div><span className="criterion-number">{change.rule_id}</span><h3>{readable(change.change)} threshold</h3></div><Badge kind={decision?.decision === 'accepted' ? 'sage' : decision?.decision === 'rejected' ? 'gray' : safety ? 'amber' : 'gray'}>{decision?.decision ?? (safety ? 'Safety review' : 'Pending')}</Badge></div>
      <p className="ledger-criterion">{old.clause ?? old.text}</p><div className="redline"><div><small>Original</small><del>{ruleValue(old)}</del></div><ArrowRight size={17} /><div><small>Proposed</small><ins>{ruleValue(next)}</ins></div></div>
      <div className="ledger-meta"><span>{readable(old.purpose)}</span><span>{old.source} source</span><span>{old.fidelity} parse</span></div>
      <label className="review-reason">Researcher rationale {safety ? '(required)' : '(optional)'}<textarea aria-label={`Review reason ${change.rule_id}`} placeholder="Why is this change acceptable or not acceptable?" value={reason} onChange={event => setReasons({ ...reasons, [change.rule_id]: event.target.value })} /></label>
      <div className="ledger-actions"><button className="btn primary" disabled={safety && !reason.trim()} onClick={() => decide(change.rule_id, { decision: 'accepted', reason: reason.trim(), at: new Date().toISOString() })}><CheckCircle2 size={15} /> Accept</button><button className="btn outline" onClick={() => decide(change.rule_id, { decision: 'rejected', reason: reason.trim(), at: new Date().toISOString() })}>Reject</button></div>
    </Card> })}</div>
    <Card className="review-export"><div><h3>Ready to export?</h3><p>Export preserves the baseline, proposed values, decisions, rationales, and modeled comparison.</p></div><button className="btn primary" disabled={!allReviewed} onClick={download}><Download size={16} /> Download review record</button></Card>
  </div>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview'), [mobileOpen, setMobileOpen] = useState(false)
  const [inputMode, setInputMode] = useState<'nct' | 'text'>('nct'), [nctId, setNctId] = useState(''), [text, setText] = useState('')
  const [mode, setMode] = useState(defaultPopulationMode('nct')), [size, setSize] = useState(10000), [seed, setSeed] = useState(42), [useLlm, setUseLlm] = useState(false)
  const [health, setHealth] = useState<ApiHealth | null>(null)
  const [chalkCheck, setChalkCheck] = useState<ChalkCheck | null>(null), [checkingChalk, setCheckingChalk] = useState(false)
  const [catalog, setCatalog] = useState<PopulationCatalog | null>(null), [variables, setVariables] = useState<Record<string, VariableMeta>>({})
  const [catalogError, setCatalogError] = useState<string | null>(null), [error, setError] = useState<string | null>(null), [busy, setBusy] = useState<'analysis' | 'compare' | 'rare' | null>(null), [selectedId, setSelectedId] = useState('')
  const initialHistoryState = useRef(false)
  const [rareReach, setRareReach] = useState<RareReachResponse | null>(null)
  const option = catalog?.options.find(item => item.mode === mode)
  const population = useMemo<PopulationChoice>(() => ({ mode, size: mode !== 'generated' ? option?.size ?? 500 : size, seed: mode !== 'generated' ? option?.seed ?? 0 : seed, version: option?.version, ...(option?.cohort_id ? { cohort_id: option.cohort_id } : {}) }), [mode, size, seed, option])
  const context = JSON.stringify([inputMode, nctId.trim().toUpperCase(), text, population, useLlm])
  const [workspace, dispatch] = useReducer(workspaceReducer, context, emptyWorkspace)
  const controller = useRef<AbortController | null>(null), sequence = useRef(0)
  function cancel() { sequence.current++; controller.current?.abort(); setBusy(null) }
  useEffect(() => {
    const abort = new AbortController()
    Promise.all([getPopulations(abort.signal), getVariables(abort.signal), getHealth(abort.signal)]).then(([populations, metadata, status]) => { setCatalog(populations); setVariables(metadata); setHealth(status); setCatalogError(null) }).catch(cause => { if (!abort.signal.aborted) setCatalogError(`Cannot reach the backend. Start FastAPI on port 8000. ${String(cause)}`) })
    return () => abort.abort()
  }, [])
  useEffect(() => { cancel(); dispatch({ type: 'reset', context }); setError(null) }, [context])
  useEffect(() => {
    const current = window.history.state
    if (current?.clinovaTab) setTab(current.clinovaTab as Tab)
    else window.history.replaceState({ ...(current ?? {}), clinovaTab: 'overview' }, '', window.location.href)
    const onPopState = (event: PopStateEvent) => {
      const next = event.state?.clinovaTab as Tab | undefined
      if (next) setTab(next)
    }
    window.addEventListener('popstate', onPopState)
    initialHistoryState.current = true
    return () => window.removeEventListener('popstate', onPopState)
  }, [])
  useEffect(() => () => controller.current?.abort(), [])
  // Verify the Chalk gateway once on load so the AI fallback can start enabled.
  useEffect(() => { if (health?.llm_configured && !chalkCheck && !checkingChalk) void testChalk() }, [health])
  const analysis = workspace.analysis, baseline = analysis?.rules ?? [], changes = changedRules(baseline, workspace.draft)
  const selected = workspace.draft.find(r => r.id === selectedId) ?? workspace.draft[0]
  const populationValid = mode !== 'generated' || (Number.isInteger(size) && size >= 100 && size <= 200000 && Number.isInteger(seed) && seed >= 0 && seed <= 4294967295)
  const inputValid = inputMode === 'nct' ? /^NCT\d{8}$/.test(nctId.trim().toUpperCase()) : Boolean(text.trim()) && text.length <= 30000
  async function testChalk() {
    setCheckingChalk(true); setError(null)
    try {
      const result = await checkChalk()
      setChalkCheck(result)
      setUseLlm(result.status === 'ready')   // AI fallback is on by default only after a live check passes
    } catch (cause) { setError(String(cause)) }
    finally { setCheckingChalk(false) }
  }
  async function analyze() {
    cancel(); const requestId = sequence.current; const abort = new AbortController(); controller.current = abort
    dispatch({ type: 'reset', context }); setRareReach(null); setBusy('analysis'); setError(null)
    try {
      const result = await analyzeTrial({ ...(inputMode === 'nct' ? { nct_id: nctId.trim().toUpperCase() } : { eligibility_text: text }), use_llm: useLlm }, population, abort.signal)
      if (requestId !== sequence.current) return
      if (result.simulation.cohort.mode !== population.mode) throw new Error('Population mismatch. Reload and rerun the analysis.')
      dispatch({ type: 'analyzed', context, result }); setSelectedId(result.rules[0]?.id ?? ''); go('analysis')
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
  async function loadRareReach() {
    if (!analysis?.trial.nct_id) return
    cancel(); const requestId = sequence.current; const abort = new AbortController(); controller.current = abort; setBusy('rare'); setError(null)
    try { const result = await getRareReach(analysis.trial.nct_id, workspace.draft, abort.signal); if (requestId === sequence.current) setRareReach(result) }
    catch (cause) { if (!abort.signal.aborted && requestId === sequence.current) setError(String(cause)) }
    finally { if (requestId === sequence.current) setBusy(null) }
  }
  function edit(field: 'value' | 'value_max', value: number) { if (selected) { cancel(); dispatch({ type: 'edit', id: selected.id, field, value }) } }
  const go = (next: Tab) => {
    if (next !== tab && initialHistoryState.current) window.history.pushState({ clinovaTab: next }, '', window.location.href)
    setTab(next); setMobileOpen(false)
  }
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? 'shown' : ''}`}><div className="logo-wrap"><div className="logo-mark"><Leaf size={22} /></div><div><div className="logo-text">CliNova<span className="logo-period">.</span></div><div className="logo-sub">Clinical trial intelligence</div></div><button className="close-mobile" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={19} /></button></div><div className="workspace-label">WORKSPACE</div><nav className="nav">{tabs.map(item => <button key={item.id} className={`nav-item ${tab === item.id ? 'active' : ''}`} onClick={() => go(item.id)}><item.icon size={18} />{item.name}</button>)}</nav><div className="side-bottom"><div className="side-footer"><ShieldCheck size={17} /> Researcher review required</div></div></aside>
    <div className="mobile-shade" onClick={() => setMobileOpen(false)} style={{ display: mobileOpen ? 'block' : 'none' }} /><div className="main-area"><header className="topbar"><button className="menu-btn" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><button className="back-button" disabled={tab === 'overview'} onClick={() => window.history.back()} aria-label="Go back"><ArrowLeft size={16} /> Back</button><div className="crumb">CliNova <ChevronRight size={14} /> {tabs.find(item => item.id === tab)?.name}</div><span className="demo-pill"><FlaskConical size={15} /> {mode === 'synthea' ? 'Synthea patients' : mode === 'fixed' ? 'Patient population' : 'Exploration population'}</span></header>
    <main className="content"><div className="page-heading"><div><h1>{tabs.find(item => item.id === tab)?.name}</h1></div></div>
      {catalogError && <div className="error-notice" role="alert">{catalogError}<button className="btn outline" onClick={() => window.location.reload()}>Retry connection</button></div>}{error && <div className="error-notice" role="alert"><ShieldAlert size={18} />{error}</div>}
      {tab === 'overview' && <Card className="welcome-card"><div className="welcome-icon"><FlaskConical size={20} /></div><div><span className="eyebrow">CLINOVA WORKSPACE</span><h2>Understand eligibility before changing the protocol.</h2><p>Load a trial, review each criterion, and compare proposed changes using clear patient-level results.</p></div></Card>}
      <Card className="population-controls"><div className="population-field"><label htmlFor="population-mode">Patient population</label><select id="population-mode" value={mode} onChange={event => { cancel(); setMode(event.target.value as PopulationMode) }}>{(catalog?.options.filter(item => item.visible !== false || item.mode === mode) ?? []).map(item => <option key={item.mode} value={item.mode}>{item.label}</option>)}</select></div>{mode === 'generated' && <><label>Population size<input aria-label="Population size" type="number" min={100} max={200000} value={size} onChange={event => { cancel(); setSize(Number(event.target.value)) }} /></label><label>Seed<input aria-label="Population seed" type="number" min={0} max={4294967295} value={seed} onChange={event => { cancel(); setSeed(Number(event.target.value)) }} /></label></>}<p>{mode === 'synthea' ? 'Synthetic adults generated with Synthea (open-source patient simulator), the same patients for every comparison. Anything Synthea does not simulate, such as ECOG, stays unknown.' : mode === 'fixed' ? 'Uses the selected patient records for every comparison.' : 'Use a repeatable exploration population. Changing these settings starts a new analysis.'} {option && <b>Version: {option.version}</b>}</p>{!populationValid && <span className="error-text">Use an integer size of 100–200,000 and a nonnegative 32-bit seed.</span>}</Card>
      {tab === 'overview' ? <div className="results-stack"><Card><div className="card-top"><div><h2>Analyze a trial</h2><p>Enter a trial identifier or paste eligibility criteria.</p></div><Badge kind="gray">No mock results</Badge></div><div className="toolbar-actions"><button className={`btn ${inputMode === 'nct' ? 'primary' : 'outline'}`} onClick={() => { cancel(); setInputMode('nct'); setMode(defaultPopulationMode('nct')) }}>ClinicalTrials.gov ID</button><button className={`btn ${inputMode === 'text' ? 'primary' : 'outline'}`} onClick={() => { cancel(); setInputMode('text'); setMode(defaultPopulationMode('text')) }}>Paste criteria</button></div>
        {inputMode === 'nct' ? <label className="source-input">ClinicalTrials.gov identifier<input aria-label="ClinicalTrials.gov identifier" placeholder="NCT followed by 8 digits" value={nctId} onChange={event => { cancel(); setNctId(event.target.value) }} /></label> : <label className="source-input">Eligibility criteria<textarea aria-label="Eligibility criteria" maxLength={30000} rows={10} value={text} onChange={event => { cancel(); setText(event.target.value) }} /><small>{text === exampleProtocol ? 'Example criteria loaded.' : `${text.length.toLocaleString()} / 30,000 characters`}</small></label>}
        <label className="checkbox-label"><input type="checkbox" disabled={!health?.llm_configured || Boolean(chalkCheck && chalkCheck.status !== 'ready')} checked={useLlm} onChange={event => { cancel(); setUseLlm(event.target.checked) }} />Use Chalk AI fallback for unread criteria (may take up to the server time budget)</label><p className="muted" role="status">Chalk AI: {chalkCheck ? `${chalkCheck.status === 'ready' ? 'Live check passed' : 'Live check failed'} · ${chalkCheck.message} Checked ${new Date(chalkCheck.checked_at).toLocaleTimeString()}.` : health ? health.llm_configured ? `Configured (${health.model}); live connection not verified. Only used when the checkbox is enabled and unread criteria remain.` : `Not configured. Missing: ${health.llm_missing_configuration.join(', ')}. Deterministic parsing still works.` : 'Checking configuration…'}        </p><div className="toolbar-actions connection-actions"><button className="btn outline" disabled={!health?.llm_configured || checkingChalk || Boolean(busy)} onClick={testChalk}>{checkingChalk ? 'Testing Chalk…' : 'Test live Chalk connection'}        </button></div><div className="toolbar-actions analysis-actions"><button className="btn primary" disabled={!catalog || !inputValid || !populationValid || Boolean(busy)} onClick={analyze}>{busy === 'analysis' ? 'Analyzing…' : 'Load and analyze'} <ArrowRight size={16} /></button>{busy && <button className="btn outline" onClick={cancel}>Cancel</button>}</div></Card></div> : !analysis ? <Card><div className="empty-view"><FlaskConical size={30} /><h2>Start with a trial or public eligibility text</h2><p>Changing the population or source clears the previous baseline and review decisions.</p><button className="btn primary" onClick={() => go('overview')}>Set up analysis <ArrowRight size={16} /></button></div></Card> : <>
        <div className="trial-heading"><h2>{analysis.trial.title ?? (text === exampleProtocol ? 'Fictional example protocol' : 'Pasted eligibility criteria')}</h2><span>{analysis.trial.nct_id ?? 'Public text input'} · {baseline.length} parsed rules</span>{analysis.trial.nct_id && <a href={`https://clinicaltrials.gov/study/${encodeURIComponent(analysis.trial.nct_id)}`} target="_blank" rel="noreferrer">Registry source ↗</a>}</div>
        <Warnings items={analysis.warnings.filter(warning => !analysis.simulation.warnings.includes(warning) || tab === 'review')} />
        {tab === 'analysis' && <><div className="toolbar-actions analysis-actions"><button className="btn primary" onClick={() => go('scenario')}>Edit a draft <ArrowRight size={16} /></button></div><Results result={analysis.simulation} rules={baseline} variables={variables} /></>}
        {tab === 'scenario' && <><div className="scenario-toolbar"><div><h2>Draft eligibility rules</h2><p>Original rules stay intact. Changes apply only to this exploratory draft.</p></div><div className="toolbar-actions"><button className="btn outline" disabled={!changes.length || Boolean(busy)} onClick={() => dispatch({ type: 'analyzed', context, result: analysis })}><RotateCcw size={15} />Reset draft</button><button className="btn primary" disabled={!changes.length || !validDraft(workspace.draft) || Boolean(busy)} onClick={compare}>{busy === 'compare' ? 'Comparing…' : 'Compare draft'}<ArrowRight size={16} /></button>{busy && <button className="btn outline" onClick={cancel}>Cancel</button>}</div></div>
          {!validDraft(workspace.draft) && <div className="error-notice">Enter finite numeric thresholds and keep upper bounds at least as large as lower bounds.</div>}
          <div className="scenario-grid connected-grid"><Card className="criteria-card"><div className="card-top"><h3>Parsed rules</h3><Badge kind="gray">{baseline.length}</Badge></div><div className="criteria-list">{workspace.draft.map(rule => <button key={rule.id} className={`criterion-item ${selected?.id === rule.id ? 'selected' : ''}`} onClick={() => setSelectedId(rule.id)}><span className="criterion-number">{rule.id}</span><span><strong>{variables[rule.variable ?? '']?.label ?? readable(rule.category)}</strong><small>{rule.clause ?? rule.text}</small></span><Badge kind={rule.simulatable && option?.available_variables.includes(rule.variable ?? '') ? 'sage' : 'gray'}>{rule.simulatable ? option?.available_variables.includes(rule.variable ?? '') ? 'Modeled' : 'Unavailable' : 'Unmodeled'}</Badge></button>)}</div></Card>{selected && <RuleEditor rule={selected} original={baseline.find(r => r.id === selected.id)!} metadata={variables[selected.variable ?? '']} available={Boolean(option?.available_variables.includes(selected.variable ?? ''))} onEdit={edit} />}</div>
          {workspace.comparison ? <div className="results-stack comparison-stack"><Comparison result={workspace.comparison} /><button className="btn primary" onClick={() => go('review')}>Review proposed changes <FileCheck2 size={16} /></button><Results result={workspace.comparison.proposed} rules={workspace.draft} variables={variables} /></div> : <div className="notice"><CircleHelp size={17} />{changes.length ? `${changes.length} edited rule(s). Compare the draft to update results.` : 'Select a supported numeric rule to explore a threshold change.'}</div>}
        </>}
        {tab === 'rare' && (analysis.trial.nct_id ? <RareReach result={rareReach} loading={busy === 'rare'} onLoad={loadRareReach} /> : <Card><div className="empty-view"><MapPinned size={30} /><h2>RareReach needs an NCT ID</h2><p>Load a public ClinicalTrials.gov trial first. Pasted text has no registry condition or public site history to research.</p><button className="btn primary" onClick={() => go('overview')}>Load a trial <ArrowRight size={16} /></button></div></Card>)}
        {tab === 'review' && <Review workspace={workspace} decide={(id, decision) => dispatch({ type: 'decide', id, decision })} />}
      </>}
    </main><footer className="footer"><div><Leaf size={15} /> CliNova</div><span>Qualified researcher review required</span></footer></div>
  </div>
}
