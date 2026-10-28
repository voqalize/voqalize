/**
 * The extension's service worker: what neither a page nor the holder may do.
 *
 *   - It makes the holder, the offscreen document the call lives in
 *     (`call.html`), on the visitor's first press of the call button, one at
 *     a time however many tabs ask, and tells every tab of the site when it is
 *     up (`holder-up`), so each page opens its port to it. It closes the
 *     holder when the holder says no page is left. The reasons are USER_MEDIA
 *     and WEB_RTC, which keep the document alive through any silence;
 *     AUDIO_PLAYBACK alone closes it after 30 s without sound.
 *   - It opens and focuses tabs for the agent's moves (`chrome.tabs`, which an
 *     offscreen document has no access to), only at the site's own addresses.
 *   - It opens the microphone grant page in a tab of its own when the grant
 *     made in the widget's frame did not hold, and closes it once answered.
 *   - It keeps each tab's job for its next page (`pend`, `pending`, `unpend`), in
 *     `chrome.storage.session`, per browser tab: the next page may be another
 *     origin, and a worker stopped meanwhile forgets nothing.
 *   - It keeps the visitor's language choice for every host of the site, in
 *     `chrome.storage.local`.
 *   - It answers any request the site adds (`ops`).
 */

import { type SiteConfig } from "./site";

export interface BackgroundConfig {
  /** Where a tab the agent opens may point; nothing else is opened, whatever
   *  the agent sends. */
  openable: RegExp[];
  /** Chrome's offscreen justification: why the document holds a call. */
  justification: string;
  /** The holder's page (`call.html`). */
  holderPage?: string;
  /** The grant page (`grant.html`). */
  grantPage?: string;
  /** The site's own requests, by op. */
  ops?: Record<string, (ask: Record<string, unknown>, sender: chrome.runtime.MessageSender) => Promise<unknown>>;
}

/** How long the grant tab waits for the visitor's answer. */
const GRANT_TAB_MS = 120_000;
const LANG_KEY = "lang";

