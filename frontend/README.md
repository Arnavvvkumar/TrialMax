# CliNova frontend starter

React + TypeScript + Vite frontend for the HackHarvard CliNova clinical-trial eligibility prototype.

## Run locally

```bash
npm install
npm run dev
```

Open the URL displayed by Vite (usually http://localhost:5173).

## Build

```bash
npm run build
```

## Current behavior

- Responsive white/sage-green dashboard with four views.
- Trial setup field, demo study and navigation.
- Eligibility summary with clearly labeled illustrative placeholder counts.
- Wind Tunnel sliders with a **placeholder UI-only formula**, **not** per-patient eligibility computation or clinical safety calculation.
- Protocol review checkboxes, draft accept/reject state (local only).

**No backend, Chalk API, trial retrieval, authentic clinical evidence, or real patient data is connected yet.** The fictional NCT-DEMO-001 entry is deliberately not a real study. Do not cite demonstration figures as analysis results.

## Integrating with an existing repository

If the team's `frontend/` folder already has an app, inspect its files first. Merge the components/styles carefully rather than overwriting colleagues' work. This starter can also run in a fresh directory independently.

## Next implementation steps

1. Replace the demo trial with GET /api/trials/:nctId data.
2. Replace illustrative counts and chart values with POST /api/simulate responses.
3. Replace placeholder Wind Tunnel formula with POST /api/compare.
4. Populate review drafts from structured rule/safety review output.
