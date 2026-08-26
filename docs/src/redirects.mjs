/**
 * Every URL this site has ever published that no longer exists, and where it
 * went. One map, two consumers.
 *
 * `astro.config.mjs` turns each entry into a redirect for the browser.
 * `src/pages/[...slug].md.ts` turns the same entry into a markdown stub at the
 * old path plus `.md`, because **Astro's static redirects are meta-refresh
 * HTML** — the twin route never runs for them, so an agent that follows
 * `/deploy/inbound.md` out of an `llms.txt` it fetched last week gets a 404
 * where a human gets a working page. Verified in `dist/` on 2026-08-25: the
 * pre-existing `/client/react` redirect emitted `client/react/index.html` and
 * no `client/react.md` at all.
 *
 * On 2026-08-25 the tree went to four sections whose names are their
 * namespaces, which moved sixteen of the twenty-six pages that had shipped. A
 * URL is navigation that survives being copied; these are the copies.
 *
 * Plain `.mjs` for the same reason `sidebar.mjs` is: the Astro config and a
 * `src/pages/` endpoint both import it and neither should have to care how the
 * other's toolchain handles TypeScript.
 */
export const redirects = {
  // Start dissolved into Build — it was the prologue of the next section.
  "/start/session-end-to-end": "/build/session",
  "/start/pipecat": "/build/pipecat",
  "/start/what-voqalize-is": "/",

  // Eight namespaces became four. `deploy` described our verb, not the
  // reader's; `client` and `brain` were component names, not places.
  "/deploy/brain-url": "/build/hosting",
  "/deploy/inbound": "/build/inbound",
  "/deploy/cortex": "/build/outbound",
  "/client/handshake": "/build/connect",
  "/client/avatar": "/build/avatar",
  "/brain/testing": "/build/testing",
  "/operate/keys": "/build/keys",
  "/develop": "/design",

  // `@voqalize/client-react` was deprecated 2026-08-24 and its page deleted
  // rather than rewritten. The replacement has since moved too, so this
  // repoints at where it landed rather than chaining through a second hop.
  "/client/react": "/build/connect",

  // Slugs that read wrong without their page open.
  "/design/voice-points-screen-holds": "/design/speech-vs-screen",
  "/design/the-turn-budget": "/design/turn-budget",
  "/operate/logs": "/operate/reading-a-call",

  // Folded into the page it was arguing with.
  "/reference/no-provider-slot": "/reference/catalog",
};
