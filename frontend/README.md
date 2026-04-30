# Longevity Lab Frontend

This directory contains the React + TypeScript UI for the Longevity Lab project.

The current UX is split into two top-level views:

- `Explorer`: primary organ heatmap + drill-down experience with side-by-side `Current` and
  `What-if` profiles, live slider updates, and always-visible `Current | What-if | Change vs current`
  comparison cards controlling the main heatmap
- `Data integration`: pipeline status and provenance checks kept out of the main analysis flow

## Prereqs

- Node.js 22+ (npm 10+)

## Run (dev)

```bash
npm ci
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` (see `vite.config.ts`).

Useful routes:

- Explorer: `http://localhost:5173/`
- Data integration: `http://localhost:5173/#/data`

If you are adding/updating dependencies, use `npm install` and commit the resulting `package-lock.json` change.

## Checks

```bash
npm run check
npm run lint
npm run build
```

## E2E smoke test (Playwright)

The repo includes a small Playwright test that starts (or reuses) both the backend and frontend dev servers
and validates that the scenario compare flow renders.

```bash
npm run test:e2e
```

Current smoke coverage:

- app bootstraps successfully
- live compare flow renders
- profile edits update results automatically
- organ drill-down interaction works
- always-visible heatmap comparison cards switch the main state cleanly and label relative-change semantics explicitly
- invalid numeric input clamps correctly
- failed compare requests preserve the last good UI state and show an error
- guidance appears when either `Current` or `What-if` remains in the high-risk band

## Code map (where to change things)

- API client + contracts: `src/api/client.ts`, `src/types.ts`
- Scenario form inputs: `src/components/scenario-form.tsx`
- Organ heatmap (SVG-first): `src/components/body-heatmap.tsx`
- Drill-down inspector: `src/components/condition-inspector.tsx`
- App state (reducer + context): `src/state/scenario-context.tsx`

## Frontend guardrails

- TypeScript `strict` is enabled; avoid `any`.
- React owns the DOM. D3 is used for utilities (scales/geometry), not DOM rendering.
- Keep UI "contributors/drivers" aligned with the backend explanation method (no hand-wavy labels).

## Manual QA checklist

Before you hand off a frontend change:

1. Start backend + frontend locally.
2. Verify the Explorer page still renders summaries and the heatmap.
3. Change a `Current` or `What-if` input and confirm the summaries update live.
4. Click the `Current`, `What-if`, and `Change vs current` heatmap cards and confirm the legend/values update.
5. Click an organ/callout and confirm the drill-down updates.
6. Open `#/data` and confirm the Data integration page still loads.
7. Run `npm run check`, `npm run lint`, `npm run build`, and `npm run test:e2e`.
