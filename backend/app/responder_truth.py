"""Deterministic ground truth for the efficacy-subgroup evaluation.

Every number here is computed from the committed trial CSVs in dataset/rct/data/ (no LLM,
no network). For each trial and each prespecified subgroup S we fit Cox models of the
treatment effect overall, within S, within not-S, and with a treated*S interaction, then
apply Benjamini-Hochberg across the trial's interaction p-values and label each subgroup.

Planted variants nullify the treatment effect inside one subgroup (treated patients'
outcomes are replaced by bootstrap draws from that subgroup's controls), so the expected
truth is known by construction.

Regenerate:  cd backend && python -m app.responder_truth
"""
from __future__ import annotations

import json
import math
import warnings
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

METHOD_VERSION = "responder-truth-v1"
DEFAULT_SEED = 20261018
BH_Q = 0.10
MIN_EVENTS_PER_ARM = 20
N_PLANTED = 3
GBSG_NOTE = "Partly non-randomized treatment assignment: weaker evidence"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "dataset" / "rct" / "data"
OUTPUT_PATH = REPO_ROOT / "dataset" / "rct" / "ground_truth.jsonl"


class NotEstimable(Exception):
    """A model that cannot be fit honestly (empty arm, no events, non-convergence)."""


@dataclass(frozen=True)
class Subgroup:
    id: str
    label: str
    rule: Callable[[pd.DataFrame], pd.Series]  # raw frame -> boolean Series (NaN when unknown)


@dataclass
class Trial:
    name: str
    treatment: str
    endpoint: str
    evidence_note: str | None
    # Columns: time, event, treated (0/1), plus one float column per subgroup id (1/0/NaN).
    frame: pd.DataFrame
    subgroups: list[Subgroup] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading


def _read(path: Path, required: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Rdatasets prepends a row-index column ("rownames" or an unnamed one); drop it if present.
    df = df.drop(columns=[c for c in df.columns if c == "rownames" or str(c).startswith("Unnamed")])
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}; got {list(df.columns)}")
    return df


def _flag(cond: pd.Series, *sources: pd.Series) -> pd.Series:
    """Boolean condition as float 1/0, NaN wherever any source value is missing."""
    out = cond.astype(float)
    for s in sources:
        out[s.isna()] = np.nan
    return out


def _build(name, treatment, endpoint, note, raw, time, event, treated, subgroups) -> Trial:
    frame = pd.DataFrame({
        "time": raw[time].astype(float).to_numpy(),
        "event": raw[event].astype(int).to_numpy(),
        "treated": treated.astype(int).to_numpy(),
    })
    for sg in subgroups:
        frame[sg.id] = sg.rule(raw).to_numpy(dtype=float)
    return Trial(name, treatment, endpoint, note, frame, list(subgroups))


def load_colon(data_dir: Path = DATA_DIR) -> Trial:
    raw = _read(data_dir / "colon.csv", ["id", "rx", "etype", "time", "status", "age", "sex", "node4",
                                         "obstruct", "perfor", "adhere", "differ", "extent"])
    raw = raw[(raw["etype"] == 2) & raw["rx"].isin(["Lev+5FU", "Obs"])].reset_index(drop=True)
    if raw["id"].duplicated().any():
        raise ValueError("colon: expected one death record per patient")
    subgroups = [
        Subgroup("age_ge_60", "Age >= 60", lambda d: _flag(d["age"] >= 60, d["age"])),
        Subgroup("male", "Male", lambda d: _flag(d["sex"] == 1, d["sex"])),
        Subgroup("nodes_gt_4", "More than 4 positive nodes", lambda d: _flag(d["node4"] == 1, d["node4"])),
        Subgroup("obstruct", "Colon obstruction", lambda d: _flag(d["obstruct"] == 1, d["obstruct"])),
        Subgroup("perfor", "Colon perforation", lambda d: _flag(d["perfor"] == 1, d["perfor"])),
        Subgroup("adhere", "Adherence to nearby organs", lambda d: _flag(d["adhere"] == 1, d["adhere"])),
        Subgroup("poor_differ", "Poor differentiation", lambda d: _flag(d["differ"] == 3, d["differ"])),
        Subgroup("extent_ge_3", "Extent: serosa or contiguous", lambda d: _flag(d["extent"] >= 3, d["extent"])),
    ]
    return _build("colon", "Lev+5FU vs observation", "overall survival", None, raw,
                  "time", "status", raw["rx"] == "Lev+5FU", subgroups)


