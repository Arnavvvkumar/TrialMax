export type PopulationMode = 'synthea' | 'fixed' | 'generated'
export interface PopulationChoice { mode: PopulationMode; size: number; seed: number; version?: string; cohort_id?: string }
export interface CohortInfo { id: string; mode: PopulationMode; version: string; label: string; population_n: number; seed: number | null; available_variables: string[] }
export interface PopulationOption { mode: PopulationMode; version: string; label: string; size: number; seed: number | null; cohort_id: string | null; available_variables: string[]; visible?: boolean }
export interface PopulationCatalog { default_mode: PopulationMode; options: PopulationOption[] }
export interface ApiHealth { status: string; llm_configured: boolean; model: string | null; llm_status: 'not_configured' | 'configured_not_verified'; llm_missing_configuration: string[] }
export interface ChalkCheck { status: string; message: string; model: string | null; http_status: number | null; checked_at: string; elapsed_ms: number }
export type RuleOperator = '>=' | '<=' | '>' | '<' | '==' | 'between' | 'present' | 'absent'
export interface Rule {
  id: string; kind: 'inclusion' | 'exclusion'; text: string; clause: string | null
  category: string; variable: string | null; operator: RuleOperator | null
  value: number | null; value_max: number | null; unit: string | null; simulatable: boolean
  fidelity: 'exact' | 'approximate'; purpose: string; findability: string; safety_critical: boolean
  parsed_by: 'rules' | 'llm' | 'none'; source: 'text' | 'registry'; notes: string[]
}
export interface VariableMeta { label: string; type: 'numeric' | 'int' | 'bool'; unit: string | null; purpose: string; findability: string; safety_critical: boolean; rationale: string }
export interface TrialInfo {
  nct_id: string | null; title: string | null; phases: string[]; conditions: string[]
  sponsor: string | null; status: string | null; enrollment: number | null
  minimum_age: string | null; maximum_age: string | null; sex: string | null; eligibility_text: string
}
export interface RuleImpact { rule_id: string; simulated: boolean; fail_n: number; fail_pct: number; unique_fail_n: number; unique_fail_pct: number; pass_n: number; unknown_n: number }
export interface FunnelStep { rule_id: string | null; label: string; remaining_n: number; remaining_pct: number; unknown_n: number }
export interface PatientResult { patient_id: string; overall_status: 'pass' | 'fail' | 'unknown'; modeled_status: 'pass' | 'fail' | 'unknown'; criteria: { rule_id: string; status: 'pass' | 'fail' | 'unknown'; value: number | boolean | null }[] }
export interface SimulationResult {
  cohort: CohortInfo; population_n: number; seed: number; estimate_label: string
  eligible_n: number | null; eligible_pct: number | null; excluded_n: number; unknown_n: number
  modeled_eligible_n: number | null; modeled_eligible_pct: number | null; modeled_unknown_n: number; complete: boolean; coverage_pct: number | null
  modeled_rule_ids: string[]; approximate_rule_ids: string[]; unmodeled_rule_ids: string[]
  not_applicable_rule_ids: string[]; not_simulated_rule_ids: string[]; impacts: RuleImpact[]
  funnel_basis: 'modeled_checks'; funnel: FunnelStep[]; worst_rule_id: string | null; assumptions: string[]; warnings: string[]
  patient_results: PatientResult[]; patient_results_complete: boolean
  rule_overlaps: { rule_a_id: string; rule_b_id: string; patient_n: number }[]; overlaps_truncated: boolean
}
export interface AnalyzeResponse { trial: TrialInfo; rules: Rule[]; simulation: SimulationResult; llm_used: boolean; warnings: string[] }
export interface RuleChange { rule_id: string; change: 'added' | 'removed' | 'disabled' | 'enabled' | 'tightened' | 'relaxed' | 'mixed' | 'ambiguous'; safety_critical: boolean }
export interface CompareResult {
  cohort: CohortInfo; baseline: SimulationResult; proposed: SimulationResult
  eligible_change_n: number | null; eligible_change_pct_points: number | null
  newly_eligible_n: number | null; newly_excluded_n: number | null; modeled_eligible_change_n: number | null
  modeled_eligible_change_pct_points: number | null; modeled_newly_eligible_n: number | null; modeled_newly_excluded_n: number | null; modeled_transitions: Record<string, number>
  changes: RuleChange[]; changed_rule_ids: string[]; relaxed_safety_critical_rule_ids: string[]
  review_safety_critical_rule_ids: string[]; safety_review_rule_ids: string[]; transitions: Record<string, number>; warnings: string[]
}
export interface ReviewDecision { decision: 'accepted' | 'rejected'; reason: string; at: string }
