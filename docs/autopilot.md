# What-if Autopilot

Autopilot explores a prespecified threshold table on the **current draft**, on the same selected synthetic cohort. The existing deterministic evaluator remains the source of every patient count, gain, comparison and unknown result. “Safe” in the button text means passing the critical-rule exclusion screen; it is **not** a clinical safety determination. Qualified researchers and clinicians must review every suggestion.

## Prespecified table (version: initial hackathon policy)

These are illustrative candidate steps supplied for the feature, not clinical recommendations or validated protocol amendments. Only a matching starting threshold is eligible; arbitrary intermediate thresholds are not rounded into this table.

| Variable / constraint | Allowed new thresholds |
| --- | --- |
| ECOG upper limit 1 | 2 |
| ANC lower limit 1.5 × 10^9/L | 1.0 × 10^9/L |
| Platelet lower limit 100 × 10^9/L | 75 × 10^9/L |
| Hemoglobin lower limit 10 g/dL | 9 or 8 g/dL |
| Hemoglobin lower limit 9 g/dL | 8 g/dL |
| eGFR or creatinine clearance lower limit 60 | 45 or 30, in the original variable's units |
| eGFR or creatinine clearance lower limit 45 | 30, in the original variable's units |
| Bilirubin upper limit 1.5 × ULN | 2.0 × ULN |
| AST or ALT upper limit 2.5 × ULN | 3.0 × ULN |
| Age upper limit | Original upper limit +5 or +10 years |

Lower-limit steps apply to inclusion `>=` or equivalent numeric exclusions `<` / `<=`; upper-limit steps apply to inclusion `<=` or equivalent exclusions `>` / `>=`. Age also supports changing `value_max` of an inclusion range. No lower age limit is changed, including 18. Boolean operators, equality and other compound ranges have no candidate steps.

Units, variable, kind, operator, IDs, source text, notes and all other rule metadata are preserved. For bilirubin/AST/ALT, exact canonical-unit equivalents are supported using the existing assumed ULN constants (for example bilirubin 1.8 mg/dL → 2.4 mg/dL). A 1.5 mg/dL threshold is not confused with 1.5 × ULN. Indexed eGFR and absolute creatinine clearance remain different variables; no conversion between them occurs. Every candidate passes `validate_rule_semantics`, Pydantic validation and `classify_change == relaxed`.

## Safety boundary

- `_critical(rule)` is authoritative: a rule flag **or** the variable registry can hard-block an edit. Pregnancy, myocarditis, active infection, hepatic impairment, ILD and drug hypersensitivity therefore cannot be relaxed even if the client clears the flag.
- No rule is removed, disabled, added or relabeled. Every simulator call receives the complete original rule set with only listed numeric thresholds replaced.
- Safety-purpose rules can use only the table steps. Safety-purpose metadata defaults and comparison safety-review flags produce **clinical review required** badges.
- Every `compare_population` result is checked again; any critical change or critical relaxation is rejected. Manual draft changes made before starting Autopilot are not retrospectively certified.
- Missing values remain unknown. A rule absent from the population cannot supply recovery gains. Diagnosis/stage and other unmodeled requirements still prevent claims of full-protocol eligibility.

## Exploratory hidden filters

`engine.rule_masks()` shares preparation with `evaluate()`; it returns known-failure and unknown masks without changing evaluation semantics. `F[patient, rule]` is one only for a **known failure**, otherwise zero. PCA uses only modeled, substantive rules with varying failures. Always-pass, always-fail and unavailable rules are dropped from PCA, not from the protocol or simulator.

Columns are centered in blocks. NumPy SVD is applied to the centered covariance matrix: its singular values are component variances and its axes equal the principal axes from SVD of centered F. This avoids allocating a large patient-by-component U matrix for API populations up to 200,000. Loadings are unit principal-axis coefficients, not causal effects or clinical importance scores. Axes have a deterministic sign convention; exact degeneracies can rotate across numerical-library versions.

Keep enough components for 85% of variance, at most five. The response reports retained variance and whether that target was reached. Labels use the strongest absolute loadings from the known variable registry, not an LLM. Jaccard ≥0.5 identifies overlapping failure sets and returns exact intersection counts. Orthogonality does not prove clinical independence; missingness can influence this binary representation. Display: **“Exploratory summary of binary pass/fail data; not a statistical test.”**

## Search and limits

