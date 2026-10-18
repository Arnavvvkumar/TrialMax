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

flowchart TD
    A["Enter NCT ID"] --> B["Fetch public trial data from ClinicalTrials.gov"]
    B --> C["Parse eligibility criteria"]
    C --> D["Evaluate synthetic patient cohort"]
    D --> E["Pass / Fail / Unknown per criterion"]
    E --> F["Eligibility funnel and overlap analysis"]
    F --> G["Scenario comparison"]
    G --> H["Researcher review"]

    B --> I["RareReach verification"]
    I --> J{"Exact Orphadata rare-disease match?"}
    J -->|Yes| K["Show ORPHAcode, synonyms, US site history, and public outreach links"]
    J -->|No| L["Stop RareReach and explain that no rare-disease match was confirmed"]

    H --> M["Export decision brief"]
    K --> M

## 🧪 Eligibility Results

| Status | Meaning |
| --- | --- |
| ✅ Pass | Synthetic patient meets a modeled criterion |
| ❌ Fail | Synthetic patient fails a modeled criterion |
| ❓ Unknown | Required information is unavailable |
| 🔎 Not checked | Criterion cannot currently be modeled reliably |

> Passing modeled checks does **not** confirm full real-world protocol eligibility.

---

## 🧬 RareReach

RareReach supports recruitment research for verified rare-disease trials.

```text
NCT ID
  ↓
Trial condition from ClinicalTrials.gov
  ↓
Orphadata rare-disease lookup
  ↓
Exact rare-disease match?
  ├── No  → Stop and explain why RareReach is unavailable
  └── Yes → ORPHAcode + synonyms
              ↓
          Public US ClinicalTrials.gov site history
              ↓
          Interactive US map + ranked site list
              ↓
          Orphanet and NORD public resource links
```

| RareReach shows | Important limitation |
| --- | --- |
| ORPHAcode and synonyms | Only after an exact terminology match |
| Public US site locations | Historical activity, not patient volume |
| Orphanet and NORD links | Research links, not verified partnerships |
| Outreach suggestions | Does not recommend relaxing criteria |

---

## 🤖 Chalk Integration

| Capability | Use in CliNova |
| --- | --- |
| Chalk SQL | Optional public-trial lookup source |
| Chalk Model Gateway | Optional fallback parser for unread criteria |
| Chalk evaluations | Evaluates responder-evidence agent output |

The deterministic simulator remains the source of truth for pass, fail, and unknown outcomes.

---

## 🛠️ Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI, Pydantic |
| Simulation | NumPy + deterministic eligibility engine |
| Synthetic data | Synthea-derived synthetic adult cohort |
| Trial data | ClinicalTrials.gov API |
| Rare-disease data | Orphadata / Orphanet |
| Mapping | D3 Geo, TopoJSON, US Atlas |
| AI and evaluation | Chalk |
| Testing | Pytest, Node test runner |
| Deployment | Docker |

---

## 🏃 Run Locally

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open: `http://127.0.0.1:5173`

---

## ✅ Test

```bash
python -m pytest backend/tests -q

cd frontend
npm test
npm run build
```

---

## ⚠️ Important Note

CliNova is a research prototype, not a clinical decision system.

- All patient-level results use synthetic data.
- Modeled eligibility is not real-world recruitment evidence.
- Public site history is not patient volume or current site capacity.
- Clinical and scientific review is always required.

---

## 📄 License

See [LICENSE](LICENSE).
