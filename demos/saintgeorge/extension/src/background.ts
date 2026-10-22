/**
 * The hub: one call across every Saint George's tab.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. The school's site answers on
 * saintgeorge.cl (and www.saintgeorge.cl, which redirects there), and its
 * pages load in full, so the call's tab is between documents at every move. So
 * the relay runs here, in the extension's service worker, which every tab
 * reaches through `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     reloads takes its own call back and no other tab can take it meanwhile;
 *   - a page Javier opens in a new tab — a document, the musical's tickets, a
 *     families' portal, or a site page when no site tab is open — opens from
 *     here (`chrome.tabs.create`), because the page itself may only open a tab
 *     from the visitor's own click and his move arrives over the call, not a
 *     click. Only the hosts the site itself links; the extension does not run
 *     on any of them but the site;
 *   - the school's public calendar is fetched here (`calendar`): its iCal
 *     feed sends no CORS headers, so the page cannot read it, and the brain,
 *     far from Chile, must not. The worker has a host permission for it.
 *
 * The worker may be stopped while nothing is happening; its one piece of state,
 * the holder, is kept in `chrome.storage.session` so a restart forgets nothing.
 */

import { ICAL_URL, parseIcs, todayIn, upcoming } from "./ical";

interface Port extends chrome.runtime.Port {}

/** Requests a tab makes of the hub, answered on the same port with `re`. */
type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "pending" }
  | { op: "calendar"; count?: number };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

const ports = new Map<number, Set<Port>>();

/** The addresses Javier may open a tab on: the site's own (its documents,
 *  its families' systems), and the hosts its pages link: the musical's
 *  tickets, the families' portals, the careers portal, the community's sites. */
const OPENABLE =
  /^https:\/\/([a-z0-9-]+\.)*(saintgeorge\.cl|ticketplus\.cl|colegium\.com|lirmi\.com|profejobs\.cl|cdasaintgeorge\.cl|oldgeorgians\.cl|congregaciondesantacruz\.cl|sites\.google\.com|instagram\.com|linkedin\.com)(\/|$)/i;

/** How long a read of the calendar is kept: one call reads it once or twice. */
const CALENDAR_TTL_MS = 10 * 60_000;
let calendar: { at: number; events: ReturnType<typeof parseIcs> } | null = null;

/** The calendar's coming events, fetched here and parsed (`ical.ts`). */
async function readCalendar(count: number): Promise<unknown> {
  if (!calendar || Date.now() - calendar.at > CALENDAR_TTL_MS) {
    const res = await fetch(ICAL_URL, { cache: "no-store" });
    if (!res.ok) return { ok: false, error: `the school's calendar answered ${res.status}` };
    calendar = { at: Date.now(), events: parseIcs(await res.text()) };
  }
  const now = new Date();
  return { ok: true, today: todayIn(now), events: upcoming(calendar.events, now, count) };
}

/** How long a holder's tab may be without a port (a page loading) before its
 *  claim lapses, should the tab never come back. */
const HOLDER_AWAY_MS = 20_000;

interface Holder {
  tab: number;
  /** When the holder's last port closed, or 0 while it is connected. */
  awaySince: number;
}

async function holder(): Promise<Holder | null> {
  const got = await chrome.storage.session.get("holder");
  return (got.holder as Holder | undefined) ?? null;
}

async function setHolder(next: Holder | null): Promise<void> {
  if (next) await chrome.storage.session.set({ holder: next });
  else await chrome.storage.session.remove("holder");
}

async function answer(tab: number, ask: Ask): Promise<unknown> {
  switch (ask.op) {
    case "whoami":
      return { tab };
    case "lock": {
      const h = await holder();
      const lapsed = h && h.awaySince && Date.now() - h.awaySince > HOLDER_AWAY_MS && !ports.has(h.tab);
      if (!h || h.tab === tab || lapsed) {
        await setHolder({ tab, awaySince: 0 });
        return { ok: true };
      }
      return { ok: false };
    }
    case "unlock": {
      const h = await holder();
      if (h?.tab === tab) await setHolder(null);
      return { ok: true };
    }
    case "open_tab": {
      if (!OPENABLE.test(ask.url)) {
        return { ok: false, error: `not an address the school's site links to: ${ask.url}` };
      }
      const created = await chrome.tabs.create({ url: ask.url, active: ask.active ?? true, openerTabId: tab });
      // A move for the new page once it is up (a section of it to scroll
      // to): kept until that tab asks for it.
      if (ask.then !== undefined && created.id !== undefined) {
        await chrome.storage.session.set({ [`pending:${created.id}`]: ask.then });
      }
      return { ok: true, tab: created.id };
    }
    case "focus_tab": {
      const t = await chrome.tabs.update(ask.tab, { active: true });
      if (t?.windowId !== undefined) await chrome.windows.update(t.windowId, { focused: true });
      return { ok: true };
    }
    case "calendar":
      return readCalendar(Math.min(Math.max(ask.count ?? 30, 1), 60));
    case "pending": {
      const key = `pending:${tab}`;
      const got = await chrome.storage.session.get(key);
      await chrome.storage.session.remove(key);
      return { then: got[key] ?? null };
    }
  }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "voqalize") return;
  const tab = port.sender?.tab?.id;
  if (tab === undefined) return port.disconnect();
  (ports.get(tab) ?? ports.set(tab, new Set()).get(tab)!).add(port);
  void holder().then((h) => {
    if (h?.tab === tab && h.awaySince) void setHolder({ tab, awaySince: 0 });
  });

  port.onMessage.addListener((msg: FromTab) => {
    if (msg.ask) {
      void answer(tab, msg.ask)
        .catch((error: unknown) => ({ ok: false, error: String(error) }))
        .then((result) => {
          try {
            port.postMessage({ re: msg.id, result });
          } catch {
            /* The tab went away before its answer. */
          }
        });
      return;
    }
    if (msg.relay === undefined) return;
    for (const [other, set] of ports) {
      if (other === tab) continue;
      for (const p of set) {
        try {
          p.postMessage({ relay: msg.relay });
        } catch {
          /* Closed; onDisconnect tidies it. */
        }
      }
    }
  });

  port.onDisconnect.addListener(() => {
    const set = ports.get(tab);
    set?.delete(port);
    if (set && set.size === 0) {
      ports.delete(tab);
      void holder().then((h) => {
        if (h?.tab === tab) void setHolder({ tab, awaySince: Date.now() });
      });
    }
  });
});

// A closed tab's claim goes with it.
chrome.tabs.onRemoved.addListener((tab) => {
  ports.delete(tab);
  void holder().then((h) => {
    if (h?.tab === tab) void setHolder(null);
  });
});