def load_veteran(data_dir: Path = DATA_DIR) -> Trial:
    raw = _read(data_dir / "veteran.csv", ["trt", "celltype", "time", "status", "karno", "age", "prior"])
    raw = raw[raw["trt"].isin([1, 2])].reset_index(drop=True)
    cell = lambda kind: (lambda d: _flag(d["celltype"] == kind, d["celltype"]))  # noqa: E731
    subgroups = [
        Subgroup("cell_squamous", "Squamous cell", cell("squamous")),
        Subgroup("cell_smallcell", "Small cell", cell("smallcell")),
        Subgroup("cell_adeno", "Adenocarcinoma", cell("adeno")),
        Subgroup("cell_large", "Large cell", cell("large")),
        Subgroup("karno_ge_60", "Karnofsky >= 60", lambda d: _flag(d["karno"] >= 60, d["karno"])),
        Subgroup("prior_therapy", "Prior therapy", lambda d: _flag(d["prior"] > 0, d["prior"])),
        Subgroup("age_ge_60", "Age >= 60", lambda d: _flag(d["age"] >= 60, d["age"])),
    ]
    return _build("veteran", "test chemotherapy vs standard chemotherapy", "overall survival", None, raw,
                  "time", "status", raw["trt"] == 2, subgroups)


def load_gbsg(data_dir: Path = DATA_DIR) -> Trial:
    raw = _read(data_dir / "gbsg.csv", ["age", "meno", "size", "grade", "nodes", "pgr", "er", "hormon",
                                        "rfstime", "status"])
    raw = raw[raw["hormon"].isin([0, 1])].reset_index(drop=True)
    subgroups = [
        Subgroup("age_ge_50", "Age >= 50", lambda d: _flag(d["age"] >= 50, d["age"])),
        Subgroup("postmenopausal", "Postmenopausal", lambda d: _flag(d["meno"] == 1, d["meno"])),
        Subgroup("grade_3", "Tumor grade 3", lambda d: _flag(d["grade"] == 3, d["grade"])),
        Subgroup("nodes_gt_3", "More than 3 positive nodes", lambda d: _flag(d["nodes"] > 3, d["nodes"])),
        Subgroup("pgr_ge_10", "Progesterone receptor >= 10 fmol", lambda d: _flag(d["pgr"] >= 10, d["pgr"])),
        Subgroup("er_ge_10", "Estrogen receptor >= 10 fmol", lambda d: _flag(d["er"] >= 10, d["er"])),
        Subgroup("size_gt_20", "Tumor size > 20 mm", lambda d: _flag(d["size"] > 20, d["size"])),
    ]
    return _build("gbsg", "hormonal therapy vs none", "recurrence-free survival", GBSG_NOTE, raw,
                  "rfstime", "status", raw["hormon"] == 1, subgroups)


LOADERS = {"colon": load_colon, "veteran": load_veteran, "gbsg": load_gbsg}


# ---------------------------------------------------------------------------
# Statistics


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    v = round(float(x), 4)
    return 0.0 if v == 0 else v  # no "-0.0" in the output


def _check_arms(df: pd.DataFrame, where: str) -> None:
    for arm, name in ((1, "treated"), (0, "control")):
        sub = df[df["treated"] == arm]
        if len(sub) == 0:
            raise NotEstimable(f"empty {name} arm {where}")
        if sub["event"].sum() == 0:
            raise NotEstimable(f"no events in {name} arm {where}")


def cox(df: pd.DataFrame, covariates: list[str], term: str) -> dict:
    """Fit a Cox PH model (Efron ties) and return HR, 95% CI and Wald p for `term`."""
    from lifelines import CoxPHFitter
    from lifelines.exceptions import ConvergenceError, ConvergenceWarning

    data = df[["time", "event", *covariates]]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            fit = CoxPHFitter().fit(data, duration_col="time", event_col="event")
    except (ConvergenceError, ConvergenceWarning, np.linalg.LinAlgError, ValueError, ZeroDivisionError) as exc:
        raise NotEstimable(f"Cox model for {term} did not converge: {str(exc).splitlines()[0][:160]}") from exc
    row = fit.summary.loc[term]
    coef, se, p = float(row["coef"]), float(row["se(coef)"]), float(row["p"])
    if not all(math.isfinite(v) for v in (coef, se, p)) or abs(coef) > 20 or se > 50:
        raise NotEstimable(f"Cox model for {term} gave a non-finite or degenerate estimate")
    return {"hr": math.exp(coef), "ci": [math.exp(coef - 1.959964 * se), math.exp(coef + 1.959964 * se)], "p": p}


