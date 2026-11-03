/**
 * What one call keeps for itself across its pages and tabs.
 *
 * The snippet keeps a call's ledgers in the tab's `sessionStorage` (its call
 * lives in one tab): how many page views the brain has been sent (`page_seq`,
 * which the brain's mirror and every `run_site_tool` carry), each site tool's
 * failures, the coupon codes tried (hashed) and the undoable runs. Here one
 * call spans every tab of the site, so those ledgers live in `localStorage`,
 * which the site's tabs share, under the call's own id: a new call starts from
 * nothing, and a tab the agent opens mid-call carries on the same count.
 *
 * Two keys stay in the tab's own `sessionStorage`, where the snippet keeps
 * them, because they belong to the tab: a site tool's continuation across
 * the full page load it started, and when the agent last acted (so the next
 * page's view says `by: "agent"`). They are cleared the first time a tab
 * sees a new call.
 *
 * The call's id is made on the page whose button started it (`newCall`,
 * from the session's `init`), so every page can tell a new call from the one
 * it was already part of. `localStorage` is per origin: www.wom.cl and wom.cl
 * keep apart, which only matters if one call spans both.
 */

import type { PageSeq } from "@snippet/watcher";
import { CONTINUATION_KEY } from "@snippet/executor/keys";
import { AGENT_AT_KEY } from "@snippet/watcher";

import { SITE } from "./site";

// Not `voqalize.<id>.call`: that is the shell's own sessionStorage key.
const CALL = `voqalize.${SITE.id}.call_id`;
const JOINED = `voqalize.${SITE.id}.joined`;
const LEDGER = `voqalize.${SITE.id}.ledger.`;

function local(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function session(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Forget every ledger of every call. */
function dropLedgers(): void {
  const s = local();
  if (!s) return;
  const keys: string[] = [];
  for (let i = 0; i < s.length; i++) {
    const k = s.key(i);
    if (k?.startsWith(LEDGER)) keys.push(k);
  }
  for (const k of keys) s.removeItem(k);
}

/** A call is starting on this page: a new id, and nothing kept from the last. */
export function newCall(): void {
  dropLedgers();
  local()?.setItem(CALL, `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`);
}

/** This page is in the call now: the call's id, after clearing what this tab
 *  kept for a call before it. */
export function joinCall(): string {
  const id = local()?.getItem(CALL) ?? "none";
  const s = session();
  if (s && s.getItem(JOINED) !== id) {
    s.removeItem(CONTINUATION_KEY);
    s.removeItem(AGENT_AT_KEY);
    s.setItem(JOINED, id);
  }
  return id;
}

/** The call ended: its ledgers and this tab's continuation go. */
export function endCall(): void {
  dropLedgers();
  session()?.removeItem(CONTINUATION_KEY);
}

/** A `Storage` over the call's ledgers, for the snippet's ledgers (which read
 *  `win.sessionStorage`). */
export function ledgerStorage(call: string): Storage {
  const prefix = `${LEDGER}${call}.`;
  const s = () => local();
  const store = {
    getItem: (k: string) => s()?.getItem(prefix + k) ?? null,
    setItem: (k: string, v: string) => s()?.setItem(prefix + k, v),
    removeItem: (k: string) => s()?.removeItem(prefix + k),
    clear: () => dropLedgers(),
    key: () => null,
    get length() {
      return 0;
    },
  };
  return store as Storage;
}

/** The call's page-view count, read afresh each time: two tabs of one call
 *  count on one number. */
export function sharedPageSeq(store: Storage): PageSeq {
  const KEY = "page_seq";
  const read = () => Math.max(0, Math.floor(Number(store.getItem(KEY)) || 0));
  return {
    current: read,
    bump: () => {
      const n = read() + 1;
      store.setItem(KEY, String(n));
      return n;
    },
  };
}
