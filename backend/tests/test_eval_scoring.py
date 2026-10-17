"""The AACT evaluation scorer must count unsafe modeling and refusals correctly."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parents[2] / "dataset" / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


def row(rid, kind, text, decision, variable="", operator="", value="", value_max="", unit=""):
    return {"id": rid, "kind": kind, "text": text, "gold_decision (model/refuse)": decision,
            "gold_variable": variable, "gold_operator": operator, "gold_value": value,
            "gold_value_max": value_max, "gold_unit": unit}


def test_scores_exact_matches_refusals_and_unsafe_modeling():
    rows = [
        row("a", "inclusion", "ECOG performance status 0 or 1", "model", "ecog", "<=", "1"),
        row("b", "inclusion", "Hemoglobin >= 9 g/dL", "model", "hemoglobin", ">=", "9", "", "g/dL"),
        row("c", "inclusion", "Histologically confirmed clear cell carcinoma", "refuse"),
        # A person says refuse, but the parser models age: this must count as unsafe.
        row("d", "inclusion", "Age >= 18 years", "refuse"),
        # Gold says model, parser models a different threshold: not exact.
        row("e", "inclusion", "Platelets >= 100 x10^9/L", "model", "platelets", ">=", "75", "", "10^9/L"),
    ]
    report = run_eval.score(rows, with_ai=False)
    assert report["scored"] == 5 and report["gold_refuse_n"] == 2 and report["gold_model_n"] == 3
    assert report["accuracy_pct"] == 60.0            # a, b, c
    assert report["unsafe_model_pct"] == 50.0        # d of {c, d}
    assert report["refusal_recall_pct"] == 50.0
    assert report["coverage_pct"] == 66.7            # a, b of {a, b, e}
    assert {f["id"] for f in report["failures"]} == {"d", "e"}


def test_multi_rule_gold_uses_semicolon_lists():
    rows = [row("m", "inclusion", "ANC >= 1.5 x10^9/L and platelets >= 100 x10^9/L", "model",
                "anc;platelets", ">=;>=", "1.5;100", ";", "10^9/L;10^9/L")]
    assert run_eval.score(rows, with_ai=False)["accuracy_pct"] == 100.0
