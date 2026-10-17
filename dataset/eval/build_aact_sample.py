"""Build the AACT evaluation sample for the eligibility parser (step 2 of the evaluation plan).

Pulls interventional Phase 2/3 cancer trials from AACT (CTTI's copy of ClinicalTrials.gov), splits their
eligibility text into single criteria with our own splitter, and draws a fixed, stratified sample.

Writes:
  dataset/eval/aact_sample.jsonl     one criterion per line, with provenance and the parser's draft answer
  dataset/eval/aact_labels.csv       the sheet the team fills in (gold answers, checked by a person)

Usage (from the repo root, AACT_USER / AACT_PASS in .env):
  python dataset/eval/build_aact_sample.py [--size 120]

The draft answers come from our parser and exist only to save typing. They are NOT the answer key:
every row must be confirmed or corrected by a person, otherwise we would be grading the parser
against itself.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.criteria import parse_criterion, split_criteria  # noqa: E402

OUT = Path(__file__).resolve().parent
CONDITIONS = ["%non-small cell lung%", "%renal cell%", "%melanoma%", "%breast cancer%", "%colorectal%"]
# Target mix so the set exercises every kind of criterion, including ones that must be refused.
STRATA = {"lab": 25, "age": 12, "ecog": 13, "condition": 25, "prior_therapy": 10, "refuse": 35}

QUERY = """
SELECT s.nct_id, s.brief_title, s.phase, e.criteria
FROM studies s
JOIN eligibilities e ON e.nct_id = s.nct_id
WHERE lower(s.study_type) = 'interventional'
  AND replace(lower(coalesce(s.phase, '')), ' ', '') IN ('phase2', 'phase3', 'phase2/phase3')
  AND s.start_date >= '2015-01-01'
  AND EXISTS (SELECT 1 FROM conditions c WHERE c.nct_id = s.nct_id AND c.downcase_name LIKE ANY (%s))
  AND length(e.criteria) BETWEEN 200 AND 12000
ORDER BY md5(s.nct_id)
LIMIT %s
"""


def stratum(rules) -> str:
    modeled = [r for r in rules if r.simulatable]
    if not modeled:
        return "refuse"
    cats = {r.category for r in modeled}
    for name in ("lab", "age", "performance_status", "prior_therapy", "condition", "pregnancy"):
        if name in cats:
            return {"performance_status": "ecog", "pregnancy": "condition"}.get(name, name)
    return "condition"


def draft_of(rules) -> list[dict]:
    return [{"variable": r.variable, "operator": r.operator, "value": r.value, "value_max": r.value_max,
             "unit": r.unit, "fidelity": r.fidelity} for r in rules if r.simulatable]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=400, help="trials to pull from AACT")
    ap.add_argument("--size", type=int, default=sum(STRATA.values()))
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(host="aact-db.ctti-clinicaltrials.org", port=5432, dbname="aact",
                            user=os.environ["AACT_USER"], password=os.environ["AACT_PASS"], connect_timeout=20)
    with conn, conn.cursor() as cur:
        cur.execute(QUERY, (CONDITIONS, args.trials))
        trials = cur.fetchall()
    conn.close()
    print(f"pulled {len(trials)} trials from AACT")

    pool: dict[str, list[dict]] = {k: [] for k in STRATA}
    for nct_id, title, phase, criteria in trials:
        for idx, item in enumerate(split_criteria(criteria or "")):
            text = " ".join(item.text.split())
            if item.uncertain or not 15 <= len(text) <= 400:
                continue
            rules = parse_criterion("X1", item.kind, text)
            row = {"id": f"{nct_id}-{item.kind[0].upper()}{idx + 1}", "nct_id": nct_id, "phase": phase,
                   "trial_title": title, "kind": item.kind, "text": text, "stratum": stratum(rules),
                   "parser_draft": draft_of(rules)}
            row["_order"] = hashlib.sha256(row["id"].encode()).hexdigest()
            pool[row["stratum"]].append(row)

    sample, per_trial = [], {}
    for name, target in STRATA.items():
        for row in sorted(pool[name], key=lambda r: r["_order"]):
            if sum(1 for r in sample if r["stratum"] == name) >= target:
                break
            if per_trial.get(row["nct_id"], 0) >= 2:      # spread across trials
                continue
            per_trial[row["nct_id"]] = per_trial.get(row["nct_id"], 0) + 1
            sample.append(row)
    sample = sorted(sample, key=lambda r: r["_order"])[: args.size]
    for row in sample:
        row.pop("_order")

    meta = {"source": "AACT (aact-db.ctti-clinicaltrials.org)", "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trials_pulled": len(trials), "conditions": CONDITIONS, "strata_target": STRATA,
            "strata_actual": {k: sum(1 for r in sample if r["stratum"] == k) for k in STRATA}}
    with open(OUT / "aact_sample.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": meta}) + "\n")
        for row in sample:
            fh.write(json.dumps(row) + "\n")

    with open(OUT / "aact_labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "nct_id", "kind", "text", "parser_draft", "gold_decision (model/refuse)", "gold_variable",
                    "gold_operator", "gold_value", "gold_value_max", "gold_unit", "labeler", "disagree? (y)", "comment"])
        for row in sample:
            d = row["parser_draft"]
            summary = "; ".join(f"{x['variable']} {x['operator']} {x['value'] if x['value'] is not None else ''}"
                                f"{'-' + str(x['value_max']) if x['value_max'] is not None else ''} {x['unit'] or ''}".strip()
                                for x in d) or "REFUSE"
            w.writerow([row["id"], row["nct_id"], row["kind"], row["text"], summary, "", "", "", "", "", "", "", "", ""])
    print("strata:", meta["strata_actual"])
    print(f"wrote {OUT / 'aact_sample.jsonl'} and {OUT / 'aact_labels.csv'} ({len(sample)} criteria)")


if __name__ == "__main__":
    main()
