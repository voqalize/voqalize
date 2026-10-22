/**
 * The hub: one call across every Cannon Home tab, with or without `www.`.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. Cannon Home answers on cannonhome.cl
 * and on www.cannonhome.cl (which redirects to it, but a tab can still be on
 * it), two origins. So the relay runs here, in the extension's service worker,
 * which every tab of both hosts reaches through `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     reloads takes its own call back and no other tab can take it meanwhile;
 *   - a page Javier opens with no site tab open opens in a new tab from here
 *     (`chrome.tabs.create`), because the page itself may only open a tab from
 *     the visitor's own click and his move arrives over the call, not a click.
 *
 * The worker may be stopped while nothing is happening; its one piece of state,
 * the holder, is kept in `chrome.storage.session` so a restart forgets nothing.
 * The visitor's language choice is kept in `chrome.storage.local`, so it holds
 * on both origins and the next visit.
 */

interface Port extends chrome.runtime.Port {}

/** Requests a tab makes of the hub, answered on the same port with `re`. */
type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "pending" }
  | { op: "get_lang" }
  | { op: "set_lang"; lang: "es" | "en" };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

const ports = new Map<number, Set<Port>>();

/** Where the visitor's language choice is kept, in `chrome.storage.local`. */
const LANG_KEY = "lang";

/**
 * Where a tab Javier opens may point: Cannon Home's own pages (never its
 * checkout, its account pages or a payment), and WhatsApp, which the site
 * links as its sales chat. Nothing else, whatever the brain sends.
 */
const OPENABLE = [
  /^https:\/\/(www\.)?cannonhome\.cl(\/(?!checkout(?!\/cart\/?(\?|#|$))|customer\/account|onestepcheckout)|$)/i,
  /^https:\/\/(wa\.me|api\.whatsapp\.com)\//i,
];

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
      if (!OPENABLE.some((re) => re.test(ask.url))) {
        return { ok: false, error: `not an address Javier opens: ${ask.url}` };
      }
      const created = await chrome.tabs.create({ url: ask.url, active: ask.active ?? true, openerTabId: tab });
      // A move for the new page once it is up (a section of the page to
      // scroll to): kept until that tab asks for it.
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
    // The visitor's language on the widget's toggle, for both origins: a
    // page's own storage is per origin.
    case "get_lang": {
      const got = await chrome.storage.local.get(LANG_KEY);
      const lang = got[LANG_KEY];
      return { lang: lang === "es" || lang === "en" ? lang : null };
    }
    case "set_lang": {
      if (ask.lang !== "es" && ask.lang !== "en") return { ok: false };
      await chrome.storage.local.set({ [LANG_KEY]: ask.lang });
      return { ok: true };
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
