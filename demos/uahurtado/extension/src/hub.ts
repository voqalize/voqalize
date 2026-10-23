/**
 * The page's end of the extension, through `bridge.ts`: messages for the
 * holder (the offscreen document the call lives in, `holder.ts`) and its
 * messages back, and requests of the holder and of the service worker — among
 * them what a page keeps for the next page of its tab, on any of the three
 * hosts (`sessionStorage` does not cross from one host to another), and the
 * site's own records, which only the service worker may read across hosts.
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

/** The language the visitor chose on the toggle on any UAH host, or `null`
 *  if they never have. */
export async function sharedLanguage(): Promise<"es" | "en" | null> {
  const got = await askWorker<{ lang: "es" | "en" | null }>({ op: "get_lang" }, 1500);
  return got?.lang ?? null;
}

/** Keep the visitor's choice for every UAH host. */
export function shareLanguage(lang: "es" | "en"): void {
  void askWorker({ op: "set_lang", lang });
}

/** A move for the tab's next page to make once it is up. */
export interface Then {
  command: string;
  payload: unknown;
}

/** Keep `value` for this tab's next page, on any host, under `key`; taken
 *  once (`take`), and only for a minute. */
export async function stash(key: string, value: unknown): Promise<boolean> {
  const got = await askWorker<{ ok: boolean }>({ op: "stash", key, value });
  return Boolean(got?.ok);
}

/** What this tab's last page kept under `key`, once. */
export async function take<T>(key: string): Promise<T | null> {
  const got = await askWorker<{ value: T | null }>({ op: "take", key }, 1500);
  return got?.value ?? null;
}

/** A move for this tab's next page to make once it is up: a page Action sent
 *  before a full page load (perhaps to another host), made on the page it
 *  loads. `false` when the worker did not take it. */
export function setPendingMove(then: Then): Promise<boolean> {
  return stash("pending", then);
}

/** The move this tab's page was loaded to make, once. */
export function pendingMove(): Promise<Then | null> {
  return take<Then>("pending");
}

/** What the service worker read of the site's own record of a career
 *  (`carrera`: its fees, as text) or a programme (`programa`: its dates and
 *  requisitos), or `null` when the read failed or took too long. */
export interface RestRecord {
  fees_text?: string;
  postulacion_desde?: string;
  postulacion_hasta?: string;
  inicio_programa?: string;
  requisitos_text?: string;
}

export async function readRecord(kind: "carrera" | "programa", slug: string): Promise<RestRecord | null> {
  const got = await askWorker<{ ok: boolean; record?: RestRecord }>({ op: "rest", kind, slug }, 5000);
  return got?.ok ? (got.record ?? null) : null;
}
