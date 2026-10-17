"""Wind Tunnel API. Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .ctgov import TrialNotFound, fetch_trial
from .models import (
    AnalyzeRequest, AnalyzeResponse, CompareRequest, CompareResult, SimulateRequest,
    SimulationResult, TrialInfo,
)
from .pipeline import parse_eligibility
from .simulate import compare, simulate
from .variables import VARIABLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Wind Tunnel API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def _get_trial(nct_id: str) -> TrialInfo:
    try:
        return fetch_trial(nct_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TrialNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ClinicalTrials.gov request failed: {exc}")


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": config.llm_configured(), "model": config.LLM_MODEL or None}


@app.get("/api/variables")
def variables():
    return VARIABLES


@app.get("/api/trials/{nct_id}", response_model=TrialInfo)
def get_trial(nct_id: str):
    return _get_trial(nct_id)


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    if req.nct_id:
        trial = _get_trial(req.nct_id)
    elif req.eligibility_text:
        trial = TrialInfo(eligibility_text=req.eligibility_text)
    else:
        raise HTTPException(status_code=400, detail="Send either nct_id or eligibility_text.")
    if not trial.eligibility_text.strip():
        raise HTTPException(status_code=422, detail="This trial has no eligibility text on ClinicalTrials.gov.")
    rules, warnings, llm_used = parse_eligibility(trial.eligibility_text, use_llm=req.use_llm)
    sim = simulate(rules, req.population_size, req.seed)
    return AnalyzeResponse(trial=trial, rules=rules, simulation=sim, llm_used=llm_used, warnings=warnings)


@app.post("/api/simulate", response_model=SimulationResult)
def simulate_rules(req: SimulateRequest):
    return simulate(req.rules, req.population_size, req.seed)


@app.post("/api/compare", response_model=CompareResult)
def compare_rules(req: CompareRequest):
    return compare(req.baseline_rules, req.proposed_rules, req.population_size, req.seed)
