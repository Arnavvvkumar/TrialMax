# Responder evidence

This is a separate, historical **efficacy-method benchmark**, not evidence about
the trial currently loaded in TrialMax and not an extension of the Synthea
eligibility simulation. It never edits a rule or recommends a protocol change.
A researcher decides. Treatment safety is outside its scope.

## Frozen reference data

`dataset/rct/ground_truth.jsonl` contains three original cases and nine planted
variants. Part 2 reads this snapshot without rebuilding it. Its SHA-256 is
`bdd5d804a00309b6475dba46607b8350be0c3912ef29909af2858ccfb73eef26`.
The CSVs and provenance files make the evidence table available offline. CSV
SHA-256 is checked before serving evidence; evaluation summaries are checked
against the ground-truth hash, model, agent prompt, evidence policy, and scorer version.

Credit: the **R survival package**, distributed through the public Rdatasets
mirror. Individual source URLs, download times, hashes and citations are in
`*.provenance.json`. Colon uses death (`etype=2`) records once per patient and
only Lev+5FU versus observation (619 patients). Veteran compares test versus
standard (137). GBSG compares hormonal versus no hormonal therapy (686).
**GBSG treatment assignment is partly non-randomized: weaker evidence.**
The R documentation also identifies a colon `nodes`/`node4` inconsistency; the
snapshot uses the supplied `node4` flag.

Original/reference publications:

