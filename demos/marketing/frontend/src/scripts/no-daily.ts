/**
 * Stands in for `@daily-co/daily-js` (aliased in astro.config.mjs).
 *
 * pipecat's small-webrtc transport imports daily-js only for its default media
 * manager. Every call here passes @voqalize/client-transport's manager instead, so
 * that path never runs, and this stub keeps daily-js out of the bundle. If anything
 * does reach it, it fails loudly instead of loading daily.
 */
function unavailable(): never {
  throw new Error('daily-js is not bundled on this site: construct the transport with createVoqalizeTransport()');
}

export default { createCallObject: unavailable, getCallInstance: unavailable };
