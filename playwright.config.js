const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './browser-tests',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 30000,
  reporter: [['list'], ['json', { outputFile: 'browser-qa-report.json' }]],
  outputDir: 'browser-qa-artifacts',
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ...devices['Desktop Chrome']
  },
  webServer: {
    command: 'uvicorn tradingdyor.api:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/health',
    timeout: 60000,
    reuseExistingServer: !process.env.CI
  }
});