def bh_qvalues(pvalues: list[float | None]) -> list[float | None]:
    """Benjamini-Hochberg adjusted p-values (q-values); None entries are skipped and stay None."""
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    m = len(idx)
    out: list[float | None] = [None] * len(pvalues)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: (pvalues[i], i))
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        out[i] = min(running, 1.0)
    return out


def _counts(df: pd.DataFrame, col: str) -> tuple[dict, dict]:
    known = df[df[col].notna()]
    n, ev = {}, {}
    for side, val in (("in", 1.0), ("out", 0.0)):
        for arm, name in ((1, "treated"), (0, "control")):
            part = known[(known[col] == val) & (known["treated"] == arm)]
            n[f"{name}_{side}"] = int(len(part))
            ev[f"{name}_{side}"] = int(part["event"].sum())
    return n, ev


def analyze_subgroup(df: pd.DataFrame, sg: Subgroup) -> dict:
    n, ev = _counts(df, sg.id)
    known = df[df[sg.id].notna()].copy()
    result = {
        "id": sg.id, "label": sg.label, "n": n, "events": ev,
        "hr_in": None, "ci_in": None, "hr_out": None, "ci_out": None,
        "interaction_hr": None, "interaction_ci": None, "interaction_p": None,
        "q_value": None, "status": "ok", "reason": None,
        "underpowered": min(ev["treated_in"], ev["control_in"]) < MIN_EVENTS_PER_ARM,
    }
    reasons = []
    for side, val in (("in", 1.0), ("out", 0.0)):
        part = known[known[sg.id] == val]
        try:
            _check_arms(part, f"{'in' if side == 'in' else 'outside'} {sg.id}")
            fit = cox(part, ["treated"], "treated")
            result[f"hr_{side}"], result[f"ci_{side}"] = fit["hr"], fit["ci"]
        except NotEstimable as exc:
            reasons.append(str(exc))
    if not reasons:
        known["S"] = known[sg.id]
        known["treated_x_S"] = known["treated"] * known["S"]
        try:
            fit = cox(known, ["treated", "S", "treated_x_S"], "treated_x_S")
            result["interaction_hr"], result["interaction_ci"], result["interaction_p"] = fit["hr"], fit["ci"], fit["p"]
        except NotEstimable as exc:
            reasons.append(str(exc))
    if reasons:
        result["status"], result["reason"] = "not_estimable", "; ".join(reasons)
        result["interaction_hr"] = result["interaction_ci"] = result["interaction_p"] = None
    elif result["underpowered"]:
        low = min(("treated_in", "control_in"), key=lambda k: ev[k])
        result["reason"] = f"underpowered: {ev[low]} events in {low.replace('_in', '')} arm within subgroup (< {MIN_EVENTS_PER_ARM})"
    return result


def _label(sg: dict) -> str:
    if sg["status"] != "ok" or sg["underpowered"] or sg["q_value"] is None or sg["q_value"] > BH_Q:
        return "no_reliable_difference"
    return "weaker_benefit" if sg["hr_in"] > sg["hr_out"] else "stronger_benefit"


def analyze_trial(trial: Trial) -> tuple[dict, list[dict]]:
    """Overall effect plus the labeled subgroup table, with unrounded floats."""
    df = trial.frame
    _check_arms(df, "overall")
    overall = cox(df, ["treated"], "treated")
    overall.update(n=int(len(df)), events=int(df["event"].sum()))
    subs = [analyze_subgroup(df, sg) for sg in trial.subgroups]
    for sg, q in zip(subs, bh_qvalues([s["interaction_p"] for s in subs])):
        sg["q_value"] = q
        sg["truth"] = _label(sg)
    return overall, subs


# ---------------------------------------------------------------------------
# Planted variants


def plant_null(trial: Trial, subgroup_id: str, seed: int = DEFAULT_SEED) -> Trial:
    """Nullify the treatment effect in one subgroup: each treated patient in S gets a
    (time, event) pair drawn with replacement from the control patients in S."""
    df = trial.frame.copy()
    in_s = df[subgroup_id] == 1.0
    treated_idx = df.index[in_s & (df["treated"] == 1)]
    control_idx = df.index[in_s & (df["treated"] == 0)]
    if len(control_idx) == 0 or len(treated_idx) == 0:
        raise NotEstimable(f"cannot plant in {subgroup_id}: an arm is empty")
    rng = np.random.default_rng([seed, zlib.crc32(f"{trial.name}:{subgroup_id}".encode())])
    draws = control_idx[rng.integers(0, len(control_idx), size=len(treated_idx))]
    df.loc[treated_idx, ["time", "event"]] = df.loc[draws, ["time", "event"]].to_numpy()
    df["event"] = df["event"].astype(int)
    return replace(trial, frame=df)


