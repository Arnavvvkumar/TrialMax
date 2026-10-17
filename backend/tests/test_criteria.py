import json
from pathlib import Path

import pytest

from app.criteria import parse_criterion, parse_eligibility_rules, split_criteria

FIXTURES = Path(__file__).parent / "fixtures"


def eligibility(nct_id: str) -> str:
    data = json.loads((FIXTURES / f"{nct_id}.json").read_text(encoding="utf-8"))
    return data["protocolSection"]["eligibilityModule"]["eligibilityCriteria"]


def one(rid, kind, text):
    rules = parse_criterion(rid, kind, text)
    assert len(rules) == 1, rules
    return rules[0]


def by_id(rules):
    return {r.id: r for r in rules}


@pytest.mark.parametrize('text,variable,operator', [
    ('EGFR mutation positive', 'egfr_mutation_positive', 'present'),
    ('EGFR mutation negative', 'egfr_mutation_positive', 'absent'),
    ('Confirmed ALK rearrangement positive status', 'alk_positive', 'present'),
    ('ALK rearrangement negative', 'alk_positive', 'absent'),
])
def test_plain_binary_biomarker_status(text, variable, operator):
    rule = one('I1', 'inclusion', text)
    assert (rule.variable, rule.operator) == (variable, operator)
    assert rule.purpose == 'predictive_enrichment'


def test_variant_specific_biomarker_is_not_replaced_with_binary_status():
    rules = parse_criterion('I1', 'inclusion', 'EGFR exon 19 deletion mutation positive')
    assert not any(rule.simulatable for rule in rules)


# ---------------------------------------------------------------- splitting

def test_split_bulleted_fixture():
    items = split_criteria(eligibility("NCT07223541"))
    kinds = [i.kind for i in items]
    assert kinds.count("inclusion") == 15
    assert kinds.count("exclusion") == 31
    assert items[0].text.startswith("Patient must be >= 18 years")


def test_split_numbered_fixture_with_nested_items_and_note():
    items = split_criteria(eligibility("NCT06149286"))
    inclusion = [i for i in items if i.kind == "inclusion"]
    exclusion = [i for i in items if i.kind == "exclusion"]
    assert len(inclusion) == 6
    assert len(exclusion) == 7
    assert "teratogenic" in inclusion[5].text  # nested sub-items folded into item 6
    assert not any("Other protocol-defined" in i.text for i in items)


def test_split_freeform_headers():
    items = split_criteria(eligibility("NCT06165419"))
    assert [i.kind for i in items].count("inclusion") == 6
    assert [i.kind for i in items].count("exclusion") == 3
    assert not any(i.uncertain for i in items)
    assert not any("ineligible" in i.text for i in items)


def test_alternate_header_switches_to_exclusion():
    items = split_criteria("Inclusion Criteria:\n* Age >= 18 years\nPatients are ineligible if they have:\n* HIV infection")
    assert items[-1].kind == "exclusion" and items[-1].text == "HIV infection"


def test_headerless_text_is_uncertain_and_conditions_not_modeled():
    rules, warnings = parse_eligibility_rules("* HIV infection\n* Age >= 18 years")
    assert warnings
    hiv, age = rules
    assert not hiv.simulatable and hiv.parsed_by == "rules"
    assert age.simulatable and any("treated as inclusion" in n for n in age.notes)


# ---------------------------------------------------------------- age / ECOG

@pytest.mark.parametrize("text,op,value", [
    ("Patient must be \\>= 18 years of age.", ">=", 18),
    ("Age 18 years or older", ">=", 18),
    ("Participants aged at least 21 years", ">=", 21),
    ("Patients aged >=18 years are eligible", ">=", 18),  # requirement phrased permissively
])
def test_age(text, op, value):
    r = one("I1", "inclusion", text)
    assert (r.variable, r.operator, r.value) == ("age", op, value)


@pytest.mark.parametrize("text,lo,hi", [
    ("Aged 18 to 75 years at screening", 18, 75),
    ("Age >=18 years and <=65 years", 18, 65),
    ("Age 18 years or older and under 75 years", 18, 74),
])
def test_age_ranges(text, lo, hi):
    r = one("I1", "inclusion", text)
    assert (r.variable, r.operator, r.value, r.value_max) == ("age", "between", lo, hi)


