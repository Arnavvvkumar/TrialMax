# Randomized-trial evidence (responder evaluation)

Public patient-level data from three randomized trials, used to compute deterministic ground truth for the
responder-evidence agent and its Chalk evaluation. Method, caveats, results and rerun steps are in
[docs/responder.md](../../docs/responder.md).

| Trial | File | Comparison | Endpoint |
|---|---|---|---|
| colon | `colon.csv` | Lev+5FU vs observation (Lev-alone arm dropped) | overall survival (`etype == 2`, one row per patient) |
| veteran | `veteran.csv` | test vs standard chemotherapy | overall survival |
| gbsg | `gbsg.csv` | hormonal therapy vs none (partly non-randomized: weaker evidence) | recurrence-free survival |

Data: R `survival` package (Therneau T, *A Package for Survival Analysis in R*) via the Rdatasets mirror,
and the original trial publications (colon: Moertel et al., NEJM 1990; veteran: Kalbfleisch & Prentice 1980;
gbsg: Schumacher et al. 1994). Each `<trial>.provenance.json` records the URL, download time and sha256.

- `fetch_rct.py`: re-download the CSVs (network) and update provenance.
- `backend/app/responder_truth.py`: compute `ground_truth.jsonl` (no AI; Cox models, interaction tests,
  Benjamini-Hochberg, seeded planted variants).
- `chalk_eval.py`, `eval_common.py`, `chalk_transport.py`: run the Chalk evaluation; IDs and scores are in
  `chalk_runs.json` and `local_eval_results.json`.

An independent implementation of the same ground truth (identical data, different output schema) is preserved
in commit `8633ff3` (`data/` layout). The app and evaluation use the version in this folder.
