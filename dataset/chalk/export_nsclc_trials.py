"""Export the Chalk SQL dataset chalk.datasets."nsclc-trials" to a bundled snapshot.

The backend queries Chalk live through the Chalk CLI when it is installed. Hosts
without the CLI (e.g. Render) read this snapshot instead, so trials still come
from the Chalk dataset. Re-run after the dataset changes:

    python dataset/chalk/export_nsclc_trials.py --environment hmlsd28bca6e
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TABLE = 'chalk.datasets."nsclc-trials"'
COLUMNS = "nct_id, brief_title, criteria, gender, minimum_age, maximum_age, phase, overall_status, enrollment"
OUT = Path(__file__).resolve().parents[2] / "backend" / "data" / "chalk_nsclc_trials.json.gz"
PAGE = 500


def sql(query: str, environment: str) -> list[dict]:
    done = subprocess.run(["chalk", "sql", query, "--environment", environment, "--json"],
                          capture_output=True, text=True, timeout=180, check=True)
    payload = json.loads(done.stdout)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload.get("rows") or []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    expected = sql(f"SELECT COUNT(*) AS n FROM {TABLE}", args.environment)[0]["n"]
    rows: list[dict] = []
    while len(rows) < expected:
        page = sql(f"SELECT {COLUMNS} FROM {TABLE} ORDER BY nct_id LIMIT {PAGE} OFFSET {len(rows)}", args.environment)
        if not page:
            break
        rows.extend(page)
    if len(rows) != expected:
        raise SystemExit(f"Expected {expected} rows, exported {len(rows)}.")
    trials = {row["nct_id"]: row for row in rows if row.get("nct_id")}
    body = json.dumps(trials, sort_keys=True, ensure_ascii=False)
    snapshot = {
        "source": TABLE,
        "environment": args.environment,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": len(trials),
        "trials_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "trials": trials,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip bytes stable for identical content.
    with gzip.GzipFile(OUT, "wb", mtime=0) as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode())
    print(f"Wrote {len(trials)} trials to {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
