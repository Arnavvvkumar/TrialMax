# Responder-truth ground truth (randomized trials)

Deterministic ground truth for the efficacy-subgroup evaluation. Every number in
`ground_truth.jsonl` is computed by `backend/app/responder_truth.py` from the CSVs in `data/`.
No LLM is involved.

## Data and credit

| Trial | File | Arms | Endpoint |
|---|---|---|---|
| colon | `data/colon.csv` | Lev+5FU (treated) vs observation; Lev-alone arm dropped | overall survival (`etype == 2` rows only, one per patient) |
| veteran | `data/veteran.csv` | test (`trt == 2`) vs standard (`trt == 1`) chemotherapy | overall survival |
| gbsg | `data/gbsg.csv` | hormonal therapy (`hormon == 1`) vs none | recurrence-free survival (`rfstime`) |

The CSVs are the Rdatasets mirror (Arel-Bundock) of datasets in R's **survival** package
(Therneau T, *A Package for Survival Analysis in R*). `data/provenance.json` records each URL,
download time, sha256, row count, columns and citation. Original trials:

- **colon**: Moertel CG et al. Levamisole and fluorouracil for adjuvant therapy of resected colon carcinoma. *N Engl J Med* 1990;322:352-358; Moertel CG et al. *Ann Intern Med* 1995;122:321-326.
- **veteran**: Veterans' Administration Lung Cancer Trial, in Kalbfleisch JD, Prentice RL. *The Statistical Analysis of Failure Time Data*. Wiley, 1980.
- **gbsg**: Schumacher M et al. (German Breast Cancer Study Group). *J Clin Oncol* 1994;12:2086-2093.

## Method (`responder-truth-v1`)

For each trial and each prespecified subgroup S (see `load_*` in the module):

1. **Overall**: Cox model of `treated` on the whole trial (HR, 95% Wald CI, Wald p).
2. **Within S / not S**: Cox model of `treated` in each half (HR, 95% CI).
3. **Interaction**: Cox model with `treated`, `S`, `treated*S`; the interaction HR, CI and p.
   Cox fits use lifelines (Efron ties, the same default as R's `coxph`).
4. **Counts**: n and events per arm in S and not S. `underpowered` if either arm in S has < 20 events.
5. **Not estimable**: an empty arm, an arm with no events, non-convergence, or a degenerate
   estimate gives `status: "not_estimable"` with a `reason`; nothing is imputed.
6. **Multiplicity**: Benjamini-Hochberg across the trial's estimable interaction p-values → `q_value`.
7. **Label**: `weaker_benefit` if q ≤ 0.10 and HR in S > HR outside S; `stronger_benefit` if
   q ≤ 0.10 and HR in S < HR outside; otherwise `no_reliable_difference` (always for
   underpowered or not-estimable subgroups).

Patients with a missing value for a subgroup variable (e.g. colon `differ`) are left out of that
subgroup's in/out/interaction models only.

**Planted variants.** For each trial, the 3 largest estimable, non-underpowered subgroups (by n in S)
each get one variant: every treated patient in S has their (time, event) replaced by a draw with
replacement from the control patients in S (seed 20261018, combined with a CRC32 of
`trial:subgroup`). The full table is recomputed. `truth_flag` is the planted subgroup and
`truth_direction` is `weaker_benefit` by construction; the subgroup's own `truth` stays the computed
label, and `planted_detectable` says whether it came out `weaker_benefit`.

For original cases, `truth_flag` is the `weaker_benefit` subgroup with the smallest q (else null).

## Caveats

- **Old trials.** These are 1970s-1990s trials with dated standards of care; the results are a test
  bed for subgroup reasoning, not clinical guidance.
- **Multiplicity.** BH controls the false discovery rate within a trial only, not across trials or
  variants. Subgroup interactions in trials of this size have low power.
- **Small subgroups.** Many veteran subgroups (137 patients) are underpowered; they are labeled
  `no_reliable_difference` regardless of p-value. veteran has only 2 non-underpowered subgroups, so it
  has 2 planted variants, not 3.
- **gbsg is not fully randomized.** Hormonal therapy was partly assigned by choice, so every gbsg case
  carries `evidence_note: "Partly non-randomized treatment assignment: weaker evidence"`.
- **Planted cases are synthetic perturbations of real data.** The draws ignore other covariates, so a
  plant can (a) be statistically undetectable when the true effect in S is small or the complement is
  small, and (b) create spurious interactions in overlapping subgroups (e.g. `colon:planted:extent_ge_3`
  shows a BH-significant `stronger_benefit` in `nodes_gt_4`). Use `planted_detectable` when scoring.

## Regenerate

```bash
pip install -r backend/requirements.txt
python dataset/rct/fetch_rct.py          # optional: re-download (network); updates provenance.json
cd backend && python -m app.responder_truth   # writes dataset/rct/ground_truth.jsonl, prints summary
python -m pytest tests/test_responder_truth.py -q
```

Output is byte-identical across runs for a given seed and data snapshot (sorted keys, fixed order,
floats rounded to 4 decimals).
