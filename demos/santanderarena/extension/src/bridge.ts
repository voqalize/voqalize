/**
 * The bridge between the page and the extension.
 *
 * The page's own script (`content.ts`) runs in the page's JavaScript world,
 * where extension messaging does not exist; this one runs in the extension's
 * isolated world on the same page, where it does. It carries `window`
 * messages tagged `voqalize:out` on, and the answers back as `voqalize:in`:
 *
 *   - to the holder (`holder.ts`, the offscreen document the call lives in),
 *     over one port, which the holder's messages come back on;
 *   - to the service worker (`background.ts`), as one message each.
 *
 * A port opened while there is no holder has no one at the other end and
 * stays useless, so the port is opened only once the holder is up: at once
 * when the worker says it is, and again whenever the worker says a holder has
 * just come up (`holder-up`). The page is told (`holder-up`) so it says hello
 * on the new port, and told when the holder went away (`holder-down`).
 */

import { PORT } from "./protocol";

const OUT = "voqalize:out";
const IN = "voqalize:in";

interface Out {
  to: "holder" | "sw";
  /** A request, answered with `re`. */
  ask?: Record<string, unknown>;
  id?: number;
  /** A message for the holder. */
  msg?: unknown;
}

let port: chrome.runtime.Port | null = null;

const toPage = (msg: unknown) => window.postMessage({ [IN]: msg }, location.origin);

function connect(): void {
  try {
    port?.disconnect();
  } catch {
    /* Already gone. */
  }
  let p: chrome.runtime.Port;
  try {
    p = chrome.runtime.connect({ name: PORT });
  } catch {
    // The extension was reloaded under this page: it has no extension now.
    port = null;
    return;
  }
  port = p;
  p.onMessage.addListener((msg: unknown) => toPage(msg));
  p.onDisconnect.addListener(() => {
    void chrome.runtime.lastError;
    if (port !== p) return;
    port = null;
    toPage({ k: "holder-down" });
  });
  toPage({ k: "holder-up" });
}

async function toWorker(ask: Record<string, unknown>): Promise<unknown> {
  try {
    return await chrome.runtime.sendMessage({ to: "sw", ...ask });
  } catch {
    return null;
  }
}

window.addEventListener("message", (e: MessageEvent) => {
  if (e.source !== window) return;
  const data = e.data as Record<string, unknown> | null;
  if (!data || typeof data !== "object" || !(OUT in data)) return;
  const out = data[OUT] as Out;
  if (out.to === "sw" && out.ask) {
    void (async () => {
      const result = await toWorker(out.ask!);
      // The holder is up once the worker answers `ensure`: open the port to
      // it before the page asks it anything.
      if (out.ask!.op === "ensure" && (result as { ok?: boolean } | null)?.ok && !port) connect();
      toPage({ re: out.id, result });
    })();
    return;
  }
  if (out.to !== "holder") return;
  const msg = out.ask ? { ask: out.ask, id: out.id } : out.msg;
  if (!port) {
    // No holder: an ask is answered at once, and a message has no one to go to.
    if (out.ask) toPage({ re: out.id, result: null });
    return;
  }
  try {
    port.postMessage(msg);
  } catch {
    port = null;
    if (out.ask) toPage({ re: out.id, result: null });
  }
});

chrome.runtime.onMessage.addListener((msg: { k?: string }) => {
  if (msg?.k === "holder-up") connect();
});

const reconnect = () =>
  void toWorker({ op: "has_holder" }).then((got) => {
    if ((got as { up?: boolean } | null)?.up && !port) connect();
  });
reconnect();
// Back from the back/forward cache, whose pages lose their ports.
window.addEventListener("pageshow", (e) => {
  if (e.persisted) {
    port = null;
    reconnect();
  }
});
