import { defineConfig } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
const reuseExistingServer = process.env.E2E_REUSE_SERVER === '1'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL,
    headless: true,
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command:
        'pdm run python -m uvicorn longevity_lab.api.main:app --host 127.0.0.1 --port 8000',
      env: {
        LONGEVITY_LAB_ENGINE: 'demo',
        PYTHONPATH: 'src',
      },
      url: 'http://127.0.0.1:8000/api/health',
      cwd: '..',
      reuseExistingServer,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: baseURL,
      reuseExistingServer,
      timeout: 120_000,
    },
  ],
})
