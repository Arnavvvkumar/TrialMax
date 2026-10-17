"""Turn the registry's structured eligibility fields (age limits, sex) into rules.

These restrictions apply even when the free-text criteria do not repeat them.
"""
from __future__ import annotations

import re

from .models import Rule, TrialInfo
from .variables import VARIABLES

_TO_YEARS = {"year": 1.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}


def parse_age_years(raw: str | None) -> float | None:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(year|month|week|day)s?\s*$", raw or "", re.I)
    if not m:
        return None
    return round(float(m.group(1)) * _TO_YEARS[m.group(2).lower()], 2)


def _rule(rid: str, text: str, variable: str, operator: str, value=None, unit=None) -> Rule:
    meta = VARIABLES[variable]
    return Rule(id=rid, kind="inclusion", text=text, category="sex" if variable == "female" else "age",
                variable=variable, operator=operator, value=value, unit=unit, simulatable=True,
                purpose=meta["purpose"], findability=meta["findability"], safety_critical=meta["safety_critical"],
                parsed_by="rules", source="registry",
                notes=["From the registry's structured eligibility fields."])


def registry_rules(trial: TrialInfo) -> list[Rule]:
    rules: list[Rule] = []
    lo, hi = parse_age_years(trial.minimum_age), parse_age_years(trial.maximum_age)
    if lo is not None and lo > 0:
        rules.append(_rule("REG-AGE-MIN", f"Registry minimum age: {trial.minimum_age}", "age", ">=", lo, "years"))
    if hi is not None:
        rules.append(_rule("REG-AGE-MAX", f"Registry maximum age: {trial.maximum_age}", "age", "<=", hi, "years"))
    sex = (trial.sex or "").upper()
    if sex == "FEMALE":
        rules.append(_rule("REG-SEX", "Registry sex: female only", "female", "present"))
    elif sex == "MALE":
        rules.append(_rule("REG-SEX", "Registry sex: male only", "female", "absent"))
    return rules
