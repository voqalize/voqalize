/**
 * The page's end of the extension, through the bridge: messages for the
 * holder (the offscreen document the call lives in) and its messages back,
 * requests of the holder and of the service worker, and the job a page leaves
 * for the next one (`loadThen`, which may be on another host).
 */

import type { FromPage, HolderAsk, Job, ToPage, WorkerAsk } from "./protocol.js";

export const OUT = "voqalize:out";
export const IN = "voqalize:in";

/** What the bridge says itself: a holder is there to talk to, or went away. */
export type FromBridge = { k: "holder-up" } | { k: "holder-down" };

let nextId = 1;
const waiting = new Map<number, (result: unknown) => void>();
const listeners = new Set<(msg: ToPage | FromBridge) => void>();
let listening = false;

function out(msg: unknown): void {
  window.postMessage({ [OUT]: msg }, location.origin);
}

function listen(): void {
  if (listening) return;
  listening = true;
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
}

function request<T>(to: "holder" | "sw", ask: HolderAsk | WorkerAsk, ms: number): Promise<T | null> {
  listen();
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
  listen();
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let loads = 0;

/** How many loads this page has started (`loadThen`): a move that should
 *  have loaded another page and did not can be told from one that stayed. */
export const loadsStarted = () => loads;

/** Load `url` in this tab, with a job for the page it lands on to make once
 *  it is up (`pendingMove`), across hosts: the page itself goes, so the job
 *  is kept by the service worker, for this browser tab. */
export async function loadThen(url: string, then?: Job): Promise<void> {
  if (then) await askWorker({ op: "pend", then });
  loads++;
  location.href = url;
}

/** Keep a job for this tab's next page, should the page go before it is done;
 *  `pendingMove` takes it back. Internal: a move keeps the rest of itself
 *  with `MoveContext.keep`/`drop`. */
export async function pend(then: Job): Promise<void> {
  await askWorker({ op: "pend", then });
}

/** Forget the job kept for this tab's next page, if it is `callRef`'s. */
export async function unpend(callRef: string): Promise<void> {
  await askWorker({ op: "unpend", call_ref: callRef });
}

/** The job this tab's last page left for this one (`loadThen`), once. */
export async function pendingMove(): Promise<Job | null> {
  const got = await askWorker<{ then: Job | null }>({ op: "pending" });
  return got?.then ?? null;
}

/** The visitor's language choice, kept by the worker for every host. */
export async function sharedLanguage(): Promise<string | null> {
  const got = await askWorker<{ lang: string | null }>({ op: "get_lang" }, 1500);
  return got?.lang ?? null;
}

export function shareLanguage(lang: string): void {
  void askWorker({ op: "set_lang", lang });
}
