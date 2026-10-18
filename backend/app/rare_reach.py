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

def _normalise_term(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())

def lookup_orpha(term: str, client: httpx.Client) -> tuple[str | None, str | None, list[str], str, str]:
    """Accept only an exact preferred-term or synonym match from one disease record."""
    url = f"{config.ORPHADATA_API_BASE}/rd-cross-referencing/orphacodes/names/{quote(term, safe='')}"
    try:
        response = client.get(url, params={"lang": "en"}, timeout=config.RARE_REACH_TIMEOUT_S)
        if response.status_code == 404: return None, None, [], "no_match", f"Orphadata did not return a disease record for '{term}'."
        response.raise_for_status(); payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None, None, [], "unavailable", "Orphadata could not be reached, so rare-disease status could not be verified."
    results = payload.get("data", {}).get("results") if isinstance(payload, dict) else None
    record = results[0] if isinstance(results, list) and results else results
    if not isinstance(record, dict):
        return None, None, [], "no_match", f"Orphadata returned no usable disease record for '{term}'."
    code = record.get("ORPHAcode")
    preferred = record.get("Preferred term")
    raw_synonyms = record.get("Synonym") or []
    synonyms = [item for item in raw_synonyms if isinstance(item, str)] if isinstance(raw_synonyms, list) else [raw_synonyms] if isinstance(raw_synonyms, str) else []
    if not isinstance(code, (str, int)) or not isinstance(preferred, str):
        return None, None, [], "no_match", f"Orphadata returned an incomplete disease record for '{term}'."
    candidate_terms = [preferred, *synonyms]
    if _normalise_term(term) not in {_normalise_term(candidate) for candidate in candidate_terms}:
        return None, None, [], "no_match", f"Orphadata returned the rare-disease candidate '{preferred}', but it does not exactly match the trial condition '{term}'. RareReach did not treat it as a confirmation."
    return str(code), preferred, list(dict.fromkeys(synonyms))[:20], "matched", f"Orphadata returned an exact rare-disease match for '{term}'."

def _nord_candidate_url(term: str | None) -> str | None:
    if not term: return None
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    return f"{NORD_URL}{slug}/" if slug else None

def _is_us_location(location: dict) -> bool:
    return str(location.get("country") or "").strip().casefold() in US_COUNTRY_NAMES


# Explicit aliases, scoped to a city and state: no fuzzy matching of unrelated sites.
SITE_ALIASES = {
    ("houston", "tx"): ("University of Texas MD Anderson Cancer Center", {
        "mdanderson", "mdandersoncancercenter", "universityoftexasmdanderson",
        "universityoftexasmdandersoncancercenter", "theuniversityoftexasmdandersoncancercenter",
    }),
    ("dallas", "tx"): ("University of Texas Southwestern Medical Center", {
        "utsouthwestern", "utsouthwesternmedicalcenter", "utsouthwesternmedicalcenteratdallas",
        "universityoftexassouthwestern", "universityoftexassouthwesternmedicalcenter",
        "universityoftexassouthwesternmedicalcenteratdallas",
    }),
}


def site_identity(name: str, city: str, region: str):
    normalized_city = _normalise_term(city)
    normalized_region = {"texas": "tx", "massachusetts": "ma"}.get(_normalise_term(region), _normalise_term(region))
    normalized_name = _normalise_term(name)
    alias = SITE_ALIASES.get((normalized_city, normalized_region))
    display = alias[0] if alias and normalized_name in alias[1] else name
    return (_normalise_term(display), normalized_city, normalized_region), display


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
    sites: dict[tuple[str,str,str], set[str]] = defaultdict(set)
    names: dict[tuple[str,str,str], set[str]] = defaultdict(set)
    display_sites = {}
    coordinates: dict[tuple[str,str,str], set[tuple[float,float]]] = defaultdict(set)
    for study in studies if isinstance(studies, list) else []:
        protocol = study.get("protocolSection", {}); nct = protocol.get("identificationModule", {}).get("nctId")
        for loc in protocol.get("contactsLocationsModule", {}).get("locations", []) or []:
            if not _is_us_location(loc):
                continue
            name, city, region = (str(loc.get(k) or "").strip() for k in ("facility", "city", "state"))
            if nct and name:
                key, display = site_identity(name, city, region)
                sites[key].add(str(nct))
                names[key].add(name)
                # Stable display independent of the order returned by the API.
                candidate = (display, city, region)
                display_sites[key] = min(display_sites.get(key, candidate), candidate)
                geo = loc.get("geoPoint") or {}
                latitude, longitude = geo.get("lat"), geo.get("lon")
                if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
                    coordinates[key].add((float(latitude), float(longitude)))
    out = []
    for key, ids in sites.items():
        name, city, region = display_sites[key]
        ids = sorted(ids)
        aliases = f" Name variants merged: {'; '.join(sorted(names[key]))}." if len(names[key]) > 1 else ""
        # Merged name variants can report slightly different points; pick one independent of API order.
        latitude, longitude = min(coordinates[key]) if coordinates[key] else (None, None)
        out.append(RecruitmentSite(name=name, city=city or None, region=region or None, country="United States", latitude=latitude, longitude=longitude, historical_trial_count=len(ids), matching_nct_ids=ids, source_urls=[STUDY_URL.format(nct_id=i) for i in ids], explanation=f"Listed in {len(ids)} distinct public ClinicalTrials.gov record(s) matching '{conditions[0]}'.{aliases} Historical activity is not patient volume, expertise, availability, or a partnership."))
    return sorted(out, key=lambda x: (-x.historical_trial_count, x.name))[:config.RARE_REACH_MAX_SITES]

