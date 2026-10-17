# Code review prompt (paste into ChatGPT, then attach or paste the files listed below)

You are a senior software engineer and code reviewer with experience in Python, FastAPI, data
pipelines, LLM safety, and clinical-research software. Review the code I share for a hackathon
project. Read all the context below before reviewing.

## 1. What the project is

**CliNova** is a web app for clinical-trial designers. A researcher pastes a ClinicalTrials.gov
trial ID (or eligibility text). The app:

1. Fetches the trial's eligibility criteria from the public ClinicalTrials.gov API (v2).
2. Splits the text into individual criteria and parses each one into a checkable rule
   (for example "ECOG <= 2", "ANC >= 1.5 x10^9/L", "exclude if brain metastases present").
3. Runs the rules on a **synthetic** patient population and reports: the % eligible, how many
   patients each rule excludes on its own and uniquely, an attrition funnel, the single most
   restrictive rule, and per-patient "why excluded" reasons.
4. Lets the researcher compare an edited rule set against the original (newly eligible patients,
   and a warning when a safety-critical rule is relaxed).

The pitch is **"see the trade-offs of every eligibility rule before you lock the protocol"**, NOT
"loosen the rules to enroll faster". Each rule is tagged with its purpose (safety, predictive
enrichment, prognostic enrichment, reducing variability) and how a site could find such patients
(coded lab, diagnosis code, chart review, ...). Final decisions always stay with qualified researchers.

## 2. Hackathon context and judging

- Event: HackHarvard 2026 (36 hours). Team of 4. Track: Healthcare, "Reinvent Clinical Trials",
  presented by Regeneron. We also enter the Chalk sponsor challenge ("Best Data-Driven Agent Built on Chalk",
  judged on impact, use of data, and how it is evaluated).
- Regeneron judges on: **Usefulness**, **Design** (workflow fit, not just looks) and **Readiness**
  (working, deployed code that performs as claimed; "working beats convincing").
- Regeneron mentor guidance we follow:
  - Sponsors do not recruit patients; sites do. Never assume sponsor-to-patient outreach.
  - Eligibility criteria are deliberate trade-offs (safety, predictive enrichment, prognostic
    enrichment, reducing variability). Every exclusion also costs generalizability.
  - Name AI-agent risks (prompt injection, excessive agency) and show mitigations: least privilege,
    human confirmation, logging, traceability of every number.
  - Never use real patient data. Public or synthetic data only.

## 3. Architecture and stack

- Backend: Python 3.12, FastAPI, Pydantic v2, httpx, numpy, openai SDK (pointed at Chalk), pytest.
- LLM calls go through the **Chalk Model Gateway**, an OpenAI-compatible router
  (base URL `https://api.chalk.ai/v1/router`, headers `Authorization: Bearer <key>` and
  `X-Chalk-Env-Id`). The upstream model is a Google Gemini/Gemma model. Secrets live only in a local
  `.env` (git-ignored); `.env.example` documents the variables.
- Frontend: being built separately by a teammate in `frontend/` against the API below.
- Planned Chalk use beyond the gateway: Chalk sandboxes for any AI-generated code, Chalk evaluations
  for our accuracy tests.

### API (backend/app/main.py)
- `GET /api/health` -> status, whether the LLM is configured, model name
- `GET /api/variables` -> variables the simulator understands, with default purpose/findability
- `GET /api/trials/{nct_id}` -> trial metadata and raw eligibility text
- `POST /api/analyze` {nct_id | eligibility_text, use_llm, population_size, seed} -> trial, rules, simulation, warnings
- `POST /api/simulate` {rules, population_size, seed} -> simulation
- `POST /api/compare` {baseline_rules, proposed_rules, population_size, seed} -> both simulations + deltas

### Files (backend/)
- `app/variables.py` - registry of simulatable variables with default purpose, findability,
  safety_critical flag and rationale; ULN constants for "x ULN" thresholds.
- `app/models.py` - Pydantic models shared with the frontend (Rule, TrialInfo, SimulationResult, ...).
- `app/criteria.py` - deterministic splitter and regex parser (age, ECOG/Karnofsky, lab panels with
  unit conversion, conditions, prior therapy, administrative items, permissive statements).
- `app/population.py` - synthetic adult oncology population. All distributions are stated
  assumptions returned with every result. Variables are independent (a known simplification).
- `app/simulate.py` - applies rules to the population: per-rule and unique exclusion, funnel, worst
  rule, sample of excluded patients, and the compare function.
- `app/llm.py` - LLM fallback for criteria the regex parser cannot read. The prompt treats criterion
  text as untrusted data; the model has no tools; output must pass strict Pydantic validation against
  the known variable list or it is rejected; results are cached on disk.
- `app/pipeline.py` - deterministic parse first, then concurrent LLM calls for the leftovers.
- `app/ctgov.py` - ClinicalTrials.gov client with strict NCT ID validation.
- `app/config.py` - settings from `.env`.
- `tests/` - 38 pytest tests: real trial fixtures (NCT07223541, NCT06149286), planted-truth
  simulation checks, LLM-output validation, ID validation.

## 4. Known issues (already on our list; still comment if you see a better fix)

1. An inclusion criterion like "For patients with chronic HBV, viral load must be undetectable on
   suppressive therapy" is parsed as "hepatitis B absent", but it is really a permission with a condition.
2. Section headers such as "Patients are ineligible if they have:" are not recognized as the start of
   exclusion criteria.
3. Severity and timing qualifiers ("active", "uncontrolled", "within 30 days") are not modeled; the
   rule notes say so.
4. The synthetic population treats variables as independent.
5. The LLM is slow on the free tier, which is why there is a cache.

## 5. What I want from you

Review for, in priority order:
1. **Correctness bugs**: wrong parsing logic, wrong inclusion/exclusion semantics, unit conversion
   errors, off-by-one or percentage errors, edge cases in the splitter, incorrect statistics.
2. **Security**: prompt injection paths, input validation, SSRF, secret handling, CORS, anything
   that could leak the API key, unsafe defaults.
3. **Clinical/scientific honesty**: anything that overstates what the simulation means, or tags a
   criterion's purpose misleadingly. The numbers are estimates from synthetic data, and the UI must
   never imply otherwise.
4. **Readiness**: what would break in a live demo (timeouts, slow LLM, ClinicalTrials.gov errors,
   large inputs, concurrency).
5. **Test gaps**: important behavior that has no test.
6. Code quality: only where it matters for the above. Skip style nitpicks.

Rules for your review:
- Do not ask for or suggest committing secrets. Never suggest putting the API key in code or git.
- Do not suggest using real patient data.
- Be specific: cite the file and function, explain the failure with a concrete input, and propose a
  minimal fix. Mark each finding as **Critical / High / Medium / Low**.
- If something looks wrong but you are not sure, say so and explain what would confirm it.
- Do not rewrite whole files. Keep suggested changes small and targeted.

Output format:
1. A short overall verdict (3-5 lines).
2. A table of findings: severity | file:function | problem | concrete failing input | suggested fix.
3. Missing tests you would add, as a short list.
4. The top 3 things to fix before the demo.

The code follows below. I will paste or attach the files listed in section 3.
