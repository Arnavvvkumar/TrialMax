"""TrialMax API. Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import deque
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, llm
from .chalk_trials import ChalkTrialError, ChalkTrialNotFound, fetch_chalk_trial, fetch_snapshot_trial
from .ctgov import TrialNotFound, fetch_trial
from .cohorts import population_catalog, simulate_population, compare_population, trial_population_warnings
from .models import (
    AutopilotRequest, AutopilotResponse,
    AnalyzeRequest, AnalyzeResponse, CompareRequest, CompareResult, ScenarioReviewRequest,
    ScenarioReviewResponse, SimulateRequest, RareReachRequest, RareReachResponse,
    SimulationResult, TrialInfo,
)
from .pipeline import parse_eligibility
from .registry import registry_rules
from .scenario_agent import review_scenario
from .rare_reach import RareReachError, build_rare_reach
from .variables import VARIABLES
from .autopilot import run_autopilot
from .responder_models import ResponderRequest, ResponderResponse
from .responder_evidence import responder_evidence

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("windtunnel.api")

app = FastAPI(title="TrialMax API", version="0.2.0")


class BodySizeLimitMiddleware:
    """Bound received bytes before JSON parsing, including chunked request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or not scope["path"].startswith("/api/")
                or scope["method"] == "OPTIONS"):
            await self.app(scope, receive, send)
            return
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > config.MAX_BODY_BYTES:
                response = JSONResponse(status_code=413, content={"detail": "Request body too large."})
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-WT-Token"])


# ---------------------------------------------------------------- protection

@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method != "OPTIONS":
        if config.API_TOKEN and path != "/api/health":
            token = request.headers.get("x-wt-token", "")
            if not hmac.compare_digest(token, config.API_TOKEN):
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid X-WT-Token."})
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body too large."})
    return await call_next(request)