def planted_targets(subs: list[dict], k: int = N_PLANTED) -> list[str]:
    """The k largest (by n in S) estimable, non-underpowered subgroups, in table order on ties."""
    eligible = [(i, s) for i, s in enumerate(subs) if s["status"] == "ok" and not s["underpowered"]]
    eligible.sort(key=lambda t: (-(t[1]["n"]["treated_in"] + t[1]["n"]["control_in"]), t[0]))
    return [s["id"] for _, s in eligible[:k]]


# ---------------------------------------------------------------------------
# Output


def _round_sub(sg: dict) -> dict:
    out = dict(sg)
    for key in ("hr_in", "hr_out", "interaction_hr", "interaction_p", "q_value"):
        out[key] = _r(sg[key])
    for key in ("ci_in", "ci_out", "interaction_ci"):
        out[key] = None if sg[key] is None else [_r(v) for v in sg[key]]
    return out


def build_case(trial: Trial, variant: str, seed: int, planted: str | None = None) -> tuple[dict, list[dict]]:
    overall, subs = analyze_trial(trial)
    if planted is not None:
        target = next(s for s in subs if s["id"] == planted)
        truth_flag, truth_direction = planted, "weaker_benefit"
        planted_detectable = target["truth"] == "weaker_benefit"
    else:
        weaker = [s for s in subs if s["truth"] == "weaker_benefit"]
        best = min(weaker, key=lambda s: s["q_value"]) if weaker else None
        truth_flag = best["id"] if best else None
        truth_direction = "weaker_benefit" if best else None
        planted_detectable = None
    case = {
        "case_id": f"{trial.name}:{variant}",
        "trial": trial.name,
        "variant": variant,
        "treatment": trial.treatment,
        "endpoint": trial.endpoint,
        "evidence_note": trial.evidence_note,
        "overall": {"hr": _r(overall["hr"]), "ci": [_r(v) for v in overall["ci"]], "p": _r(overall["p"]),
                    "n": overall["n"], "events": overall["events"]},
        "subgroups": [_round_sub(s) for s in subs],
        "truth_flag": truth_flag,
        "truth_direction": truth_direction,
        "any_significant": any(s["truth"] != "no_reliable_difference" for s in subs),
        "planted_detectable": planted_detectable,
        "seed": seed,
        "method_version": METHOD_VERSION,
    }
    return case, subs


def build_trial_cases(trial: Trial, seed: int = DEFAULT_SEED) -> list[dict]:
    original, subs = build_case(trial, "original", seed)
    cases = [original]
    for sid in planted_targets(subs):
        cases.append(build_case(plant_null(trial, sid, seed), f"planted:{sid}", seed, planted=sid)[0])
    return cases


def spot_check_colon(data_dir: Path = DATA_DIR) -> dict:
    trial = load_colon(data_dir)
    overall = cox(trial.frame, ["treated"], "treated")
    if not (overall["hr"] < 1 and overall["ci"][1] < 1):
        raise RuntimeError(f"colon spot-check failed: Lev+5FU vs Obs HR {overall['hr']:.3f} CI {overall['ci']} "
                           "does not show clear benefit (Moertel et al., NEJM 1990)")
    return overall


def build_all(data_dir: Path = DATA_DIR, seed: int = DEFAULT_SEED) -> list[dict]:
    cases = []
    for name in ("colon", "veteran", "gbsg"):
        cases.extend(build_trial_cases(LOADERS[name](data_dir), seed))
    return cases


def dumps_jsonl(cases: list[dict]) -> str:
    return "".join(json.dumps(c, sort_keys=True, separators=(",", ":")) + "\n" for c in cases)


def main(seed: int = DEFAULT_SEED, out: Path = OUTPUT_PATH) -> list[dict]:
    sc = spot_check_colon()
    print(f"Spot-check colon Lev+5FU vs Obs (death): HR {sc['hr']:.3f} "
          f"(95% CI {sc['ci'][0]:.3f}-{sc['ci'][1]:.3f}), p={sc['p']:.2g}")
    cases = build_all(seed=seed)
    out.write_text(dumps_jsonl(cases))
    print(f"Wrote {len(cases)} cases to {out}")
    print(f"{'case_id':<38} {'truth_flag':<16} {'any_significant':<16} planted_detectable")
    for c in cases:
        print(f"{c['case_id']:<38} {str(c['truth_flag']):<16} {str(c['any_significant']):<16} {c['planted_detectable']}")
    return cases


if __name__ == "__main__":
    main()
