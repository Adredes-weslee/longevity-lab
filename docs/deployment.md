# Deployment

This repo remains local-first. Deployment is a demo/smoke-test surface, not the canonical place to
store raw datasets or trained model artifacts.

## Recommended free-tier shape

- **API:** Render web service running FastAPI in demo mode.
- **Frontend:** Vercel static site or Render static site.
- **Artifacts:** do not commit or bundle `data/external/`, `data/processed/`, or
  `artifacts/models/`. Use `LONGEVITY_LAB_ENGINE=demo` for public demo deployments unless you add
  an explicit trusted artifact retrieval step later.

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
4. Keep `LONGEVITY_LAB_ENGINE=demo` unless a trusted artifact download/build step is added.

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

Public deployments can run artifact-backed scoring by downloading a trusted zipped bundle during the
Render build. The current release asset is:

- `LONGEVITY_LAB_ARTIFACT_BUNDLE=real-20260504-full`
- `LONGEVITY_LAB_ARTIFACT_URL=https://github.com/Adredes-weslee/longevity-lab/releases/download/model-real-20260504-full/real-20260504-full.zip`
- `LONGEVITY_LAB_ARTIFACT_SHA256=289e3e6981a9140cc5fdf727d19c64d430703f860c84755f98842fb8a6272440`

The build command runs `scripts/download_model_bundle.py`, which downloads the zip, verifies SHA256,
rejects unsafe zip paths, and extracts the bundle under `artifacts/models/`. Production can then set
`LONGEVITY_LAB_ENGINE=artifact`.

Keep `LONGEVITY_LAB_ENGINE=demo` as the rollback path. Do not commit `data/external/`,
`data/processed/`, or `artifacts/models/` directly to the repo.
