# RareReach

## Data flow

`NCT ID → ClinicalTrials.gov trial record → condition → ClinicalTrials.gov public study/location search → United States site filter → source-linked site activity → RareReach dashboard`.

The existing parser supplies protocol rules to the strategy panel. RareReach does not propose changing any rule; it keeps the criterion and suggests public recruitment research.

The public Orphadata name lookup resolves a trial condition to an ORPHAcode, preferred term, and returned synonyms when available. The Orphanet Expert Centres and Networks directories are linked for manual research using that ORPHAcode. They are not programmatically retrieved or ranked, because a stable permitted search API was not verified.

## Acceptance criteria

- `POST /api/rare-reach` accepts an NCT ID and parsed rules, and returns source links and warnings.
- Each hospital is a United States site with one or more matching public NCT IDs; its count is explicitly historical trial activity, never patient volume or availability.
- No patient data, registry data, or recruitment partnership is accessed or claimed.
- Orphadata provides terminology matches when available; Orphanet centres/networks and NORD are source-linked for public manual research.
- Every strategy keeps the criterion and offers only an outreach recommendation; there is no criterion-relaxation option.
- The dashboard renders empty and source-unavailable states without fabricated sites or organisations.