export function startBackground(site: SiteConfig, config: BackgroundConfig): void {
  const HOLDER = config.holderPage ?? "call.html";
  const GRANT = config.grantPage ?? "grant.html";
  const languages = new Set(site.widget.languages.map((l) => l.code));

  let making: Promise<void> | null = null;
  let closing: Promise<void> | null = null;

  async function hasHolder(): Promise<boolean> {
    const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
    return contexts.length > 0;
  }

  async function ensureHolder(): Promise<void> {
    if (closing) await closing;
    if (await hasHolder()) return;
    making ??= chrome.offscreen
      .createDocument({
        url: HOLDER,
        reasons: [chrome.offscreen.Reason.USER_MEDIA, chrome.offscreen.Reason.WEB_RTC],
        justification: config.justification,
      })
      .catch(async (error: unknown) => {
        // Made meanwhile by another call: that is the one.
        if (!(await hasHolder())) throw error;
      })
      .finally(() => {
        making = null;
      });
    await making;
  }

  async function closeHolder(): Promise<void> {
    if (making) await making.catch(() => {});
    closing ??= (async () => {
      if (await hasHolder()) await chrome.offscreen.closeDocument().catch(() => {});
    })().finally(() => {
      closing = null;
    });
    await closing;
  }

  async function holderUp(): Promise<void> {
    const open = await chrome.tabs.query({ url: site.matches });
    for (const t of open) {
      if (t.id === undefined) continue;
      chrome.tabs.sendMessage(t.id, { k: "holder-up" }).catch(() => {
        /* A tab whose content script is not there (still loading, or older). */
      });
    }
  }

  const grants = new Map<number, (result: string) => void>();

  async function focus(tab: number): Promise<void> {
    const t = await chrome.tabs.update(tab, { active: true });
    if (t?.windowId !== undefined) await chrome.windows.update(t.windowId, { focused: true });
  }

  async function grantTab(opener: number | undefined, lang: string): Promise<{ result: string }> {
    const l = languages.has(lang) ? lang : site.opening;
    const url = chrome.runtime.getURL(`${GRANT}?tab=1&lang=${encodeURIComponent(l)}`);
    const tab = await chrome.tabs.create({ url, active: true, openerTabId: opener });
    if (tab.id === undefined) return { result: "no tab" };
    const id = tab.id;
    const result = await new Promise<string>((resolve) => {
      const timer = setTimeout(() => resolve("timeout"), GRANT_TAB_MS);
      grants.set(id, (r) => {
        clearTimeout(timer);
        resolve(r);
      });
    });
    grants.delete(id);
    await chrome.tabs.remove(id).catch(() => {});
    if (opener !== undefined) await focus(opener).catch(() => {});
    return { result };
  }

  async function answer(ask: Record<string, unknown> & { op: string }, sender: chrome.runtime.MessageSender): Promise<unknown> {
    const tabId = sender.tab?.id;
    switch (ask.op) {
      case "ensure":
        await ensureHolder();
        return { ok: true };
      case "has_holder":
        return { up: await hasHolder() };
      case "holder_up":
        await holderUp();
        return { ok: true };
      case "holder_idle":
        await closeHolder();
        return { ok: true };
      case "open_tab": {
        const url = String(ask.url ?? "");
        if (!config.openable.some((re) => re.test(url))) return { ok: false, error: `not an address this extension opens: ${url}` };
        const created = await chrome.tabs.create({ url, active: true });
        return { ok: true, tab: created.id };
      }
      case "focus_tab":
        if (typeof ask.tab !== "number") return { ok: false };
        await focus(ask.tab);
        return { ok: true };
      case "grant_tab":
        return grantTab(tabId, String(ask.lang ?? site.opening));
      case "grant_done":
        if (tabId !== undefined) grants.get(tabId)?.(String(ask.result ?? ""));
        return { ok: true };
      case "grant_url":
        return { url: chrome.runtime.getURL(GRANT) };
      case "open_settings":
        await chrome.tabs.create({ url: "chrome://settings/content/microphone", active: true });
        return { ok: true };
      case "pend":
        if (tabId === undefined) return { ok: false };
        await chrome.storage.session.set({ [`pending:${tabId}`]: ask.then });
        return { ok: true };
      case "unpend": {
        if (tabId === undefined) return { ok: false };
        const key = `pending:${tabId}`;
        const got = (await chrome.storage.session.get(key))[key] as { call_ref?: string } | undefined;
        if (got && got.call_ref === ask.call_ref) await chrome.storage.session.remove(key);
        return { ok: true };
      }
      case "pending": {
        if (tabId === undefined) return { then: null };
        const key = `pending:${tabId}`;
        const got = await chrome.storage.session.get(key);
        await chrome.storage.session.remove(key);
        return { then: got[key] ?? null };
      }
      case "get_lang": {
        const got = await chrome.storage.local.get(LANG_KEY);
        const lang = got[LANG_KEY];
        return { lang: typeof lang === "string" && languages.has(lang) ? lang : null };
      }
      case "set_lang":
        if (typeof ask.lang !== "string" || !languages.has(ask.lang)) return { ok: false };
        await chrome.storage.local.set({ [LANG_KEY]: ask.lang });
        return { ok: true };
      default: {
        const op = config.ops?.[ask.op];
        return op ? op(ask, sender) : { ok: false, error: `unknown request ${ask.op}` };
      }
    }
  }

  chrome.runtime.onMessage.addListener((msg: { to?: string; op?: string }, sender, reply) => {
    if (msg?.to !== "sw" || typeof msg.op !== "string") return;
    void answer(msg as Record<string, unknown> & { op: string }, sender)
      .catch((error: unknown) => ({ ok: false, error: String(error) }))
      .then(reply);
    return true;
  });

  // A closed tab: the holder forgets it, and any job kept for it.
  chrome.tabs.onRemoved.addListener((tab) => {
    grants.get(tab)?.("closed");
    void chrome.storage.session.remove(`pending:${tab}`);
    void hasHolder().then((up) => {
      if (up) chrome.runtime.sendMessage({ to: "holder", op: "tab_removed", tab }).catch(() => {});
    });
  });
}
