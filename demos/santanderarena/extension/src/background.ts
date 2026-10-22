/**
 * The hub: one call across every Santander Arena tab.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. Santander Arena answers on two,
 * www.santanderarena.cl and santanderarena.cl, and its pages load in full, so
 * the call's tab is between documents at every move. So the relay runs here,
 * in the extension's service worker, which every tab reaches through
 * `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     reloads takes its own call back and no other tab can take it meanwhile;
 *   - a page Javier opens in a new tab — a ticket, parking or VIP link on
 *     Puntoticket, or a site page when no site tab is open — opens from here
 *     (`chrome.tabs.create`), because the page itself may only open a tab from
 *     the visitor's own click and his move arrives over the call, not a click.
 *     Only those two sites; the extension does not run on Puntoticket.
 *
 * The worker may be stopped while nothing is happening; its one piece of state,
 * the holder, is kept in `chrome.storage.session` so a restart forgets nothing.
 */

interface Port extends chrome.runtime.Port {}

/** Requests a tab makes of the hub, answered on the same port with `re`. */
type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "pending" };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

const ports = new Map<number, Set<Port>>();

/** The addresses Javier may open a tab on: the site's; Puntoticket's, where
 *  its tickets, parking and VIP experiences are sold; and the arena's
 *  reservations site for private events, which keeps the arena's old name. */
const OPENABLE =
  /^https:\/\/((www\.)?(santanderarena\.cl|puntoticket\.com)|reservas\.movistararena\.cl)(\/|$)/i;

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
        return { ok: false, error: `not a Santander Arena or Puntoticket address: ${ask.url}` };
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
