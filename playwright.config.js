import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure', channel: process.env.CHESS_ANALYZER_BROWSER_CHANNEL },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `${process.env.CHESS_ANALYZER_PYTHON || '.venv/bin/python'} manage.py runserver 127.0.0.1:8765 --noreload`,
    url: 'http://127.0.0.1:8765',
    reuseExistingServer: false,
    env: { DJANGO_DEBUG: '1', DJANGO_ALLOWED_HOSTS: 'localhost,127.0.0.1' },
  },
});