"""Convert Synthea CSV output into the compact cohort file the backend loads.

Usage:
    python dataset/synthea/build_cohort.py <synthea csv dir> <output json> [--profile adults|nsclc] [--seed N]

Only living patients on the reference date are kept. Names, addresses, SSNs and other
identifiers are never copied; patients get a short pseudonymous ID.

A variable is filled only from data Synthea actually simulates. When Synthea does not
model something (ECOG, ANC, brain metastases, hepatitis B/C, ...), the value is null
("unknown"), never invented. When Synthea does model a condition, its absence is a real "no".
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

REFERENCE_DATE = date(2026, 10, 1)   # must match generate.sh
LAB_LOOKBACK_DAYS = 3 * 365          # latest lab value within this window, else unknown
COHORT_FORMAT = "clinova-synthea-cohort-v1"

# LOINC codes, in order of preference, for each numeric variable.
LABS = {
    "hemoglobin": (["718-7"], "g/dL"),
    "platelets": (["777-3"], "10*3/uL"),          # 10^3/uL == 10^9/L
    "creatinine": (["2160-0", "38483-4"], "mg/dL"),
    "egfr": (["33914-3"], "mL/min/{1.73_m2}"),
    "bilirubin": (["1975-2"], "mg/dL"),           # serum, not the urine dipstick 20505-4
    "ast": (["1920-8"], "U/L"),
    "alt": (["1742-6"], "U/L"),
    "weight": (["29463-7"], "kg"),
    "systolic_bp": (["8480-6"], "mm[Hg]"),
    "diastolic_bp": (["8462-4"], "mm[Hg]"),
}

# Condition definitions use Synthea's SNOMED descriptions. Each entry is something Synthea simulates.
COND = {
    "hiv": re.compile(r"human immunodeficiency virus|\bHIV\b", re.I),
    "pregnant": re.compile(r"pregnan", re.I),
    # "Significant cardiac disease" as trial exclusions use it: heart failure, arrhythmia, unstable angina,
    # cardiomyopathy or serious valve disease. Stable ischemic heart disease and old MI history are excluded
    # on purpose; a recent MI is handled separately (RECENT_MI, onset within 180 days).
    "cardiac_disease": re.compile(r"heart failure|atrial fibrillation|unstable angina|cardiomyopathy|"
                                  r"aortic valve stenosis|mitral valve stenosis", re.I),
    "hypertension": re.compile(r"hypertension", re.I),
    "thromboembolic": re.compile(r"embolism|thrombosis|cerebrovascular accident|\bstroke\b|ischemic stroke", re.I),
    "infection": re.compile(r"\bacute\b.*(sinusitis|pharyngitis|bronchitis|cystitis|otitis|tonsillitis)|pneumonia|sepsis|"
                            r"septic|streptococcal sore throat|viral sinusitis|viral pharyngitis|infection|"
                            r"coronavirus|COVID|cellulitis|tuberculosis|appendicitis", re.I),
    "autoimmune": re.compile(r"lupus|rheumatoid arthritis", re.I),
    "malignancy": re.compile(r"malignant|carcinoma(?! in situ)|\bcancer\b|leukemia|lymphoma|neoplasm of prostate", re.I),
}
RECENT_MI = re.compile(r"acute .*myocardial infarction|^myocardial infarction", re.I)
NOT_CURRENT_PREGNANCY =re.compile(r"history|miscarriage|past pregnancy|tubal|preeclampsia history", re.I)
NOT_ACTIVE_INFECTION = re.compile(r"chronic|recurrent|history|suspected|screening|exposure|carrier|immunodeficiency", re.I)
NOT_MALIGNANCY = re.compile(r"suspected|history of|screening|benign|in situ", re.I)

IMMUNOSUPPRESSANT = re.compile(r"prednisone|prednisolone|methylprednisolone|dexamethasone|hydrocortisone(?!.*topical)|"
                               r"methotrexate|tacrolimus|cyclosporine|azathioprine|mycophenolate|sirolimus", re.I)
ANTINEOPLASTIC = re.compile(r"cisplatin|carboplatin|paclitaxel|docetaxel|etoposide|pemetrexed|gemcitabine|vinorelbine|"
                            r"cyclophosphamide|doxorubicin|epirubicin|fluorouracil|capecitabine|oxaliplatin|irinotecan|"
                            r"leucovorin|cytarabine|daunorubicin|idarubicin|trastuzumab|tamoxifen|letrozole|anastrozole|"
                            r"exemestane|leuprolide|bicalutamide|abiraterone|enzalutamide|imatinib", re.I)
LIVE_VACCINE = re.compile(r"\blive\b|MMR|measles|varicella|zoster vaccine live|yellow fever|rotavirus|typhoid.*oral|"
                          r"influenza.*(nasal|LAIV)", re.I)

NOT_SIMULATED = {
    "ecog": "Synthea does not record performance status.",
    "anc": "Synthea records total white cells (6690-2) but not absolute neutrophil count.",
    "crcl": None,  # derived below, documented in variable_sources
    "brain_mets": "Synthea's lung cancer module does not record CNS metastases.",
    "hepatitis_b": "Synthea has no hepatitis B disease module (only screening).",
    "hepatitis_c": "Synthea has no hepatitis C disease module (only screening).",
    "ibd": "Synthea has no inflammatory bowel disease module.",
    "hepatic_impairment": "Synthea has no cirrhosis/liver failure module.",
    "interstitial_lung_disease": "Synthea has no interstitial lung disease module.",
    "myocarditis_history": "Synthea has no myocarditis module.",
    "drug_hypersensitivity": "Hypersensitivity to a specific investigational drug cannot be known.",
    "recent_major_surgery": "Not derived: classifying 'major' surgery from procedure codes is not reliable.",
    "prior_immunotherapy": "Synthea does not simulate checkpoint inhibitors or other immunotherapy.",
    "egfr_mutation_positive": "Synthea does not simulate tumor biomarkers.",
    "alk_positive": "Synthea does not simulate tumor biomarkers.",
}


def d(text: str) -> date | None:
    return datetime.fromisoformat(text[:10]).date() if text else None


def active_on(start: date | None, stop: date | None, day: date) -> bool:
    return start is not None and start <= day and (stop is None or stop > day)


def cockcroft_gault(creatinine, age, weight, female):
    if None in (creatinine, age, weight, female) or creatinine <= 0:
        return None
    return round((140 - age) * weight / (72 * creatinine) * (0.85 if female else 1.0), 1)


def build(csv_dir: Path, profile: str, seed: int | None) -> dict:
    ref = REFERENCE_DATE
    patients: dict[str, dict] = {}
    deceased = 0
    with open(csv_dir / "patients.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["DEATHDATE"]:
                deceased += 1
                continue
            born = d(r["BIRTHDATE"])
            age = ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))
            patients[r["Id"]] = {"age": age, "female": r["GENDER"] == "F"}

    # Latest lab value within the lookback window.
    latest: dict[tuple[str, str], tuple[date, float]] = {}
    code_to_var = {code: (var, rank) for var, (codes, _) in LABS.items() for rank, code in enumerate(codes)}
    with open(csv_dir / "observations.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = r["PATIENT"]
            if pid not in patients or r["CODE"] not in code_to_var or r["TYPE"] != "numeric":
                continue
            when = d(r["DATE"])
            if when is None or when > ref or (ref - when).days > LAB_LOOKBACK_DAYS:
                continue
            var, rank = code_to_var[r["CODE"]]
            try:
                value = float(r["VALUE"])
            except ValueError:
                continue
            key = (pid, var)
            old = latest.get(key)
            # Prefer the most recent value; on the same day prefer the higher-ranked code.
            if old is None or (when, -rank) > (old[0], -old[2]):
                latest[key] = (when, value, rank)

    flags: dict[str, set[str]] = defaultdict(set)
    with open(csv_dir / "conditions.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = r["PATIENT"]
            if pid not in patients:
                continue
            desc, start, stop = r["DESCRIPTION"], d(r["START"]), d(r["STOP"])
            is_active = active_on(start, stop, ref)
            if is_active and COND["hiv"].search(desc):
                flags[pid].add("hiv")
            if is_active and COND["pregnant"].search(desc) and not NOT_CURRENT_PREGNANCY.search(desc):
                flags[pid].add("pregnant")
            if is_active and COND["cardiac_disease"].search(desc):
                flags[pid].add("cardiac_disease")
            if start and start <= ref and (ref - start).days <= 180 and RECENT_MI.search(desc):
                flags[pid].add("cardiac_disease")
            if is_active and COND["hypertension"].search(desc):
                flags[pid].add("hypertension")
            if start and start <= ref and (ref - start).days <= 180 and COND["thromboembolic"].search(desc):
                flags[pid].add("thromboembolic_event_recent")
            if is_active and COND["infection"].search(desc) and not NOT_ACTIVE_INFECTION.search(desc):
                flags[pid].add("active_infection")
            if is_active and COND["autoimmune"].search(desc):
                flags[pid].add("autoimmune_active")
            if start and start <= ref and COND["malignancy"].search(desc) and not NOT_MALIGNANCY.search(desc):
                flags[pid].add("prior_malignancy")

    chemo_starts: dict[str, list[date]] = defaultdict(list)
    with open(csv_dir / "medications.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = r["PATIENT"]
            if pid not in patients:
                continue
            desc, start, stop = r["DESCRIPTION"], d(r["START"]), d(r["STOP"])
            if active_on(start, stop, ref) and IMMUNOSUPPRESSANT.search(desc):
                flags[pid].add("systemic_immunosuppression")
            if start and start <= ref and ANTINEOPLASTIC.search(desc):
                chemo_starts[pid].append(start)

    immunizations = csv_dir / "immunizations.csv"
    if immunizations.exists():
        with open(immunizations, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                when = d(r["DATE"])
                if r["PATIENT"] in patients and when and when <= ref and (ref - when).days <= 30 \
                        and LIVE_VACCINE.search(r["DESCRIPTION"]):
                    flags[r["PATIENT"]].add("recent_live_vaccine")

    def lab(pid, var):
        hit = latest.get((pid, var))
        return round(hit[1], 3) if hit else None

    rows = []
    for pid, base in patients.items():
        f = flags[pid]
        weight = lab(pid, "weight")
        creatinine = lab(pid, "creatinine")
        systolic, diastolic = lab(pid, "systolic_bp"), lab(pid, "diastolic_bp")
        if "hypertension" not in f:
            uncontrolled = False
        elif systolic is None and diastolic is None:
            uncontrolled = None
        else:
            uncontrolled = (systolic or 0) >= 160 or (diastolic or 0) >= 100
        # Synthea writes chemotherapy as daily orders across cycles. A new treatment line starts only
        # after a gap of more than 90 days without antineoplastic orders.
        lines, last = 0, None
        for start in sorted(chemo_starts[pid]):
            if last is None or (start - last).days > 90:
                lines += 1
            last = start
        row = {
            "patient_id": "SYN-" + hashlib.sha256(pid.encode()).hexdigest()[:10].upper(),
            "synthetic": True,
            "age": base["age"],
            "female": base["female"],
            "hemoglobin": lab(pid, "hemoglobin"),
            "platelets": lab(pid, "platelets"),
            "creatinine": creatinine,
            "egfr": lab(pid, "egfr"),
            "crcl": cockcroft_gault(creatinine, base["age"], weight, base["female"]),
            "bilirubin": lab(pid, "bilirubin"),
            "ast": lab(pid, "ast"),
            "alt": lab(pid, "alt"),
            "weight": weight,
            "prior_systemic_lines": lines,
            "hiv": "hiv" in f,
            "pregnant": base["female"] and "pregnant" in f,
            "cardiac_disease": "cardiac_disease" in f,
            "uncontrolled_hypertension": uncontrolled,
            "thromboembolic_event_recent": "thromboembolic_event_recent" in f,
            "active_infection": "active_infection" in f,
            "autoimmune_active": "autoimmune_active" in f,
            "prior_malignancy": "prior_malignancy" in f,
            "systemic_immunosuppression": "systemic_immunosuppression" in f,
            "recent_live_vaccine": "recent_live_vaccine" in f,
        }
        for var in NOT_SIMULATED:
            row.setdefault(var, None)
        rows.append(row)
    rows.sort(key=lambda r: r["patient_id"])

    sources = {
        **{var: f"Latest LOINC {' / '.join(codes)} ({unit}) within {LAB_LOOKBACK_DAYS // 365} years before {ref}"
           for var, (codes, unit) in LABS.items()},
        "age": f"Whole years from BIRTHDATE to the reference date {ref}",
        "female": "GENDER == 'F'",
        "crcl": "Derived: Cockcroft-Gault from the latest creatinine, age, weight and sex",
        "prior_systemic_lines": "Derived: antineoplastic medication orders; a gap of more than 90 days starts a new line",
        "cardiac_disease": "Active heart failure, atrial fibrillation, unstable angina, cardiomyopathy, aortic/mitral "
                           "stenosis, or a myocardial infarction starting within 180 days (stable ischemic disease excluded)",
        "uncontrolled_hypertension": "Derived: active hypertension diagnosis and latest BP >= 160 systolic or >= 100 diastolic",
        "thromboembolic_event_recent": "Stroke, embolism or thrombosis diagnosis starting within 180 days",
        "active_infection": "Acute infectious condition active on the reference date",
        "prior_malignancy": "Any Synthea-simulated cancer diagnosis (in situ and suspected excluded)",
        "recent_live_vaccine": "Live-vaccine immunization within 30 days",
        "systemic_immunosuppression": "Active systemic steroid or immunosuppressant medication",
    }
    return {
        "format": COHORT_FORMAT,
        "metadata": {
            "source": "Synthea (synthetichealth/synthea), official release jar",
            "profile": profile,
            "seed": seed,
            "reference_date": ref.isoformat(),
            "lab_lookback_days": LAB_LOOKBACK_DAYS,
            "living_patients": len(rows),
            "excluded_deceased": deceased,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "variable_sources": sources,
            "not_simulated": {k: v for k, v in NOT_SIMULATED.items() if v},
        },
        "patients": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_dir", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--profile", default="adults")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--synthea-sha256", default=None)
    args = ap.parse_args()
    cohort = build(args.csv_dir, args.profile, args.seed)
    if args.synthea_sha256:
        cohort["metadata"]["synthea_jar_sha256"] = args.synthea_sha256
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cohort, separators=(",", ":")), encoding="utf-8")
    pts = cohort["patients"]
    print(f"wrote {args.output} with {len(pts)} living patients ({cohort['metadata']['excluded_deceased']} deceased excluded)")
    for var in [k for k in pts[0] if k not in ("patient_id", "synthetic")]:
        known = sum(p[var] is not None for p in pts)
        print(f"  {var:28} known {known:5}/{len(pts)}")


if __name__ == "__main__":
    main()
