"""Planted-truth checks plus safety and coverage behavior."""
import pytest
from pydantic import ValidationError

from app.models import Rule, TrialInfo
from app.population import ECOG_PROBS, PREVALENCE
from app.registry import registry_rules
from app.simulate import classify_change, compare, coverage_warnings, simulate

N, SEED = 50000, 7


def rule(rid, kind, variable, operator, value=None, **kw):
    return Rule(id=rid, kind=kind, text=f"{variable} {operator} {value}", variable=variable,
                operator=operator, value=value, simulatable=True, **kw)


# ---------------------------------------------------------------- planted truth

def test_ecog_inclusion_recovers_planted_rate():
    sim = simulate([rule("I1", "inclusion", "ecog", "<=", 1)], N, SEED)
    assert abs(sim.eligible_pct - 100 * (ECOG_PROBS[0] + ECOG_PROBS[1])) < 1.0


def test_exclusion_recovers_planted_prevalence():
    sim = simulate([rule("E1", "exclusion", "brain_mets", "present")], N, SEED)
    assert abs(sim.impacts[0].fail_pct - 100 * PREVALENCE["brain_mets"]) < 1.0


def test_independent_rules_combine_and_unique_counts_are_consistent():
    rules = [rule("I1", "inclusion", "ecog", "<=", 1), rule("E1", "exclusion", "brain_mets", "present")]
    sim = simulate(rules, N, SEED)
    expected = 100 * (ECOG_PROBS[0] + ECOG_PROBS[1]) * (1 - PREVALENCE["brain_mets"])
    assert abs(sim.eligible_pct - expected) < 1.0
    for impact in sim.impacts:
        assert impact.unique_fail_n <= impact.fail_n
    assert sim.funnel[-1].remaining_n == sim.eligible_n
    assert sim.worst_rule_id == "I1" and sim.complete


def test_x_uln_conversion():
    sim = simulate([rule("I1", "inclusion", "bilirubin", "<=", 1.5, unit="x_uln")], N, SEED)
    assert 85 < sim.eligible_pct < 100


def test_truth_table_tiny_population():
    # small seeds still give exactly-defined answers for impossible combinations
    sim = simulate([rule("A", "inclusion", "age", ">=", 80), rule("B", "inclusion", "age", "<=", 30)], 10000, 42)
    assert sim.eligible_n == 0


def test_same_seed_is_reproducible():
    rules = [rule("I1", "inclusion", "ecog", "<=", 1)]
    assert simulate(rules, 3000, 1).eligible_n == simulate(rules, 3000, 1).eligible_n


# ---------------------------------------------------------------- validation

def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError):
        simulate([rule("R", "inclusion", "age", ">=", 80), rule("R", "inclusion", "age", "<=", 30)], 1000, 1)


@pytest.mark.parametrize("bad", [
    dict(variable="anc", operator="present"),                          # numeric needs a comparison
    dict(variable="age", operator="between", value=18),                # missing value_max
    dict(variable="age", operator="between", value=65, value_max=18),  # reversed range
    dict(variable="creatinine", operator="<=", value=1.5, unit="years"),
    dict(variable="hiv", operator=">=", value=1),
    dict(variable="age", operator=">=", value=float("inf")),
    dict(variable="unknown_thing", operator="present"),
])
def test_invalid_rules_are_rejected(bad):
    with pytest.raises(ValidationError):
        Rule(id="X", kind="inclusion", text="x", simulatable=True, **bad)


# ---------------------------------------------------------------- coverage

def test_unmodeled_rules_are_reported_and_warned():
    rules = [rule("I1", "inclusion", "ecog", "<=", 1),
             Rule(id="I2", kind="inclusion", text="Some unusual requirement"),
             Rule(id="I3", kind="inclusion", text="Must sign consent", category="administrative")]
    sim = simulate(rules, 2000, SEED)
    assert sim.unmodeled_rule_ids == ["I2"] and sim.not_applicable_rule_ids == ["I3"]
    assert sim.coverage_pct == 50.0 and not sim.complete
    assert any("not modeled" in w for w in coverage_warnings(sim))


def test_nothing_modeled_gives_no_estimate():
    sim = simulate([Rule(id="I1", kind="inclusion", text="Some unusual requirement")], 2000, SEED)
    assert sim.eligible_pct is None and sim.eligible_n is None
    assert coverage_warnings(sim)


def test_registry_restrictions_are_applied():
    trial = TrialInfo(minimum_age="65 Years", sex="FEMALE", eligibility_text="x")
    rules = registry_rules(trial) + [rule("I1", "inclusion", "ecog", "<=", 2)]
    sim = simulate(rules, 20000, SEED)
    assert {r.id for r in rules} >= {"REG-AGE-MIN", "REG-SEX"}
    assert sim.eligible_pct < 30  # roughly half are female and about half are 65+


# ---------------------------------------------------------------- comparing and safety warnings

def test_compare_counts_newly_eligible():
    base = [rule("I1", "inclusion", "ecog", "<=", 1)]
    relaxed = [rule("I1", "inclusion", "ecog", "<=", 2)]
    result = compare(base, relaxed, N, SEED)
    assert result.newly_eligible_n > 0 and result.newly_excluded_n == 0
    assert abs(result.eligible_change_pct_points - 100 * ECOG_PROBS[2]) < 1.5
    assert [c.change for c in result.changes] == ["relaxed"]


def test_removing_safety_rule_is_flagged_even_when_sample_has_no_cases():
    base = [rule("E1", "exclusion", "myocarditis_history", "present", safety_critical=True)]
    result = compare(base, [], 100, 1)
    assert result.relaxed_safety_critical_rule_ids == ["E1"]


def test_safety_flag_cannot_be_bypassed_by_clearing_it():
    base = [rule("E1", "exclusion", "pregnant", "present")]
    disabled = [Rule(id="E1", kind="exclusion", text="x", safety_critical=False)]
    assert compare(base, disabled, 1000, 1).relaxed_safety_critical_rule_ids == ["E1"]


@pytest.mark.parametrize("old,new,expected", [
    (dict(kind="inclusion", operator=">=", value=1.5), dict(kind="inclusion", operator=">=", value=1.0), "relaxed"),
    (dict(kind="inclusion", operator=">=", value=1.0), dict(kind="inclusion", operator=">=", value=1.5), "tightened"),
    (dict(kind="exclusion", operator=">", value=2.0), dict(kind="exclusion", operator=">", value=3.0), "relaxed"),
    (dict(kind="inclusion", operator="between", value=18, value_max=65),
     dict(kind="inclusion", operator="between", value=21, value_max=75), "mixed"),
    (dict(kind="inclusion", operator=">=", value=1.5), dict(kind="inclusion", operator="<=", value=3.0), "ambiguous"),
])
def test_change_classification(old, new, expected):
    a = Rule(id="R", text="x", variable="anc" if old["operator"] != "between" else "age", simulatable=True, **old)
    b = Rule(id="R", text="x", variable="anc" if new["operator"] != "between" else "age", simulatable=True, **new)
    assert classify_change(a, b) == expected
