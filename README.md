# 🧬 CliNova — TrialMax

### Clinical-trial eligibility and recruitment intelligence

CliNova helps researchers understand how trial eligibility criteria affect recruitment **before** a protocol is finalized.

Enter a ClinicalTrials.gov NCT ID to parse public eligibility criteria, simulate modeled rules on a synthetic patient cohort, explore draft threshold changes, and investigate rare-disease recruitment opportunities.

---

## 🔍 The Problem

Clinical trial criteria can be long, restrictive, and difficult to evaluate before recruitment begins.

| Challenge | CliNova helps by |
| --- | --- |
| Long eligibility criteria | Parsing criteria into clear inclusion/exclusion rules |
| Unknown recruitment bottlenecks | Showing which modeled rules exclude the most patients |
| Safety trade-offs | Flagging sensitive draft changes for review |
| Overlapping exclusions | Showing funnels, unique failures, and rule overlap |
| Rare-disease recruitment | Finding public trial-site history and resource links |

---

## 🚀 What CliNova Does

- Loads public ClinicalTrials.gov trials using an NCT ID
- Parses eligibility criteria into structured rules
- Evaluates modeled rules as **pass**, **fail**, or **unknown**
- Shows criteria that remain **not checked**
- Creates funnels, rule-impact charts, and overlap analysis
- Lets researchers compare original and draft thresholds on the same cohort
- Keeps the original protocol unchanged
- Supports researcher review and printable decision briefs
- Verifies rare-disease status before enabling RareReach
- Maps public US trial-site history for verified rare diseases
- Includes dark mode, light mode, interactive charts, and animations

---

## ⚙️ How It Works

```mermaid
flowchart TD
    A[Enter NCT ID] --> B[ClinicalTrials.gov record]
    B --> C[Parse eligibility criteria]
    C --> D{Can the rule be modeled?}

    D -->|Yes| E[Evaluate synthetic cohort]
    E --> F[Pass / Fail / Unknown]
    F --> G[Results dashboard]

    D -->|No| H[Show as Not checked]
    H --> G

    G --> I[Funnel, overlap and rule impact]
    I --> J[Draft threshold changes]
    J --> K[Compare same cohort]
    K --> L[Researcher review]
