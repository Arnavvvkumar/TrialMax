"""Read trials from the public ClinicalTrials.gov API (v2). No login needed."""
from __future__ import annotations

import re

import httpx

from .models import TrialInfo

API_URL = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
NCT_RE = re.compile(r"^NCT\d{8}$")


class TrialNotFound(Exception):
    pass


def normalize_nct_id(raw: str) -> str:
    nct_id = raw.strip().upper()
    if not NCT_RE.match(nct_id):
        raise ValueError("A trial ID looks like NCT followed by 8 digits, for example NCT07223541.")
    return nct_id


def parse_study(data: dict) -> TrialInfo:
    p = data.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    elig = p.get("eligibilityModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    return TrialInfo(
        nct_id=ident.get("nctId"),
        title=ident.get("briefTitle"),
        phases=design.get("phases", []) or [],
        conditions=p.get("conditionsModule", {}).get("conditions", []) or [],
        sponsor=sponsor.get("name"),
        status=status.get("overallStatus"),
        enrollment=(design.get("enrollmentInfo") or {}).get("count"),
        minimum_age=elig.get("minimumAge"),
        maximum_age=elig.get("maximumAge"),
        sex=elig.get("sex"),
        eligibility_text=elig.get("eligibilityCriteria", "") or "",
        data_source="ctgov",
    )


def fetch_trial(raw_id: str, timeout: float = 20.0) -> TrialInfo:
    nct_id = normalize_nct_id(raw_id)
    resp = httpx.get(API_URL.format(nct_id=nct_id), timeout=timeout)
    if resp.status_code == 404:
        raise TrialNotFound(f"{nct_id} was not found on ClinicalTrials.gov.")
    resp.raise_for_status()
    return parse_study(resp.json())
