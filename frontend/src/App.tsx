import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BarChart3, CheckCircle2, ChevronRight, CircleHelp, Download, FileCheck2, FlaskConical, Info, LayoutDashboard, Leaf, MapPinned, Menu, RotateCcw, ShieldAlert, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import { analyzeTrial, checkChalk, compareCriteria, getHealth, getPopulations, getRareReach, getVariables } from './simulationService'
import { changedRules, defaultPopulationMode, emptyWorkspace, notCheckedDetail, validDraft, workspaceReducer } from './workspace'
import { exampleProtocol } from './exampleProtocol'
import type { ApiHealth, ChalkCheck, CompareResult, PopulationCatalog, PopulationChoice, PopulationMode, RareReachResponse, ReviewDecision, Rule, SimulationResult, VariableMeta } from './scenarioTypes'
import type { Workspace } from './workspace'
import { AutopilotCard } from './AutopilotCard'

type Tab = 'overview' | 'analysis' | 'scenario' | 'rare' | 'review'
const tabs = [
  { id: 'overview' as const, name: 'Trial setup', icon: LayoutDashboard },
  { id: 'analysis' as const, name: 'Results', icon: BarChart3 },
  { id: 'scenario' as const, name: 'Scenario analysis', icon: SlidersHorizontal },
  { id: 'review' as const, name: 'Review', icon: FileCheck2 },
  { id: 'rare' as const, name: 'RareReach', icon: MapPinned },
]
const readable = (text: string) => text.replaceAll('_', ' ')
const count = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toLocaleString()
const pct = (value: number | null) => value === null ? 'Unavailable' : `${value.toFixed(2)}%`
function ruleValue(rule: Rule) { return rule.operator === 'between' ? `${rule.value}–${rule.value_max} ${rule.unit ?? ''}` : `${rule.operator ?? 'Unmodeled'} ${rule.value ?? ''} ${rule.unit ?? ''}` }
function ruleTagLabel(id: string, kind?: Rule['kind']) {
  const match = id.match(/^([IE])(\d+)([a-z])?$/)
  if (match) return `${match[1] === 'I' ? 'Inclusion' : 'Exclusion'} criterion ${match[2]}${match[3] ?? ''}`
  if (id.startsWith('REG-')) return `Registry ${readable(id.slice(4)).toLowerCase()}`
  return kind ? `${readable(kind)} criterion` : 'Protocol criterion'
}
function Badge({ children, kind = 'sage' }: { children: React.ReactNode; kind?: 'sage' | 'amber' | 'gray' | 'red' }) { return <span className={`badge ${kind}`}>{children}</span> }
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section> }
function Stat({ label, value, sub }: { label: string; value: string; sub: string }) { return <Card className="stat"><span className="stat-label">{label}</span><strong>{value}</strong><p>{sub}</p></Card> }
function Warnings({ items }: { items: string[] }) { return items.length ? <div className="notice notice-list" role="status"><CircleHelp size={18} /><ul>{[...new Set(items)].map(item => <li key={item}>{item}</li>)}</ul></div> : null }
function Evidence({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="evidence-drawer"><summary><Info size={14} />{title}</summary><div>{children}</div></details>
}
function notCheckedKind(status: string): 'amber' | 'red' | 'gray' {
  if (status === 'No data in population') return 'amber'
  if (status === 'Not modeled') return 'red'
  return 'gray'
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

function VisualAnalysis({ result, rules }: { result: SimulationResult; rules: Rule[] }) {
  const eligible = result.modeled_eligible_n ?? 0
  const unknown = result.modeled_unknown_n
  const excluded = result.excluded_n
  const total = Math.max(result.population_n, 1)
  const names = new Map(rules.map(rule => [rule.id, rule.simulatable ? `${readable(rule.variable ?? '')} ${ruleValue(rule)}` : rule.clause || rule.text]))
  const impacts = [...result.impacts].filter(item => !result.not_applicable_rule_ids.includes(item.rule_id)).sort((a, b) => b.fail_n - a.fail_n).slice(0, 6)
  return <details className="results-section" open><summary>Visual cohort analysis <Badge kind="sage">Overview</Badge></summary><div className="visual-analysis">
    <Card className="population-chart"><div className="card-top"><div><span className="eyebrow">AT A GLANCE</span><h2>What happened to the cohort?</h2><p>Each segment is mutually exclusive for the modeled checks.</p></div><Badge kind={result.complete ? 'sage' : 'amber'}>{pct(result.modeled_eligible_pct)} eligible</Badge></div>
      <div className="cohort-bar" role="img" aria-label={`${count(eligible)} passing, ${count(excluded)} excluded, ${count(unknown)} unknown`}><span className="cohort-pass" style={{ width: `${100 * eligible / total}%` }} /><span className="cohort-fail" style={{ width: `${100 * excluded / total}%` }} /><span className="cohort-unknown" style={{ width: `${100 * unknown / total}%` }} /></div>
      <div className="chart-legend"><span><i className="legend-dot pass" />Passing <b>{count(eligible)}</b></span><span><i className="legend-dot fail" />Excluded <b>{count(excluded)}</b></span><span><i className="legend-dot unknown" />Unknown <b>{count(unknown)}</b></span></div>
      <Evidence title="What counts as unknown?"><p>Unknown patients have missing or unavailable information. They are not counted as eligible or excluded. Rules that could not be modeled remain outside this headline.</p></Evidence>
    </Card>
    <Card className="impact-chart"><div className="card-top"><div><span className="eyebrow">RECRUITMENT BOTTLENECKS</span><h2>Which rules remove the most patients?</h2><p>Top modeled exclusions, ranked by failure count.</p></div><Badge kind="gray">{impacts.length} shown</Badge></div>
      <div className="horizontal-bars">{impacts.length ? impacts.map(item => <div className="chart-row" key={item.rule_id}><div className="chart-label"><strong>{item.rule_id}</strong><span>{names.get(item.rule_id)}</span><b>{count(item.fail_n)}</b></div><div className="chart-track"><i style={{ width: `${Math.min(100, item.fail_pct)}%` }} /></div><small>{item.fail_pct.toFixed(1)}% of cohort</small></div>) : <p className="empty-state">No modeled rule impacts are available.</p>}</div>
    </Card>
  </div></details>
}

function Results({ result, rules, variables = {} }: { result: SimulationResult; rules: Rule[]; variables?: Record<string, VariableMeta> }) {
  const names = new Map(rules.map(rule => [rule.id, rule.simulatable ? `${rule.kind}: ${readable(rule.variable ?? '')} ${ruleValue(rule)}` : rule.clause || rule.text]))
  const rankedImpacts = [...result.impacts].sort((a, b) => b.fail_n - a.fail_n)
  return <div className="results-stack"><Summary result={result} /><VisualAnalysis result={result} rules={rules} />
    <details className="results-section"><summary>Eligibility funnel <Badge kind="gray">{result.modeled_rule_ids.length} checks</Badge></summary><Card><div className="card-top"><div><h2>Eligibility funnel</h2><p>{result.modeled_rule_ids.length} checks applied in protocol order.</p></div></div>
      {result.modeled_rule_ids.length ? <div className="funnel-dashboard">{result.funnel.map(step => <div className="funnel-step" key={step.rule_id ?? 'start'}><div className="funnel-step-heading"><strong>{step.rule_id ?? 'Start'}</strong><span>{step.label}</span><b>{count(step.remaining_n)} passing</b></div><div className="funnel-track"><span style={{ width: `${100 * step.remaining_n / result.population_n}%` }} /></div><div className="funnel-step-meta"><span>{pct(step.remaining_pct)} remaining</span><span>{count(step.unknown_n)} unknown</span><span>{count(result.population_n - step.remaining_n - step.unknown_n)} excluded</span></div></div>)}</div> : <p className="empty-state">No eligibility checks are available for this population.</p>}
    </Card></details>
    {result.unmodeled_rule_ids.length > 0 && <details className="results-section"><summary>Not checked <Badge kind="amber">{result.unmodeled_rule_ids.length} rules</Badge></summary><Card><div className="card-top"><div><h2>Not checked criteria</h2><p>Review these criteria before making protocol decisions.</p></div></div><div className="table-scroll"><table className="status-table"><thead><tr><th>Rule</th><th>Requirement</th><th>Status</th><th>Next step</th></tr></thead><tbody>{result.unmodeled_rule_ids.map(id => { const rule = rules.find(item => item.id === id); const detail = rule ? notCheckedDetail(rule, variables) : null; return <tr key={id}><td><b>{id}</b></td><td>{detail?.what ?? rule?.clause ?? id}</td><td><Badge kind={notCheckedKind(detail?.badge ?? 'Not modeled')}>{detail?.badge ?? 'Not modeled'}</Badge></td><td>{detail?.badge === 'No data in population' ? 'Add this field to the cohort' : 'Qualified researcher review'}</td></tr> })}</tbody></table></div></Card></details>}
    <details className="results-section"><summary>Rule impact <Badge kind="amber">{result.worst_rule_id ? `Largest: ${ruleTagLabel(result.worst_rule_id, rules.find(rule => rule.id === result.worst_rule_id)?.kind)}` : 'Ranked'}</Badge></summary><Card><div className="card-top"><div><h2>Rule impact</h2><p>Rules ranked by patients excluded. Select a row for the detailed counts.</p></div><Badge kind="amber">Largest impact: {result.worst_rule_id ? ruleTagLabel(result.worst_rule_id, rules.find(rule => rule.id === result.worst_rule_id)?.kind) : 'Unavailable'}</Badge></div>
      <div className="impact-dashboard">{rankedImpacts.map(impact => { const rule = rules.find(item => item.id === impact.rule_id); return <details className="impact-row" key={impact.rule_id}><summary><span className="impact-rule"><strong>{impact.rule_id}</strong><span className="impact-rule-tag">{ruleTagLabel(impact.rule_id, rule?.kind)}</span><span>{names.get(impact.rule_id)}</span></span>{result.not_applicable_rule_ids.includes(impact.rule_id) ? <Badge kind="gray">Not applicable</Badge> : <span className="impact-fail-count">{count(impact.fail_n)} fail</span>}</summary>{!result.not_applicable_rule_ids.includes(impact.rule_id) && <div className="impact-bar"><span style={{ width: `${Math.min(100, impact.fail_pct)}%` }} /></div>}<div className="impact-details"><span>Pass <b>{count(impact.pass_n)}</b></span><span>Fail <b>{count(impact.fail_n)}</b></span><span>Unknown <b>{count(impact.unknown_n)}</b></span><span>Unique fail <b>{count(impact.unique_fail_n)}</b></span></div></details> })}</div>
    </Card></details>
    <details className="results-section"><summary>Patient-level details <Badge kind="gray">{result.patient_results.length} available</Badge></summary><Card><h2>Patient explanations</h2><p className="muted">{result.patient_results_complete ? `All ${result.patient_results.length} patients returned.` : `Showing ${result.patient_results.length} patient records.`}</p>
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
  const maxEligible = Math.max(result.baseline.population_n, result.proposed.population_n, 1)
  const bars = [
    { label: 'Original', value: result.baseline.modeled_eligible_n ?? 0, tone: 'baseline' },
    { label: 'Modified', value: result.proposed.modeled_eligible_n ?? 0, tone: 'proposed' },
  ]
  return <Card><div className="card-top"><div><h2>Baseline versus modified</h2><p>Same cohort, version and patient identities on both sides.</p></div><Badge kind="gray">{result.cohort.mode}</Badge></div>
    <div className="comparison-visual"><div className="comparison-bars">{bars.map(bar => <div className="comparison-bar-row" key={bar.label}><span>{bar.label}</span><div className="comparison-track"><i className={bar.tone} style={{ width: `${100 * bar.value / maxEligible}%` }} /></div><b>{count(bar.value)}</b></div>)}</div><div className="comparison-delta"><span>Eligibility change</span><strong>{result.modeled_eligible_change_pct_points === null ? 'Unavailable' : `${result.modeled_eligible_change_pct_points > 0 ? '+' : ''}${result.modeled_eligible_change_pct_points.toFixed(2)} pp`}</strong><small>percentage points</small></div></div>
    <div className="stat-grid compact-stats"><Stat label="Excluded" value={`${count(result.baseline.excluded_n)} → ${count(result.proposed.excluded_n)}`} sub="At least one modeled failure" /><Stat label="Unknown" value={`${count(result.baseline.modeled_unknown_n)} → ${count(result.proposed.modeled_unknown_n)}`} sub="Missing values, not exclusions" /><Stat label="Newly passing" value={count(result.modeled_newly_eligible_n)} sub="Same cohort comparison" /></div>
    <p className="muted">Newly passing modeled checks: {count(result.modeled_newly_eligible_n)} · Newly excluded by checks: {count(result.modeled_newly_excluded_n)}. Not-checked requirements remain outside these counts.</p>
    {result.safety_review_rule_ids.length > 0 && <div className="warning-box" role="status"><ShieldAlert size={20} /><div><strong>Safety-sensitive changes require review</strong><p>Rules: {result.safety_review_rule_ids.join(', ')}. A larger passing group does not establish an acceptable safety trade-off. No draft is automatically accepted.</p></div></div>}
  </Card>
}

function RareReach({ result, loading, onLoad }: { result: RareReachResponse | null; loading: boolean; onLoad: () => void }) {
  const [decisions, setDecisions] = useState<Record<string, 'keep' | 'review'>>({})
  if (!result) return <Card><div className="empty-view"><MapPinned size={30} /><h2>Find public recruitment channels</h2><p>RareReach identifies public ClinicalTrials.gov site history and links to Orphanet and NORD research resources. It never accesses patient records or estimates patient volume.</p><button className="btn primary" disabled={loading} onClick={onLoad}>{loading ? 'Searching public sources…' : 'Research recruitment options'} <ArrowRight size={16} /></button></div></Card>
  if (!result.is_rare_disease) return <div className="results-stack rare-reach-page"><Card className="rare-hero"><div><span className="eyebrow">RARE-DISEASE VERIFICATION</span><h2>RareReach stopped here.</h2><p>{result.rare_disease_message}</p></div><Badge kind="amber">Rare disease not confirmed</Badge></Card><Card><h2>What was checked</h2><p>ClinicalTrials.gov condition: <b>{result.query_terms.join(', ') || 'Unavailable'}</b></p><p className="muted">RareReach did not search hospitals, specialist centres, NORD, or outreach strategies because this condition was not confirmed by an ORPHAcode.</p><div className="rare-source-list">{result.sources.map(source => <a className="rare-source" key={source.name} href={source.url} target="_blank" rel="noreferrer"><span>{source.name}</span><Badge kind={source.access === 'live' ? 'sage' : 'gray'}>{source.access}</Badge></a>)}</div></Card></div>
  const sites = [...result.hospitals].sort((a, b) => b.historical_trial_count - a.historical_trial_count)
  const maxHistory = Math.max(...sites.map(site => site.historical_trial_count), 1)
  const safetyCount = result.strategies.filter(item => item.safety_sensitive).length
  const outreachCount = result.strategies.length - safetyCount
  const strategyTotal = Math.max(result.strategies.length, 1)
  const diseaseLabel = result.orpha_preferred_name ?? result.query_terms[0] ?? 'this condition'
  return <div className="results-stack rare-reach-page">
    <div className="rare-hero"><div><span className="eyebrow">PUBLIC RECRUITMENT INTELLIGENCE</span><h2>Turn rare-disease history into outreach decisions.</h2><p>Use public trial-site patterns and criterion-level actions to decide where to investigate recruitment next. No patient volume or clinical benefit is inferred.</p></div><Badge kind={result.orpha_status === 'matched' ? 'sage' : 'amber'}>{result.orpha_status === 'matched' ? 'Condition matched' : 'Match needs review'}</Badge></div>
    <div className="stat-grid impact-stats rare-stats"><Stat label="Potential site leads" value={sites.length.toLocaleString()} sub="Public US history returned" /><Stat label="Highest site signal" value={sites[0] ? sites[0].historical_trial_count.toLocaleString() : '0'} sub={sites[0]?.name ?? 'No site history'} /><Stat label="Criteria to plan around" value={result.strategies.length.toLocaleString()} sub={`${safetyCount} safety-sensitive`} /><Stat label="Condition reference" value={result.orpha_code ?? 'Review'} sub={diseaseLabel} /></div>
    <details className="results-section rare-section" open><summary>Recruitment opportunity map <Badge kind="sage">Action first</Badge></summary><div className="rare-grid"><Card><div className="card-top"><div><h2>Where should outreach start?</h2><p>Ranked by matching public trial history, not estimated patient volume.</p></div><Badge kind="gray">{sites.length} leads</Badge></div>{sites.length ? <div className="rare-site-bars">{sites.slice(0, 6).map((site, index) => <div className="rare-site-row" key={`${site.name}-${site.city}`}><div><b>{index + 1}. {site.name}</b><span>{[site.city, site.region].filter(Boolean).join(', ') || 'Location unavailable'}</span></div><div className="rare-bar-track"><i style={{ width: `${100 * site.historical_trial_count / maxHistory}%` }} /></div><strong>{site.historical_trial_count}</strong></div>)}</div> : <p className="empty-state">No public site history was returned for this trial.</p>}</Card>
      <Card className="rare-split-card"><div className="card-top"><div><h2>What kind of work is needed?</h2><p>Separate outreach opportunities from criteria needing clinical review.</p></div></div><div className="rare-donut-wrap"><div className="rare-donut" style={{ background: `conic-gradient(#d99a57 0 ${100 * safetyCount / strategyTotal}%, #6e9d80 ${100 * safetyCount / strategyTotal}% 100%)` }}><div><strong>{result.strategies.length}</strong><span>criteria</span></div></div><div className="rare-legend"><span><i className="legend-dot fail" />Safety-sensitive <b>{safetyCount}</b></span><span><i className="legend-dot pass" />Outreach planning <b>{outreachCount}</b></span></div></div><p className="rare-callout"><ShieldAlert size={16} />A larger recruitment channel is not evidence that a safety criterion should be relaxed.</p></Card></div></details>
    <details className="results-section rare-section" open><summary>Outreach action queue <Badge kind="gray">{result.strategies.length} criteria</Badge></summary><Card><div className="card-top"><div><h2>What to do next</h2><p>Choose a next step for each criterion. These choices do not change the protocol.</p></div></div><div className="rare-action-list">{result.strategies.map(item => { const decision = decisions[item.rule_id]; return <div className={`rare-action${decision ? ' is-decided' : ''}`} key={item.rule_id}><div className="rare-action-heading"><b>{item.rule_id}</b><Badge kind={item.safety_sensitive ? 'amber' : 'sage'}>{item.safety_sensitive ? 'Clinical review' : 'Outreach lead'}</Badge></div><p>{item.criterion}</p>{item.safety_sensitive ? <><strong>Decide how to proceed with this safety-sensitive criterion:</strong><div className="rare-decision-buttons" role="group" aria-label={`Decision for ${item.rule_id}`}><button className={decision === 'keep' ? 'selected' : ''} onClick={() => setDecisions(current => ({ ...current, [item.rule_id]: 'keep' }))}>Keep restriction</button><button className={decision === 'review' ? 'selected' : ''} onClick={() => setDecisions(current => ({ ...current, [item.rule_id]: 'review' }))}>Ask qualified reviewer</button></div>{decision && <p className="rare-decision-status">{decision === 'keep' ? 'Restriction marked to remain in place while outreach is explored.' : 'Reviewer assessment requested before considering specialist-site outreach.'}</p>}</> : <strong>Investigate specialist centers, advocacy groups, and registries that may reach this population.</strong>}</div> })}</div></Card></details>
    <details className="results-section rare-section"><summary>Evidence and public links <Badge kind="gray">{result.sources.length} sources</Badge></summary><Card><div className="rare-evidence-grid"><div><h2>Condition reference</h2><p>{result.orpha_code ? <><b>ORPHAcode {result.orpha_code}</b> · {result.orpha_preferred_name ?? 'Preferred term unavailable'}</> : 'No ORPHAcode match is claimed.'}</p><p className="muted">{result.orpha_synonyms.length ? `Search terms: ${result.orpha_synonyms.slice(0, 4).join(', ')}` : 'No additional public synonyms returned.'}</p>{result.nord_url && <a href={result.nord_url} target="_blank" rel="noreferrer">Open NORD resources ↗</a>}</div><div><h2>Source register</h2>{result.sources.map(source => <a className="rare-source" key={source.name} href={source.url} target="_blank" rel="noreferrer"><span>{source.name}</span><Badge kind={source.access === 'live' ? 'sage' : 'gray'}>{source.access}</Badge></a>)}</div></div></Card></details>
  </div>
}

function Review({ workspace, decide }: { workspace: Workspace; decide: (id: string, decision: ReviewDecision) => void }) {
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [printing, setPrinting] = useState(false)
  const comparison = workspace.comparison
  useEffect(() => {
    if (!printing) return
    const timer = window.setTimeout(() => window.print(), 100)
    const finish = () => setPrinting(false)
    window.addEventListener('afterprint', finish)
    return () => { window.clearTimeout(timer); window.removeEventListener('afterprint', finish) }
  }, [printing])
  if (!comparison || !workspace.analysis) return <Card><div className="empty-view"><FileCheck2 size={28} /><h2>Compare a draft first</h2><p>Researcher review uses the latest comparison for the current cohort.</p></div></Card>
  const allReviewed = comparison.changed_rule_ids.length > 0 && comparison.changed_rule_ids.every(id => workspace.decisions[id])
  const reviewedCount = comparison.changed_rule_ids.filter(id => workspace.decisions[id]).length
  const modeledDelta = comparison.modeled_eligible_change_pct_points
  const reviewedChanges = comparison.changed_rule_ids.map(id => {
    const original = workspace.analysis!.rules.find(rule => rule.id === id)
    const proposed = workspace.draft.find(rule => rule.id === id)
    const decision = workspace.decisions[id]
    return { id, original, proposed, decision, reason: reasons[id] || 'No rationale provided.' }
  })
  const statusLabel = (decision: ReviewDecision['decision'] | undefined) => decision === 'accepted' ? 'Accepted' : 'Rejected'
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
    <Card className="review-export"><div><h3>Ready to export?</h3><p>Generate a plain-language decision brief with the baseline, selected changes, trade-offs, and modeled impact.</p></div><button className="btn primary" disabled={!allReviewed} onClick={() => setPrinting(true)}><Download size={16} /> Generate PDF report</button></Card>
    {printing && <article className="print-report" aria-label="TrialMax decision brief">
      <header className="print-report-header"><div><strong>TrialMax.</strong><span>Clinical trial intelligence</span></div><span>Protocol decision brief</span></header>
      <h1>Eligibility protocol decision brief</h1>
      <p className="print-report-subtitle">A concise summary of the reviewed protocol changes and their modeled impact.</p>
      <div className="print-report-meta"><div><b>Trial</b><span>{workspace.analysis!.trial.nct_id ?? 'Pasted protocol'} · {workspace.analysis!.trial.title ?? 'Title unavailable'}</span></div><div><b>Population</b><span>{comparison.cohort.label} · {comparison.cohort.id}</span></div><div><b>Generated</b><span>{new Date().toLocaleString()}</span></div></div>
      <section><h2>Executive summary</h2><div className="print-summary-grid"><div><b>Modeled eligibility</b><strong>{count(comparison.baseline.modeled_eligible_n)} → {count(comparison.proposed.modeled_eligible_n)}</strong><span>{modeledDelta === null ? 'Change unavailable' : `${modeledDelta > 0 ? '+' : ''}${modeledDelta.toFixed(2)} percentage points`}</span></div><div><b>Excluded patients</b><strong>{count(comparison.baseline.excluded_n)} → {count(comparison.proposed.excluded_n)}</strong><span>{count(comparison.modeled_newly_eligible_n)} newly passing modeled checks</span></div><div><b>Unknown patients</b><strong>{count(comparison.baseline.modeled_unknown_n)} → {count(comparison.proposed.modeled_unknown_n)}</strong><span>Missing or unavailable data</span></div></div></section>
      <section><h2>Starting protocol</h2><p>The original protocol contained {workspace.analysis!.rules.length} parsed criteria. The baseline values below are preserved and were used as the comparison reference.</p><ul className="print-rule-list">{workspace.analysis!.rules.map(rule => <li key={rule.id}><b>{rule.id}</b><span>{rule.clause ?? rule.text}</span><em>{ruleValue(rule)}</em></li>)}</ul></section>
      <section><h2>Reviewed recommendations</h2><table className="print-table"><thead><tr><th>Criterion</th><th>Original</th><th>Proposed</th><th>Decision</th><th>Rationale</th></tr></thead><tbody>{reviewedChanges.map(item => <tr key={item.id}><td><b>{item.id}</b><br />{item.original?.clause ?? item.original?.text ?? 'Unavailable'}</td><td>{item.original ? ruleValue(item.original) : 'Unavailable'}</td><td>{item.proposed ? ruleValue(item.proposed) : 'Unavailable'}</td><td className={item.decision?.decision === 'accepted' ? 'print-accepted' : 'print-rejected'}>{statusLabel(item.decision?.decision)}</td><td>{item.reason}</td></tr>)}</tbody></table></section>
      <section><h2>Trade-offs and interpretation</h2><ul><li><b>Performance:</b> The proposed draft changes modeled eligibility by {modeledDelta === null ? 'an unavailable amount' : `${modeledDelta > 0 ? '+' : ''}${modeledDelta.toFixed(2)} percentage points`} on the same synthetic cohort.</li><li><b>Recruitment:</b> {count(comparison.modeled_newly_eligible_n)} patients newly pass the modeled checks; this does not predict real enrollment.</li><li><b>Uncertainty:</b> Unknown results represent missing or unavailable data and are not counted as exclusions.</li><li><b>Safety:</b> Any safety-sensitive change remains subject to qualified clinical and scientific review.</li></ul></section>
      <footer className="print-report-footer">This report is an exploratory, synthetic-cohort analysis. It does not establish treatment safety, protocol approval, patient eligibility, site capacity, or real-world enrollment performance. Qualified researcher review is required.</footer>
    </article>}
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
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? 'shown' : ''}`}><div className="logo-wrap"><div className="logo-mark"><Leaf size={22} /></div><div><div className="logo-text">TrialMax<span className="logo-period">.</span></div><div className="logo-sub">Clinical trial intelligence</div></div><button className="close-mobile" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={19} /></button></div><div className="workspace-label">WORKSPACE</div><nav className="nav">{tabs.map(item => <button key={item.id} className={`nav-item ${tab === item.id ? 'active' : ''}`} onClick={() => go(item.id)}><item.icon size={18} />{item.name}</button>)}</nav><div className="side-bottom"><div className="side-footer"><ShieldCheck size={17} /> Researcher review required</div></div></aside>
    <div className="mobile-shade" onClick={() => setMobileOpen(false)} style={{ display: mobileOpen ? 'block' : 'none' }} /><div className="main-area"><header className="topbar"><button className="menu-btn" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><button className="back-button" disabled={tab === 'overview'} onClick={() => window.history.back()} aria-label="Go back"><ArrowLeft size={16} /> Back</button><div className="crumb">TrialMax <ChevronRight size={14} /> {tabs.find(item => item.id === tab)?.name}</div><span className="demo-pill"><FlaskConical size={15} /> {mode === 'synthea' ? 'Synthea patients' : mode === 'fixed' ? 'Patient population' : 'Exploration population'}</span></header>
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
          <AutopilotCard rules={workspace.draft} population={{ ...population, cohort_id: analysis.simulation.cohort.id }} disabled={Boolean(busy) || !validDraft(workspace.draft)} llmConfigured={Boolean(health?.llm_configured)} onApply={actions => { cancel(); actions.forEach(action => dispatch(action)) }} />
          {!validDraft(workspace.draft) && <div className="error-notice">Enter finite numeric thresholds and keep upper bounds at least as large as lower bounds.</div>}
          <div className="scenario-grid connected-grid"><Card className="criteria-card"><div className="card-top"><h3>Parsed rules</h3><Badge kind="gray">{baseline.length}</Badge></div><div className="criteria-list">{workspace.draft.map(rule => <button key={rule.id} className={`criterion-item ${selected?.id === rule.id ? 'selected' : ''}`} onClick={() => setSelectedId(rule.id)}><span className="criterion-number">{rule.id}</span><span><strong>{variables[rule.variable ?? '']?.label ?? readable(rule.category)}</strong><small>{rule.clause ?? rule.text}</small></span><Badge kind={rule.simulatable && option?.available_variables.includes(rule.variable ?? '') ? 'sage' : 'gray'}>{rule.simulatable ? option?.available_variables.includes(rule.variable ?? '') ? 'Modeled' : 'Unavailable' : 'Unmodeled'}</Badge></button>)}</div></Card>{selected && <RuleEditor rule={selected} original={baseline.find(r => r.id === selected.id)!} metadata={variables[selected.variable ?? '']} available={Boolean(option?.available_variables.includes(selected.variable ?? ''))} onEdit={edit} />}</div>
          {workspace.comparison ? <div className="results-stack comparison-stack"><Comparison result={workspace.comparison} /><button className="btn primary" onClick={() => go('review')}>Review proposed changes <FileCheck2 size={16} /></button><Results result={workspace.comparison.proposed} rules={workspace.draft} variables={variables} /></div> : <div className="notice"><CircleHelp size={17} />{changes.length ? `${changes.length} edited rule(s). Compare the draft to update results.` : 'Select a supported numeric rule to explore a threshold change.'}</div>}
        </>}
        {tab === 'rare' && (analysis.trial.nct_id ? <RareReach result={rareReach} loading={busy === 'rare'} onLoad={loadRareReach} /> : <Card><div className="empty-view"><MapPinned size={30} /><h2>RareReach needs an NCT ID</h2><p>Load a public ClinicalTrials.gov trial first. Pasted text has no registry condition or public site history to research.</p><button className="btn primary" onClick={() => go('overview')}>Load a trial <ArrowRight size={16} /></button></div></Card>)}
        {tab === 'review' && <Review workspace={workspace} decide={(id, decision) => dispatch({ type: 'decide', id, decision })} />}
      </>}
    </main><footer className="footer"><div><Leaf size={15} /> TrialMax</div><span>Qualified researcher review required</span></footer></div>
  </div>
}
