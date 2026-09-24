import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const venvBin = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin');
const server = path.join(venvBin, process.platform === 'win32' ? 'viz-server.exe' : 'viz-server');

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: 'http://127.0.0.1:8000', headless: true },
  webServer: {
    command: `"${server}"`,
    url: 'http://127.0.0.1:8000/api/health',
    cwd: root,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      ...(process.env as Record<string, string>),
      VIZ_STORAGE: 'local',
      VIZ_LOCAL_DIR: path.join(root, 'sample-bucket'),
      VIZ_WEB_DIST: path.join(root, 'web', 'dist'),
      VIZ_ALLOWED_HOSTS: '127.0.0.1,localhost',
    },
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
