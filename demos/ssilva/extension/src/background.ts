/**
 * The hub: one call across every Ssilva tab, on both of its hosts.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. Ssilva answers on two
 * (www.ssilva.cl and ssilva.cl), and every link there is a full page load. So
 * the relay runs here, in the extension's service worker, which every tab of
 * both hosts reaches through `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     reloads takes its own call back and no other tab can take it meanwhile;
 *   - what a page keeps for its tab's next page (`stash` / `take`) is held
 *     here: the move Javier sent before a page load (the section to show on
 *     the page he opened) and the cues his voice had not reached yet;
 *   - a project's WhatsApp chat opens in a new tab from here
 *     (`chrome.tabs.create`), because the page itself may only open a tab from
 *     the visitor's own click and his move arrives over the call, not a click.
 *
 * The worker may be stopped while nothing is happening; its state, the holder
 * and what is stashed, is kept in `chrome.storage.session` so a restart
 * forgets nothing.
 */

interface Port extends chrome.runtime.Port {}

/** Requests a tab makes of the hub, answered on the same port with `re`. */
type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "stash"; key: string; value: unknown }
  | { op: "take"; key: string };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

/** The pages Javier may open in a new tab: Ssilva's, and WhatsApp's chat. */
const OPENABLE = /^https:\/\/((www\.)?ssilva\.cl|wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)(\/|$)/i;

/** How long a stashed move waits for its tab's next page. */
const STASH_MS = 60_000;

const ports = new Map<number, Set<Port>>();

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
        return { ok: false, error: `not a Ssilva or WhatsApp address: ${ask.url}` };
      }
      const created = await chrome.tabs.create({ url: ask.url, active: ask.active ?? true, openerTabId: tab });
      // A move for the new page once it is up (a section to scroll to):
      // kept until that tab asks for it.
      if (ask.then !== undefined && created.id !== undefined) {
        await chrome.storage.session.set({ [`pending:${created.id}`]: { value: ask.then, at: Date.now() } });
      }
      return { ok: true, tab: created.id };
    }
    case "focus_tab": {
      const t = await chrome.tabs.update(ask.tab, { active: true });
      if (t?.windowId !== undefined) await chrome.windows.update(t.windowId, { focused: true });
      return { ok: true };
    }
    case "stash": {
      await chrome.storage.session.set({ [`${ask.key}:${tab}`]: { value: ask.value, at: Date.now() } });
      return { ok: true };
    }
    case "take": {
      const key = `${ask.key}:${tab}`;
      const got = await chrome.storage.session.get(key);
      await chrome.storage.session.remove(key);
      const kept = got[key] as { value: unknown; at: number } | undefined;
      // A page that never came (the load failed, the visitor went elsewhere)
      // leaves its move behind; a stale one is not made on a later page.
      return { value: kept && Date.now() - kept.at < STASH_MS ? kept.value : null };
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

// A closed tab's claim goes with it, and anything it kept.
chrome.tabs.onRemoved.addListener((tab) => {
  ports.delete(tab);
  void chrome.storage.session.remove([`pending:${tab}`, `cues:${tab}`]);
  void holder().then((h) => {
    if (h?.tab === tab) void setHolder(null);
  });
});
