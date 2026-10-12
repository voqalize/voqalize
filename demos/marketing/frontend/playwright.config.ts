/**
 * End-to-end tests for Talk mode: every action Tanvi's brain can send, applied to
 * the built site the way a live call applies it (`window.vq.act`), and checked on
 * the page. No call, no microphone, no keys needed.
 *
 *   pnpm test:e2e
 *
 * Uses Playwright's own Chromium, or the newest one already in the local cache
 * (set PW_CHROMIUM to point at another).
 */
import { defineConfig, devices } from '@playwright/test';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

function cachedChromium(): string | undefined {
  if (process.env.PW_CHROMIUM) return process.env.PW_CHROMIUM;
  const cache = join(homedir(), 'Library/Caches/ms-playwright');
  if (!existsSync(cache)) return undefined;
  const build = readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().pop();
  if (!build) return undefined;
  const dir = readdirSync(join(cache, build)).find((d) => d.startsWith('chrome-mac'));
  if (!dir) return undefined;
  const app = readdirSync(join(cache, build, dir)).find((d) => d.endsWith('.app'));
  return app ? join(cache, build, dir, app, 'Contents/MacOS', app.replace('.app', '')) : undefined;
}

const PORT = 4455;

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 30_000,
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    launchOptions: { executablePath: cachedChromium() },
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'phone', use: { ...devices['iPhone 13'], browserName: 'chromium', defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: `pnpm astro build --outDir .e2e-dist > /dev/null && python3 -I -m http.server ${PORT} --directory .e2e-dist`,
    url: `http://localhost:${PORT}/`,
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
  },
});
