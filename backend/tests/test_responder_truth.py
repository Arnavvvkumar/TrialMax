import json

import numpy as np
import pandas as pd
import pytest

from app import responder_truth as rt


def synthetic_trial(hr_in: float, hr_out: float, n: int = 800, seed: int = 7) -> rt.Trial:
    rng = np.random.default_rng(seed)
    raw = pd.DataFrame({
        "treated": rng.integers(0, 2, n),
        "s": rng.integers(0, 2, n),
        "noise": rng.integers(0, 2, n),
    })
    hr = np.where(raw["treated"] == 1, np.where(raw["s"] == 1, hr_in, hr_out), 1.0)
    event_time = rng.exponential(1.0 / (0.1 * hr))
    censor = rng.uniform(0, 30, n)
    raw["time"] = np.minimum(event_time, censor)
    raw["event"] = (event_time <= censor).astype(int)
    subgroups = [
        rt.Subgroup("s", "S", lambda d: rt._flag(d["s"] == 1, d["s"])),
        rt.Subgroup("noise", "Noise", lambda d: rt._flag(d["noise"] == 1, d["noise"])),
    ]
    return rt._build("synthetic", "drug vs placebo", "overall survival", None, raw,
                     "time", "event", raw["treated"] == 1, subgroups)


def by_id(subs):
    return {s["id"]: s for s in subs}


def test_strong_interaction_is_weaker_benefit():
    _, subs = rt.analyze_trial(synthetic_trial(hr_in=1.0, hr_out=0.35))
    s = by_id(subs)["s"]
    assert s["status"] == "ok" and not s["underpowered"]
    assert s["interaction_p"] < 0.01
    assert s["hr_in"] > s["hr_out"]
    assert s["truth"] == "weaker_benefit"
    assert by_id(subs)["noise"]["truth"] == "no_reliable_difference"


def test_no_interaction_is_no_reliable_difference():
    _, subs = rt.analyze_trial(synthetic_trial(hr_in=0.6, hr_out=0.6))
    assert all(s["truth"] == "no_reliable_difference" for s in subs)


def test_bh_qvalues_match_hand_computation():
    # m=5, sorted p: .01 .02 .03 .04 .5 -> p*m/rank = .05 .05 .05 .05 .5, then cumulative min from the top.
    q = rt.bh_qvalues([0.04, 0.01, 0.5, 0.03, 0.02])
    assert q == pytest.approx([0.05, 0.05, 0.5, 0.05, 0.05])
    q = rt.bh_qvalues([0.001, 0.2, None, 0.04])
    assert q[2] is None
    assert q[0] == pytest.approx(0.003) and q[3] == pytest.approx(0.06) and q[1] == pytest.approx(0.2)
    assert rt.bh_qvalues([0.9, 0.95]) == pytest.approx([0.95, 0.95])


def test_colon_one_row_per_patient_two_arms_and_benefit():
    raw = pd.read_csv(rt.DATA_DIR / "colon.csv")
    trial = rt.load_colon()
    expected = raw[(raw["etype"] == 2) & raw["rx"].isin(["Lev+5FU", "Obs"])]
    assert len(trial.frame) == len(expected) == expected["id"].nunique()
    assert set(trial.frame["treated"]) == {0, 1}
    overall = rt.spot_check_colon()
    assert overall["hr"] < 1 and overall["ci"][1] < 1


@pytest.fixture(scope="module")
def colon_cases():
    return rt.build_trial_cases(rt.load_colon(), seed=rt.DEFAULT_SEED)


def test_planted_variants_are_deterministic_and_flag_planted_subgroup(colon_cases):
    again = rt.build_trial_cases(rt.load_colon(), seed=rt.DEFAULT_SEED)
    assert rt.dumps_jsonl(colon_cases) == rt.dumps_jsonl(again)
    planted = [c for c in colon_cases if c["variant"].startswith("planted:")]
    assert len(planted) == rt.N_PLANTED
    for case in planted:
        sid = case["variant"].split(":", 1)[1]
        assert case["case_id"] == f"colon:planted:{sid}"
        assert case["truth_flag"] == sid and case["truth_direction"] == "weaker_benefit"
        target = by_id(case["subgroups"])[sid]
        assert case["planted_detectable"] == (target["truth"] == "weaker_benefit")
    # Different seed, different bootstrap draws.
    other = rt.build_trial_cases(rt.load_colon(), seed=1)
    assert rt.dumps_jsonl(other) != rt.dumps_jsonl(colon_cases)


def test_plant_null_only_touches_treated_in_subgroup():
    trial = rt.load_colon()
    planted = rt.plant_null(trial, "male", seed=rt.DEFAULT_SEED)
    touched = (trial.frame["male"] == 1) & (trial.frame["treated"] == 1)
    pd.testing.assert_frame_equal(planted.frame[~touched], trial.frame[~touched])
    controls = trial.frame[(trial.frame["male"] == 1) & (trial.frame["treated"] == 0)]
    pool = set(zip(controls["time"], controls["event"]))
    assert set(zip(planted.frame.loc[touched, "time"], planted.frame.loc[touched, "event"])) <= pool


def test_underpowered_subgroup_is_no_reliable_difference_with_reason():
    trial = synthetic_trial(hr_in=1.0, hr_out=0.35)
    trial.frame["tiny"] = 0.0
    trial.frame.loc[trial.frame.index[:40], "tiny"] = 1.0
    trial.subgroups.append(rt.Subgroup("tiny", "Tiny", lambda d: d))
    sub = by_id(rt.analyze_trial(trial)[1])["tiny"]
    assert sub["underpowered"] and sub["truth"] == "no_reliable_difference"
    assert "underpowered" in sub["reason"]


def test_not_estimable_subgroup_is_no_reliable_difference_with_reason():
    trial = synthetic_trial(hr_in=1.0, hr_out=0.35)
    # Subgroup containing only control patients: the treated arm in S is empty.
    trial.frame["controls_only"] = np.where(trial.frame["treated"] == 0, 1.0, 0.0)
    trial.subgroups.append(rt.Subgroup("controls_only", "Controls only", lambda d: d))
    sub = by_id(rt.analyze_trial(trial)[1])["controls_only"]
    assert sub["status"] == "not_estimable"
    assert "empty treated arm" in sub["reason"]
    assert sub["hr_in"] is None and sub["interaction_p"] is None and sub["q_value"] is None
    assert sub["truth"] == "no_reliable_difference"


def test_committed_ground_truth_matches_contract():
    lines = (rt.OUTPUT_PATH).read_text().splitlines()
    cases = [json.loads(line) for line in lines]
    assert [c["case_id"] for c in cases][:1] == ["colon:original"]
    for c in cases:
        assert c["method_version"] == rt.METHOD_VERSION and c["seed"] == rt.DEFAULT_SEED
        assert c["evidence_note"] == (rt.GBSG_NOTE if c["trial"] == "gbsg" else None)
        assert set(c) == {"case_id", "trial", "variant", "treatment", "endpoint", "evidence_note", "overall",
                          "subgroups", "truth_flag", "truth_direction", "any_significant",
                          "planted_detectable", "seed", "method_version"}
        for s in c["subgroups"]:
            assert s["truth"] in {"weaker_benefit", "stronger_benefit", "no_reliable_difference"}
            assert s["status"] in {"ok", "not_estimable"}
        if c["variant"] == "original":
            assert c["planted_detectable"] is None
    assert lines == [json.dumps(c, sort_keys=True, separators=(",", ":")) for c in cases]
