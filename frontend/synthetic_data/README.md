# TrialMax synthetic cohort v1

**Entirely synthetic. Not observed patient data, not Synthea output, and not a representative clinical cohort.**

This is a fixed 500-person *fictional non-small cell lung cancer (NSCLC) prescreening cohort* for functional testing of the TrialMax eligibility simulator. No real records or identifiable patient data are used. Values and distributions are manually chosen for an interactive demo and must not be cited as disease prevalence, treatment safety, actual enrollment probability, or actual recruitment performance.

## Files
- `patients.json`: application-ready records with JSON null for missing data.
- `patients.csv`: same cohort for inspection.
- `generate_patients.py`: reproducible generator, Python standard library only.
- `demo_criteria.json`: six fictional criteria for simulation testing, **not a real protocol**.
- `demo_validation.json`: example results for the fictional criteria, computed from the dataset.

## Reproduce
```bash
cd clinova_synthetic_data
python3 generate_patients.py
```

## Cohort fields
- `patient_id`: pseudonym `SYN-0001` etc.
- `synthetic`: always true.
- `cohort`: fictional NSCLC pre-screen population.
- `age_years`: age (integer).
- `sex_at_birth`: categorical synthetic attribute; not used in default criteria.
- `ecog_score`: 0–4 performance status.
- `egfr_mutation`: positive / negative / unknown. This is a simplified binary classification, not a complete molecular report.
- `alk_rearrangement`: positive / negative / unknown.
- `hemoglobin_g_dl`: illustrative lab value.
- `anc_cells_ul`: absolute neutrophil count (cells/µL).
- `platelets_cells_ul`: count (cells/µL).
- `egfr_kidney_ml_min_1_73m2`: *estimated glomerular filtration rate*, distinct from EGFR gene biomarker.
- `ast_u_l`, `alt_u_l`: liver enzyme levels.
- `prior_systemic_therapy_lines`: nonnegative integer.
- `brain_metastases`, `active_infection`: synthetic booleans.
- `data_version`: synthetic-v1.

## Missing values and logic
Numeric or boolean unknowns use JSON `null`. Genetic biomarker results can be string `unknown`. CSV blank cells represent JSON null. The simulator must treat missing data as **unknown**, not automatically pass or fail.

For a patient across all criteria: **excluded** if any rule fails, otherwise **unknown** if any rule is unknown, otherwise **eligible**. Exclusion-by-criterion counts overlap and must not be summed as unique patients. A funnel is dependent on the chosen criterion order.

## Clinical safeguards
Rule thresholds and distributions are invented. They must not be presented as medically correct limits for a particular investigational product. Real protocol text needs expert review to map into evaluable fields. Disease, dose, safety, pharmacology, predictive enrichment, statistical power, and generalizability **cannot** be established by this toy dataset. Use source-backed trial information and qualified clinical judgment separately.

## Integration
Frontend can read `patients.json` in mock mode; backend can load it for deterministic simulations. Chalk should consume nonidentifying features and return verifiable computed outcomes; confirm enabled Chalk capabilities and free-use limits before deployment. Replace the fictional cohort with a documented Synthea-derived cohort if needed later, preserving source provenance and assumptions.
