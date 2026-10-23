/**
 * The site adapter alone, for the page test (`page.mjs`): what `content.ts`
 * lends it in the extension — the service worker's REST read, the microphone, the move
 * kept for the next page, a page load — is recorded here instead, and what it
 * reports is collected on `window.__uah`.
 */

import "../src/uah-actions";

import type { RestRecord, Then } from "../src/hub";

interface Recorder {
  events: [string, unknown][];
  mic: boolean[];
  pend: Then[];
  loads: string[];
  rest: Record<string, Record<string, RestRecord>>;
}

const rec: Recorder = { events: [], mic: [], pend: [], loads: [], rest: {} };
const adapter = window.voqalizeUah!;
adapter.configure({
  rest: async (kind, slug) => rec.rest[kind]?.[slug] ?? null,
  holdMic: (on) => void rec.mic.push(on),
  pend: async (then) => {
    rec.pend.push(then);
    return true;
  },
  load: (url) => void rec.loads.push(url),
});
adapter.start((event, payload) => void rec.events.push([event, payload]));

(window as unknown as { __uah: unknown }).__uah = { adapter, ...rec, rec };