_slots = threading.BoundedSemaphore(config.MAX_CONCURRENT_HEAVY)
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def heavy_request(request: Request):
    """Per-IP rate limit plus a cap on heavy requests running at once."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _hits_lock:
        if len(_hits) > 10000:
            for key in [k for k, q in _hits.items() if not q or now - q[-1] > 60]:
                _hits.pop(key, None)
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_PER_MIN:
            raise HTTPException(status_code=429, detail="Too many requests; try again in a minute.")
        q.append(now)
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server is busy; try again shortly.")
    try:
        yield
    finally:
        _slots.release()


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ---------------------------------------------------------------- endpoints

def _get_trial(nct_id: str, source: str = "auto") -> TrialInfo:
    if source in ("auto", "chalk"):
        try:
            return fetch_chalk_trial(nct_id)
        except ChalkTrialNotFound as exc:
            if source == "chalk":
                raise HTTPException(status_code=404, detail=str(exc))
            log.info("Chalk has no trial %s; falling back to ClinicalTrials.gov.", nct_id)
        except ChalkTrialError as exc:
            # No live Chalk SQL here (e.g. no CLI on the host): use the bundled export of the same dataset.
            log.info("Live Chalk SQL unavailable (%s); using the Chalk dataset snapshot.", exc)
            try:
                return fetch_snapshot_trial(nct_id)
            except ChalkTrialNotFound as missing:
                if source == "chalk":
                    raise HTTPException(status_code=404, detail=str(missing))
                log.info("Chalk snapshot has no trial %s; falling back to ClinicalTrials.gov.", nct_id)
            except ChalkTrialError as snapshot_exc:
                if source == "chalk":
                    log.warning("Chalk trial request failed: %s; %s", exc, snapshot_exc)
                    raise HTTPException(status_code=502, detail="Chalk trial request failed; try again.")
                log.info("Chalk trial source unavailable; falling back to ClinicalTrials.gov: %s", snapshot_exc)
    try:
        return fetch_trial(nct_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TrialNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except httpx.HTTPError as exc:
        log.warning("ClinicalTrials.gov request failed: %s", exc)
        raise HTTPException(status_code=502, detail="ClinicalTrials.gov request failed; try again.")


@app.get("/api/health")
def health():
    missing = [name for name in ("CHALK_ROUTER_API_KEY", "CHALK_ENV_ID", "LLM_MODEL") if not getattr(config, name)]
    return {"status": "ok", "llm_configured": config.llm_configured(), "model": config.LLM_MODEL or None,
            "llm_status": "configured_not_verified" if not missing else "not_configured",
            "llm_missing_configuration": missing}


@app.get("/api/variables")
def variables():
    return VARIABLES


@app.post("/api/chalk/check", dependencies=[Depends(heavy_request)])
def check_chalk():
    return llm.check_connection()


@app.get("/api/populations")
def populations():
    return population_catalog()


@app.get("/api/trials/{nct_id}", response_model=TrialInfo)
def get_trial(nct_id: str, source: str = "auto"):
    selected = config.CHALK_TRIAL_SOURCE if source == "auto" else source
    if selected not in {"auto", "chalk", "ctgov"}:
        raise HTTPException(status_code=422, detail="source must be auto, chalk, or ctgov.")
    return _get_trial(nct_id, selected)


@app.post("/api/analyze", response_model=AnalyzeResponse, dependencies=[Depends(heavy_request)])
def analyze(req: AnalyzeRequest):
    if req.nct_id:
        selected = config.CHALK_TRIAL_SOURCE if req.source == "auto" else req.source
        if selected not in {"auto", "chalk", "ctgov"}:
            raise HTTPException(status_code=422, detail="source must be auto, chalk, or ctgov.")
        trial = _get_trial(req.nct_id, selected)
    elif req.eligibility_text:
        trial = TrialInfo(eligibility_text=req.eligibility_text, data_source="manual")
    else:
        raise HTTPException(status_code=400, detail="Send either nct_id or eligibility_text.")
    if not trial.eligibility_text.strip():
        raise HTTPException(status_code=422, detail="This trial has no eligibility text on ClinicalTrials.gov.")
    rules, warnings, llm_used = parse_eligibility(trial.eligibility_text, use_llm=req.use_llm)
    rules = registry_rules(trial) + rules
    sim = simulate_population(rules, req.population)
    return AnalyzeResponse(trial=trial, rules=rules, simulation=sim, llm_used=llm_used,
                           warnings=warnings + sim.warnings + trial_population_warnings(trial, req.population.mode))


@app.post("/api/simulate", response_model=SimulationResult, dependencies=[Depends(heavy_request)])
def simulate_rules(req: SimulateRequest):
    return simulate_population(req.rules, req.population)


@app.post("/api/compare", response_model=CompareResult, dependencies=[Depends(heavy_request)])
def compare_rules(req: CompareRequest):
    return compare_population(req.baseline_rules, req.proposed_rules, req.population)


@app.post("/api/autopilot", response_model=AutopilotResponse, dependencies=[Depends(heavy_request)])
def suggest_autopilot(req: AutopilotRequest):
    return run_autopilot(req)


@app.post('/api/responder-evidence', response_model=ResponderResponse, dependencies=[Depends(heavy_request)])
def get_responder_evidence(req: ResponderRequest):
    return responder_evidence(req.trial_key)


@app.post("/api/scenario-review", response_model=ScenarioReviewResponse, dependencies=[Depends(heavy_request)])
def scenario_review(req: ScenarioReviewRequest):
    return review_scenario(req.baseline_rules, req.proposed_rules, req.population, req.source)


@app.post("/api/rare-reach", response_model=RareReachResponse, dependencies=[Depends(heavy_request)])
def rare_reach(req: RareReachRequest):
    """Research public recruitment channels without accessing patient data."""
    try:
        return build_rare_reach(req.nct_id, req.rules)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TrialNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (RareReachError, httpx.HTTPError) as exc:
        log.warning("RareReach request failed: %s", exc)
        raise HTTPException(status_code=502, detail="RareReach could not retrieve public source data; try again.")


# A built frontend can be served on the same origin as the API in production.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def frontend():
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"status": "backend ready", "frontend": "Run npm ci and npm run build in frontend/ or use the Vite development server.", "docs": "/docs"}
