"""Score the eligibility parser (and optionally the Chalk AI fallback) against the human-labeled AACT set.

Usage (repo root):
  python dataset/eval/run_eval.py                 # parser only
  python dataset/eval/run_eval.py --with-ai       # parser + Chalk AI fallback (uses the Model Gateway)

Reads dataset/eval/aact_labels.csv. Only rows with a filled "gold_decision" and no "disagree" mark are scored.
Several rules for one criterion are written as ';'-separated lists in the gold_* columns, in the same order.

Metrics
  accuracy        exact match between the modeled rules and the gold answer (refusals included)
  unsafe_model    criteria a person marked "refuse" that the system modeled anyway (should be ~0)
  coverage        of criteria a person marked "model", the share the system modeled correctly
  refusal_recall  of criteria a person marked "refuse", the share the system refused
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
HERE = Path(__file__).resolve().parent


def _num(text):
    text = (text or "").strip()
    return float(text) if text else None


def gold_rules(row: dict) -> list[tuple]:
    cols = ["gold_variable", "gold_operator", "gold_value", "gold_value_max", "gold_unit"]
    parts = [[p.strip() for p in (row.get(c) or "").split(";")] for c in cols]
    n = max(len(p) for p in parts)
    rules = []
    for i in range(n):
        var, op, val, vmax, unit = (p[i] if i < len(p) else "" for p in parts)
        if var:
            rules.append((var, op, _num(val), _num(vmax), unit or None))
    return rules


def same_rule(a: tuple, b: tuple) -> bool:
    def close(x, y):
        return x is None and y is None or (x is not None and y is not None and abs(x - y) <= 1e-6 + 0.01 * abs(y))
    return a[0] == b[0] and a[1] == b[1] and close(a[2], b[2]) and close(a[3], b[3]) and (a[4] or None) == (b[4] or None)


def predicted_rules(kind: str, text: str, with_ai: bool) -> list[tuple]:
    if with_ai:
        from app.pipeline import parse_eligibility
        header = "Inclusion Criteria:" if kind == "inclusion" else "Exclusion Criteria:"
        rules, _, _ = parse_eligibility(f"{header}\n* {text}", use_llm=True)
    else:
        from app.criteria import parse_criterion
        rules = parse_criterion("X1", kind, text)
    return [(r.variable, r.operator, r.value, r.value_max, r.unit) for r in rules if r.simulatable]


def score(rows: list[dict], with_ai: bool) -> dict:
    results = []
    for row in rows:
        gold_refuse = row["gold_decision (model/refuse)"].strip().lower().startswith("r")
        gold = [] if gold_refuse else gold_rules(row)
        pred = predicted_rules(row["kind"], row["text"], with_ai)
        exact = len(pred) == len(gold) and all(any(same_rule(p, g) for p in pred) for g in gold)
        results.append({"id": row["id"], "kind": row["kind"], "text": row["text"], "gold_refuse": gold_refuse,
                        "gold": gold, "predicted": pred, "exact": exact,
                        "unsafe_model": gold_refuse and bool(pred), "refused": not pred})
    refuse = [r for r in results if r["gold_refuse"]]
    model = [r for r in results if not r["gold_refuse"]]
    pct = lambda n, d: round(100 * n / d, 1) if d else None
    return {
        "mode": "parser + Chalk AI" if with_ai else "parser only",
        "scored": len(results),
        "accuracy_pct": pct(sum(r["exact"] for r in results), len(results)),
        "unsafe_model_pct": pct(sum(r["unsafe_model"] for r in refuse), len(refuse)),
        "coverage_pct": pct(sum(r["exact"] for r in model), len(model)),
        "refusal_recall_pct": pct(sum(r["refused"] for r in refuse), len(refuse)),
        "gold_model_n": len(model), "gold_refuse_n": len(refuse),
        "failures": [r for r in results if not r["exact"]],
    }


def load_labeled(path: Path) -> tuple[list[dict], int]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    usable = [r for r in rows if (r.get("gold_decision (model/refuse)") or "").strip()
              and not (r.get("disagree? (y)") or "").strip().lower().startswith("y")]
    return usable, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=HERE / "aact_labels.csv")
    ap.add_argument("--with-ai", action="store_true")
    args = ap.parse_args()
    rows, total = load_labeled(args.labels)
    if not rows:
        sys.exit(f"No labeled rows yet in {args.labels} ({total} rows). Fill gold_decision first.")
    report = score(rows, args.with_ai)
    report["labeled_of_total"] = f"{len(rows)}/{total}"
    report["run_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    name = "results_ai.json" if args.with_ai else "results_parser.json"
    (HERE / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{report['mode']}: {report['scored']} scored ({report['labeled_of_total']} labeled)")
    for k in ("accuracy_pct", "coverage_pct", "refusal_recall_pct", "unsafe_model_pct"):
        print(f"  {k:20} {report[k]}")
    print(f"  failures: {len(report['failures'])} (details in {HERE / name})")


if __name__ == "__main__":
    main()