def build_rare_reach(raw_nct_id: str, rules: list[Rule], trial: TrialInfo | None = None, client: httpx.Client | None = None) -> RareReachResponse:
    nct = normalize_nct_id(raw_nct_id); trial = trial or fetch_trial(nct)
    conditions = [c for c in trial.conditions if c]
    owned = client is None; client = client or httpx.Client()
    try:
        term = conditions[0] if conditions else (trial.title or "")
        code, preferred, synonyms, status, verification_reason = lookup_orpha(term, client) if term else (None, None, [], "no_match", "The trial did not provide a condition to verify.")
        is_rare_disease = status == "matched" and code is not None
        hospitals = find_hospitals(trial, client) if is_rare_disease else []
    except RareReachError: hospitals = []; code, preferred, synonyms, status, verification_reason = None, None, [], "unavailable", "ClinicalTrials.gov site research was unavailable."
    finally:
        if owned: client.close()
    is_rare_disease = status == "matched" and code is not None
    if not is_rare_disease:
        message = f"{verification_reason} ORPHAcodes are Orphanet's identifiers for rare diseases, so RareReach stopped before site or outreach research."
        return RareReachResponse(trial=trial, query_terms=conditions or ([trial.title] if trial.title else []), is_rare_disease=False, rare_disease_message=message, orpha_code=None, orpha_status=status, hospitals=[], strategies=[], sources=[{"name":"ClinicalTrials.gov","url":STUDY_URL.format(nct_id=nct),"access":"live"},{"name":"Orphadata terminology API","url":ORPHANET_URL,"access":"live" if status != "unavailable" else "unavailable"}], warnings=[message])
    strategies = [RecruitmentStrategy(rule_id=r.id, criterion=r.clause or r.text, safety_sensitive=r.safety_critical or r.purpose == "safety", outreach="Keep this criterion and investigate the public sites, Orphanet directories, and NORD resource below.") for r in rules if r.simulatable or r.safety_critical][:12]
    warnings = ["Historical trial counts are not patient counts, capacity, expertise, availability, or partnership evidence.", "No private patient records or registry access were used.", "Use the Orphanet Expert Centres Directory with the returned ORPHAcode to research centres and networks. RareReach does not automatically retrieve or rank directory listings."]
    return RareReachResponse(trial=trial, query_terms=conditions or ([trial.title] if trial.title else []), is_rare_disease=True, rare_disease_message=f"{verification_reason} RareReach public recruitment research is available for this condition.", orpha_code=code, orpha_status=status, orpha_preferred_name=preferred, orpha_synonyms=synonyms, hospitals=hospitals, nord_url=NORD_URL, nord_candidate_url=_nord_candidate_url(preferred or (conditions[0] if conditions else None)), strategies=strategies, sources=[{"name":"ClinicalTrials.gov","url":STUDY_URL.format(nct_id=nct),"access":"live"},{"name":"Orphadata terminology API","url":ORPHANET_URL,"access":"live"},{"name":"Orphanet Expert Centres Directory","url":ORPHANET_CENTRES_URL,"access":"public_manual_search"},{"name":"Orphanet Networks Directory","url":ORPHANET_NETWORKS_URL,"access":"public_manual_search"},{"name":"NORD","url":NORD_URL,"access":"public_link"}], warnings=warnings)
