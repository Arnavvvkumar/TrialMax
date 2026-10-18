# RareReach

## Data flow

`NCT ID → ClinicalTrials.gov trial record → condition → Orphadata ORPHAcode verification → rare-disease match only: ClinicalTrials.gov public study/location search → United States site filter → source-linked site activity → RareReach dashboard`.

The existing parser supplies protocol rules to the strategy panel. RareReach does not propose changing any rule; it keeps the criterion and suggests public recruitment research.

The public Orphadata name lookup resolves a trial condition to an ORPHAcode, preferred term, and returned synonyms when available. The Orphanet Expert Centres and Networks directories are linked for manual research using that ORPHAcode. They are not programmatically retrieved or ranked, because a stable permitted search API was not verified.

## Acceptance criteria

- `POST /api/rare-reach` accepts an NCT ID and parsed rules, and returns source links and warnings.
- No exact preferred-term/synonym ORPHAcode match, or an unavailable terminology lookup, stops RareReach before site, NORD, Orphanet-directory, or outreach results are returned. A broad condition must not be treated as confirmation of a differently named rare subtype.
- Each hospital is a United States site with one or more matching public NCT IDs; its count is explicitly historical trial activity, never patient volume or availability.
- No patient data, registry data, or recruitment partnership is accessed or claimed.
- Orphadata provides terminology matches when available; Orphanet centres/networks and NORD are source-linked for public manual research.
- Every strategy keeps the criterion and offers only an outreach recommendation; there is no criterion-relaxation option.
- The dashboard renders empty and source-unavailable states without fabricated sites or organisations.


Site ranking groups punctuation/case variants and a small explicit, city/state-scoped
alias list for MD Anderson (Houston, Texas) and UT Southwestern (Dallas, Texas).
Counts are the union of distinct NCT IDs, never the sum of duplicate listings.
Aliases and source study links remain in each site's explanation/evidence. Unlisted
name variants and different cities remain separate rather than being fuzzy-merged.
