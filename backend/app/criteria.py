"""Split registry eligibility text into criteria and parse each one into rules.

Parsing here is deterministic (regular expressions). Anything it cannot read is
left unparsed so the LLM step (see llm.py) can try, or a human can edit it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Rule
from .variables import meta_for

# ---------------------------------------------------------------- splitting

HEADER_RE = re.compile(
    r"^\s*(?:key\s+|main\s+|major\s+|other\s+)?(inclusion|exclusion)\s+criteria\b\s*:?\s*(.*)$", re.I
)
BULLET_RE = re.compile(r"^(\s*)(?:[*\-\u2022]|\d{1,2}[.)]|[a-zA-Z][.)]|\(\w{1,3}\))\s+(.*)$")
NOTE_RE = re.compile(r"^\s*note\s*:", re.I)


@dataclass
class RawCriterion:
    kind: str
    text: str


def normalize_text(text: str) -> str:
    """Undo registry markdown escapes and unify symbols, keeping the wording."""
    t = text.replace("\r\n", "\n")
    t = re.sub(r"\\([\[\]<>*_()#+.!-])", r"\1", t)
    for a, b in (("\u2265", ">="), ("\u2264", "<="), ("\u00d7", "x"), ("\u2013", "-"),
                 ("\u2014", "-"), ("\u00a0", " "), ("\u2019", "'"), ("\u00b5", "u"), ("\u03bc", "u")):
        t = t.replace(a, b)
    return t


def split_criteria(text: str) -> list[RawCriterion]:
    items: list[RawCriterion] = []
    kind = "inclusion"
    current: RawCriterion | None = None
    base_indent: int | None = None
    for line in normalize_text(text).split("\n"):
        if not line.strip():
            continue
        header = HEADER_RE.match(line)
        if header:
            kind = header.group(1).lower()
            current, base_indent = None, None
            rest = header.group(2).strip()
            if rest:
                current = RawCriterion(kind, rest)
                items.append(current)
            continue
        if NOTE_RE.match(line):
            current = None
            continue
        bullet = BULLET_RE.match(line)
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            content = bullet.group(2).strip()
            if base_indent is None:
                base_indent = indent
            if indent > base_indent and current is not None:
                current.text += " " + content  # nested sub-item belongs to its parent
            else:
                current = RawCriterion(kind, content)
                items.append(current)
        elif current is not None:
            current.text += " " + line.strip()
        else:
            current = RawCriterion(kind, line.strip())
            items.append(current)
    return [item for item in items if len(item.text.strip()) > 2]


# ---------------------------------------------------------------- comparators

_CMP_PHRASES = [
    (r"greater than or equal to|more than or equal to|equal to or greater than|no less than|"
     r"not less than|at least|>\s*or\s*=|=\s*>|\bgte\b", ">="),
    (r"less than or equal to|equal to or less than|no more than|not more than|at most|up to|"
     r"<\s*or\s*=|=\s*<|\blte\b", "<="),
    (r"greater than|more than|\babove\b|\bexceeding\b|\bexceeds\b|\bover\b", ">"),
    (r"less than|\bbelow\b|\bunder\b", "<"),
]


def cmp_normalize(text: str) -> str:
    s = text.lower()
    for pattern, symbol in _CMP_PHRASES:
        s = re.sub(pattern, f" {symbol} ", s)
    return re.sub(r"\s+", " ", s)


def _num(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
        return float(raw.replace(",", ""))
    return float(raw.replace(",", "."))


NUM = r"(\d+(?:[.,]\d+)*)"

# ---------------------------------------------------------------- classifiers

ADMIN_RE = re.compile(
    r"informed consent|consent form|\bwilling|willingness|able to comply|comply with|contracepti|"
    r"\babstain|agree to|agree not|understanding that|documentation from|\bsigned\b|counsel",
    re.I,
)
PERMISSION_RE = re.compile(
    r"\b(?:are|is|will be|would be)\s+(?:also\s+)?(?:eligible|allowed|permitted)\b|can be included|"
    r"may (?:be )?(?:enrolled|included|eligible)|non-exclusionary",
    re.I,
)
NEGATION_RE = re.compile(r"\b(no|without|must not|free of|absence of|not have|none)\b", re.I)
QUALIFIER_RE = re.compile(r"\b(active|uncontrolled|untreated|symptomatic|within \d+|unless|except)\b", re.I)

CONDITIONS: list[tuple[str, str]] = [
    ("brain_mets", r"brain metasta|cns metasta|central nervous system (?:involvement|metasta|lymphoma|pathology)|"
                   r"leptomeningeal|\bcns\b"),
    ("hiv", r"\bhiv\b|human immunodeficiency virus"),
    ("hepatitis_b", r"hepatitis b|\bhbv\b"),
    ("hepatitis_c", r"hepatitis c|\bhcv\b"),
    ("prior_malignancy", r"(?:other|another|prior|second|concurrent|additional|previous)\s+(?:active\s+|invasive\s+)?"
                         r"malignan|malignancy other than"),
    ("autoimmune_active", r"autoimmune"),
    ("myocarditis_history", r"myocarditis"),
    ("cardiac_disease", r"congestive heart failure|\bnyha\b|new york heart association|cardiac disease|"
                        r"unstable angina|myocardial infarction|arrhythmia|cardiovascular disease"),
    ("thromboembolic_event_recent", r"cerebrovascular accident|\bstroke\b|thrombo(?:tic|embolic|sis)|"
                                    r"pulmonary embolism|\bdvt\b"),
    ("uncontrolled_hypertension", r"hypertension"),
    ("active_infection", r"active infection|infection requiring|tuberculosis|uncontrolled infection"),
    ("ibd", r"inflammatory bowel|crohn|ulcerative colitis"),
    ("hepatic_impairment", r"child-?pugh|hepatic impairment|cirrhosis"),
    ("interstitial_lung_disease", r"pneumonitis|interstitial lung"),
    ("systemic_immunosuppression", r"corticosteroid|immunosuppress"),
    ("recent_major_surgery", r"major surgery"),
    ("recent_live_vaccine", r"live vaccine|live attenuated"),
    ("drug_hypersensitivity", r"hypersensitivity|allerg"),
    ("pregnant", r"pregnan|breast-?feed|lactat|nursing"),
]

LABS: list[tuple[str, str]] = [
    ("anc", r"absolute neutrophil count|\banc\b|neutrophil"),
    ("platelets", r"platelet"),
    ("hemoglobin", r"ha?emoglobin|\bhgb\b|\bhb\b"),
    ("egfr", r"creatinine clearance|\bcr\s?cl\b|\begfr\b|glomerular filtration"),
    ("creatinine", r"creatinine(?!\s*clearance)"),
    ("bilirubin", r"bilirubin"),
    ("ast", r"\bast\b|aspartate (?:amino)?transferase|\bsgot\b|transaminase"),
    ("alt", r"\balt\b|alanine (?:amino)?transferase|\bsgpt\b|transaminase"),
]

THRESHOLD_RE = re.compile(
    r"(>=|<=|>|<)\s*" + NUM + r"\s*((?:x|times)\s*(?:the\s*)?(?:institutional\s*)?(?:upper limit of normal|uln))?"
)


@dataclass
class Parsed:
    category: str
    variable: str
    operator: str
    value: float | None = None
    value_max: float | None = None
    unit: str | None = None
    note: str | None = None


def parse_age(s: str) -> Parsed | None:
    if not re.search(r"\bage\b|\baged\b|years? of age|years? old|\byrs\b", s):
        return None
    m = (re.search(r"(?:aged?|between|from)\s*(\d{1,3})\s*(?:-|to|and)\s*(\d{1,3})\s*(?:years|yrs)", s)
         or re.search(r"(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\s*years? (?:of age|old)", s))
    if m:
        return Parsed("age", "age", "between", float(m.group(1)), float(m.group(2)), "years")
    m = re.search(r"(>=|<=|>|<)\s*(\d{1,3})\s*(?:years|yrs)", s) or re.search(r"\bage[d]?\s*(>=|<=|>|<)\s*(\d{1,3})", s)
    if m:
        return Parsed("age", "age", m.group(1), float(m.group(2)), unit="years")
    m = re.search(r"(\d{1,3})\s*(?:years|yrs)(?:\s*of age|\s*old)?\s*(?:or|and)\s*(?:older|>)", s)
    if m:
        return Parsed("age", "age", ">=", float(m.group(1)), unit="years")
    return None


_KPS_TO_ECOG = [(90, 0), (70, 1), (50, 2), (30, 3)]


def parse_ecog(s: str) -> Parsed | None:
    if re.search(r"\becog\b|\bwho performance|performance status|\bzubrod\b", s):
        m = re.search(r"(?:ecog|performance status|\bps\b)[^0-9<>]{0,40}?(\d)\s*(?:-|to|or|and|,)\s*(\d)\b", s)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo == 0:
                return Parsed("performance_status", "ecog", "<=", float(hi))
            return Parsed("performance_status", "ecog", "between", float(lo), float(hi))
        m = re.search(r"(?:ecog|performance status)[^0-9<>]{0,40}?(<=|<|>=|>)\s*(\d)\b", s)
        if m:
            return Parsed("performance_status", "ecog", m.group(1), float(m.group(2)))
        m = re.search(r"(?:ecog|performance status)[^0-9<>]{0,40}?\bof\s*(\d)\b", s)
        if m:
            return Parsed("performance_status", "ecog", "<=", float(m.group(1)))
    if "karnofsky" in s:
        m = re.search(r"karnofsky[^0-9]{0,40}?(>=|>)\s*(\d{2,3})", s)
        if m:
            kps = float(m.group(2))
            for cutoff, ecog in _KPS_TO_ECOG:
                if kps >= cutoff:
                    return Parsed("performance_status", "ecog", "<=", float(ecog),
                                  note=f"Karnofsky >= {kps:g} approximated as ECOG <= {ecog}.")
    return None


def _convert_lab(variable: str, value: float, uln: bool, unit_text: str) -> tuple[float, str]:
    if uln:
        return value, "x_uln"
    u = unit_text
    if variable == "anc":
        return (value / 1000 if value >= 100 else value), "10^9/L"
    if variable == "platelets":
        return (value / 1000 if value >= 1000 else value), "10^9/L"
    if variable == "hemoglobin":
        return (value / 10 if (("g/l" in u and "g/dl" not in u) or value > 25) else value), "g/dL"
    if variable == "creatinine":
        return (value / 88.4 if ("mol" in u or value > 20) else value), "mg/dL"
    if variable == "bilirubin":
        return (value / 17.1 if ("mol" in u or value > 10) else value), "mg/dL"
    if variable == "egfr":
        return value, "mL/min"
    return value, "U/L"


def parse_labs(s: str) -> list[Parsed]:
    mentions = []
    for variable, pattern in LABS:
        for m in re.finditer(pattern, s):
            mentions.append((m.start(), m.end(), variable))
    if not mentions:
        return []
    mentions.sort()
    results: dict[str, Parsed] = {}
    assigned: set[int] = set()
    for t in THRESHOLD_RE.finditer(s):
        pending = [i for i, (_, end, _) in enumerate(mentions) if i not in assigned and end <= t.start()]
        if not pending:
            continue
        value = _num(t.group(2))
        uln = bool(t.group(3))
        unit_text = s[t.end(): t.end() + 25]
        for i in pending:
            assigned.add(i)
            variable = mentions[i][2]
            if variable in results:
                continue
            v, unit = _convert_lab(variable, value, uln, unit_text)
            results[variable] = Parsed("lab", variable, t.group(1), round(v, 4), unit=unit)
    return list(results.values())


def parse_prior_therapy(s: str, kind: str) -> Parsed | None:
    if kind == "exclusion" and re.search(
        r"checkpoint inhibitor|anti-?pd-?l?1|anti-?ctla|immunotherap|immune therap|immune-oncology", s
    ):
        return Parsed("prior_therapy", "prior_immunotherapy", "present")
    if not re.search(r"prior|previous|lines? of|regimen|treatment-?naive", s):
        return None
    m = re.search(r"(>=|<=|>|<)\s*(\d+)\s*(?:prior|previous|lines?|regimens?)", s)
    if m:
        note = None
        if kind == "exclusion" and m.group(1) in ("<=", "<"):
            note = "Exclusion phrased as a maximum: check whether the wording is inverted."
        return Parsed("prior_therapy", "prior_systemic_lines", m.group(1), float(m.group(2)), unit="lines", note=note)
    m = re.search(r"(\d+)\s*(?:or more|\+)\s*(?:prior|previous)?\s*(?:lines?|regimens?)", s)
    if m:
        return Parsed("prior_therapy", "prior_systemic_lines", ">=", float(m.group(1)), unit="lines")
    if re.search(r"\b(?:no|without)\s+(?:any\s+)?(?:prior|previous)\s+(?:systemic|chemo|anti-?cancer|treatment|therapy)|"
                 r"treatment-?naive", s):
        return Parsed("prior_therapy", "prior_systemic_lines", "==", 0.0, unit="lines")
    if kind == "exclusion" and re.search(r"(?:any\s+)?prior\s+(?:\w+\s+){0,2}systemic (?:therapy|treatment)", s):
        return Parsed("prior_therapy", "prior_systemic_lines", ">=", 1.0, unit="lines")
    return None


def parse_conditions(s: str, kind: str) -> list[Parsed]:
    found = [variable for variable, pattern in CONDITIONS if re.search(pattern, s)]
    if not found:
        return []
    if kind == "inclusion":
        if "pregnant" in found and re.search(r"negative|rule out|not pregnant|non-?pregnant", s):
            return [Parsed("pregnancy", "pregnant", "absent")]
        if NEGATION_RE.search(s):
            return [Parsed("condition", v, "absent") for v in found[:3]]
        return []  # an inclusion that mentions a condition is ambiguous: leave it for the LLM
    category = lambda v: "pregnancy" if v == "pregnant" else "condition"  # noqa: E731
    return [Parsed(category(v), v, "present") for v in found[:4]]


# ---------------------------------------------------------------- assembly

def _rule_from(rid: str, kind: str, text: str, p: Parsed, extra_notes: list[str]) -> Rule:
    meta = meta_for(p.variable)
    notes = list(extra_notes)
    if p.note:
        notes.append(p.note)
    return Rule(
        id=rid, kind=kind, text=text, category=p.category, variable=p.variable, operator=p.operator,
        value=p.value, value_max=p.value_max, unit=p.unit, simulatable=True,
        purpose=meta["purpose"] if meta else "unknown",
        findability=meta["findability"] if meta else "unknown",
        safety_critical=meta["safety_critical"] if meta else False,
        parsed_by="rules", notes=notes,
    )


def parse_criterion(rid: str, kind: str, text: str) -> list[Rule]:
    s = cmp_normalize(text)
    if ADMIN_RE.search(s):
        return [Rule(id=rid, kind=kind, text=text, category="administrative", purpose="administrative",
                     findability="patient_reported", notes=["Administrative requirement; not simulated."])]
    if kind == "inclusion" and PERMISSION_RE.search(s):
        return [Rule(id=rid, kind=kind, text=text, category="permission", purpose="unknown",
                     notes=["Permissive statement: it widens eligibility, so it is not simulated as a restriction."])]

    parsed: list[Parsed] = []
    for single in (parse_age(s), parse_ecog(s), parse_prior_therapy(s, kind)):
        if single:
            parsed.append(single)
    parsed.extend(parse_labs(s))
    if not any(p.category in ("lab", "prior_therapy") for p in parsed):
        parsed.extend(p for p in parse_conditions(s, kind)
                      if not any(q.variable == p.variable for q in parsed))

    if not parsed:
        notes = []
        if re.search(r"per protocol|as described in the protocol|as defined in the protocol", s):
            notes.append("Details are in the full protocol, not in the registry text.")
        return [Rule(id=rid, kind=kind, text=text, notes=notes)]

    extra = []
    if QUALIFIER_RE.search(s) and any(p.operator in ("present", "absent") for p in parsed):
        extra.append("Severity, timing or exception qualifiers are not modeled; any history counts as present.")
    if len(parsed) == 1:
        return [_rule_from(rid, kind, text, parsed[0], extra)]
    return [_rule_from(f"{rid}{chr(97 + i)}", kind, text, p, extra) for i, p in enumerate(parsed)]


def parse_eligibility_rules(text: str) -> list[Rule]:
    """Deterministic parse of a full eligibility section."""
    rules: list[Rule] = []
    counters = {"inclusion": 0, "exclusion": 0}
    for item in split_criteria(text):
        counters[item.kind] += 1
        prefix = "I" if item.kind == "inclusion" else "E"
        rules.extend(parse_criterion(f"{prefix}{counters[item.kind]}", item.kind, item.text))
    return rules
