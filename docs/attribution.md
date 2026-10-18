# Order-independent exclusion attribution

This feature uses Shapley values to attribute **known patient exclusions in a synthetic cohort**. It does not estimate survival, treatment benefit, adverse events or safety. [Liu et al., Nature 2021 (Trial Pathfinder)](https://www.nature.com/articles/s41586-021-03430-5) used real-world patient data and attributed survival hazard-ratio effects. Our game and data are different: we have synthetic records and no outcome data. We do not reproduce that study's clinical conclusions or hazard-ratio attribution.

## Definition and exact computation

Let `R` be the engine's `modeled_rule_ids`: supported substantive rules with usable data in the chosen cohort, excluding administrative/permission items. For rule `i`, let `F_i` be its known-failure set. Unknowns never count as failures. Define the cooperative coverage game `v(S) = |union(F_i for i in S)|`.

For each patient `p`, let `m_p` count the rules in `R` they are known to fail. The exact Shapley attribution is:

```text
phi_i = sum(1 / m_p for p in F_i)
F[p, i] = known_failure(p, i)
weights[p] = 1 / m_p if m_p > 0 else 0
phi = F.T @ weights
```

Proof sketch: decompose `v` into a sum of patient-level games. A patient contributes one exclusion if any rule that fails them is present. In a uniformly random rule ordering, exactly the first of their `m_p` failing rules receives that marginal unit; each is equally likely to be first, with probability `1/m_p`. Shapley additivity lets us sum these expected patient-level contributions. Therefore every excluded patient contributes exactly one unit split among their failing rules, and the sum of all `phi_i` equals the union's exclusion count. No subset enumeration or permutation sampling is needed in production.

The Shapley arithmetic costs `O(patients × rules)` using NumPy. The additional top-overlap summaries compare rule pairs using packed failure bits, with pairwise cost `O(rules² × ceil(patients/8))` and no patient-by-rule integer matrix. Overlaps cover all modeled rules, independently of the existing top-20 overlap preview. No new dependency or LLM call is used.

## API and display

`SimulationResult` adds `attributions` (default `[]`) and `attribution_total_excluded` (default `0`). Each attribution contains:

- `rule_id`, `shapley_value` (fractional patient-equivalent exclusion credit).
- `total_fail_n`: known failures for this rule alone.
- `unique_n`: known failures shared with no other modeled rule.
- `shapley_share_pct = 100 * shapley_value / attribution_total_excluded`, or zero if there are no exclusions.
- `top_overlaps`: up to three other rules with positive shared known failures, using `rule_id` and `patient_n`; sorted by intersection count descending then ID.

Attributions sort by Shapley value descending, then rule ID. Every modeled rule gets a row, including zero-failure rules. No-modeled results return an empty list. Results displays **Order-independent impact (Shapley)** above the existing raw Rule impact section. The card uses Shapley to identify its largest impact. The sequential funnel stays unchanged and is labeled **Sequential funnel (depends on rule order)**. Before/after attribution compares each side's own exclusion total; its percentage denominator can change, so counts are also shown. Missing attribution for a rule is displayed as not modeled, not zero.

Existing simulation counts, classifications, funnel, raw per-rule impacts, worst-rule ID, population data and parser are unchanged. The new fields travel automatically in both nested comparison simulations and exported comparison JSON. The frontend supports absent new fields from an older response without inventing attribution values.

## Limits and interpretation

- This is fair allocation of observed synthetic exclusions, not a causal claim, clinical importance score or recommendation to relax a requirement.
- A value such as `12.5` means fractional exclusion credit across patients, not half of a real patient. Rounded display shares need not sum to exactly 100%.
- Full credit for a unique failure does not guarantee recovery after a change: the patient may still have unknown requirements, and a threshold edit may not remove every failure.
- Adding/removing a rule changes the game. Identical rule records split their patients' credit equally. Broad proxy variables can make clinically different rules appear identical; attribution does not establish clinical equivalence.
- Missingness, parsing approximations and cohort assumptions affect which failures are observable. Passing the checked subset never establishes full-protocol eligibility. The Synthea cohort is not validated for the selected trial's disease.
- Order independence concerns the same rule set and patient data. It does not mean independence from population choice or criterion definitions.

## Validation

Backend tests compare the closed form with all permutations for 2–6 rules, test efficiency, shuffling, symmetry, disjoint/zero failures, missingness, nonmodeled/admin/permission exclusions, and exact top overlaps beyond the old top-20 preview. An integration test uses the actual example protocol and Synthea cohort and checks every pre-existing result field and status mask is unchanged when attribution is disabled. Frontend tests cover row formatting, overlap names, zero/empty/unmodeled handling and before/after shares.

Run `python -m pytest backend/tests -q`, then `npm test` and `npm run build` in `frontend/`.
