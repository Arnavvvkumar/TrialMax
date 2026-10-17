# RareReach

## Data flow

`NCT ID → ClinicalTrials.gov trial record → condition → ClinicalTrials.gov public study/location search → source-linked site activity → RareReach dashboard`.

The existing parser supplies protocol rules to the strategy panel. It does not change a rule. Safety-sensitive rules always require qualified clinical review.

The public Orphadata name lookup resolves a trial condition to an ORPHAcode, preferred term, and returned synonyms when available. The Orphanet Expert Centres and Networks directories are linked for manual research using that ORPHAcode. They are not programmatically retrieved or ranked, because a stable permitted search API was not verified.

## Acceptance criteria

- `POST /api/rare-reach` accepts an NCT ID and parsed rules, and returns source links and warnings.
- Each hospital has one or more matching public NCT IDs; its count is explicitly historical trial activity, never patient volume or availability.
- No patient data, registry data, or recruitment partnership is accessed or claimed.
- Orphanet/NORD show `link_only` until an approved integration exists.
- A safety-sensitive criterion receives a clinical-review-only Option A and a preserve-the-criterion Option B.
- The dashboard renders empty and source-unavailable states without fabricated sites or organisations.
