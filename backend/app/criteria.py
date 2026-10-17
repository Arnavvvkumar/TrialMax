"""Split registry eligibility text into criteria, and criteria into checkable rules.

Design principle: never produce a rule whose meaning differs from the text. When the
parser is unsure (OR between requirements, subgroup conditions, partial bounds,
unsupported units, a different therapy than the variable describes), the criterion
is kept visibly "not modeled" instead of being approximated silently.

Parsing here is deterministic. Criteria it cannot read at all are left with
parsed_by="none" so the LLM step (llm.py) may try; criteria it deliberately refuses
to model are marked parsed_by="rules" so the LLM does not override that decision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from .models import Rule
from .variables import VARIABLES, meta_for

# ================================================================ splitting into criteria

INCL_EXCL_HEADER = re.compile(
    r"^\s*(?:(?:key|main|major|other|general|additional)\s+)?(inclusion|exclusion)"
    r"(?:\s+criteria\b\s*:?|\s*:)\s*(.*)$", re.I,
)
FREEFORM_HEADERS = [
    ("exclusion", re.compile(r"^\s*(?:(?:patients|participants|subjects|individuals|people)\s+)?"
                             r"(?:(?:are|will be|is)\s+)?(?:ineligible|not eligible|excluded)\b[^:]{0,80}:\s*$", re.I)),
    ("exclusion", re.compile(r"^\s*(?:(?:patients|participants|subjects|individuals)\s+)?"
                             r"(?:must not|should not|may not|cannot)\s+(?:have|meet|be)\b[^:]{0,80}:\s*$", re.I)),
    ("inclusion", re.compile(r"^\s*(?:eligible\s+)?(?:patients|participants|subjects|individuals)\s+"
                             r"(?:must|should|are eligible if|will be eligible if|may be eligible if)\b[^:]{0,80}:\s*$", re.I)),
    ("inclusion", re.compile(r"^\s*(?:(?:patients|participants|subjects|individuals)\s+)?(?:(?:are|will be)\s+)?"
                             r"eligible\b[^:]{0,80}:\s*$", re.I)),
]
BULLET_RE = re.compile(r"^(\s*)(?:[*\-\u2022]|\d{1,2}[.)]|[a-zA-Z][.)]|\(\w{1,3}\))\s+(.*)$")
NOTE_RE = re.compile(r"^\s*note\s*:", re.I)


@dataclass
class RawCriterion:
    kind: str
    text: str
    uncertain: bool = False  # True when no section header was seen before it


def normalize_text(text: str) -> str:
    """Undo registry markdown escapes and unify symbols, keeping the wording."""
    t = text.replace("\r\n", "\n")
    t = re.sub(r"\\([\[\]<>*_()#+.!^-])", r"\1", t)   # e.g. 10\^9/L -> 10^9/L
    for a, b in (("\u2265", ">="), ("\u2264", "<="), ("\u00d7", "x"), ("\u2013", "-"),
                 ("\u2014", "-"), ("\u00a0", " "), ("\u2019", "'"), ("\u00b5", "u"), ("\u03bc", "u")):
        t = t.replace(a, b)
    return t


def _header(line: str, is_bullet: bool, seen_header: bool, current_kind: str) -> tuple[str, str] | None:
    m = INCL_EXCL_HEADER.match(line)
    if m:
        return m.group(1).lower(), m.group(2).strip()
    if is_bullet:
        return None
    for kind, pattern in FREEFORM_HEADERS:
        if pattern.match(line):
            if seen_header and kind == current_kind:
                return None  # a criterion that happens to end with ":" inside its own section
            return kind, ""
    return None


def split_criteria(text: str) -> list[RawCriterion]:
    items: list[RawCriterion] = []
    kind, seen_header = "inclusion", False
    current: RawCriterion | None = None
    base_indent: int | None = None
    for line in normalize_text(text).split("\n"):
        if not line.strip():
            continue
        bullet = BULLET_RE.match(line)
        header = _header(line, bool(bullet), seen_header, kind)
        if header:
            kind, rest = header
            seen_header = True
            current, base_indent = None, None
            if rest:
                current = RawCriterion(kind, rest)
                items.append(current)
            continue
        if NOTE_RE.match(line):
            current = None
            continue
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            content = bullet.group(2).strip()
            if base_indent is None:
                base_indent = indent
            if indent > base_indent and current is not None:
                current.text += " " + content  # nested sub-item belongs to its parent
            else:
                current = RawCriterion(kind, content, uncertain=not seen_header)
                items.append(current)
        elif current is not None:
            current.text += " " + line.strip()
        else:
            current = RawCriterion(kind, line.strip(), uncertain=not seen_header)
            items.append(current)
    return [item for item in items if len(item.text.strip()) > 2]


# ================================================================ splitting criteria into clauses

_ABBREVIATIONS = [(r"\be\.g\.", "eg"), (r"\bi\.e\.", "ie"), (r"\bvs\.", "vs"), (r"\betc\.", "etc"),
                  (r"\bapprox\.", "approx")]
_NEW_REQUIREMENT = r"(?:no|not|without|must|should|has|have|had|is|are|be|agree|agrees|willing|absence|negative)\b"
CLAUSE_SPLIT_RE = re.compile(r";\s*|(?<=[^\s\d.])\.\s+(?=[A-Z(])|,?\s+and\s+(?=" + _NEW_REQUIREMENT + ")")


def split_clauses(text: str) -> list[str]:
    t = text
    for pattern, repl in _ABBREVIATIONS:
        t = re.sub(pattern, repl, t, flags=re.I)
    return [p.strip(" .,:") for p in CLAUSE_SPLIT_RE.split(t) if p and p.strip(" .,:")]


# ================================================================ comparators and numbers

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
    return re.sub(r"\s+", " ", s).strip()


def _num(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
        return float(raw.replace(",", ""))
    return float(raw.replace(",", "."))


NUM = r"(\d+(?:[.,]\d+)*)"

# ================================================================ classifiers

ADMIN_RE = re.compile(
    r"informed consent|consent form|\bwilling|willingness|able to comply|comply with|contracepti|"
    r"\babstain|agree to|agree not|understanding that|documentation from|\bsigned\b|counsel"
)
PERMISSION_RE = re.compile(
    r"\b(?:are|is|will be|would be)\s+(?:also\s+)?(?:eligible|allowed|permitted|acceptable)\b|"
    r"\bcan be (?:included|enrolled)\b|\bmay (?:be )?(?:enrolled|included|eligible|participate)\b|"
    r"non-exclusionary|\bare not excluded\b|\b(?:is|are) not required\b"
)
CONDITIONAL_RE = re.compile(
    r"^(?:for|in)\s+(?:patients|participants|subjects|those|women|men|individuals|people)\b|^if\b|"
    r"\bif (?:indicated|applicable|present|positive|known)\b|\b(?:provided that|as long as|only if)\b|"
    r"^(?:patients|participants|subjects)\s+(?:with|who)\b.*\b(?:must|should)\b"
)
NEGATION_RE = re.compile(r"\b(no|not|without|free of|absence of|none of|negative for|non)\b")
QUALIFIER_RE = re.compile(
    r"\b(active|uncontrolled|untreated|symptomatic|unstable|significant|severe|moderate|requiring|"
    r"within (?:the )?(?:last |past )?\d+|in the (?:last|past) \d+|unless|except|other than)\b"
)
BREASTFEEDING_RE = re.compile(r"breast-?feed|lactat(?:ing|ion)|\bnursing\b")

CONDITIONS: list[tuple[str, str]] = [
    ("brain_mets", r"brain metasta|cns (?:metasta|involvement|lymphoma)|"
                   r"central nervous system (?:\(cns\) )?(?:involvement|metasta|lymphoma)|leptomeningeal"),
    ("hiv", r"\bhiv\b|human immunodeficiency virus"),
    ("hepatitis_b", r"hepatitis b\b|\bhbv\b"),
    ("hepatitis_c", r"hepatitis c\b|\bhcv\b"),
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
    ("pregnant", r"pregnan"),
]

LABS: list[tuple[str, str]] = [
    ("anc", r"absolute neutrophil count|\banc\b|neutrophil"),
    ("platelets", r"platelet|\bplts?\b"),
    ("hemoglobin", r"ha?emoglobin|\bhgb\b|\bhb\b"),
    ("crcl", r"creatinine clearance|\bcr\s?cl\b"),
    ("egfr", r"\begfr\b|estimated glomerular filtration|glomerular filtration rate|\bgfr\b"),
    ("creatinine", r"creatinine(?!\s*clearance)"),
    ("bilirubin", r"bilirubin"),
    ("ast", r"\bast\b|aspartate (?:amino)?transferase|\bsgot\b|transaminase"),
    ("alt", r"\balt\b|alanine (?:amino)?transferase|\bsgpt\b|transaminase"),
]
OTHER_KEYWORDS = re.compile(r"ecog|performance|karnofsky|line|prior|regimen|weight|bmi|"
                            + "|".join(p for _, p in LABS))

THRESHOLD_RE = re.compile(
    r"(>=|<=|>|<)\s*" + NUM + r"\s*((?:(?:x|times)\s*)?(?:the\s*)?(?:institutional\s*)?(?:upper limit of normal|uln))?"
)

# ================================================================ parsed pieces


@dataclass
class Parsed:
    category: str
    variable: str
    operator: str
    value: float | None = None
    value_max: float | None = None
    unit: str | None = None
    start: int = 0
    end: int = 0
    approximate: bool = False
    notes: list[str] = field(default_factory=list)
    spans: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Unmodeled:
    reason: str


# ---------------------------------------------------------------- age

_AGE_CONTEXT = re.compile(r"\bage\b|\baged\b|years? of age|years? old|\byrs?\b")
_OTHER_UNIT_AFTER = re.compile(r"^\s*(?:days?|weeks?|months?|hours?|mg|kg|g\b|g/|ml|mm|cm|%|x\b|times|cells|/)")


def _leftover_bounds(s: str, consumed: list[tuple[int, int]]) -> bool:
    for m in re.finditer(r"(>=|<=|>|<)\s*\d+(?:\.\d+)?", s):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        if _OTHER_UNIT_AFTER.match(s[m.end():]):
            continue
        if OTHER_KEYWORDS.search(s[max(0, m.start() - 40): m.start()]):
            continue
        return True
    return False


def parse_age(s: str) -> Parsed | Unmodeled | None:
    if not _AGE_CONTEXT.search(s):
        return None
    m = (re.search(r"(?:\baged?|between|from)\s*(\d{1,3})\s*(?:(?:years?|yrs?)(?:\s*(?:of age|old))?\s*)?"
                   r"(?:-|to|and)\s*(\d{1,3})\s*(?:years|yrs)", s)
         or re.search(r"\b(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\s*years?\s*(?:of age|old)", s))
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo > hi:
            return Unmodeled("Age range is reversed.")
        return Parsed("age", "age", "between", lo, hi, "years", m.start(), m.end())

    bounds: dict[tuple[str, float], tuple[int, int]] = {}
    for m in re.finditer(r"(>=|<=|>|<)\s*(\d{1,3})\s*(?:years?|yrs?)\b", s):
        bounds.setdefault((m.group(1), float(m.group(2))), m.span())
    for m in re.finditer(r"\bage[d]?\s*(>=|<=|>|<)\s*(\d{1,3})\b(?!\s*(?:years?|yrs?)\b)", s):
        bounds.setdefault((m.group(1), float(m.group(2))), m.span())
    for m in re.finditer(r"(\d{1,3})\s*(?:years?|yrs?)(?:\s*of age|\s*old)?\s*(?:or|and)\s*(older|>|younger|<)(?![=\s]*\d)", s):
        op = ">=" if m.group(2) in ("older", ">") else "<="
        bounds.setdefault((op, float(m.group(1))), m.span())
    if not bounds:
        return None
    consumed = list(bounds.values())
    if len(bounds) > 1 and any(not any(a <= m.start() < b for a, b in consumed)
                               for m in re.finditer(r"\bor\b", s)):
        return Unmodeled("Alternative age bounds cannot be represented as a single range.")
    if _leftover_bounds(s, consumed):
        return Unmodeled("Age criterion has bounds the parser could not read completely.")
    lows = [(op, v) for op, v in bounds if op in (">=", ">")]
    highs = [(op, v) for op, v in bounds if op in ("<=", "<")]
    if len(lows) > 1 or len(highs) > 1:
        return Unmodeled("Age criterion has more than one lower or upper bound.")
    start, end = min(a for a, _ in consumed), max(b for _, b in consumed)
    if lows and highs:
        lo = lows[0][1] if lows[0][0] == ">=" else lows[0][1] + 1  # ages are whole years
        hi = highs[0][1] if highs[0][0] == "<=" else highs[0][1] - 1
        if lo > hi:
            return Unmodeled("Age bounds do not overlap.")
        return Parsed("age", "age", "between", lo, hi, "years", start, end, spans=consumed)
    op, v = (lows or highs)[0]
    return Parsed("age", "age", op, v, unit="years", start=start, end=end)


# ---------------------------------------------------------------- performance status

_KPS_TO_ECOG = [(90, 0), (70, 1), (50, 2), (30, 3)]
_ECOG_KEY = re.compile(r"\becog\b|\bwho performance|performance status|\bzubrod\b")


def parse_ecog(s: str) -> Parsed | Unmodeled | None:
    key = _ECOG_KEY.search(s)
    if key:
        window = re.split(r"(?<!\d)[;.](?!\d)", s[key.end(): key.end() + 70])[0]
        mc = re.match(r"[^0-9<>]{0,45}?(<=|<|>=|>)\s*([0-4])\b", window)
        if mc:
            end = key.end() + mc.end()
            return Parsed("performance_status", "ecog", mc.group(1), float(mc.group(2)), start=key.start(), end=end)
        ml = re.match(r"[^0-9<>]{0,45}?([0-4](?:\s*(?:,\s*or|,\s*and|,|-|to|or|and)\s*[0-4])*)\b", window)
        if ml:
            seq = ml.group(1)
            nums = [int(x) for x in re.findall(r"[0-4]", seq)]
            if len(nums) == 2 and re.search(r"\d\s*(?:-|to)\s*\d", seq):
                lo, hi = min(nums), max(nums)
            else:
                values = sorted(set(nums))
                if values != list(range(values[0], values[-1] + 1)):
                    return Unmodeled("ECOG values listed are not a continuous range.")
                lo, hi = values[0], values[-1]
            end = key.end() + ml.end()
            if lo == 0:
                return Parsed("performance_status", "ecog", "<=", float(hi), start=key.start(), end=end)
            return Parsed("performance_status", "ecog", "between", float(lo), float(hi), start=key.start(), end=end)
    if "karnofsky" in s:
        m = re.search(r"karnofsky[^0-9]{0,40}?(>=|>)\s*(\d{2,3})", s)
        if m:
            kps = float(m.group(2))
            for cutoff, ecog in _KPS_TO_ECOG:
                if kps >= cutoff:
                    return Parsed("performance_status", "ecog", "<=", float(ecog), start=m.start(), end=m.end(),
                                  approximate=True,
                                  notes=[f"Karnofsky >= {kps:g} approximated as ECOG <= {ecog}."])
    return None


# ---------------------------------------------------------------- labs

_UNITS: list[tuple[str, re.Pattern]] = [
    ("10^9/L", re.compile(r"^(?:x\s*)?10\s*(?:\^|e|\*)?\s*9\s*/\s*l\b")),
    ("10^3/uL", re.compile(r"^(?:x\s*)?10\s*(?:\^|e|\*)?\s*3\s*/\s*(?:ul|mcl|mm\s*\^?\s*3)")),
    ("/uL", re.compile(r"^(?:cells\s*)?/\s*(?:ul|mcl|mm\s*\^?\s*3|microliter)")),
    ("g/dL", re.compile(r"^g\s*/\s*dl\b")),
    ("g/L", re.compile(r"^g\s*/\s*l\b")),
    ("mg/dL", re.compile(r"^mg\s*/\s*dl\b")),
    ("mg/L", re.compile(r"^mg\s*/\s*l\b")),
    ("umol/L", re.compile(r"^(?:u|micro)mol\s*/\s*l\b")),
    ("mmol/L", re.compile(r"^mmol\s*/\s*l\b")),
    ("U/L", re.compile(r"^(?:i?u|units?)\s*/\s*l\b")),
    ("mL/min/1.73m2", re.compile(r"^ml\s*/\s*min\s*(?:/|per)\s*1\.73")),
    ("mL/min", re.compile(r"^ml\s*/\s*min\b")),
    ("%", re.compile(r"^%")),
]
_CONVERSIONS: dict[str, tuple[str, dict[str, float]]] = {
    "anc": ("10^9/L", {"10^9/L": 1.0, "10^3/uL": 1.0, "/uL": 0.001}),
    "platelets": ("10^9/L", {"10^9/L": 1.0, "10^3/uL": 1.0, "/uL": 0.001}),
    "hemoglobin": ("g/dL", {"g/dL": 1.0, "g/L": 0.1, "mmol/L": 1.611}),
    "creatinine": ("mg/dL", {"mg/dL": 1.0, "umol/L": 1 / 88.4, "mmol/L": 1000 / 88.4}),
    "bilirubin": ("mg/dL", {"mg/dL": 1.0, "umol/L": 1 / 17.1, "mmol/L": 1000 / 17.1}),
    "ast": ("U/L", {"U/L": 1.0}),
    "alt": ("U/L", {"U/L": 1.0}),
    "egfr": ("mL/min/1.73m2", {"mL/min/1.73m2": 1.0}),
    "crcl": ("mL/min", {"mL/min": 1.0}),
}
_ULN_SUPPORTED = {"creatinine", "bilirubin", "ast", "alt"}
# These tokens start surrounding prose, not a unit. Other explicit suffixes
# must be recognized rather than silently treated as absent units.
_UNIT_CONTEXT_RE = re.compile(
    r"^(?:$|[),.;:]|\(|(?:and|or|at|during|within|before|after|measured|determined|calculated|"
    r"using|by|on|for|in|per|as|if|unless|except|to|with|without|required|must|should)\b)"
)


def _detect_unit(text: str) -> str | None:
    t = text.strip().lstrip("(").lstrip()
    for unit, pattern in _UNITS:
        if pattern.match(t):
            return unit
    return None


def _infer_unit(variable: str, value: float) -> str:
    if variable in ("anc",):
        return "/uL" if value >= 100 else "10^9/L"
    if variable == "platelets":
        return "/uL" if value >= 1000 else "10^9/L"
    if variable == "hemoglobin":
        return "g/L" if value > 25 else "g/dL"
    if variable == "creatinine":
        return "umol/L" if value > 20 else "mg/dL"
    if variable == "bilirubin":
        return "umol/L" if value > 10 else "mg/dL"
    return _CONVERSIONS[variable][0]


def _convert_lab(variable: str, value: float, uln: bool, unit_text: str) -> tuple[float, str, list[str]] | str:
    label = VARIABLES[variable]["label"]
    if uln:
        if variable in _ULN_SUPPORTED:
            return value, "x_uln", []
        return f"'x ULN' threshold is not supported for {label}."
    notes: list[str] = []
    unit = _detect_unit(unit_text)
    if unit is None:
        unit_candidate = unit_text.strip().lstrip("(").lstrip()
        if not _UNIT_CONTEXT_RE.match(unit_candidate):
            return f"Unit suffix {unit_text.strip()[:30]!r} is not supported for {label}."
        unit = _infer_unit(variable, value)
        notes.append(f"{label}: unit not stated; assumed {unit}.")
    canonical, table = _CONVERSIONS[variable]
    if unit not in table:
        return f"Unit {unit} is not supported for {label}."
    return round(value * table[unit], 4), canonical, notes


def parse_labs(s: str) -> tuple[list[Parsed], list[str]]:
    mentions = []
    for variable, pattern in LABS:
        for m in re.finditer(pattern, s):
            mentions.append((m.start(), m.end(), variable))
    if not mentions:
        return [], []
    mentions.sort()
    renal_method_ckd = bool(re.search(r"ckd-?epi|mdrd", s))
    measured_crcl = bool(re.search(r"measured|24[- ]?h(?:ou)?r|urine collection|timed urine", s))
    has_exception = bool(re.search(r"\bif\b|\bunless\b|\bexcept\b|\bin patients with\b", s))

    results: dict[str, Parsed] = {}
    failures: list[str] = []
    assigned: set[int] = set()
    for t in THRESHOLD_RE.finditer(s):
        pending = [i for i, (_, end, _) in enumerate(mentions) if i not in assigned and end <= t.start()]
        if not pending:
            continue
        value, uln = _num(t.group(2)), bool(t.group(3))
        for i in pending:
            assigned.add(i)
            start, _, variable = mentions[i]
            if variable == "crcl" and renal_method_ckd and "egfr" not in {m[2] for m in mentions}:
                variable = "egfr"
            if variable in results:
                continue
            converted = _convert_lab(variable, value, uln, s[t.end(): t.end() + 30])
            if isinstance(converted, str):
                failures.append(converted)
                continue
            v, unit, notes = converted
            parsed = Parsed("lab", variable, t.group(1), v, unit=unit, start=start, end=t.end(),
                            approximate=bool(notes), notes=list(notes))
            if variable == "crcl" and measured_crcl:
                parsed.approximate = True
                parsed.notes.append("Measured (urine) clearance requested; modeled with a Cockcroft-Gault estimate.")
            if has_exception:
                parsed.approximate = True
                parsed.notes.append("Subgroup exception thresholds (for example 'if liver metastases') are not modeled.")
            results[variable] = parsed
    return list(results.values()), failures


# ---------------------------------------------------------------- prior therapy

IMMUNO_RE = re.compile(r"check\s?point inhibitor|anti-?pd-?l?1|anti-?ctla-?4?|immunotherap|immune therap|"
                       r"immune-oncology|immuno-oncology")
OTHER_THERAPY_RE = re.compile(r"combination|tyrosine kinase|\btkis?\b|chemotherap|chemo-|targeted therap|"
                              r"radiation|radiotherap|surgery|resection|transplant|nephrectomy|metastasectomy")
PRIOR_CONTEXT_RE = re.compile(r"\b(?:prior|previous|previously|received|receiving|treated with|treatment with|"
                              r"exposure to|had)\b")
THERAPY_WORD_RE = re.compile(r"therap|treatment|regimen|\blines?\b|chemo|radiation|radiotherap|surgery|resection|"
                             r"transplant|inhibitor|antibod|agent|\bdrug|vaccine|nephrectomy|metastasectomy")
SETTING_RE = re.compile(r"metastatic|advanced|adjuvant|neoadjuvant|setting|for (?:this|the) disease")


def _negated_before(s: str, pos: int) -> bool:
    segment = s[:pos]
    cut = max(segment.rfind(","), segment.rfind(";"), segment.rfind(":"), segment.rfind("("))
    return bool(NEGATION_RE.search(segment[cut + 1:][-60:]))


def parse_prior_therapy(s: str, kind: str) -> Parsed | Unmodeled | None:
    immuno = IMMUNO_RE.search(s)
    if immuno and PRIOR_CONTEXT_RE.search(s) and not OTHER_THERAPY_RE.search(s):
        if re.search(r"toxicit|adverse (?:event|reaction)|intoleran|progress(?:ed|ion)|"
                     r"refractor|resistan|(?:lack of|no) response|failed to respond", s):
            return Unmodeled("Treatment outcome or toxicity is not modeled by prior exposure.")
        timing = bool(re.search(r"within|in the (?:last|past)|months?|weeks?", s))
        notes = ["Timing window is not modeled; any prior exposure counts."] if timing else []
        op = "absent" if _negated_before(s, immuno.start()) else "present"
        return Parsed("prior_therapy", "prior_immunotherapy", op, start=immuno.start(), end=immuno.end(),
                      approximate=timing, notes=notes)

    typed = bool(OTHER_THERAPY_RE.search(s) or IMMUNO_RE.search(s) or SETTING_RE.search(s))
    type_note = ["Therapy type or setting is not modeled; any prior systemic line counts."] if typed else []
    m = re.search(r"(>=|<=|>|<)\s*(\d+)\s*(?:prior|previous|lines?|regimens?)\b", s)
    if m:
        notes = list(type_note)
        if kind == "exclusion" and m.group(1) in ("<=", "<"):
            notes.append("Exclusion phrased as a maximum: check whether the wording is inverted.")
        return Parsed("prior_therapy", "prior_systemic_lines", m.group(1), float(m.group(2)), unit="lines",
                      start=m.start(), end=m.end(), approximate=typed, notes=notes)
    m = re.search(r"(\d+)\s*(?:or more|\+)\s*(?:prior|previous)?\s*(?:lines?|regimens?)", s)
    if m:
        return Parsed("prior_therapy", "prior_systemic_lines", ">=", float(m.group(1)), unit="lines",
                      start=m.start(), end=m.end(), approximate=typed, notes=list(type_note))
    m = re.search(r"\b(?:no|without)\s+(?:any\s+)?(?:prior|previous)\s+(?:systemic|anti-?cancer)\s+"
                  r"(?:therapy|treatment)|treatment-?naive", s)
    if m and not OTHER_THERAPY_RE.search(s):
        return Parsed("prior_therapy", "prior_systemic_lines", "==", 0.0, unit="lines", start=m.start(), end=m.end())
    m = re.search(r"\b(?:any\s+)?prior\s+systemic\s+(?:therapy|treatment)", s)
    if kind == "exclusion" and m and not typed:
        return Parsed("prior_therapy", "prior_systemic_lines", ">=", 1.0, unit="lines", start=m.start(), end=m.end())
    if PRIOR_CONTEXT_RE.search(s) and THERAPY_WORD_RE.search(s):
        return Unmodeled("Restriction on a specific prior treatment is not modeled.")
    return None


# ---------------------------------------------------------------- conditions

def parse_conditions(s: str, kind: str, taken: list[tuple[int, int]]) -> list[Parsed]:
    found: list[Parsed] = []
    seen: set[str] = set()
    for variable, pattern in CONDITIONS:
        m = re.search(pattern, s)
        if not m or variable in seen or any(a <= m.start() < b for a, b in taken):
            continue
        seen.add(variable)
        category = "pregnancy" if variable == "pregnant" else "condition"
        negated = _negated_before(s, m.start())
        if kind == "inclusion":
            if variable == "pregnant" and re.search(r"negative|rule out|not pregnant|non-?pregnant", s):
                found.append(Parsed(category, variable, "absent", start=m.start(), end=m.end()))
            elif negated:
                found.append(Parsed(category, variable, "absent", start=m.start(), end=m.end()))
            # an inclusion that requires a condition is ambiguous (often disease-defining): leave it
            continue
        parsed = Parsed(category, variable, "absent" if negated else "present", start=m.start(), end=m.end())
        if negated:
            parsed.notes.append("Exclusion is phrased negatively; check the wording.")
        found.append(parsed)
    if found and QUALIFIER_RE.search(s):
        for p in found:
            p.approximate = True
            p.notes.append("Severity, timing or exception qualifiers are not modeled; any history counts.")
    return found


# ---------------------------------------------------------------- one clause

@dataclass
class ClauseResult:
    text: str
    tag: str  # items | administrative | permission | conditional | compound | unmodeled | unparsed | filler
    items: list[Parsed] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    partial_failures: list[str] = field(default_factory=list)


_LIST_SEPARATOR = re.compile(r"[\s,;/()\[\]]*(?:(?:and/or|or|and)[\s,;/()\[\]]*)?")


def _is_compound(items: list[Parsed], s: str, kind: str) -> bool:
    if len(items) < 2:
        return False
    ordered = sorted(items, key=lambda p: p.start)
    betweens = [s[a.end: b.start] for a, b in zip(ordered, ordered[1:])]
    if kind == "inclusion":
        return any(re.search(r"\bor\b", b) for b in betweens)  # OR cannot be represented as AND
    if re.search(r"\bboth\b|\bin combination with\b|\btogether with\b", s):
        return True
    for b in betweens:
        if not _LIST_SEPARATOR.fullmatch(b):
            return True  # words between conditions change their meaning
    span = s[ordered[0].start: ordered[-1].end]
    if len(ordered) == 2 and re.fullmatch(r"\s*and\s*", betweens[0]) and "," not in span:
        return True  # "X and Y" in an exclusion may mean both together
    return False


# Labs trials often list that the simulator has no variable for.
UNMODELED_LAB_RE = re.compile(
    r"\bwbc\b|white blood cell|leukocyte|\balbumin\b|\binr\b|\ba?ptt\b|prothrombin|lymphocyte|\bldh\b|"
    r"lactate dehydrogenase|alkaline phosphatase|\balp\b|amylase|lipase|magnesium|potassium|calcium|sodium|"
    r"\btsh\b|troponin|urine protein|proteinuria|\blvef\b|ejection fraction|\bqtc\b")


def _unconsumed_bounds(s: str, items: list[Parsed]) -> tuple[bool, list[str]]:
    """Return (blocking, separately_unmodeled) for comparisons not owned by a parsed item.

    Parenthetical subgroup exceptions already carry an approximation warning. A comparison
    that directly follows a lab we do not model (e.g. 'WBC>=3.5') in a comma/AND list is its
    own requirement: it is kept as a visible unmodeled part instead of discarding the labs we
    can model. Any other leftover comparison (an extra bound on a modeled variable, or an
    unnamed number) still blocks the clause. OR lists are never split.
    """
    spans = [span for p in items for span in (p.spans or [(p.start, p.end)])]
    exceptions = [m.span() for m in re.finditer(r"\([^)]*\b(?:if|unless|except)\b[^)]*\)", s)]
    has_or = any(not any(a <= m.start() < b for a, b in spans) for m in re.finditer(r"\bor\b", s))
    separate: list[str] = []
    for bound in THRESHOLD_RE.finditer(s):
        if any(a <= bound.start() < b for a, b in spans):
            continue
        if any(a <= bound.start() < b for a, b in exceptions) and any(p.approximate for p in items):
            continue
        prefix = s[:bound.start()]
        cut = max([prefix.rfind(ch) for ch in ",;:"] + [b for a, b in spans if b <= bound.start()] + [-1])
        segment = prefix[cut + 1:]
        if not has_or and UNMODELED_LAB_RE.search(segment) and not any(re.search(p, segment) for _, p in LABS):
            unit = re.match(r"[^,;]*", s[bound.end():]).group(0).strip()
            separate.append(f"{(segment.strip() + ' ' + bound.group(0).strip() + ' ' + unit).strip()} "
                            "(no cohort field for this lab; not modeled)")
            continue
        return True, []
    return False, separate


def _unparsed_conjuncts(s: str, items: list[Parsed]) -> list[str]:
    """Retain conjuncts without a parsed item, rather than claiming full coverage."""
    spans = [span for p in items for span in (p.spans or [(p.start, p.end)])]
    connectors = [m for m in re.finditer(r"\b(?:and|or)\b", s)
                  if not any(a <= m.start() < b for a, b in spans)]
    if not connectors:
        return []
    starts = [0] + [m.end() for m in connectors]
    ends = [m.start() for m in connectors] + [len(s)]
    leftovers = []
    for start, end in zip(starts, ends):
        part = s[start:end].strip(" ,:;()")
        if not part or any(a < end and b > start for a, b in spans):
            continue
        if ADMIN_RE.search(part) or PERMISSION_RE.search(part):
            continue
        if BREASTFEEDING_RE.search(part):
            continue  # already retained as an explicit unmodeled requirement
        if re.fullmatch(r"(?:older|younger|above|below|over|under)", part):
            continue
        leftovers.append(f"Additional requirement is not modeled: {part}")
    return leftovers


BOTH_SEXES_RE = re.compile(r"\b(?:males?|men) (?:or|and) (?:females?|women)\b|\b(?:females?|women) (?:or|and) (?:males?|men)\b")


def parse_clause(clause: str, kind: str) -> ClauseResult:
    s = cmp_normalize(normalize_text(clause))
    # "Males or females" places no restriction; its "or" must not trigger compound-logic refusal.
    s = BOTH_SEXES_RE.sub("participants", s)
    if len(re.findall(r"[a-z]{2,}", s)) < 2 and not re.search(r"\d", s):
        return ClauseResult(clause, "filler")
    if kind == "inclusion" and CONDITIONAL_RE.search(s):
        return ClauseResult(clause, "conditional",
                            notes=["Applies only to a subgroup (conditional requirement); not modeled."])

    items: list[Parsed] = []
    failures: list[str] = []
    biomarker = re.fullmatch(r"(?:documented |confirmed |known )?(egfr mutation|alk rearrangement) (positive|negative)(?: status)?", s)
    if biomarker:
        items.append(Parsed("condition", "egfr_mutation_positive" if biomarker.group(1) == "egfr mutation" else "alk_positive",
                            "present" if biomarker.group(2) == "positive" else "absent", start=0, end=len(s)))
    if BREASTFEEDING_RE.search(s):
        failures.append("Breastfeeding status is not modeled by the pregnancy variable.")
    for parsed in (parse_age(s), parse_ecog(s)):
        if isinstance(parsed, Unmodeled):
            failures.append(parsed.reason)
        elif parsed:
            items.append(parsed)
    labs, lab_failures = parse_labs(s)
    items.extend(labs)
    failures.extend(lab_failures)
    prior = parse_prior_therapy(s, kind)
    numeric = bool(items)

    if not numeric:
        if PERMISSION_RE.search(s):
            return ClauseResult(clause, "permission",
                                notes=["Permissive statement: it widens eligibility, so it is not simulated."])

    if isinstance(prior, Parsed):
        items.append(prior)
    taken = [(p.start, p.end) for p in items]
    items.extend(parse_conditions(s, kind, taken))

    if _is_compound(items, s, kind):
        return ClauseResult(clause, "compound", notes=[
            "Combines requirements with OR/AND in a way the simulator cannot represent; not modeled."])
    if items:
        blocking, separate_labs = _unconsumed_bounds(s, items)
        if blocking:
            return ClauseResult(clause, "unmodeled", notes=[
                "Additional numeric bounds could not be read completely; the clause is not modeled."])
        failures.extend(f"Additional requirement is not modeled: {text}" for text in separate_labs)
    if items:
        unparsed = _unparsed_conjuncts(s, items)
        unsafe_connector = "or" if kind == "inclusion" else "and"
        if unparsed and any(not any(a <= m.start() < b for p in items
                                    for a, b in (p.spans or [(p.start, p.end)]))
                            for m in re.finditer(r"\b" + unsafe_connector + r"\b", s)):
            return ClauseResult(clause, "compound", notes=[
                "An unmodeled requirement is part of a logical group; the whole clause is not modeled."])
        failures.extend(unparsed)
        if isinstance(prior, Unmodeled):
            failures.append(prior.reason)
        notes = []
        if ADMIN_RE.search(s):
            notes.append("Also includes an administrative requirement (not simulated).")
        return ClauseResult(clause, "items", items=items, notes=notes, partial_failures=failures)
    if ADMIN_RE.search(s):
        return ClauseResult(clause, "administrative", notes=["Administrative requirement; not simulated."])
    if failures:
        return ClauseResult(clause, "unmodeled", notes=failures)
    if isinstance(prior, Unmodeled):
        return ClauseResult(clause, "unmodeled", notes=[prior.reason])
    return ClauseResult(clause, "unparsed")


# ================================================================ assembling rules

def _rule_from(rid: str, kind: str, text: str, clause: str, p: Parsed, extra_notes: list[str]) -> Rule:
    meta = meta_for(p.variable)
    try:
        return Rule(
            id=rid, kind=kind, text=text, clause=clause, category=p.category, variable=p.variable,
            operator=p.operator, value=p.value, value_max=p.value_max, unit=p.unit, simulatable=True,
            fidelity="approximate" if p.approximate else "exact",
            purpose=meta["purpose"] if meta else "unknown",
            findability=meta["findability"] if meta else "unknown",
            safety_critical=meta["safety_critical"] if meta else False,
            parsed_by="rules", notes=(p.notes + extra_notes)[:20],
        )
    except ValidationError:
        return Rule(id=rid, kind=kind, text=text, clause=clause, parsed_by="rules",
                    notes=["Parsed values failed validation; not modeled."])


_UNMODELED_PRIORITY = ["compound", "conditional", "unmodeled", "unparsed"]


def _leftover_rule(rid: str, kind: str, text: str, clause: str | None, results: list[ClauseResult]) -> Rule:
    tags = {r.tag for r in results}
    tag = next(t for t in _UNMODELED_PRIORITY if t in tags)
    notes = [n for r in results for n in r.notes]
    category = tag if tag in ("compound", "conditional") else "other"
    parsed_by = "none" if tags == {"unparsed"} else "rules"
    if re.search(r"per protocol|as described in the protocol|as defined in the protocol", text, re.I):
        notes.append("Details are in the full protocol, not in the registry text.")
    return Rule(id=rid, kind=kind, text=text, clause=clause, category=category, parsed_by=parsed_by,
                notes=notes[:20])


def parse_criterion(rid: str, kind: str, text: str, uncertain: bool = False) -> list[Rule]:
    clean = normalize_text(text)
    clauses = split_clauses(clean)
    results = [parse_clause(c, kind) for c in clauses] or [ClauseResult(clean, "unparsed")]
    if any(r.tag == "conditional" for r in results) and any(r.items for r in results):
        return [Rule(id=rid, kind=kind, text=text, category="conditional", parsed_by="rules", notes=[
            "The scope of a subgroup requirement across these clauses is unclear; not modeled."])]
    # Splitting must not erase an OR across inclusion clauses, or turn an
    # explicitly conjoined exclusion into several independent exclusions.
    clinical = [r for r in results if r.tag not in ("administrative", "permission", "filler")]
    cross_or = any(re.match(r"(?:or|alternatively)\b", c, re.I) for c in clauses[1:])
    cross_or |= any(re.search(r"\bor\s*$", c, re.I) for c in clauses[:-1])
    split_and = re.search(r"\band\s+(?=" + _NEW_REQUIREMENT + ")", clean, re.I)
    if ((kind == "inclusion" and cross_or) or (kind == "exclusion" and split_and and len(clinical) > 1)):
        return [Rule(id=rid, kind=kind, text=text, category="compound", parsed_by="rules", notes=[
            "Logical connectors between clauses cannot be represented faithfully; not modeled."])]

    item_pairs = [(r, p) for r in results if r.tag == "items" for p in r.items]
    leftovers = [r for r in results if r.tag in _UNMODELED_PRIORITY]
    for r in results:
        for failure in r.partial_failures:
            leftovers.append(ClauseResult(r.text, "unmodeled", notes=[failure]))

    if not item_pairs:
        if leftovers:
            return [_leftover_rule(rid, kind, text, None, leftovers)]
        tags = {r.tag for r in results}
        if "administrative" in tags:
            return [Rule(id=rid, kind=kind, text=text, category="administrative", purpose="administrative",
                         findability="patient_reported", parsed_by="rules",
                         notes=["Administrative requirement; not simulated."])]
        if "permission" in tags:
            return [Rule(id=rid, kind=kind, text=text, category="permission", parsed_by="rules",
                         notes=["Permissive statement: it widens eligibility, so it is not simulated."])]
        return [Rule(id=rid, kind=kind, text=text)]

    extra = [n for r in results if r.tag == "items" for n in r.notes]
    extra += [f"Also contains an exception that widens eligibility (not modeled): \"{r.text[:120]}\""
              for r in results if r.tag == "permission"]
    extra += [f"Also contains an administrative requirement (not simulated): \"{r.text[:120]}\""
              for r in results if r.tag == "administrative"]

    total = len(item_pairs) + len(leftovers)
    rules: list[Rule] = []
    for i, (res, p) in enumerate(item_pairs):
        sub_id = rid if total == 1 else f"{rid}{chr(97 + i)}"
        rule = _rule_from(sub_id, kind, text, res.text, p, extra)
        if uncertain and rule.simulatable:
            if rule.operator in ("present", "absent"):
                rule = Rule(id=sub_id, kind=kind, text=text, clause=res.text, parsed_by="rules",
                            notes=["No inclusion/exclusion header before this criterion; direction unclear, "
                                   "so it is not modeled."])
            else:
                rule.notes.append("No inclusion/exclusion header before this criterion; treated as inclusion.")
        rules.append(rule)
    for j, res in enumerate(leftovers):
        sub_id = f"{rid}{chr(97 + len(item_pairs) + j)}"
        leftover = _leftover_rule(sub_id, kind, text, res.text, [res])
        leftover.notes.append(f"Part of criterion {rid} that is not modeled.")
        rules.append(leftover)
    return rules


def parse_eligibility_rules(text: str) -> tuple[list[Rule], list[str]]:
    """Deterministic parse of a full eligibility section. Returns (rules, warnings)."""
    rules: list[Rule] = []
    warnings: list[str] = []
    counters = {"inclusion": 0, "exclusion": 0}
    criteria = split_criteria(text)
    for item in criteria:
        counters[item.kind] += 1
        prefix = "I" if item.kind == "inclusion" else "E"
        new = parse_criterion(f"{prefix}{counters[item.kind]}", item.kind, item.text, item.uncertain)
        if item.uncertain:
            for r in new:
                if r.parsed_by == "none":
                    r.parsed_by = "rules"
                    r.notes.append("No inclusion/exclusion header before this criterion; not sent to AI.")
        rules.extend(new)
    if criteria and all(c.uncertain for c in criteria):
        warnings.append("No inclusion/exclusion headers were found; criteria were treated as inclusion "
                        "and yes/no conditions were not modeled. Add headers for a better analysis.")
    return rules, warnings
