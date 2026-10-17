# Chalk scenario loop

The deterministic simulator remains the only component that determines pass,
fail, or unknown. Chalk supplies the synthetic patient features and records the
feature-query run used for a scenario.

## Setup

1. Install the backend dependencies, then authenticate the Chalk CLI with
   `chalk login`.
2. Deploy a Chalk feature set containing the `patient.*` names listed in
   `backend/app/feature_sources.py` from the checked-in synthetic cohort only.
3. Verify a known row with `chalk query --in patient.id=SYN-0001` and the
   required output features.
4. Set `CHALK_FEATURE_BRANCH` if querying a Chalk branch, and set
   `VITE_USE_BACKEND=true` plus `VITE_SCENARIO_SOURCE=chalk` in a local
frontend `.env`.

## Trial lookup from Chalk SQL

The API reads the existing `chalk.datasets."nsclc-trials"` dataset directly
with a read-only, validated `chalk sql` call. It selects only the NCT ID,
criteria, title, status, enrollment, gender, and age-limit columns; no
`trial.*` features or Chalk-dashboard changes are required. Use
`GET /api/trials/NCT...?source=chalk` to require Chalk. The default
`source=auto` tries Chalk, then explicitly falls back to ClinicalTrials.gov
when that dataset lacks the requested NCT ID.

`POST /api/scenario-review` accepts baseline and proposed validated rules. It
queries the requested synthetic features through Chalk, runs the deterministic
comparison, and returns a source label and query identifier. If Chalk is not
configured or unavailable, the endpoint explicitly returns
`data_source: local-json-fallback` and uses the checked-in synthetic cohort.

## Evaluation

Run the backend suite and require the Chalk-backed results to match
`frontend/synthetic_data/demo_validation.json`. In particular, missing values
must remain `unknown`, and safety-critical relaxations must be returned for
human review.
