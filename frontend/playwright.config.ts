import { defineConfig, devices } from "@playwright/test";

// Default: build and serve two production builds, one with the Research Console and one without.
// Set PW_BASE_URL to run against an already running dev server instead (fast local loop).
const external = process.env.PW_BASE_URL;
const e2eEnv = { NEXT_PUBLIC_MOCK_STREAM: "off", NEXT_PUBLIC_MOCK_LATENCY_MS: "20" };

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: external ?? "http://localhost:3100",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    { name: "app", testIgnore: /research-removal|screenshots/, use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "screenshots", testMatch: /screenshots/, use: { ...devices["Desktop Chrome"] } },
    { name: "research-off", testMatch: /research-removal/, use: { baseURL: process.env.PW_BASE_URL_NORESEARCH ?? "http://localhost:3101" } },
  ],
  webServer: external
    ? undefined
    : [
        {
          command: "npx next build && npx next start -p 3100",
          port: 3100,
          timeout: 600_000,
          reuseExistingServer: !process.env.CI,
          env: e2eEnv,
        },
        {
          command: "node scripts/research-off-server.mjs",
          port: 3101,
          timeout: 900_000,
          reuseExistingServer: !process.env.CI,
        },
      ],
});