@pytest.mark.parametrize("text,op,value", [
    ("Eastern Cooperative Oncology Group (ECOG) Performance Status 0-2.", "<=", 2),
    ("ECOG performance status of 0 or 1", "<=", 1),
    ("ECOG performance status 0, 1, or 2", "<=", 2),
    ("ECOG ≤ 2", "<=", 2),
])
def test_ecog(text, op, value):
    r = one("I1", "inclusion", text)
    assert (r.variable, r.operator, r.value) == ("ecog", op, value)


def test_ecog_with_gap_is_not_modeled():
    r = one("I1", "inclusion", "ECOG performance status 0 or 2")
    assert not r.simulatable and r.parsed_by == "rules"


# ---------------------------------------------------------------- labs and units

def test_lab_panel_in_one_bullet():
    text = ("Adequate organ function: ANC ≥ 1.5 × 10^9/L; platelets ≥ 100,000/mm3; "
            "hemoglobin ≥ 9 g/dL; total bilirubin ≤ 1.5 × ULN; AST/ALT ≤ 2.5 × ULN "
            "(≤ 5 × ULN if liver metastases); creatinine clearance ≥ 60 mL/min")
    rules = {r.variable: r for r in parse_criterion("I5", "inclusion", text)}
    assert rules["anc"].value == 1.5 and rules["anc"].operator == ">="
    assert rules["platelets"].value == 100 and rules["platelets"].unit == "10^9/L"
    assert rules["hemoglobin"].value == 9
    assert rules["bilirubin"].value == 1.5 and rules["bilirubin"].unit == "x_uln"
    assert rules["ast"].value == 2.5 and rules["alt"].value == 2.5  # first threshold, not the exception
    assert rules["ast"].fidelity == "approximate"                   # the exception is flagged
    assert rules["crcl"].value == 60 and rules["crcl"].unit == "mL/min"
    assert "egfr" not in rules
    assert all(r.purpose == "safety" and r.findability == "coded_lab" for r in rules.values())


@pytest.mark.parametrize("text,variable,value", [
    ("Creatinine <= 0.11 mmol/L", "creatinine", 1.2443),
    ("Total bilirubin <= 12 mg/dL", "bilirubin", 12),
    ("Total bilirubin <= 25 umol/L", "bilirubin", 1.462),
    ("Hemoglobin >= 90 g/L", "hemoglobin", 9),
    ("eGFR >= 60 mL/min/1.73 m2", "egfr", 60),
])
def test_explicit_units_win(text, variable, value):
    r = one("I1", "inclusion", text)
    assert r.variable == variable and r.value == pytest.approx(value, rel=1e-3)
    assert r.fidelity == "exact"


def test_unitless_value_is_inferred_and_flagged():
    r = one("I1", "inclusion", "Serum creatinine <= 133")
    assert r.value == pytest.approx(133 / 88.4, rel=1e-3)
    assert r.fidelity == "approximate" and any("assumed" in n for n in r.notes)


def test_unsupported_unit_is_not_modeled():
    r = one("I1", "inclusion", "Creatinine <= 15 mg/L")
    assert not r.simulatable and any("not supported" in n for n in r.notes)


def test_lab_without_numbers_is_left_unparsed_with_note():
    r = one("I11", "inclusion", "Patients must have adequate organ and bone marrow function per protocol.")
    assert not r.simulatable
    assert any("full protocol" in n for n in r.notes)


# ---------------------------------------------------------------- compound logic

def test_or_between_inclusion_requirements_is_not_flattened():
    r = one("I4", "inclusion", "Creatinine <= 1.5 x ULN or creatinine clearance >= 60 mL/min")
    assert r.category == "compound" and not r.simulatable and r.parsed_by == "rules"


def test_both_in_exclusion_is_not_flattened():
    r = one("E2", "exclusion", "Patients with both HIV and HBV infection")
    assert r.category == "compound" and not r.simulatable


def test_exclusion_list_is_or():
    rules = parse_criterion("E3", "exclusion", "Known HIV, hepatitis B, or hepatitis C infection")
    assert {r.variable for r in rules} == {"hiv", "hepatitis_b", "hepatitis_c"}
    assert all(r.operator == "present" for r in rules)


