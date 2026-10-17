# CliNova

See the trade-offs of every eligibility rule before you lock the protocol.

Wind Tunnel connects a React frontend to a FastAPI parser and deterministic eligibility engine. Researchers can load a ClinicalTrials.gov ID or paste public eligibility text, inspect per-rule outcomes and exclusions, edit numeric thresholds, compare the draft on the same synthetic patients, and record accept/reject decisions. The original criteria stay intact.

## Run locally

Use Python 3.12 and Node.js 22.12+ (or 24+). From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). Vite proxies `/api` to port 8000. The API documentation is at `http://127.0.0.1:8000/docs`. Preserve an existing local `.env` rather than copying over it.

Chalk credentials are optional for the deterministic workflow. Keep them only in the local, ignored root `.env` or server environment. The UI's Chalk fallback checkbox is off by default; enabling it uses the existing server-side Model Gateway parser for unread criteria, subject to its configured time budget. No model tools or generated code are executed.

For an offline demo, click **Load example text**, then **Load and analyze**. This fictional protocol uses the actual parser and simulation engine; there are no fabricated result counts. A real NCT lookup requires ClinicalTrials.gov network access.

## Two explicit population modes

| Mode | Data | Interpretation |
| --- | --- | --- |
| Fixed (pasted-text/example default) | The checked-in 500 fictional NSCLC records in `frontend/synthetic_data/patients.json` | Same records and missing values on every run. Not representative of other populations. |
| Generated (registry-lookup default) | Reproducible adult oncology records, selected size and seed | Assumed distributions and simplified correlations; exploratory only. Some fixed-cohort biomarkers are unavailable. |

These datasets are entirely synthetic, not Synthea. Neither validates diagnosis, histology, stage, treatment safety, actual recruitment, or real-world eligibility. Every result includes assumptions, coverage, approximation warnings, and a versioned cohort ID. Do not compare rates across different population modes as if they measured the same population.

Each substantive check returns pass, fail, or unknown. A known failure excludes a record; otherwise any missing/unsupported requirement makes its overall result unknown. `eligible_n` is known passing all substantive checks, and is null when nothing can be modeled. `modeled_eligible_n` separately counts those passing the available checks. Administrative and permissive statements are shown but do not participate in patient classification. Incomplete or approximate rules are disclosed.

The headline, rate and comparisons use `modeled_eligible_n`/`modeled_eligible_pct`. The funnel has `funnel_basis: "modeled_checks"` and applies only available modeled rules; its last row matches those counts, including missing values as unknown. Unsupported rules and fields absent from the selected cohort appear separately as **Not checked**, and remain unresolved in full-protocol and patient-level results. Patients have both `modeled_status` and `overall_status`. Modeled comparison deltas and transitions are explicitly prefixed `modeled_`; legacy unprefixed deltas retain full-protocol semantics. Passing the checked subset never confirms eligibility for the full protocol.

Registry lookups start with generated exploration for broader field coverage; the user can explicitly select the fixed cohort. The app warns when the fixed NSCLC cohort is not a verified disease match, and discloses that even a shared disease label or a generated population does not establish representativeness.

Changing the input, population mode, generated size, seed, or AI setting clears the baseline, draft comparison, and review decisions. Comparisons reuse exactly the same cohort. Safety-sensitive edits require a rationale before local acceptance; acceptance records a researcher decision and does not approve clinical safety or change the source protocol. Review records can be downloaded as JSON. Decisions are session-only; refresh clears them. A mix of accepted/rejected edits needs a fresh combined simulation before using its counts.

## API population contract

`GET /api/populations` returns the available versions, fixed cohort ID, and supported fields. `POST /api/analyze`, `/api/simulate`, and `/api/compare` all accept the same `population` object:

```json
{"mode": "generated", "size": 10000, "seed": 42}
```

On `/api/analyze`, omitting population defaults NCT lookups to generated exploration (10,000, seed 42) and pasted text to fixed. `/api/simulate` and `/api/compare` default to fixed when population is omitted; clients should always send the baseline's explicit selection. Send `{"mode":"fixed"}` to explicitly choose the fixed cohort. Its supplied size/seed do not alter the checked-in dataset. Send the returned `version` and `cohort_id` with later calls to pin the baseline; stale or mismatched selections return 422. Generated cohort identity includes generator version, NumPy version, size, and seed. Changes to generator logic require incrementing its version.

Legacy top-level `population_size` and `seed` are deprecated, validated but ignored; migrate clients to `population.size` and `population.seed`. The frontend uses the new contract throughout.

Counts use the full cohort. Patient details include all records up to 500, otherwise a bounded preview of up to 100; the UI displays the first 20. Pair overlaps are bounded to the 20 rules with the largest exclusions, and the UI displays up to 30 returned pairs. Overlap and unique-failure counts are not additive.

The optional `WT_COHORT_PATH` server environment variable overrides the fixed JSON location. The file must remain synthetic, with unique patient IDs. Cohort content is fingerprinted; replacing it requires restarting the server and reloading the baseline.

## Build and deployment

```powershell
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

FastAPI serves the built UI and API at `http://127.0.0.1:8000`. Build before starting the server so static assets are mounted. For separate frontend hosting, set `VITE_API_BASE_URL` at build time and allow that exact frontend origin through `ALLOWED_ORIGINS` on the backend.

A Dockerfile packages the frontend, backend, and fixed synthetic data together (build from the repository root):

```powershell
docker build -f backend/Dockerfile -t wind-tunnel .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env wind-tunnel
```

Root and nested `.env` files are excluded from the image build context. Pass secrets at runtime. If `WT_API_TOKEN` is enabled, the current browser client can send `VITE_API_TOKEN`; values starting with `VITE_` are public browser bundle configuration, not secret storage. Never put the Chalk key there. The shared token is a demo access gate, not per-user authentication. Existing rate, body-size and concurrency limits are configurable in `.env.example`.

## Checks

```powershell
python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

Tests cover parser fixtures, malformed LLM output, semantic validation, planted simulation outcomes, missing data, cohort identity across endpoints, safety comparisons, and frontend stale-state/review behavior. Live provider availability and deployment credentials require separate environment-specific checks.

Chalk feature-store queries, hosted Chalk evals/sandboxes, comparable-trial benchmarks, site ranking and PDF reports are outside this integration. The current Chalk connection is the optional Model Gateway parser fallback; do not present the other capabilities as implemented.

`GET /api/health` and the source-input view report missing Chalk configuration by variable name, without exposing credentials. A configured gateway is labeled **not verified** until tested; configuration alone does not prove authentication, quota or model availability. **Test live Chalk connection** calls `POST /api/chalk/check`: one fresh, uncached parser request, with retries disabled and a 15-second timeout. Success requires both a response and the expected validated age rule. Authentication, model permission, rate-limit and malformed-output failures are shown explicitly; failed checks disable the AI checkbox until a check passes. No provider error bodies or credentials are returned.

The sponsor-provided settings are `CHALK_ENV_ID=clkdcdaf84e`, `LLM_MODEL=openai/gpt-6-sol` and `CHALK_BASE_URL=https://api.chalk.ai/v1/router`. Use the actual router key shared by its issuer in the private `CHALK_ROUTER_API_KEY` setting. A key without model access receives 403; changing code cannot grant that access. Restart the backend after changing `.env`. The sponsor reports a shared daily token allowance; the app retains its own work/time limits.