- Colon: Moertel et al., NEJM 1990;322:352–358,
  [doi:10.1056/NEJM199002083220602](https://pubmed.ncbi.nlm.nih.gov/2300087/).
- Veteran: Kalbfleisch and Prentice (1980), *The Statistical Analysis of Failure
  Time Data*, cited by the [R survival documentation](https://vincentarelbundock.github.io/Rdatasets/doc/survival/veteran.html).
- GBSG: Schumacher et al., JCO 1994;12:2086–2093,
  [doi:10.1200/JCO.1994.12.10.2086](https://pubmed.ncbi.nlm.nih.gov/7931478/).

## Statistical reference labels (computed in Part 1)

Prespecified subgroup definitions live in `responder_truth.py`. Unpenalized Cox
models estimate treatment HR and 95% CI within a subgroup and its complement,
plus an overall treatment HR. A treatment + subgroup + treatment×subgroup model
tests interaction. Missing subgroup values are excluded from both sides; missing
outcomes are never silently imputed. Failed/unstable fits are unestimable.

Benjamini–Hochberg adjusts all prespecified interaction tests within each
trial/variant at q≤0.10. Unestimable tests count as p=1 in that family and retain
null output. A significant interaction with HR-in > HR-out is labeled
`weaker_benefit`; the reverse is `stronger_benefit`; otherwise the label is
`no_reliable_difference`. This is a deterministic statistical reference, not
biological truth. A group is marked underpowered when any of its four
subgroup/complement arm event counts is below 20. The frozen statistical
reference retains its original label. The API/UI and evaluation policy derive
a separate decision label: **underpowered means no reliable difference, even if
BH-significant**. The raw direction is retained as `statistical_direction`;
q-values and `bh_significant` remain visible. This conservative label does not
prove equal effects. The snapshot is not rewritten.

Planted variants bootstrap paired time/event observations from controls into
treated patients of one prespecified subgroup, with fixed seeds. Three balanced
subgroups were selected per trial by size, without searching for significant
p-values. Labels are still calculated from the resulting statistics: a plant
never forces a positive label. **All nine planted targets in this frozen
snapshot are not detectable after adjustment.** Consequently these evaluations
cannot establish positive-case sensitivity or demonstrate that supplying
statistics improves the agent. The ground truth has not been regenerated to
improve the benchmark.

No significant interaction does not establish equal treatment effects. HRs
assume proportional hazards; small samples, old regimens, correlated subgroups,
missingness, partly observational treatment assignment and repeated exploration
limit inference. HR-in > HR-out can also mean more harm, rather than benefit in
either group. There is no automated exclusion decision.

## Agent and privacy boundary

The configured Chalk Model Gateway is the only model route. The agent uses the
existing OpenAI SDK client and `llm.call_model` with a 15-second maximum call
timeout and `max_retries=0`. It has no tools. Trial names and table contents are
untrusted data, never instructions.

`names_only` receives subgroup ID, label and n only. `with_stats` also receives
arm counts/events, HRs/CIs, interaction p/q, `bh_significant` and underpower flags.
Both prompts state Benjamini–Hochberg significance at q≤0.10 and the underpower
policy. Names-only receives no subgroup effect statistics. A whitelist
excludes reference labels, expected flags/directions, planted/original status,
detectability and patient-level rows from both prompts. The response is strict
Pydantic JSON with no extra keys, one known subgroup or null, a paired direction,
confidence and a rationale of at most 400 characters. Numeric claims must occur
in the input within absolute 0.01 or 1% relative tolerance. Rationales must
mention multiplicity and researcher review. `responder_claims.py` rejects flags
on underpowered/non-significant groups and directions inconsistent with the HRs.
It detects specific blanket denials of BH significance and named direction
contradictions. **Free prose is never silently assumed verified:** displayed
rationales must match an approved context-specific template. The model must copy
the applicable supplied rationale option verbatim. Invalid schema, numbers or
claims produce a low-confidence null with a plain verified template;
`used_template`, reasons and the raw response are retained. Provider failure or
absent configuration still returns an unavailable/invalid null. Verified
responses and fallbacks are cached by policy version, model, prompt and input,
and rechecked when read.

The numeric check verifies copying, not clinical interpretation or whether a
number was associated with the correct subgroup. The claim gate covers aggregate
policy and approved wording, not arbitrary medical facts or clinical validity.
Human review remains necessary.
Public trial-level aggregate tables go to the model; individual outcome rows do
not. Reference labels go to evaluation scorers separately, never the task's
model prompt.

## Evaluation and actual execution mode

There are four evaluations: names-only/with-statistics × originals/planted,
with 3 originals or 9 variants in each group. The expected exclusion flag is the
BH-significant, non-underpowered weaker-benefit subgroup with the smallest q (ID breaks ties), or
null. A detectable planted target takes precedence. Significant stronger-benefit
groups do not become exclusion candidates.

Metrics use the same pure functions locally and in Chalk:

- `correct_flag`: exact expected flag, including null.
- `no_overclaim`: penalizes a high-confidence subgroup flag unsupported by the
  subgroup's conservative reference label or direction. A high-confidence null
  is abstention, not an efficacy claim. Incorrect statements in its rationale
  are checked separately by claim consistency.
- `abstains_when_null`: null flag when no subgroup interaction is significant;
  other cases return an empty scorer list and do not enter the denominator.
- `planted_recall`: flags the planted subgroup with weaker-benefit direction,
  only when the plant is detectable and its decision label permits that flag.
  Originals, undetectable plants and underpowered targets return an empty list.
  This snapshot therefore reports N/A with denominator zero, not 0% recall.
- `number_fidelity`: every rationale number appears in the input table within
  the tolerance above. A number-free rationale passes this check.
- `claim_consistency`: displayed flag/direction and rationale meet the aggregate
  policy and approved wording, with rejection reasons in metadata. This is not
  a general natural-language truth test.
- `raw_claim_consistency`: the same check on new AI output before the guard.
  `legacy_claim_consistency` checks archived prior responses and original inputs
  retrospectively. **Unverified free prose is not a demonstrated false claim.**
  Old responses were not prompted to use the new template contract: their zero
  template-verification score is not a fair measure of factual accuracy. The
  separate audit counts concrete contradictions.
- Chalk's built-in `json_valid`: checks the raw model output, including malformed
  outputs rejected by the agent. This is syntactic validity, not schema validity.

The hosted environment is `hmlsd28bca6e`. The successful tiny probe is recorded
in `chalk_probe.json`. It reached the model router but received HTTP 401, with
no ambient remote model credential. **The mode used is local aggregate-only
inference through the sponsor's Chalk gateway, followed by hosted Chalk
passthrough tasks and scorers.** The gateway uses the separately configured
`CHALK_ENV_ID` (`clkdcdaf84e`); it must not be overwritten with the evaluation
environment. The router key is never uploaded to hosted functions. If a future
probe succeeds with an already available remote credential, the runner selects
the packaged aggregate-only remote agent task instead.

`chalk_runs.json` stores actual hosted evaluation/run IDs and scores read from
the result datasets. Task/scorer errors prevent a completed-validation claim.
In passthrough mode the runner checks hosted scores and denominators against
the local scorers. `local_eval_results.json` retains raw responses and local
scores as an audit/fallback, clearly labeled local-only. Neither file contains
credentials. The UI displays completion status, denominators and run IDs;
completed runs do not establish clinical validity. No numbers are fabricated
when evaluation/authentication fails.

Completed run IDs are in `chalk_runs.json`. Prior results/raw responses are
archived in `chalk_runs.before_claims.json` and
`local_eval_results.before_claims.json`. `claim_consistency_before_after.json`
records the audit: the old Veteran explanation denied adjusted significance
although squamous has q≈0.0728. The new local run has one previous contradiction
versus zero in 24 new raw and displayed responses. No template fallback was
needed in this run; the regression test separately proves the guard catches the
exact old explanation and falls back correctly. Hosted scores include prior,
raw-new and displayed claim checks.

The cautious policy makes every expected exclusion flag in this snapshot null.
100% flag accuracy therefore does not show positive-case detection: always
abstaining also achieves it. Flag accuracy before and after the policy change
is not directly comparable. Planted recall remains 0% (originals N/A).
High-confidence abstentions can still fail the unchanged no-overclaim scorer.
The groups have tiny denominators and are not independent replications:
variants reuse trials, and identical names-only inputs reuse a response.

## Rerun Part 2

Install `backend/requirements.txt` and `chalkcompute==2.13.7` in the environment
where `chalk login` is authenticated. Keep the sponsor model configuration in
the ignored local `.env`. In the repo root, with the WSL virtualenv activated:

```bash
export CHALK_ENVIRONMENT=hmlsd28bca6e
python dataset/rct/chalk_probe.py
python dataset/rct/chalk_eval.py
```

These deploy authenticated top-level `@chalkcompute.function` tasks/scorers,
upload with `DatasetClient`, create the four evaluations and call
`evaluation.run(...).wait()`. They follow the
[Chalk evaluation quick start](https://docs.chalk.ai/docs/evaluations/quick-start).
The small custom httpx transport is used for object-storage transfers because
the default SDK transport timed out in this WSL environment. Signed transfer
URLs and provider exception bodies are never logged.

For local results without hosted auth or SDK deployment:

```bash
python dataset/rct/eval_common.py
```

Do not import `chalk_eval.py` or `chalk_probe.py` from tests: SDK decorators
deploy functions at import time. Their actual run orchestration is protected by
the `__main__` guard. Unit tests import only the pure scorer/agent modules and
mock network calls. Part 2 must not run `fetch_rct.py` or the ground-truth
builder to change the fixed benchmark.

## API and UI

`POST /api/responder-evidence` accepts `trial_key` colon/veteran/gbsg and optional
`variant: "original"`, using the existing heavy-request protection. Results
include precomputed subgroup evidence, a cached validated agent response,
evaluation summaries and limitations. The Results-tab card is explicitly
separate from the loaded trial, plots subgroup/complement HR confidence
intervals on a log scale, shows underpower and reference labels, and provides
no apply/accept protocol-change action. Existing eligibility, PCA, Shapley and
population data are unchanged.


### Rescoring saved outputs after metric fixes

Run `CHALK_ENVIRONMENT=hmlsd28bca6e python dataset/rct/chalk_eval.py --reuse-outputs`
from the repository root. This checks the frozen snapshot, model, prompt and evidence
policy against the saved inputs, then reruns all four hosted evaluations on the same
saved agent responses. No new model calls occur. The scorer version is recorded
separately; earlier run IDs remain historical results under their earlier definitions.
Use `--local-only --reuse-outputs` for explicitly local scoring. Template coverage is
reported separately from detected contradiction counts: failure to copy a template
does not establish that an archived explanation is false.