def test_clauses_keep_every_requirement():
    rules = parse_criterion("I5", "inclusion", "ANC >= 1.5 x10^9/L and no active infection")
    assert {(r.variable, r.operator) for r in rules} == {("anc", ">="), ("active_infection", "absent")}


def test_admin_clause_does_not_swallow_clinical_requirement():
    rules = parse_criterion("I8", "inclusion", "Must not be pregnant and agree to use contraception")
    assert [(r.variable, r.operator) for r in rules] == [("pregnant", "absent")]
    assert any("administrative" in n for n in rules[0].notes)


# ---------------------------------------------------------------- negation, conditionals, permissions

def test_conditional_hbv_is_not_modeled():
    text = ("For patients with history of chronic hepatitis B virus (HBV) infection, the HBV viral load must be "
            "undetectable on suppressive therapy, if indicated. If no previous history, testing for HBV is not "
            "required for entry onto the study.")
    r = one("I13", "inclusion", text)
    assert r.category == "conditional" and not r.simulatable and r.parsed_by == "rules"


def test_negated_exclusion_keeps_its_meaning():
    r = one("E1", "exclusion", "Patients without HIV infection")
    assert (r.variable, r.operator) == ("hiv", "absent")
    assert any("negatively" in n for n in r.notes)


def test_exclusion_conditions():
    rules = parse_criterion("E1", "exclusion", "Pregnant or breastfeeding women.")
    pregnancy = next(r for r in rules if r.variable == "pregnant")
    assert (pregnancy.operator, pregnancy.safety_critical) == ("present", True)
    assert any(not r.simulatable and any("Breastfeeding" in n for n in r.notes) for r in rules)


def test_permission_is_not_a_restriction():
    r = one("I12", "inclusion", "Human immunodeficiency virus (HIV)-infected patients on effective "
                                "anti-retroviral therapy with undetectable viral load are eligible for this trial.")
    assert r.category == "permission" and not r.simulatable


def test_administrative():
    r = one("I9", "inclusion", "Patient must have the ability to understand and the willingness to sign "
                               "a written informed consent document.")
    assert r.category == "administrative" and not r.simulatable


# ---------------------------------------------------------------- prior therapy

def test_combination_therapy_is_not_replaced_by_immunotherapy():
    text = ("Patient who have received any prior combination systemic therapy for metastatic RCC "
            "(including immune checkpoint inhibitors, tyrosine kinase inhibitors or combinations)")
    r = one("E5", "exclusion", text)
    assert not r.simulatable and r.variable is None and r.parsed_by == "rules"


def test_explicit_immunotherapy_exclusion():
    r = parse_criterion("E6", "exclusion", "Patients who have received any check point inhibitor or immune "
                                           "therapies within the last 12 months.")[0]
    assert (r.variable, r.operator, r.fidelity) == ("prior_immunotherapy", "present", "approximate")


def test_inverted_exclusion_is_flagged():
    r = one("E8", "exclusion", "Patients with no more than 1 prior systemic therapy for metastatic disease.")
    assert r.variable == "prior_systemic_lines" and r.operator == "<="
    assert any("inverted" in n for n in r.notes)


# ---------------------------------------------------------------- full fixtures

def test_fixture_expected_rules():
    rules, _ = parse_eligibility_rules(eligibility("NCT07223541"))
    r = by_id(rules)
    assert (r["I1"].variable, r["I1"].operator, r["I1"].value) == ("age", ">=", 18)
    assert (r["I10"].variable, r["I10"].operator, r["I10"].value) == ("ecog", "<=", 2)
    assert r["I12"].category == "permission"
    assert r["I13"].category == "conditional"
    assert not r["E5"].simulatable
    assert any(x.id.startswith("E20") and (x.variable, x.operator) == ("pregnant", "present") for x in rules)
    assert any(x.id.startswith("E20") and not x.simulatable for x in rules)
    ids = [x.id for x in rules]
    assert len(ids) == len(set(ids))


def test_third_fixture_parses_exclusions():
    rules, warnings = parse_eligibility_rules(eligibility("NCT06165419"))
    assert not warnings
    r = by_id(rules)
    assert (r["I6"].variable, r["I6"].operator, r["I6"].value) == ("ecog", "<=", 3)
    assert all(x.kind == "exclusion" for x in rules if x.id.startswith("E"))
