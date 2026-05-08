# Community Context and Research Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a Community Context page and supporting API that surface county/state ACS/SVI/PLACES context, PLACES validation, and causal report cards without changing personal risk scoring.

**Architecture:** Add one focused backend service and route for read-only community/research evidence. Add one React page that renders map-like state context, comparison cards, validation rows, and causal report cards. Keep the Explorer scoring contract unchanged.

**Tech Stack:** FastAPI, Pydantic v2, pandas/Parquet, React, TypeScript, Vite, Playwright.

---

### Task 1: Backend Schemas And Service

**Files:**
- Modify: `src/longevity_lab/api/schemas.py`
- Create: `src/longevity_lab/services/community_context_service.py`
- Test: `tests/test_community_context_api.py`

- [x] Add Pydantic response models: `CommunityFeatureValueResponse`, `CommunityGeographySummaryResponse`, `CommunityPlacesValidationRowResponse`, `CommunityCausalReportSummaryResponse`, and `CommunityContextOverviewResponse`.
- [x] Implement a service that reads local state/county ACS/SVI context, PLACES context, validation JSON, and causal report JSON/Markdown files.
- [x] Return `available=false` and clear messages when files are absent.
- [x] Ensure all returned file paths are relative/safe display paths.
- [x] Write tests with tiny Parquet/JSON fixtures for available and missing-data cases.

### Task 2: API Route Wiring

**Files:**
- Modify: `src/longevity_lab/api/dependencies.py`
- Modify: `src/longevity_lab/api/main.py`
- Create: `src/longevity_lab/api/routes/community.py`
- Test: `tests/test_community_context_api.py`

- [x] Add app-scoped `CommunityContextService` in lifespan.
- [x] Expose `GET /api/community/overview` with `year`, `places_year`, `state_fips`, and `county_fips` query parameters.
- [x] Include router under the configured API prefix.
- [x] Assert route response has `contract_version=v2` and does not expose absolute paths.

### Task 3: Frontend Types And Client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`

- [x] Add TypeScript interfaces matching the new backend response.
- [x] Add `fetchCommunityOverview()` with typed query parameters.
- [x] Keep API base URL behavior consistent with existing routes.

### Task 4: Community Context Page

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/CommunityContextPage.tsx`
- Modify: `frontend/src/App.css`
- Test: `frontend/e2e/app.spec.ts`

- [x] Add navigation item `Community context` at `#/community`.
- [x] Load community overview when the page is selected.
- [x] Render a lightweight SVG state map/tiles and geography selector summary.
- [x] Render ACS/SVI state and county context cards with source/caveat copy.
- [x] Render PLACES county context and aggregate validation rows with model-vs-PLACES differences.
- [x] Render causal workbench report cards with estimate/diagnostic/heterogeneity summaries.
- [x] Add Playwright smoke assertions for route reachability and caveat text.

### Task 5: Data Evidence And Docs Alignment

**Files:**
- Modify: `frontend/src/pages/DataEvidencePage.tsx`
- Modify: `docs/feature_status.md`
- Modify: `docs/roadmap.md`

- [x] Add cross-link/copy in Data Evidence that points to Community Context for context and causal report inspection.
- [x] Mark community context, PLACES validation surfacing, and causal report surfacing as done.
- [x] Keep explicit non-goal language for county-adjusted personal prediction and PLACES-adjusted scoring.

### Task 6: Validation And Review

**Files:**
- No new feature files unless fixes are needed.

- [x] Run targeted backend tests for community/evidence/context/PLACES/causal surfaces.
- [x] Run frontend type/lint/build and Playwright smoke.
- [x] Run local adversarial review over the diff and patch any confirmed P0/P1/P2 issues.
- [x] Commit in logical commits after tests and review converge.
