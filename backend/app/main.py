"""Wind Tunnel API. Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import deque

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .ctgov import TrialNotFound, fetch_trial
from .fixed_patients import simulate_fixed
from .models import (
    AnalyzeRequest, AnalyzeResponse, CompareRequest, CompareResult, SimulateRequest,
    SimulationResult, TrialInfo,
)
from .pipeline import parse_eligibility
from .registry import registry_rules
from .simulate import compare, coverage_warnings, simulate
from .variables import VARIABLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("windtunnel.api")

app = FastAPI(title="Wind Tunnel API", version="0.2.0")


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

def _get_trial(nct_id: str) -> TrialInfo:
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
    return {"status": "ok", "llm_configured": config.llm_configured(), "model": config.LLM_MODEL or None}


@app.get("/api/variables")
def variables():
    return VARIABLES


@app.get("/api/trials/{nct_id}", response_model=TrialInfo)
def get_trial(nct_id: str):
    return _get_trial(nct_id)


@app.post("/api/analyze", response_model=AnalyzeResponse, dependencies=[Depends(heavy_request)])
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
    rules = registry_rules(trial) + rules
    sim = simulate(rules, req.population_size, req.seed)
    return AnalyzeResponse(trial=trial, rules=rules, simulation=sim, llm_used=llm_used,
                           warnings=warnings + coverage_warnings(sim))


@app.post("/api/simulate", response_model=SimulationResult, dependencies=[Depends(heavy_request)])
def simulate_rules(req: SimulateRequest):
    return simulate_fixed(req.rules)


@app.post("/api/compare", response_model=CompareResult, dependencies=[Depends(heavy_request)])
def compare_rules(req: CompareRequest):
    return compare(req.baseline_rules, req.proposed_rules, req.population_size, req.seed)
