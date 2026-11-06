/**
 * Stands in for `@daily-co/daily-js` (see `no-daily.mjs`). Nothing on a page
 * built with `createVoqalizeTransport` or `useVoqalizeMedia` calls it; if
 * something does, it fails loudly rather than loading daily.
 */
function unavailable() {
  throw new Error(
    "daily-js is not bundled here: give the transport @voqalize/client-transport's media manager",
  );
}

export default { createCallObject: unavailable, getCallInstance: unavailable, version: unavailable };
