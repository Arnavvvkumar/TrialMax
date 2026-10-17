"""Settings loaded from the repo-root .env (never committed)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# Chalk Model Gateway
CHALK_ROUTER_API_KEY = os.getenv("CHALK_ROUTER_API_KEY", "")
CHALK_ENV_ID = os.getenv("CHALK_ENV_ID", "")
CHALK_BASE_URL = os.getenv("CHALK_BASE_URL", "https://api.chalk.ai/v1/router")
LLM_MODEL = os.getenv("LLM_MODEL", "")
CHALK_FEATURE_BRANCH = os.getenv("CHALK_FEATURE_BRANCH", "")
CHALK_TRIAL_SOURCE = os.getenv("CHALK_TRIAL_SOURCE", "auto").strip().lower()
CHALK_SQL_ENV_ID = os.getenv("CHALK_SQL_ENV_ID", CHALK_ENV_ID)
CHALK_SQL_TIMEOUT_S = _float("CHALK_SQL_TIMEOUT_S", 20)
RARE_REACH_TIMEOUT_S = _float("RARE_REACH_TIMEOUT_S", 15)
RARE_REACH_MAX_STUDIES = _int("RARE_REACH_MAX_STUDIES", 100)
RARE_REACH_MAX_SITES = _int("RARE_REACH_MAX_SITES", 25)
ORPHADATA_API_BASE = os.getenv("ORPHADATA_API_BASE", "https://api.orphadata.com").rstrip("/")

# LLM time and work budget for one analysis
LLM_TIMEOUT_S = _float("LLM_TIMEOUT_S", 30)          # one call
LLM_MAX_RETRIES = _int("LLM_MAX_RETRIES", 1)
LLM_TOTAL_BUDGET_S = _float("LLM_TOTAL_BUDGET_S", 60)  # whole fallback step
LLM_MAX_CRITERIA = _int("LLM_MAX_CRITERIA", 40)
LLM_MAX_WORKERS = _int("LLM_MAX_WORKERS", 6)
LLM_MAX_OUTPUT_TOKENS = _int("LLM_MAX_OUTPUT_TOKENS", 1024)
if not 1 <= LLM_MAX_OUTPUT_TOKENS <= 4096:
    raise ValueError("LLM_MAX_OUTPUT_TOKENS must be between 1 and 4096.")
CACHE_DIR = Path(os.getenv("WT_CACHE_DIR", str(BACKEND_DIR / ".cache")))

# API protection
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
).split(",") if o.strip()]
API_TOKEN = os.getenv("WT_API_TOKEN", "")              # if set, every /api request needs X-WT-Token
MAX_BODY_BYTES = _int("WT_MAX_BODY_BYTES", 1_000_000)
MAX_CONCURRENT_HEAVY = _int("WT_MAX_CONCURRENT", 4)    # analyze/simulate/compare running at once
RATE_LIMIT_PER_MIN = _int("WT_RATE_LIMIT_PER_MIN", 60)  # heavy requests per client IP


def llm_configured() -> bool:
    return bool(CHALK_ROUTER_API_KEY and CHALK_ENV_ID and LLM_MODEL)
