export interface ResponderEffect { hr: number | null; ci_low: number | null; ci_high: number | null; p: number | null; status: 'ok' | 'unestimable' }
export interface ResponderArmCounts { control_n: number; treatment_n: number; control_events: number; treatment_events: number }
export interface ResponderSubgroup {
  id: string; label: string; n: number; missing_n: number; subgroup: ResponderArmCounts; complement: ResponderArmCounts
  hr_subgroup: ResponderEffect; hr_complement: ResponderEffect; interaction: ResponderEffect; interaction_q: number | null
  bh_significant: boolean; underpowered: boolean; truth_label: 'weaker_benefit' | 'stronger_benefit' | 'no_reliable_difference'
  statistical_direction?: 'weaker_benefit' | 'stronger_benefit' | 'no_reliable_difference' | null
}
export interface ResponderRun { prompt_variant: string; variant: string; n: number; scores: Record<string, number | null>; denominators: Record<string, number>; detectable_planted_n: number; evaluation_id?: string; run_id?: string; status?: string }
export interface ResponderResponse {
  evidence: { case_id: string; trial_key: string; trial_name: string; treatment: string; control: string; endpoint: string; variant: string; n: number; events: number; overall: ResponderEffect; subgroups: ResponderSubgroup[]; provenance: { citation?: string; publication_url?: string; sha256?: string }; disclaimers: string[] }
  suggestion: { flag: string | null; direction: 'weaker_benefit' | 'stronger_benefit' | null; confidence: string; rationale: string; invalid: boolean; source: string; used_template?: boolean }
  evaluations: { status: string; mode?: string; runs: ResponderRun[]; message?: string; hosted_status?: string; limitations?: string[]; claim_audit?: {before:{n:number;contradiction_n:number;unverified_n:number}; raw_after:{n:number;contradiction_n:number;unverified_n:number}; guarded_after:{n:number;contradiction_n:number;unverified_n:number};template_fallback_n:number} }
  disclaimers: string[]
}
