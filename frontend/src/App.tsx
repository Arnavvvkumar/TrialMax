import { useMemo, useState } from 'react'
import {
  Activity, ArrowRight, BarChart3, BookOpen, ChevronRight, CircleHelp, FileCheck2,
  FlaskConical, LayoutDashboard, Leaf, Menu, RotateCcw, Search, ShieldAlert,
  ShieldCheck, SlidersHorizontal, Sparkles, X,
} from 'lucide-react'
import { demoCriteria } from './mockSimulation'
import { analyzeTrial, compareCriteria, getTrial, isBackendEnabled } from './simulationService'
import type { AnalyzeResponse, TrialInfo } from './simulationService'
import type { EligibilityCriterion, SimulationResponse } from './scenarioTypes'

type Tab = 'overview' | 'analysis' | 'scenario' | 'review'
const tabs: { id: Tab; name: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', name: 'Overview', icon: LayoutDashboard },
  { id: 'analysis', name: 'Eligibility analysis', icon: BarChart3 },
  { id: 'scenario', name: 'Scenario Analysis', icon: SlidersHorizontal },
  { id: 'review', name: 'Protocol review', icon: FileCheck2 },
]
const title: Record<Tab, string> = {
  overview: 'Trial overview',
  analysis: 'Eligibility analysis',
  scenario: 'Eligibility Scenario Analysis',
  review: 'Protocol review',
}
const description: Record<Tab, string> = {
  overview: 'Understand your trial before testing eligibility rules.',
  analysis: 'Explore the criteria shaping your simulated patient population.',
  scenario: 'Compare protocol changes against a synthetic baseline.',
  review: 'Review proposed adjustments with safety and evidence in mind.',
}

