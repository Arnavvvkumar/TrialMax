# Backend review fixes

The parser now refuses unsupported logical groups, subgroup requirements, and
unconsumed numeric bounds instead of silently changing the criterion's meaning.
Unknown conjuncts remain visible as unmodeled requirements. Explicit unsupported
units are rejected rather than inferred, and absolute GFR is not substituted for
indexed eGFR. Treatment toxicity/outcomes are not represented as prior exposure.
Breastfeeding is separate from pregnancy and remains unmodeled.

## API behavior for the frontend

- `POST /api/analyze` returns **422** if parsing produces more than 150 rules.
  It returns no truncated simulation. `/api/simulate` and `/api/compare` retain
  their existing limit of 200 rules per list.
- `eligible_n` and `eligible_pct` remain nullable when no checks can be modeled.
  `newly_eligible_n` and `newly_excluded_n` are now also **nullable** if either
  comparison has no modeled estimate. Display "Unavailable", not zero.
- Non-null comparison counts describe transitions on the modeled synthetic
  checks only. Display each side's coverage and approximation caveats.
- Changes to unmodeled rules appear as `ambiguous`. Changed safety-critical
  unmodeled rules appear in `review_safety_critical_rule_ids` for human review.
- Request size is enforced on actual received bytes, including chunked requests.
  Oversized bodies return **413** before JSON parsing.
- `assumptions` identifies the updated population as `synthetic-oncology-v1`.
  The added weight draws changed patient attributes for a given old seed. Do not
  compare saved v0 patient IDs or results with v1 as if they were the same cohort.
- LLM prompt/cache version is now 3. Old cached interpretations are not reused.

## Verification

`backend/tests/test_review_regressions.py` contains the review's failing inputs,
small explicit patient truth tables, request-limit checks, and safety/coverage
regressions. Run the complete suite from the repository root with:

```powershell
python -m pytest backend/tests -q
```

Provider calls are mocked in these tests. They do not validate live gateway
availability or replace a frontend integration check.

## Credential follow-up

The local `.env` remains ignored and its removal from the Git index is preserved.
Earlier commits still contain the previously committed credential. Its owner
must revoke/rotate it if that has not already been done. These code changes do
not revoke credentials or rewrite repository history.
