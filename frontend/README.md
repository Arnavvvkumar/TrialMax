# Wind Tunnel frontend

React, TypeScript and Vite UI connected to the FastAPI backend. Start the backend on port 8000 using the [repository instructions](../README.md), then run `npm ci` and `npm run dev` here. Node 22.12+ or 24+ is required.

All analyses and comparisons use real backend responses. The fictional example is input text only, processed by the same parser and simulator as registry trials. Backend errors are displayed explicitly. There is no mock-results fallback.

Four connected views share one workspace: trial/population selection, eligibility analysis, numeric scenario editing, and researcher review. Registry lookups default to generated exploration; pasted text/examples default to fixed synthetic records. Users can explicitly override either choice. Changing inputs invalidates earlier results and decisions. Original rules, IDs, metadata, unavailable results, and source text are preserved.

The headline, funnel and comparison use only available modeled checks. Not-checked requirements stay separately visible and full-protocol status remains unresolved where appropriate. This does not imply confirmed protocol eligibility. The source view shows Chalk configuration status; it does not claim a live connection merely because settings exist.

`npm test` checks state transitions and review semantics. `npm run build` checks TypeScript and creates `dist/`; FastAPI can serve that build on the same origin. See `.env.example` for optional separate-origin configuration. Every `VITE_` value is browser-visible, so never store provider keys there.