function Badge({ children, kind = 'sage' }: { children: React.ReactNode; kind?: 'sage' | 'amber' | 'gray' }) {
  return <span className={`badge ${kind}`}>{children}</span>
}
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>
}
function Stat({ label, value, sub, featured = false }: { label: string; value: number | string; sub: string; featured?: boolean }) {
  return <div className={`stat ${featured ? 'featured' : ''}`}><span className="stat-label">{label}</span><strong>{value}</strong><p>{sub}</p></div>
}
function Header({ tab, onMenu }: { tab: Tab; onMenu: () => void }) {
  return <header className="topbar"><button className="menu-btn" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></button><div className="crumb">Workspace <ChevronRight size={14} /> <span>{title[tab]}</span></div><div className="header-right"><span className="demo-pill"><span className="dot" /> Synthetic demo environment</span><div className="avatar">CN</div></div></header>
}
function Considerations({ criterion }: { criterion: EligibilityCriterion }) {
  return <div className="considerations"><div className="warning-box"><ShieldAlert size={18} /><div><strong>Researcher review required</strong><p>{criterion.safetyNote}</p></div></div><div className="consideration-grid">{(['Patient safety', 'Scientific validity', 'Generalizability'] as const).map((item) => <div key={item} className={criterion.considerations.includes(item) ? 'consideration active' : 'consideration'}><span>{criterion.considerations.includes(item) ? '●' : '○'}</span><div><strong>{item}</strong><p>{criterion.considerations.includes(item) ? 'Review impact before adopting this change.' : 'No specific flag for this criterion.'}</p></div></div>)}</div></div>
}
function ComparisonBar({ label, before, after }: { label: string; before: number; after: number }) {
  const max = Math.max(before, after, 1)
  return <div className="comparison-row"><div className="comparison-label"><span>{label}</span><span>{before} → {after}</span></div><div className="comparison-track"><span className="bar-before" style={{ width: `${(before / max) * 100}%` }} /><span className="bar-after" style={{ width: `${(after / max) * 100}%` }} /></div></div>
}
function ScenarioAnalysis({ onReview }: { onReview: () => void }) {
  const baseline = useMemo(() => demoCriteria.map((criterion) => ({ ...criterion })), [])
  const [draft, setDraft] = useState<EligibilityCriterion[]>(() => baseline.map((criterion) => ({ ...criterion })))
  const [selectedId, setSelectedId] = useState('E03')
  const [result, setResult] = useState<SimulationResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selected = draft.find((criterion) => criterion.id === selectedId) ?? draft[0]
  const hasChanges = draft.some((criterion, index) => criterion.value !== baseline[index].value)
  const updateValue = (value: number) => setDraft((current) => current.map((criterion) => criterion.id === selected.id ? { ...criterion, value } : criterion))
  const reset = () => { setDraft(baseline.map((criterion) => ({ ...criterion }))); setResult(null) }
  const simulate = async () => {
    setRunning(true)
    setError(null)
    try {
      setResult(await compareCriteria(baseline, draft))
    } catch (simulationError) {
      setError(simulationError instanceof Error ? simulationError.message : 'The simulation request failed.')
    } finally {
      setRunning(false)
    }
  }
  const displayed = result ?? {
    source: 'synthetic-mock' as const, evaluatedAt: '', baseline: { total: 500, eligible: 28, excluded: 450, unknown: 22 },
    modified: { total: 500, eligible: 28, excluded: 450, unknown: 22 }, eligibilityPercentagePointChange: 0,
    exclusionBreakdown: [], note: 'Run the simulation to update synthetic comparison figures.',
  }
  return <div className="scenario-page">
    <div className="notice large"><CircleHelp size={17} /><span><b>{result?.source === 'backend' ? 'Backend synthetic simulation.' : 'Synthetic demonstration data.'}</b> Results are synthetic and are not clinical evidence.</span></div>
    {error && <div className="error-notice" role="alert"><ShieldAlert size={17} /><span>{error} Check that the backend is running and that <code>VITE_USE_BACKEND=true</code> is configured.</span></div>}
    <div className="scenario-toolbar"><div><h2>Protocol criteria</h2><p>Choose one criterion to inspect or modify.</p></div><div className="toolbar-actions"><button className="btn outline" onClick={reset} disabled={!hasChanges}><RotateCcw size={15} /> Reset original</button><button className="btn primary" onClick={simulate} disabled={running || !hasChanges}>{running ? 'Running…' : 'Run Simulation'} <ArrowRight size={16} /></button></div></div>
    <div className="scenario-grid">
      <Card className="criteria-card"><div className="card-top"><div><h3>Original eligibility criteria</h3><p>Extracted from the demo protocol</p></div><Badge kind="gray">6 criteria</Badge></div><div className="criteria-list">{baseline.map((criterion) => <button className={`criterion-item ${selectedId === criterion.id ? 'selected' : ''}`} onClick={() => setSelectedId(criterion.id)} key={criterion.id}><span className="criterion-number">{criterion.id}</span><span><strong>{criterion.name}</strong><small>{criterion.originalText}</small></span>{criterion.editable ? <Badge>Editable</Badge> : <Badge kind="gray">View only</Badge>}</button>)}</div></Card>
      <Card className="editor-card"><div className="card-top"><div><h3>Selected criterion</h3><p>Original values are preserved for comparison.</p></div><Badge kind={selected.editable ? 'sage' : 'gray'}>{selected.editable ? 'Supported edit' : 'Unsupported edit'}</Badge></div><div className="selected-criterion"><span className="eyebrow">{selected.id}</span><h2>{selected.name}</h2><p>{selected.originalText}</p></div>{selected.editable ? <div className="edit-control"><label htmlFor="threshold">{selected.parameterLabel}</label><div className="range-values"><span>Original: <b>{baseline.find((item) => item.id === selected.id)?.value} {selected.unit}</b></span><span>Proposed: <b>{selected.value} {selected.unit}</b></span></div><input id="threshold" type="range" min={selected.min} max={selected.max} step={selected.step} value={selected.value} onChange={(event) => updateValue(Number(event.target.value))} /><div className="range-limits"><span>{selected.min}</span><span>{selected.max} {selected.unit}</span></div></div> : <div className="unsupported-box"><ShieldCheck size={18} /><span>This criterion is shown for context but is not supported for numerical editing in this demo.</span></div>}<Considerations criterion={selected} /></Card>
      <Card className="results-card"><div className="card-top"><div><h3>Original vs. Modified Criteria</h3><p>Eligibility impact after simulation</p></div><Badge kind="amber">Synthetic only</Badge></div><div className="result-pair"><div><span>Baseline eligible</span><strong>{displayed.baseline.eligible}</strong><small>of {displayed.baseline.total}</small></div><ArrowRight size={18} /><div className="modified-result"><span>Modified eligible</span><strong>{displayed.modified.eligible}</strong><small>of {displayed.modified.total}</small></div></div><div className="mini-distribution"><span className="eligible-segment" style={{ width: `${(displayed.baseline.eligible / 500) * 100}%` }} /><span className="modified-segment" style={{ width: `${(displayed.modified.eligible / 500) * 100}%` }} /></div><div className={`delta ${displayed.eligibilityPercentagePointChange >= 0 ? 'positive' : 'negative'}`}>{displayed.eligibilityPercentagePointChange >= 0 ? '+' : ''}{displayed.eligibilityPercentagePointChange} percentage points <small>eligibility rate change</small></div><div className="result-notice"><CircleHelp size={15} /> {result ? 'Simulation complete using synthetic mock logic.' : 'Run Simulation to compare this proposed protocol change.'}</div></Card>
    </div>
    <div className="section-header space-top"><div><h2>Eligibility Impact</h2><p>Baseline-versus-modified synthetic population comparison.</p></div><Badge kind="gray">Not clinical evidence</Badge></div>
    <div className="stat-grid impact-stats"><Stat label="Total synthetic patients evaluated" value={displayed.modified.total} sub="Fixed demo population" /><Stat label="Eligible before → after" value={`${displayed.baseline.eligible} → ${displayed.modified.eligible}`} sub={`${displayed.baseline.eligible / 5}% → ${displayed.modified.eligible / 5}% eligible`} featured /><Stat label="Excluded before → after" value={`${displayed.baseline.excluded} → ${displayed.modified.excluded}`} sub="Rule-based exclusions" /><Stat label="Unknown eligibility" value={displayed.modified.unknown} sub="Missing data kept separate" /></div>
    <div className="impact-grid"><Card><div className="card-top"><div><h3>Baseline vs. modified eligibility</h3><p>Percentage of the same synthetic population</p></div><div className="chart-legend"><span className="legend-before" /> Baseline <span className="legend-after" /> Modified</div></div><div className="bar-chart"><div className="chart-column"><div className="column-value">{(displayed.baseline.eligible / 5).toFixed(1)}%</div><div className="column before" style={{ height: `${Math.max(8, displayed.baseline.eligible / 500 * 100 * 2.2)}%` }} /><span>Baseline</span></div><div className="chart-column"><div className="column-value">{(displayed.modified.eligible / 5).toFixed(1)}%</div><div className="column after" style={{ height: `${Math.max(8, displayed.modified.eligible / 500 * 100 * 2.2)}%` }} /><span>Modified</span></div></div></Card><Card><div className="card-top"><div><h3>Per-criterion exclusion breakdown</h3><p>Illustrative contribution comparison</p></div></div>{displayed.exclusionBreakdown.length ? displayed.exclusionBreakdown.map((item) => <ComparisonBar key={item.criterionId} label={item.criterionName} before={item.before} after={item.after} />) : <div className="empty-state">Run a simulation to see how criterion exclusions are compared.</div>}</Card></div>
    <Card className="protocol-changes"><div className="card-top"><div><h2>Proposed Protocol Changes</h2><p>Only supported numerical thresholds can be edited in this prototype.</p></div><Badge kind={hasChanges ? 'amber' : 'gray'}>{hasChanges ? 'Draft change' : 'No changes'}</Badge></div><div className="change-table"><div className="change-row table-head"><span>Criterion</span><span>Original</span><span>Proposed</span><span>Review</span></div>{draft.filter((criterion) => criterion.editable).map((criterion) => <div className="change-row" key={criterion.id}><span><b>{criterion.name}</b><small>{criterion.id}</small></span><span>{baseline.find((item) => item.id === criterion.id)?.value} {criterion.unit}</span><span className={criterion.value !== baseline.find((item) => item.id === criterion.id)?.value ? 'changed' : ''}>{criterion.value} {criterion.unit}</span><span><Badge kind={criterion.value !== baseline.find((item) => item.id === criterion.id)?.value ? 'amber' : 'gray'}>{criterion.value !== baseline.find((item) => item.id === criterion.id)?.value ? 'Review needed' : 'Unchanged'}</Badge></span></div>)}</div><div className="footer-note"><ShieldAlert size={16} /> Proposed changes require qualified researcher review. No change is represented as medically safe or as improving trial outcomes.</div><button className="btn outline" onClick={onReview}>Open protocol review <ArrowRight size={16} /></button></Card>
  </div>
}
function App() {
  const [tab, setTab] = useState<Tab>('overview')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [nctId, setNctId] = useState('NCT-DEMO-001')
  const [loadedId, setLoadedId] = useState('NCT-DEMO-001')
  const [trial, setTrial] = useState<TrialInfo | null>(null)
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [apiBusy, setApiBusy] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const go = (next: Tab) => { setTab(next); setMobileOpen(false) }
  const loadTrial = async () => { setApiBusy(true); setApiError(null); try { const id = nctId.trim() || 'NCT-DEMO-001'; setTrial(await getTrial(id)); setLoadedId(id) } catch (error) { setApiError(error instanceof Error ? error.message : 'Unable to load trial.') } finally { setApiBusy(false) } }
  const runAnalysis = async () => { setApiBusy(true); setApiError(null); try { setAnalysis(await analyzeTrial({ nctId: loadedId })) } catch (error) { setApiError(error instanceof Error ? error.message : 'Unable to analyze trial.') } finally { setApiBusy(false) } }
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? 'shown' : ''}`}><div className="logo-wrap"><div className="logo-mark"><Leaf size={22} /></div><div><div className="logo-text">CliNova<span className="logo-period">.</span></div><div className="logo-sub">Clinical trial intelligence</div></div><button className="close-mobile" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={19} /></button></div><div className="workspace-label">WORKSPACE</div><nav className="nav">{tabs.map(({ id, name, icon: Icon }) => <button key={id} className={`nav-item ${tab === id ? 'active' : ''}`} onClick={() => go(id)}><Icon size={18} />{name}{tab === id && <span className="nav-indicator" />}</button>)}</nav><div className="side-bottom"><div className="help-box"><BookOpen size={19} /><strong>New to CliNova?</strong><p>Explore eligibility simulations with our guided demo.</p><button onClick={() => go('scenario')}>Open Scenario Analysis <ArrowRight size={15} /></button></div><div className="side-footer"><ShieldCheck size={17} /> Synthetic data only</div></div></aside><div className="mobile-shade" onClick={() => setMobileOpen(false)} style={{ display: mobileOpen ? 'block' : 'none' }} /><div className="main-area"><Header tab={tab} onMenu={() => setMobileOpen(true)} /><main className="content"><div className="eyebrow">CLINICAL TRIAL DESIGN / WORKSPACE</div><div className="page-heading"><div><h1>{title[tab]}</h1><p>{description[tab]}</p></div><Badge kind="gray"><FlaskConical size={13} /> {isBackendEnabled() ? 'Backend synthetic mode' : 'Illustrative prototype'}</Badge></div>{apiError && <div className="error-notice" role="alert"><ShieldAlert size={17} />{apiError}</div>}{tab === 'scenario' ? <ScenarioAnalysis onReview={() => go('review')} /> : <PlaceholderView tab={tab} nctId={nctId} setNctId={setNctId} loadedId={loadedId} trial={trial} analysis={analysis} apiBusy={apiBusy} onLoadTrial={loadTrial} onAnalyze={runAnalysis} onScenario={() => go('scenario')} />}</main><footer className="footer"><div><Leaf size={15} /> CliNova — Explore the possibilities thoughtfully.</div><span>Synthetic / illustrative data · Not clinical decision support</span></footer></div></div>
}
function PlaceholderView({ tab, nctId, setNctId, loadedId, trial, analysis, apiBusy, onLoadTrial, onAnalyze, onScenario }: { tab: Tab; nctId: string; setNctId: (value: string) => void; loadedId: string; trial: TrialInfo | null; analysis: AnalyzeResponse | null; apiBusy: boolean; onLoadTrial: () => void; onAnalyze: () => void; onScenario: () => void }) {
  if (tab === 'overview') return <><div className="hero"><div className="hero-copy"><div className="hero-chip"><Sparkles size={14} /> A clearer way to design trials</div><h2>Better insights.<br /><em>More thoughtful trials.</em></h2><p>Understand how eligibility rules affect a synthetic population—and examine trade-offs before a protocol is finalized.</p><button className="btn dark" onClick={onScenario}>Explore Scenario Analysis <ArrowRight size={17} /></button></div><div className="hero-art" aria-hidden="true"><div className="ring r1" /><div className="ring r2" /><div className="ring r3" /><div className="orb"><Activity size={58} /></div></div></div><div className="section-header"><div><h3>Start with a clinical trial</h3><p>Enter an NCT identifier or explore the included demo study.</p></div></div><Card className="trial-card"><div className="trial-form"><div className="field-wrap"><label htmlFor="nct">ClinicalTrials.gov identifier</label><div className="input-holder"><Search size={18} /><input id="nct" value={nctId} onChange={(event) => setNctId(event.target.value)} /></div></div><button className="btn primary" onClick={onLoadTrial} disabled={apiBusy}>{apiBusy ? 'Loading…' : 'Load trial'} <ArrowRight size={17} /></button></div><div className="notice"><CircleHelp size={16} /> {trial ? `Loaded ${trial.nct_id ?? loadedId} from ${isBackendEnabled() ? 'the backend' : 'local mock data'}.` : 'Enter an NCT identifier to load trial metadata from the backend.'}</div></Card></>
  return <Card><div className="empty-view"><BarChart3 size={28} /><h2>{title[tab]}</h2><p>{trial?.title ?? 'Load a trial, then run the backend eligibility analysis to inspect modeled criteria.'}</p>{tab === 'analysis' && <><button className="btn primary" onClick={onAnalyze} disabled={apiBusy}>{apiBusy ? 'Analyzing…' : 'Run eligibility analysis'} <ArrowRight size={16} /></button>{analysis && <div className="analysis-result"><strong>{analysis.simulation.eligible_n ?? '—'} eligible</strong><span>of {analysis.simulation.population_n} synthetic patients · {analysis.rules.length} parsed rules</span></div>}</>}<button className="btn outline" onClick={onScenario}>Open Scenario Analysis <ArrowRight size={16} /></button><p className="trial-reference">Loaded study: {loadedId}</p></div></Card>
}
export default App
