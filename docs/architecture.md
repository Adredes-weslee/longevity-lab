# Architecture Decision Record

## Project fit

Longevity Lab is a local-first product prototype with tightly coupled data pipelines, model artifacts, API contracts, and an interactive frontend. A single repo keeps those boundaries explicit without adding monorepo orchestration.

## Chosen architecture

### 1. Repo shape

- One repo
- One React frontend in `frontend/`
- One Python package in `src/longevity_lab/`
- Shared contracts through typed API schemas and domain metadata

### 2. Frontend

- Vite + React + TypeScript
- SVG-first rendering
- React owns state and markup
- D3 is used for scales and derived geometry, not as the primary DOM owner
- Global app state starts with `useReducer` + context, not Redux/Zustand

Why:

- React now points custom app setups to Vite.
- React recommends keeping one source of truth, avoiding redundant state, and deriving values where possible.
- D3 shape/scale modules fit well as utility layers while React owns the DOM.
- SVG is the right default for a small-to-medium interactive visual analytics interface with clickable organs, legends, and annotations.

### 3. Backend

- FastAPI
- APIRouter-based module structure
- Lifespan initialization for app-wide services
- Pydantic request/response models
- Service layer for scenario evaluation and metadata access

Why:

- FastAPI has strong support for modular route layout and startup resource loading.
- Typed schemas keep the UI and backend contract stable across six contributors.
- The service layer is enough structure without introducing unnecessary repository/DDD ceremony.

### 4. Data layer

- Public raw datasets live outside git in `data/external/`
- Derived snapshots become Parquet
- DuckDB is the default local analytics/query engine
- Model-ready tables are exported from the pipeline, not queried ad hoc from the API

Why:

- DuckDB supports local persistent files, direct Parquet access, and pushdown on Parquet scans.
- Public CSV-like datasets are messy; locking down ingest settings early reduces drift.
- The API should serve prepared artifacts, not run heavy ETL at request time.

### 5. Modeling

- One explicit classifier bundle per condition
- Scikit-learn `Pipeline` for preprocessing + estimator
- Decision tree baseline, with pruning and calibration
- Persist trusted local artifacts with `joblib`

Why:

- The product prioritizes interpretability and risk communication.
- A per-condition bundle keeps probability calibration, feature metadata, and explanations easier to reason about than a larger generic abstraction.
- Preprocessing inside the pipeline prevents leakage.

### 6. Demo strategy

The scaffold includes a deterministic demo engine so the UI and API can run before real models are trained. This keeps the repo usable while the data pipeline is still under construction.

## Current UX slice

The current dashboard is intentionally split into two views:

- `Explorer`: primary scenario editing, explicit compare/apply, organ heatmap view toggle, and condition drill-down
- `Data integration`: raw/processed artifact and provenance verification

This keeps data-health checks visible without crowding the main analysis flow.

## Design patterns we will use

- **Service layer**: orchestration lives in services, not route handlers
- **Typed DTOs**: API and domain objects are explicit and versionable
- **Strategy via protocol**: scenario engine can switch from demo logic to trained artifacts
- **Catalog pattern**: organ and condition metadata live in one authoritative place

## Design patterns we will not use

- No microservices
- No separate repos
- No generic repository pattern over files for its own sake
- No global frontend state library unless reducer/context becomes a proven bottleneck
- No Docker-first workflow until the project is stable enough to justify it

## Source links

- React + Vite: https://react.dev/learn/creating-a-react-app, https://vite.dev/guide/
- React state guidance: https://react.dev/learn/choosing-the-state-structure, https://react.dev/learn/you-might-not-need-an-effect, https://react.dev/learn/extracting-state-logic-into-a-reducer
- React DOM escape hatch: https://react.dev/learn/manipulating-the-dom-with-refs
- D3 modules: https://d3js.org/d3-scale, https://d3js.org/d3-shape, https://d3js.org/d3-selection
- SVG vs Canvas context: https://developer.mozilla.org/en-US/docs/Web/SVG, https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/canvas, https://d3js.org/d3-geo/path
- FastAPI app structure: https://fastapi.tiangolo.com/tutorial/bigger-applications/, https://fastapi.tiangolo.com/advanced/events/, https://fastapi.tiangolo.com/tutorial/dependencies/
- DuckDB local storage and Parquet: https://duckdb.org/docs/stable/connect/overview, https://duckdb.org/docs/stable/data/parquet/overview, https://duckdb.org/docs/stable/data/csv/auto_detection
- Scikit-learn pipeline and calibration: https://scikit-learn.org/stable/modules/compose.html, https://scikit-learn.org/stable/common_pitfalls.html, https://scikit-learn.org/stable/modules/tree.html, https://scikit-learn.org/stable/modules/calibration.html, https://scikit-learn.org/stable/model_persistence.html
