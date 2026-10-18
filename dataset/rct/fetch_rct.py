"""Download the randomized-trial CSVs used for the responder-truth evaluation.

Source: the Rdatasets mirror of R's `survival` package (Therneau). Saves each CSV to
dataset/rct/data/ and writes data/provenance.json (URL, download time, sha256, row count,
citation). Run once; the committed snapshot keeps the evaluation offline.

    python dataset/rct/fetch_rct.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent / "data"
BASE = "https://vincentarelbundock.github.io/Rdatasets/csv/survival"
SURVIVAL_CREDIT = "Therneau T (2024). survival: A Package for Survival Analysis in R. Data via Rdatasets (Arel-Bundock)."

DATASETS = {
    "colon": "Moertel CG et al. Levamisole and fluorouracil for adjuvant therapy of resected colon carcinoma. "
             "N Engl J Med 1990;322:352-358. Moertel CG et al. Ann Intern Med 1995;122:321-326.",
    "veteran": "Kalbfleisch JD, Prentice RL. The Statistical Analysis of Failure Time Data. Wiley, 1980 "
               "(Veterans' Administration Lung Cancer Trial).",
    "gbsg": "Schumacher M et al. Randomized 2x2 trial evaluating hormonal treatment and the duration of "
            "chemotherapy in node-positive breast cancer patients. J Clin Oncol 1994;12:2086-2093 "
            "(German Breast Cancer Study Group; hormon was not fully randomized).",
}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    provenance = {}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for name, citation in DATASETS.items():
            url = f"{BASE}/{name}.csv"
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.content
            rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))
            header, records = rows[0], rows[1:]
            (DATA_DIR / f"{name}.csv").write_bytes(body)
            provenance[name] = {
                "url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sha256": hashlib.sha256(body).hexdigest(),
                "rows": len(records),
                "columns": header,
                "citation": citation,
                "credit": SURVIVAL_CREDIT,
            }
            print(f"{name}: {len(records)} rows, columns={header}")
    (DATA_DIR / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
