/**
 * The page's end of the extension, through `bridge.ts`: messages for the
 * holder (the offscreen document the call lives in, `holder.ts`) and its
 * messages back, and requests of the holder and of the service worker: the
 * move a page leaves for the next one (`loadThen`, which may be on the other
 * host), and a www.explora.com page's translations, read by the worker.
 */

import type { FromPage, HolderAsk, ToPage, WorkerAsk } from "./protocol";

const OUT = "voqalize:out";
const IN = "voqalize:in";

/** What the bridge says itself: a holder is there to talk to, or went away. */
export type FromBridge = { k: "holder-up" } | { k: "holder-down" };

let nextId = 1;
const waiting = new Map<number, (result: unknown) => void>();
const listeners = new Set<(msg: ToPage | FromBridge) => void>();

function out(msg: unknown): void {
  window.postMessage({ [OUT]: msg }, location.origin);
}

window.addEventListener("message", (e: MessageEvent) => {
  if (e.source !== window) return;
  const data = e.data as Record<string, unknown> | null;
  if (!data || typeof data !== "object" || !(IN in data)) return;
  const msg = data[IN] as { re?: number; result?: unknown } & Record<string, unknown>;
  if (msg.re !== undefined) {
    waiting.get(msg.re)?.(msg.result);
    waiting.delete(msg.re);
    return;
  }
  for (const fn of listeners) {
    try {
      fn(msg as unknown as ToPage | FromBridge);
    } catch (error) {
      console.error(error);
    }
  }
});

function request<T>(to: "holder" | "sw", ask: HolderAsk | WorkerAsk, ms: number): Promise<T | null> {
  const id = nextId++;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      waiting.delete(id);
      resolve(null);
    }, ms);
    waiting.set(id, (result) => {
      clearTimeout(timer);
      resolve((result ?? null) as T | null);
    });
    out({ to, ask, id });
  });
}

/** One request of the holder; `null` when there is none, or no answer in time. */
export const askHolder = <T>(ask: HolderAsk, ms = 5000) => request<T>("holder", ask, ms);

/** One request of the service worker; `null` when it does not answer in time
 *  (the extension was reloaded under the page). */
export const askWorker = <T>(ask: WorkerAsk, ms = 5000) => request<T>("sw", ask, ms);

/** A message for the holder; dropped when there is none. */
export function tell(msg: FromPage): void {
  out({ to: "holder", msg });
}

export function onHolder(fn: (msg: ToPage | FromBridge) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** A move for the tab's next page to make once it is up. */
export interface Then {
  command: string;
  payload: unknown;
}

let loads = 0;

/** How many loads this page has started (`loadThen`): a move that should
 *  have loaded another page and did not can be told from one that stayed. */
export const loadsStarted = () => loads;

/** Load `url` in this tab, with a move for the page it lands on to make once
 *  it is up (`pendingMove`), across hosts: the page itself goes, so the move
 *  is kept by the service worker, for this browser tab. */
export async function loadThen(url: string, then?: Then): Promise<void> {
  if (then) await askWorker({ op: "pend", then });
  loads++;
  location.href = url;
}

/** Keep a move for this tab's next page, should the page go before it is
 *  done (a button that may load another page); `pendingMove` takes it back. */
export async function pend(then: Then): Promise<void> {
  await askWorker({ op: "pend", then });
}

/** The move this tab's last page left for this one (`loadThen`), once. */
export async function pendingMove(): Promise<Then | null> {
  const got = await askWorker<{ then: Then | null }>({ op: "pending" });
  return got?.then ?? null;
}
