import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

// Fresh SQLite DB per run; the backend uses the fixture-backed fake evaluator (no API key, no network).
const db = path.join(os.tmpdir(), "jobfit-e2e.db");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  grepInvert: process.env.SCREENSHOTS ? undefined : /@screenshots/,
  use: { baseURL: "http://127.0.0.1:3010", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `rm -f "${db}" "${db}-wal" "${db}-shm" && uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8010`,
      cwd: "../backend",
      url: "http://127.0.0.1:8010/api/health",
      env: { EVALUATOR: "fake", DATABASE_URL: `sqlite:///${db}`, LOG_LEVEL: "warning" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx next dev --port 3010",
      url: "http://127.0.0.1:3010",
      env: { BACKEND_URL: "http://127.0.0.1:8010" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
