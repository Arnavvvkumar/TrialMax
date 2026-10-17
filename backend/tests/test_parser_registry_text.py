"""Registry wording seen in NCT05738694 that the parser used to miss, plus the safety rules it must keep."""
import pytest

from app.criteria import parse_criterion

BLOOD = ("Blood routine test: WBC>=3.5x10\\^9/L, absolute neutrophil count >=1.5x10\\^9/L, "
         "PLT>=75.0x10\\^9/L, HGB>=80g/L")


def modeled(rules):
    return {r.variable: r for r in rules if r.simulatable}


@pytest.mark.parametrize("text,lo,hi", [
    ("Males or females between 18 years old and 80 years old;", 18, 80),
    ("Male or female patients aged 18 to 75 years", 18, 75),
    ("Between 18 years and 70 years of age", 18, 70),
])
def test_age_range_with_years_after_each_number_and_both_sexes(text, lo, hi):
    rules = parse_criterion("I2", "inclusion", text)
    assert len(rules) == 1
    r = rules[0]
    assert (r.variable, r.operator, r.value, r.value_max, r.simulatable) == ("age", "between", lo, hi, True)


def test_lab_list_keeps_modeled_labs_and_lists_unmodeled_wbc_separately():
    rules = parse_criterion("I6", "inclusion", BLOOD)
    labs = modeled(rules)
    assert (labs["anc"].operator, labs["anc"].value, labs["anc"].unit) == (">=", 1.5, "10^9/L")
    assert (labs["platelets"].value, labs["platelets"].unit) == (75.0, "10^9/L")       # "PLT" abbreviation
    assert (labs["hemoglobin"].value, labs["hemoglobin"].unit) == (8.0, "g/dL")       # 80 g/L converted
    unmodeled = [r for r in rules if not r.simulatable]
    assert len(unmodeled) == 1 and any("wbc" in n.lower() for n in unmodeled[0].notes)  # WBC is not dropped


def test_markdown_escaped_units_are_read():
    r = parse_criterion("I1", "inclusion", "Platelets >= 100 x10\\^9/L")[0]
    assert (r.variable, r.value, r.unit, r.simulatable) == ("platelets", 100, "10^9/L", True)


def test_or_between_modeled_and_unmodeled_lab_is_still_refused():
    rules = parse_criterion("I1", "inclusion", "ANC >= 1.5 x10^9/L or WBC >= 3.0 x10^9/L")
    assert not any(r.simulatable for r in rules)


def test_unnamed_extra_bound_on_a_modeled_lab_is_still_refused():
    rules = parse_criterion("I1", "inclusion", "ANC >=1.5 x10^9/L and <10 x10^9/L")
    assert not any(r.simulatable for r in rules)


def test_absolute_gfr_unit_is_still_not_treated_as_egfr():
    rules = parse_criterion("I1", "inclusion", "Renal function: GFR >= 45 ml/min")
    assert not any(r.simulatable for r in rules)


def test_single_sex_restriction_is_not_erased():
    # Only the 'males or females' phrase is neutral; a single sex must not be rewritten.
    rules = parse_criterion("I1", "inclusion", "Female patients aged 18 to 75 years")
    assert any(r.variable == "age" for r in rules)
    assert "Female" in rules[0].text
