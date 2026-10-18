"""Read trial metadata directly from the existing Chalk SQL dataset.

No Chalk feature definitions are required. The backend reads the already
deployed ``chalk.datasets.\"nsclc-trials\"`` table through the Chalk CLI.
Hosts without the CLI read a bundled export of the same table
(``dataset/chalk/export_nsclc_trials.py``).
"""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from . import config
from .ctgov import normalize_nct_id
from .models import TrialInfo

TABLE = 'chalk.datasets."nsclc-trials"'
COLUMNS = (
    "nct_id, brief_title, criteria, gender, minimum_age, maximum_age, "
    "phase, overall_status, enrollment"
)
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "chalk_nsclc_trials.json.gz"


class ChalkTrialError(RuntimeError):
    """The Chalk SQL request could not be completed."""


class ChalkTrialNotFound(ChalkTrialError):
    """The NCT ID has no usable row in the Chalk trial dataset."""


def _phases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def trial_from_row(nct_id: str, row: dict[str, Any], data_source: str = "chalk") -> TrialInfo:
    criteria = row.get("criteria")
    if not criteria:
        raise ChalkTrialNotFound(f"{nct_id} has no eligibility criteria in the Chalk trial dataset.")
    enrollment = row.get("enrollment")
    return TrialInfo(
        nct_id=str(row.get("nct_id") or nct_id),
        title=row.get("brief_title"),
        phases=_phases(row.get("phase")),
        status=row.get("overall_status"),
        enrollment=int(enrollment) if enrollment is not None else None,
        minimum_age=row.get("minimum_age"),
        maximum_age=row.get("maximum_age"),
        sex=row.get("gender"),
        eligibility_text=str(criteria),
        data_source=data_source,
    )


@lru_cache(maxsize=1)
def _snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ChalkTrialError(f"Chalk dataset snapshot is unavailable: {exc}") from exc


def fetch_snapshot_trial(raw_id: str, path: Path = SNAPSHOT_PATH) -> TrialInfo:
    """Read one trial from the bundled export of the Chalk dataset."""
    nct_id = normalize_nct_id(raw_id)
    row = _snapshot(path).get("trials", {}).get(nct_id)
    if not row:
        raise ChalkTrialNotFound(f"{nct_id} was not found in the Chalk trial dataset snapshot.")
    return trial_from_row(nct_id, row, data_source="chalk-snapshot")


def snapshot_info(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    data = _snapshot(path)
    return {key: data.get(key) for key in ("source", "environment", "exported_at", "row_count")}


def fetch_chalk_trial(
    raw_id: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    environment: str | None = None,
) -> TrialInfo:
    """Fetch one trial with a read-only SQL query against Chalk's dataset."""
    nct_id = normalize_nct_id(raw_id)
    if not shutil.which("chalk"):
        raise ChalkTrialError("Chalk CLI is not installed or not on PATH.")
    target_environment = environment or config.CHALK_SQL_ENV_ID
    if not target_environment:
        raise ChalkTrialError("CHALK_SQL_ENV_ID must identify the Chalk environment containing nsclc-trials.")

    # nct_id is normalized with a strict NCT + digits regex above, so it cannot
    # alter this SQL literal.
    sql = f"SELECT {COLUMNS} FROM {TABLE} WHERE nct_id = '{nct_id}' LIMIT 1"
    command = ["chalk", "sql", sql, "--environment", target_environment, "--json"]
    try:
        completed = runner(command, capture_output=True, text=True, timeout=config.CHALK_SQL_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ChalkTrialError(f"Chalk SQL request failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown Chalk CLI error").strip()
        raise ChalkTrialError(f"Chalk SQL request failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ChalkTrialError("Chalk SQL returned invalid JSON.") from exc
    if payload.get("error"):
        raise ChalkTrialError(f"Chalk SQL request failed: {payload['error']}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ChalkTrialNotFound(f"{nct_id} was not found in the Chalk trial dataset.")
    if not isinstance(rows[0], dict):
        raise ChalkTrialError("Chalk SQL returned an unsupported row format.")
    return trial_from_row(nct_id, rows[0])
