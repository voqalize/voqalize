/**
 * The page's way to the service worker. Runs in the isolated world, where
 * `chrome.runtime` is; the page script (MAIN world) posts `{bridge, id, ask}`
 * on its own window and gets `{bridge, id, answer}` back.
 */

import { BRIDGE, type WorkerAnswer, type WorkerAsk } from "./tabs-protocol";

window.addEventListener("message", (e: MessageEvent) => {
  if (e.source !== window) return;
  const data = e.data as { bridge?: string; id?: number; ask?: WorkerAsk } | null;
  if (!data || data.bridge !== BRIDGE || !data.ask || typeof data.id !== "number") return;
  const id = data.id;
  chrome.runtime
    .sendMessage(data.ask)
    .then((answer: WorkerAnswer | undefined) => answer ?? { ok: false, error: "no answer from the extension" })
    .catch((error: unknown) => ({ ok: false, error: error instanceof Error ? error.message : String(error) }))
    .then((answer) => window.postMessage({ bridge: BRIDGE, id, answer }, location.origin));
});
