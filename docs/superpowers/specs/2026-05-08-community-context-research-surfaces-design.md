# Community Context and Research Surfaces Design

**Approved direction:** Build context/research surfaces, not hidden modifiers to Explorer personal risk scores.

## Goal
Add a product surface that lets users inspect state/county ACS/SVI/PLACES context, compare geography values, review PLACES aggregate validation, and browse local causal-workbench reports while preserving the boundary that these outputs do not change individual prediction scores.

## Architecture
The API gains a thin `/api/community/*` route backed by focused services under `src/longevity_lab/services/`. The service reads trusted local processed Parquet/JSON/Markdown outputs from `data/processed/` and returns sanitized summaries with relative paths only. The React app gains a `Community context` page that consumes these summaries, renders a lightweight SVG U.S. state map plus comparison cards, and links context/validation/causal evidence without affecting `POST /api/scenario/compare`.

## Product Boundaries
- County ACS/SVI and PLACES are context/evidence only.
- State ACS/SVI may already affect scoring only through manifest-declared artifact lookup; this page still labels it separately from personal inputs.
- PLACES validation summarizes aggregate alignment between model aggregate predictions and CDC PLACES estimates; it is not person-level ground truth.
- Causal reports are assumption-bound observational analyses and are never interpreted as Explorer what-if effects.

## Backend Components
- `src/longevity_lab/services/community_context_service.py`: reads state/county context, PLACES county context, PLACES validation reports, and causal report metadata.
- `src/longevity_lab/api/routes/community.py`: exposes `/api/community/overview` with optional `year`, `places_year`, `state_fips`, and `county_fips` query parameters.
- `src/longevity_lab/api/schemas.py`: adds typed response models for context features, geography comparisons, PLACES validation rows, and causal report cards.
- `src/longevity_lab/api/main.py` and `dependencies.py`: wire the service into the app lifecycle.

## Frontend Components
- `frontend/src/pages/CommunityContextPage.tsx`: new page for map, geography context cards, PLACES validation rows, and causal report cards.
- `frontend/src/api/client.ts` and `frontend/src/types.ts`: add typed API client functions and response types.
- `frontend/src/App.tsx`: add navigation and data-loading state.
- `frontend/src/App.css`: add compact map/card/table styles reusing existing visual language.

## Data Flow
1. UI requests `/api/community/overview?year=2023&places_year=2025`.
2. Service checks `data/processed/context/context_state_year.parquet`, `context_county_year.parquet`, `data/processed/places/places_county_year.parquet`, `data/processed/validation/places_external_context_validation_2025.json`, and `data/processed/reports/causal/*/*_report.json`.
3. Missing files return explicit `available=false` summaries rather than failing the page.
4. The page displays available state/county context and local report status with caveats.

## Testing
- Backend tests create tiny Parquet/JSON report fixtures under `tmp_path` and assert response shape, value formatting, non-absolute paths, and missing-file safety.
- Frontend type/build verifies TypeScript contracts.
- Playwright smoke verifies the new page is reachable and labels context/research caveats.

## Non-Goals
- No county-level personal risk scoring.
- No PLACES feature injection into the artifact engine.
- No causal estimates inside Explorer scenario deltas.
- No third-party mapping dependency for the first pass.
