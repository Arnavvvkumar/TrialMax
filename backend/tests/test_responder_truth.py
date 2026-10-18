"""Reference-method tests on constructed data; never regenerate the frozen snapshot."""
import hashlib

import numpy as np
import pandas as pd
import pytest

from app.responder_evidence import read_cases
from app.responder_truth import RCT_DIR, analyze_frame, bh_adjust, load_trial, plant, subgroup_masks

SPEC = ('older', 'Age >=60', 'age', 'ge', 60)


def synthetic(interaction=True):
    rng = np.random.default_rng(93)
    n = 3200
    treatment = np.tile([0, 1], n // 2)
    older = np.repeat([False, True], n // 2)
    hazard = np.where(treatment == 1, np.where(older & interaction, 1., .25), 1.)
    return pd.DataFrame(dict(treatment=treatment, age=np.where(older, 70, 50),
                             duration=rng.exponential(100 / hazard), event=np.ones(n, dtype=int)))


def test_planted_interaction_and_reference_direction():
    row = analyze_frame(synthetic(), 'colon', specs=[SPEC]).subgroups[0]
    assert row.interaction.p < .01
    assert row.interaction_q < .01
    assert row.truth_label == 'weaker_benefit'
    assert row.hr_subgroup.hr > row.hr_complement.hr
    assert not row.underpowered


def test_no_interaction_does_not_claim_difference():
    # Identical survival records in the two age strata give an exact null interaction.
    frame = synthetic(False).iloc[:1600].copy()
    duplicate = frame.copy(); duplicate['age'] = 70
    row = analyze_frame(pd.concat([frame, duplicate], ignore_index=True), 'colon', specs=[SPEC]).subgroups[0]
    assert row.interaction.p > .9
    assert row.truth_label == 'no_reliable_difference'


def test_bh_includes_all_prespecified_tests():
    assert bh_adjust([.01, .04, .03, .2]) == pytest.approx([.04, .0533333333, .0533333333, .2])
    corrected = bh_adjust([.04, None])
    assert corrected[0] == pytest.approx(.08)
    assert corrected[1] is None
    assert bh_adjust([]) == []


def test_colon_death_records_have_one_patient_and_two_arms():
    frame = load_trial('colon')
    assert len(frame) == 619
    assert frame.id.is_unique
    assert set(frame.etype) == {2}
    assert set(frame.rx) == {'Lev+5FU', 'Obs'}
    assert 'rownames' not in frame


def test_missing_subgroup_is_in_neither_arm():
    frame = pd.DataFrame({'age': [50., 70., np.nan]})
    yes, no, missing = subgroup_masks(frame, SPEC)
    assert yes.tolist() == [False, True, False]
    assert no.tolist() == [True, False, False]
    assert missing.tolist() == [False, False, True]


def test_plant_is_deterministic_and_changes_only_treated_subgroup():
    frame = synthetic(False)
    before = frame.copy(deep=True)
    first, second = plant(frame, SPEC, 77), plant(frame, SPEC, 77)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(frame, before)
    target = (frame.age >= 60) & (frame.treatment == 1)
    pd.testing.assert_frame_equal(first.loc[~target], frame.loc[~target])
    assert set(map(tuple, first.loc[target, ['duration', 'event']].to_numpy())) <= set(
        map(tuple, frame.loc[(frame.age >= 60) & (frame.treatment == 0), ['duration', 'event']].to_numpy()))
    case = analyze_frame(first, 'colon', specs=[SPEC], variant='planted:older', planted_subgroup='older', seed=77)
    assert case.planted_detectable is True
    assert case.subgroups[0].truth_label == 'weaker_benefit'


def test_frozen_reference_snapshot_unchanged_and_honestly_labeled():
    assert hashlib.sha256((RCT_DIR / 'ground_truth.jsonl').read_bytes()).hexdigest() == (
        'bdd5d804a00309b6475dba46607b8350be0c3912ef29909af2858ccfb73eef26')
    cases = read_cases()
    assert len(cases) == 12
    planted = [c for c in cases if c.planted_subgroup]
    assert len(planted) == 9
    for case in planted:
        target = next(s for s in case.subgroups if s.id == case.planted_subgroup)
        assert case.planted_detectable == (target.truth_label == 'weaker_benefit')
    assert all(any('non-randomized' in d for d in c.disclaimers) for c in cases if c.trial_key == 'gbsg')
