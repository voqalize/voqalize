/**
 * The hub: one call across every Explora tab, on both of its origins.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. Explora is two: www.explora.com
 * (WordPress) and reservations.explora.com (the booking engine). A visitor
 * whose tab loads the booking site would otherwise lose Javier at the border.
 * So the relay runs here, in the extension's service worker, which every tab
 * of both hosts reaches through `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     reloads takes its own call back and no other tab can take it meanwhile;
 *   - a page Javier opens in a new tab opens from here
 *     (`chrome.tabs.create`), because the page itself may only open a tab from
 *     the visitor's own click and his move arrives over the call, not a click.
 *
 * The worker may be stopped while nothing is happening; its state — the holder,
 * each tab's move for its next page (`pend`) and each tab's saved call
 * (`stash`) — is kept in `chrome.storage.session` so a restart forgets nothing.
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
  | { op: "pend"; then: unknown }
  | { op: "stash"; call: string | null }
  | { op: "unstash" };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

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
      if (!/^https:\/\/([a-z0-9-]+\.)*explora\.com(\/|$)/i.test(ask.url)) {
        return { ok: false, error: `not an Explora address: ${ask.url}` };
      }
      const created = await chrome.tabs.create({ url: ask.url, active: ask.active ?? true, openerTabId: tab });
      // A move for the new page once it is up (a section of the post to
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
    // A move for this tab's own next page: it is about to load another.
    case "pend":
      await chrome.storage.session.set({ [`pending:${tab}`]: ask.then });
      return { ok: true };
    // The call this tab holds, as the transport saved it in the page's
    // `sessionStorage`, which is per origin: a load from www.explora.com to
    // reservations.explora.com in the same tab finds it here instead.
    case "stash":
      // A call is live: the visitor let one Explora host hear them. The other
      // host is another origin, which Chrome would ask again mid-call as the
      // tab moves to the booking site, so the microphone is allowed on every
      // Explora host now.
      if (ask.call) await allowMicrophone();
      if (ask.call) await chrome.storage.session.set({ [`call:${tab}`]: ask.call });
      else await chrome.storage.session.remove(`call:${tab}`);
      return { ok: true };
    case "unstash": {
      const key = `call:${tab}`;
      const got = await chrome.storage.session.get(key);
      return { call: (got[key] as string | undefined) ?? null };
    }
  }
}

/** The hosts a call moves between, as content-setting patterns. */
const EXPLORA_HOSTS = ["https://www.explora.com/*", "https://explora.com/*", "https://reservations.explora.com/*"];
let micAllowed = false;

async function allowMicrophone(): Promise<void> {
  if (micAllowed || !chrome.contentSettings?.microphone) return;
  micAllowed = true;
  for (const primaryPattern of EXPLORA_HOSTS) {
    try {
      await chrome.contentSettings.microphone.set({ primaryPattern, setting: "allow" });
    } catch (error) {
      console.warn("voqalize: could not allow the microphone on", primaryPattern, error);
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
  void chrome.storage.session.remove([`call:${tab}`, `pending:${tab}`]);
  void holder().then((h) => {
    if (h?.tab === tab) void setHolder(null);
  });
});