1. Resolve and pin cohort ID/version, evaluate the baseline, and calculate PCA on that cohort.
2. Simulate the furthest listed step for every eligible rule together. `max_achievable_gain` is that all-rule **table maximum**, not a population-wide maximum or a promise achievable under the selected edit limit.
3. Score individual candidates with full `compare_population` calls, keeping zero-gain steps available for combinations. To reserve combination budget, at most 36 single candidates are initially scored, in deterministic rule-ID/table order. Unscored alternatives are disclosed.
4. Add coordinated moves for same-variable bounds in the same relaxation direction that share an allowed table destination, and all allowed step combinations of PCA redundancy pairs (Jaccard ≥0.5). Same-variable grouping does not depend on PCA, so three identical always-failing bounds can still move together. Normalize x ULN only for matching table destinations; thresholds and units in the actual edits remain unchanged. A critical rule never joins a move.
5. Search breadth by **number of actual edited rules**, beam width five, with at most one step per rule. A coordinated three-rule move costs three edits. Default limit is three edited rules (API range one–five), target 80% of the table maximum (API range 50–100%). Each new combination and every returned prefix is simulated; gains are never added as independent shortcuts. The first edit in a coordinated plan can truthfully show zero marginal recovery.
6. Stop at the first explored edit count with target-reaching plans. Among those plans, prefer the **smallest sum of relative threshold movements**, `sum(abs(to-from) / max(1, abs(from)))`, then diverse dominant retained PCA components, then greater gain and deterministic candidate order. Thus eGFR 60→45 wins over 60→30 whenever both reach the target with the same edit count. This numerical movement measure is not a clinical risk score. Below the target, use greater gain, fewer edits, smaller movement, then diversity to select the search beam and fallback plan.

The hard cap is **150 actual simulator evaluations**, including the initial baseline and both evaluations inside every comparison. Thus at most 74 comparisons run (149 evaluations). Duplicate combinations use cached aggregate scores; full comparison/patient records are not retained in the search cache. Every reported marginal and cumulative gain comes from a scored prefix of the returned ordered plan. The tests independently recompute those prefixes.

This is a heuristic **smallest found** plan, not a global minimum proof. A narrow beam, the candidate budget, the edit limit, and the five-component PCA cap all limit completeness. Coordinated bounds and redundant pairs address joint-only recoveries, but arbitrary higher-order interactions are not exhaustively enumerated. A duplicate group larger than `max_edits` cannot be treated as a single edit. An empty plan explains the edit/simulation limits or lack of allowed recovery rather than inventing a gain. No clinical benefit, recruitment forecast or safety assurance is inferred.

## Optional Chalk narration

Disabled by default. When requested and configured, one no-retry request uses the existing Chalk SDK client/model/output limit with timeout bounded by the configured timeout and 15 seconds. The JSON payload contains only aggregate computed plan data—no trial text or patient-level data. All input, including user-supplied rule IDs, is untrusted data; the model has no tools.

The strict Pydantic response is `{summary, rationales}` with 600/300-character limits, no extra fields, and unknown rationale IDs discarded. Quantitative values are always rendered from the simulator fields. The LLM is deliberately restricted to **qualitative prose**: digits, number words and unsupported safety assurances are rejected, even when a number happened to appear elsewhere in the input. This avoids accepting a real threshold as a fabricated recovery count. Flagged edits require explicit clinical-review language. Invalid output, missing configuration, provider failure or timeout uses the deterministic template; narration can never alter a plan or its numbers.

## API and frontend

`POST /api/autopilot` takes `{rules, population, max_edits, target_fraction, use_llm}` under the existing heavy-request/auth/body-size guards. Duplicate IDs, invalid rules, stale cohort choices and invalid search limits return 422. The response includes filters, edits, blocked rules, rejected alternatives, simulation budget, assumptions and warnings. An edit's JSON `from` and `to` are numeric and `field` identifies `value` or `value_max`.

The Scenario analysis card searches the current draft, not a hidden alternative baseline. Input or cohort changes invalidate/cancel outstanding results. **Apply as draft** validates the cohort and starting thresholds atomically, then dispatches existing `edit` actions only. It preserves the baseline, clears stale comparison/review decisions, and never compares or accepts automatically. The researcher must click **Compare draft** (which compares against the original protocol), then use the existing review/export flow. The population dropdown and Synthea defaults are unchanged; `App.tsx` only imports the card and inserts it.

## Validation

Run `python -m pytest backend/tests -q`, then `npm test` and `npm run build` in `frontend/`. New tests cover planted PCA structure, constants/unknowns, units and table membership, critical-rule guards on every comparison, independent gain reproduction, reproducibility, exact budget limits, API validation, narration rejection/fallback, and pure draft-action conversion. Existing Synthea wiring tripwires remain required. Tests mock model calls and do not use the network.
