import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { defineConfig } from 'astro/config';

// Static site. One page holds every section; footer pages are their own routes.
//
// Live voice in dev: the browser calls /api/v1/sessions.connect same-origin, and
// this proxy forwards it to the Voqalize control plane (dev by default), the way
// the hosting rewrite will in production. Override with VOQALIZE_API_TARGET.
const apiTarget = process.env.VOQALIZE_API_TARGET || 'https://app.dev.voqalize.com';

/**
 * Optional: load an unreleased avatar runtime (AVATAR_RUNTIME=https://avatar.dev.voqalize.com/runtime/current.js).
 * Unset, the build uses exactly what the published @voqalize/avatar loads.
 * Same mechanism as platform/frontend/avatar-runtime.mjs.
 */
function avatarRuntime(url = process.env.AVATAR_RUNTIME) {
  if (!url) return null;
  const PIN = /[\\/]@voqalize[\\/]avatar[\\/]dist[\\/]pin\.js$/;
  const LINE = /export const RUNTIME_URL = "[^"]*";/;
  return {
    name: 'voqalize-avatar-runtime',
    enforce: 'pre',
    config: () => ({ optimizeDeps: { exclude: ['@voqalize/avatar'] } }),
    load(id) {
      const path = id.split('?')[0];
      if (!PIN.test(path)) return null;
      return readFileSync(path, 'utf8').replace(LINE, `export const RUNTIME_URL = ${JSON.stringify(url)};`);
    },
  };
}

export default defineConfig({
  output: 'static',
  site: 'https://voqalize.com',
  // Old footer addresses: press lives on the contact page, the terms share a page with privacy.
  redirects: { '/press': '/contact#press', '/terms': '/privacy#terms' },
  vite: {
    plugins: [avatarRuntime()].filter(Boolean),
    // `pnpm build:release` makes hidden source maps, sends them to PostHog error tracking (readable
    // stack traces) and deletes them, so they never ship with the site.
    build: { sourcemap: process.env.SOURCEMAPS ? 'hidden' : false },
    resolve: {
      alias: { '@daily-co/daily-js': fileURLToPath(new URL('./src/scripts/no-daily.ts', import.meta.url)) },
    },
    server: {
      proxy: { '/api': { target: apiTarget, changeOrigin: true, secure: true } },
    },
  },
});
