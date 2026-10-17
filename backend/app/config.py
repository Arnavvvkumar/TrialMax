"""Settings loaded from the repo-root .env (never committed)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

CHALK_ROUTER_API_KEY = os.getenv("CHALK_ROUTER_API_KEY", "")
CHALK_ENV_ID = os.getenv("CHALK_ENV_ID", "")
CHALK_BASE_URL = os.getenv("CHALK_BASE_URL", "https://api.chalk.ai/v1/router")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "90"))
LLM_MAX_WORKERS = int(os.getenv("LLM_MAX_WORKERS", "6"))
CACHE_DIR = Path(os.getenv("WT_CACHE_DIR", str(BACKEND_DIR / ".cache")))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]


def llm_configured() -> bool:
    return bool(CHALK_ROUTER_API_KEY and CHALK_ENV_ID and LLM_MODEL)
