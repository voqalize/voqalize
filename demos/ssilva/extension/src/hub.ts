/**
 * The page's end of the extension, through `bridge.ts`: messages for the
 * holder (the offscreen document the call lives in, `holder.ts`) and its
 * messages back, and requests of the holder and of the service worker.
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

/** The language the visitor chose on the toggle on any Ssilva host, or
 *  `null` if they never have. */
export async function sharedLanguage(): Promise<"es" | "en" | null> {
  const got = await askWorker<{ lang: "es" | "en" | null }>({ op: "get_lang" }, 1500);
  return got?.lang ?? null;
}

/** Keep the visitor's choice for every Ssilva host. */
export function shareLanguage(lang: "es" | "en"): void {
  void askWorker({ op: "set_lang", lang });
}

/** A move for a tab's next page to make once it is up. */
export interface Then {
  command: string;
  payload: unknown;
}

/** Open a page in a new tab, as a move of Javier's (a project's WhatsApp
 *  chat): the service worker opens it, since his moves arrive over the call
 *  and a page may not open a tab without the visitor's click. The reason it
 *  did not open, or `null`. */
export async function openTab(url: string): Promise<string | null> {
  const got = await askWorker<{ ok: boolean; error?: string }>({ op: "open_tab", url });
  if (got?.ok) return null;
  if (got) return got.error ?? "the tab did not open";
  // No extension to ask (it was reloaded under the page): the page's own
  // window.open, which a popup blocker may refuse.
  return window.open(url, "_blank", "noopener") ? null : "the browser blocked the new tab";
}

/** Keep a move for this tab's next page, which the adapter's `navigate` is
 *  about to load: kept by the service worker, for this browser tab. Whether it
 *  was kept. */
export async function setPendingMove(then: Then): Promise<boolean> {
  const got = await askWorker<{ ok: boolean }>({ op: "pend", then });
  return Boolean(got?.ok);
}

/** The move this tab's last page left for this one (`setPendingMove`), once. */
export async function pendingMove(): Promise<Then | null> {
  const got = await askWorker<{ then: Then | null }>({ op: "pending" });
  return got?.then ?? null;
}
