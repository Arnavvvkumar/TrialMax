"""Public, traceable RareReach discovery. Never accesses patient records."""
from __future__ import annotations
from collections import defaultdict
import httpx
from urllib.parse import quote
import re
from . import config
from .ctgov import fetch_trial, normalize_nct_id
from .models import RareReachResponse, RecruitmentSite, RecruitmentStrategy, Rule, TrialInfo

SEARCH_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"
ORPHANET_URL = "https://www.orpha.net/en/disease"
ORPHANET_CENTRES_URL = "https://www.orpha.net/en/expert-centres"
ORPHANET_NETWORKS_URL = "https://www.orpha.net/en/expert-centres/networks"
NORD_URL = "https://rarediseases.org/rare-diseases/"
US_COUNTRY_NAMES = {"united states", "united states of america", "usa", "us"}

class RareReachError(RuntimeError): pass

def _values(value, keys: set[str]) -> list[object]:
    """Collect values across Orphadata's nested response formats."""
    if isinstance(value, dict):
        found = [item for key, item in value.items() if key.lower() in keys]
        for item in value.values(): found.extend(_values(item, keys))
        return found
    if isinstance(value, list): return [item for child in value for item in _values(child, keys)]
    return []

def lookup_orpha(term: str, client: httpx.Client) -> tuple[str | None, str | None, list[str], str]:
    """Public name lookup; return no match/unavailable rather than guessing."""
    url = f"{config.ORPHADATA_API_BASE}/rd-cross-referencing/orphacodes/names/{quote(term, safe='')}"
    try:
        response = client.get(url, params={"lang": "en"}, timeout=config.RARE_REACH_TIMEOUT_S)
        if response.status_code == 404: return None, None, [], "no_match"
        response.raise_for_status(); payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None, None, [], "unavailable"
    codes = _values(payload, {"orphacode", "orpha_code"})
    names = _values(payload, {"name", "preferredterm", "preferred_term"})
    synonyms = [str(item) for item in _values(payload, {"synonym", "synonyms"}) if isinstance(item, str)]
    code = str(codes[0]) if codes else None
    preferred = str(names[0]) if names else None
    return code, preferred, list(dict.fromkeys(synonyms))[:20], "matched" if code else "no_match"

def _nord_candidate_url(term: str | None) -> str | None:
    if not term: return None
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    return f"{NORD_URL}{slug}/" if slug else None

def _is_us_location(location: dict) -> bool:
    return str(location.get("country") or "").strip().casefold() in US_COUNTRY_NAMES

def find_hospitals(trial: TrialInfo, client: httpx.Client | None = None) -> list[RecruitmentSite]:
    conditions = [c for c in trial.conditions if c]
    if not conditions: return []
    owned = client is None; client = client or httpx.Client()
    try:
        response = client.get(SEARCH_URL, params={"query.cond": conditions[0], "pageSize": config.RARE_REACH_MAX_STUDIES}, timeout=config.RARE_REACH_TIMEOUT_S)
        response.raise_for_status(); studies = response.json().get("studies", [])
    except httpx.HTTPError as exc: raise RareReachError(f"ClinicalTrials.gov site search failed: {exc}") from exc
    finally:
        if owned: client.close()
    sites: dict[tuple[str,str,str,str], set[str]] = defaultdict(set)
    for study in studies if isinstance(studies, list) else []:
        protocol = study.get("protocolSection", {}); nct = protocol.get("identificationModule", {}).get("nctId")
        for loc in protocol.get("contactsLocationsModule", {}).get("locations", []) or []:
            if not _is_us_location(loc):
                continue
            key = tuple(str(loc.get(k) or "").strip() for k in ("facility", "city", "state", "country"))
            if nct and key[0]: sites[key].add(str(nct))
    out = []
    for (name, city, region, country), ids in sites.items():
        ids = sorted(ids)
        out.append(RecruitmentSite(name=name, city=city or None, region=region or None, country=country or None, historical_trial_count=len(ids), matching_nct_ids=ids, source_urls=[STUDY_URL.format(nct_id=i) for i in ids], explanation=f"Listed in {len(ids)} public ClinicalTrials.gov record(s) matching '{conditions[0]}'. Historical activity is not patient volume, expertise, availability, or a partnership."))
    return sorted(out, key=lambda x: (-x.historical_trial_count, x.name))[:config.RARE_REACH_MAX_SITES]

def build_rare_reach(raw_nct_id: str, rules: list[Rule], trial: TrialInfo | None = None, client: httpx.Client | None = None) -> RareReachResponse:
    nct = normalize_nct_id(raw_nct_id); trial = trial or fetch_trial(nct)
    conditions = [c for c in trial.conditions if c]
    owned = client is None; client = client or httpx.Client()
    try:
        term = conditions[0] if conditions else (trial.title or "")
        code, preferred, synonyms, status = lookup_orpha(term, client) if term else (None, None, [], "no_match")
        is_rare_disease = status == "matched" and code is not None
        hospitals = find_hospitals(trial, client) if is_rare_disease else []
    except RareReachError: hospitals = []; code, preferred, synonyms, status = None, None, [], "unavailable"
    finally:
        if owned: client.close()
    is_rare_disease = status == "matched" and code is not None
    if not is_rare_disease:
        message = "Rare-disease status could not be confirmed because Orphadata was unavailable. RareReach did not search sites or provide outreach recommendations." if status == "unavailable" else "This trial condition did not return an ORPHAcode match. RareReach only runs recruitment research for conditions confirmed as rare diseases."
        return RareReachResponse(trial=trial, query_terms=conditions or ([trial.title] if trial.title else []), is_rare_disease=False, rare_disease_message=message, orpha_code=None, orpha_status=status, hospitals=[], strategies=[], sources=[{"name":"ClinicalTrials.gov","url":STUDY_URL.format(nct_id=nct),"access":"live"},{"name":"Orphadata terminology API","url":ORPHANET_URL,"access":"live" if status != "unavailable" else "unavailable"}], warnings=[message])
    strategies = [RecruitmentStrategy(rule_id=r.id, criterion=r.clause or r.text, safety_sensitive=r.safety_critical or r.purpose == "safety", outreach="Keep this criterion and investigate the public sites, Orphanet directories, and NORD resource below.") for r in rules if r.simulatable or r.safety_critical][:12]
    warnings = ["Historical trial counts are not patient counts, capacity, expertise, availability, or partnership evidence.", "No private patient records or registry access were used.", "Use the Orphanet Expert Centres Directory with the returned ORPHAcode to research centres and networks. RareReach does not automatically retrieve or rank directory listings."]
    return RareReachResponse(trial=trial, query_terms=conditions or ([trial.title] if trial.title else []), is_rare_disease=True, rare_disease_message="Orphadata returned an ORPHAcode match. RareReach public recruitment research is available for this condition.", orpha_code=code, orpha_status=status, orpha_preferred_name=preferred, orpha_synonyms=synonyms, hospitals=hospitals, nord_url=NORD_URL, nord_candidate_url=_nord_candidate_url(preferred or (conditions[0] if conditions else None)), strategies=strategies, sources=[{"name":"ClinicalTrials.gov","url":STUDY_URL.format(nct_id=nct),"access":"live"},{"name":"Orphadata terminology API","url":ORPHANET_URL,"access":"live"},{"name":"Orphanet Expert Centres Directory","url":ORPHANET_CENTRES_URL,"access":"public_manual_search"},{"name":"Orphanet Networks Directory","url":ORPHANET_NETWORKS_URL,"access":"public_manual_search"},{"name":"NORD","url":NORD_URL,"access":"public_link"}], warnings=warnings)
