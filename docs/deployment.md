# Deployment

This repo remains local-first. Deployment is a demo/smoke-test surface, not the canonical place to
store raw datasets or trained model artifacts.

## Recommended free-tier shape

- **API:** Render web service running FastAPI in artifact mode with a verified public model
  artifact.
- **Frontend:** Vercel static site or Render static site.
- **Artifacts:** do not commit or bundle `data/external/`, `data/processed/`, or
  `artifacts/models/`. Use the trusted artifact and evidence retrieval steps below for public
  deployments, with `LONGEVITY_LAB_ENGINE=demo` kept only as the rollback path.

Relevant provider docs:

- Render Blueprint spec: <https://render.com/docs/blueprint-spec>
- Render FastAPI services: <https://render.com/docs/deploy-fastapi>
- Render static sites: <https://render.com/docs/static-sites>
- Vercel Vite deployments: <https://vercel.com/docs/frameworks/vite>
- Vercel environment variables: <https://vercel.com/docs/environment-variables>

## Render Blueprint

`render.yaml` defines:

- `longevity-lab-api`: a Python web service that installs the package and starts Uvicorn on
  Render's `$PORT`.
- `longevity-lab-frontend`: an optional static frontend that builds `frontend/dist` and rewrites
  client-side routes to `index.html`.

The Blueprint sets `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` and `VITE_API_BASE_URL` to the public Render
service URLs. Keep these values in sync if the service names or custom domains change.

After creating the Blueprint:

1. Confirm both services deploy from the same Blueprint.
2. If you later add a custom frontend domain, update `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` to include
   that full origin.
3. If you later rename the API service, update `VITE_API_BASE_URL` to the new public API origin.
4. Keep `LONGEVITY_LAB_ENGINE=artifact` only when `LONGEVITY_LAB_ARTIFACT_URL` and
   `LONGEVITY_LAB_ARTIFACT_SHA256` point to the verified production release below.
5. Keep the Community Context evidence bundle configured only when
   `LONGEVITY_LAB_EVIDENCE_BUNDLE_URL` and `LONGEVITY_LAB_EVIDENCE_BUNDLE_SHA256` point to the
   verified public evidence release below.

Render free instances can cold-start after inactivity. The first API call after idle may be slow.

## Vercel frontend + Render API

If using Vercel for the frontend:

1. Create a Vercel project with root directory `frontend/`.
2. Use the default Vite build: `npm run build`.
3. Use output directory `dist`.
4. Set `VITE_API_BASE_URL` to the Render API origin, without `/api`.
5. Set `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` on the Render API to the Vercel production origin and any
   preview origins you intentionally support.

The frontend client appends `/api` itself, so `VITE_API_BASE_URL=https://example.onrender.com` calls
`https://example.onrender.com/api/...`.

For local testing of a non-default API origin, copy `frontend/.env.example` to `frontend/.env` and
set `VITE_API_BASE_URL` there before running `npm run build`.

## Local deployment smoke checks

Before pushing deployment config changes:

```powershell
pdm run pytest
cd frontend
npm run build
```

Optional local production preview:

```powershell
pdm run python -m uvicorn longevity_lab.api.main:app --host 127.0.0.1 --port 8000
cd frontend
npm run build
npm run preview
```

Open `http://localhost:4173` and verify:

- `/api/health` returns `{"status":"ok"}` through the configured API origin or proxy.
- Explorer renders the runtime banner and scenario comparison.
- Data Evidence shows local artifacts as ready or missing without failing the page.

## Artifact strategy

Public deployments run artifact-backed scoring by downloading a trusted zipped bundle during the
Render build. The current production release asset is:

- `LONGEVITY_LAB_ARTIFACT_BUNDLE=real-20260508-xgboost-shap`
- `LONGEVITY_LAB_ARTIFACT_URL=https://github.com/Adredes-weslee/longevity-lab/releases/download/model-real-20260508-xgboost-shap/real-20260508-xgboost-shap.zip`
- `LONGEVITY_LAB_ARTIFACT_SHA256=1c71eca4aff814f2c15d540ecb6a995230a4ac956232fd2d2b53e4eb4d3ab0aa`

The build command runs `scripts/download_model_bundle.py`, which downloads the zip, verifies SHA256,
rejects unsafe zip paths, and extracts the bundle under `artifacts/models/`. Production can then set
`LONGEVITY_LAB_ENGINE=artifact`.

The `real-20260508-xgboost-shap` bundle activates the production pieces behind the Explorer and Data
Evidence context banners:

- eight modeled conditions;
- calibrated XGBoost tree-ensemble scoring;
- manifest-declared SHAP explanation artifacts;
- manifest-declared `calibration_interval` uncertainty payloads;
- twelve ACS/SVI context features;
- bundle-local `context_state_year_lookup.json`; and
- context vintage `State-year ACS/SVI context vintage 2022 joined to BRFSS 2023 serving keys`.

ACS/SVI context is active in production only for bundles whose `manifest.json` declares
`context_features` metadata and a trusted bundle-local `context_state_year_lookup.json`. Older
artifact bundles can still serve, but geography selection remains inert for ACS/SVI scoring until a
context-aware bundle is published and its release URL/SHA are configured. County context and PLACES
remain intentionally inactive for scoring unless a future PR defines safe serving semantics and
passes ablation/reasonableness gates.

## Public evidence bundle strategy

Public deployments can also populate the Community Context page by downloading a separate trusted
evidence bundle during the Render build. The current production evidence release asset is:

- `LONGEVITY_LAB_EVIDENCE_BUNDLE=public-evidence-20260508-community-context`
- `LONGEVITY_LAB_EVIDENCE_BUNDLE_URL=https://github.com/Adredes-weslee/longevity-lab/releases/download/evidence-public-20260508-community-context/public-evidence-20260508-community-context.zip`
- `LONGEVITY_LAB_EVIDENCE_BUNDLE_SHA256=be50ac0392078eca507d42f3ed8a8f37132eadb4df8fc3dc00c480bee737dc40`

The build command runs `scripts/download_evidence_bundle.py`, which downloads the zip, verifies
SHA256, rejects unsafe zip paths, and extracts the bundle under `artifacts/evidence/`.
`scripts/build_public_evidence_bundle.py` creates the release zip from local processed outputs.

The `public-evidence-20260508-community-context` bundle contains ACS/SVI state and county context,
CDC PLACES county context, PLACES aggregate validation JSON, and non-serving causal workbench
reports. These assets populate Community Context evidence panels only; they do not change Explorer
person-level scoring or model features. Data Evidence reports the configured bundle and its bundled
contents separately from local raw/processed data readiness.

Keep `LONGEVITY_LAB_ENGINE=demo` as the rollback path. Do not commit `data/external/`,
`data/processed/`, or `artifacts/models/` directly to the repo.
