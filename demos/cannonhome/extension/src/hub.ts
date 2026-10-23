/**
 * The page's end of the hub (`background.ts`, reached through `bridge.ts`).
 *
 * `HubChannel` has the shape of a `BroadcastChannel` — `postMessage`,
 * `onmessage`, `addEventListener` — so the tab relay (`tabs.ts`, Qween's,
 * nearly unchanged) runs on it, and its messages reach every Cannon Home tab, with or
 * without `www.`, rather than only the tabs of one origin. `ask` is the rest: this
 * tab's id, the call's claim, and opening a tab without the visitor's click.
 */

const OUT = "voqalize:out";
const IN = "voqalize:in";

type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "pending" }
  | { op: "get_lang" }
  | { op: "set_lang"; lang: "es" | "en" };

let nextId = 1;
const waiting = new Map<number, (result: unknown) => void>();
const listeners = new Set<(e: MessageEvent) => void>();

function out(msg: unknown): void {
  window.postMessage({ [OUT]: msg }, location.origin);
}

window.addEventListener("message", (e: MessageEvent) => {
  if (e.source !== window) return;
  const data = e.data as Record<string, unknown> | null;
  if (!data || typeof data !== "object" || !(IN in data)) return;
  const msg = data[IN] as { re?: number; result?: unknown; relay?: unknown };
  if (msg.re !== undefined) {
    waiting.get(msg.re)?.(msg.result);
    waiting.delete(msg.re);
    return;
  }
  if (msg.relay === undefined) return;
  const event = new MessageEvent("message", { data: msg.relay });
  for (const fn of listeners) {
    try {
      fn(event);
    } catch (error) {
      console.error(error);
    }
  }
});

/** One request of the hub. `null` when it does not answer in time — the
 *  extension was reloaded under the page, or the bridge is missing. */
export function ask<T>(request: Ask, ms = 3000): Promise<T | null> {
  const id = nextId++;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      waiting.delete(id);
      resolve(null);
    }, ms);
    waiting.set(id, (result) => {
      clearTimeout(timer);
      resolve(result as T);
    });
    out({ ask: request, id });
  });
}

export class HubChannel {
  private handler: ((e: MessageEvent) => void) | null = null;

  postMessage(message: unknown): void {
    out({ relay: message });
  }

  set onmessage(fn: ((e: MessageEvent) => void) | null) {
    if (this.handler) listeners.delete(this.handler);
    this.handler = fn;
    if (fn) listeners.add(fn);
  }

  get onmessage(): ((e: MessageEvent) => void) | null {
    return this.handler;
  }

  addEventListener(_type: "message", fn: (e: MessageEvent) => void): void {
    listeners.add(fn);
  }

  removeEventListener(_type: "message", fn: (e: MessageEvent) => void): void {
    listeners.delete(fn);
  }
}

/** This browser tab's id, which survives its page loads. */
export async function tabId(): Promise<string> {
  const got = await ask<{ tab: number }>({ op: "whoami" });
  return got ? String(got.tab) : `p${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Take the call for this tab: the release, or `null` when another tab holds it.
 * The claim is the browser tab's, so this tab's next page takes it back after
 * a load. Without the hub (no bridge) every tab may take it.
 */
export async function takeCall(): Promise<(() => void) | null> {
  const got = await ask<{ ok: boolean }>({ op: "lock" });
  if (got && !got.ok) return null;
  return () => void ask({ op: "unlock" });
}

/** A move for the tab's next page to make once it is up. */
export interface Then {
  command: string;
  payload: unknown;
}

/** Open a Cannon Home page in a new tab, as a move of Javier's, with an
 *  optional move for that page to make once it has loaded. */
export async function openTab(url: string, then?: Then): Promise<string | null> {
  const got = await ask<{ ok: boolean; error?: string }>({ op: "open_tab", url, active: true, then });
  if (got?.ok) return null;
  if (got) return got.error ?? "the tab did not open";
  // No hub: the page's own window.open, which a popup blocker may refuse.
  return window.open(url, "_blank", "noopener") ? null : "the browser blocked the new tab";
}

/** Bring another of the browser's tabs to the front. */
export async function focusTab(tab: string): Promise<boolean> {
  const id = Number(tab);
  if (!Number.isInteger(id)) return false;
  const got = await ask<{ ok: boolean }>({ op: "focus_tab", tab: id });
  return Boolean(got?.ok);
}

/** The move this tab was opened to make, once: see `openTab`. */
export async function pendingMove(): Promise<Then | null> {
  const got = await ask<{ then: Then | null }>({ op: "pending" });
  return got?.then ?? null;
}

/** The language the visitor chose on the toggle on any Cannon Home host, or `null`
 *  if they never have (or there is no hub). */
export async function sharedLanguage(): Promise<"es" | "en" | null> {
  const got = await ask<{ lang: "es" | "en" | null }>({ op: "get_lang" }, 1500);
  return got?.lang ?? null;
}

/** Keep the visitor's choice for every Cannon Home host. */
export function shareLanguage(lang: "es" | "en"): void {
  void ask({ op: "set_lang", lang });
}
