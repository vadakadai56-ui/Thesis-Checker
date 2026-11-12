import { existsSync } from 'node:fs';

import { defineConfig, devices } from '@playwright/test';

// Use a Chromium that is already on the machine if one is named (or found at the
// usual place in the cloud dev environment); otherwise Playwright's own download
// (`npx playwright install chromium`).
const systemChromium = process.env.PLAYWRIGHT_CHROMIUM_PATH ?? '/opt/pw-browsers/chromium';
const executablePath = existsSync(systemChromium) ? systemChromium : undefined;

export default defineConfig({
  testDir: 'tests-e2e',
  globalSetup: './tests-e2e/global-setup.ts',
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    launchOptions: { executablePath },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Tests run against the BUILT app (`npm run build` first), like real users get it.
  webServer: {
    command: 'npm run preview',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
