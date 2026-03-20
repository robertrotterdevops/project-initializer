import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: ['*.spec.js'],
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  use: {
    baseURL: 'http://127.0.0.1:8787',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8787',
    url: 'http://127.0.0.1:8787',
    reuseExistingServer: true,
    timeout: 30000,
    cwd: '..',
  },
});
