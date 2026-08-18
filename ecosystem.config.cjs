/**
 * pm2 entrypoint for this repo's local surfaces: the docs site and the eleven
 * demo UIs.
 *
 *   pm2 start ecosystem.config.cjs                 # everything
 *   pm2 start ecosystem.config.cjs --only travel   # one demo
 *
 * Ports are declared HERE and nowhere else — no vite.config.ts or astro.config.mjs
 * in this repo names one. They are passed on the command line, so the config files
 * cannot drift from what is actually listening. The local nginx
 * (/opt/homebrew/etc/nginx/servers/voqalize.conf) has the same numbers written out;
 * change one, change the other in the same commit.
 *
 * The demo brains are not here — they run from the platform repo's ecosystem, out
 * of this checkout, so one `pm2 start` there brings up a working voice stack.
 */

'use strict';

const path = require('path');

// Bind IPv4 loopback explicitly. A vite/astro dev server left on its default
// `localhost` binds ::1 only on macOS, and nginx proxies to 127.0.0.1 — the
// symptom is a 502 from a process pm2 swears is online.
const HOST = '127.0.0.1';
const DOCS_PORT = 4331;

// port = DEMO_BASE + index. APPEND ONLY — inserting renumbers every demo after it.
const DEMO_BASE = 5750;
const DEMOS = [
  'travel',
  'shopping',
  'support',
  'servicing',
  'interview_bot',
  'sugar',
  'legal',
  'lead_qual',
  'aura',
  'forge',
  'orderdesk',
];

module.exports = {
  apps: [
    {
      name: 'docs',
      cwd: path.join(__dirname, 'docs'),
      script: 'pnpm',
      args: `exec astro dev --host ${HOST} --port ${DOCS_PORT}`,
      interpreter: 'none',
      // Astro 7 daemonizes itself when it thinks an AI agent started it, which
      // leaves pm2 supervising a process that has already exited. Setting this
      // at all turns that detection off; the value is irrelevant.
      env: { ASTRO_DEV_BACKGROUND: '0' },
      autorestart: true,
    },
    ...DEMOS.map((name, i) => ({
      name,
      namespace: 'demos',
      cwd: path.join(__dirname, 'demos', name, 'frontend'),
      script: 'pnpm',
      args: `exec vite --host ${HOST} --port ${DEMO_BASE + i} --strictPort`,
      interpreter: 'none',
      autorestart: true,
    })),
  ],
};
