/**
 * The extension's service worker: what neither a page nor the holder may do.
 *
 *   - It makes the holder, the offscreen document the call lives in
 *     (`call.html`, `holder.ts`), on the visitor's first press of the call
 *     button, one at a time however many tabs ask, and tells every Ssilva tab
 *     when it is up (`holder-up`), so each page opens its port to it: a port
 *     opened before the holder existed has no one at the other end. It closes
 *     the holder when the holder says no page is left.
 *     The reasons are USER_MEDIA and WEB_RTC, which keep the document alive
 *     through any silence; AUDIO_PLAYBACK alone closes it after 30 s without
 *     sound.
 *   - It opens and focuses tabs for Javier's moves (`chrome.tabs`, which an
 *     offscreen document has no access to): a page may only open a tab from
 *     the visitor's own click, and his moves arrive over the call. A project's
 *     WhatsApp chat opens this way, from the site adapter.
 *   - It keeps each tab's move for its next page (`pend`, `pending`): every
 *     link on ssilva.cl is a full page load, so the adapter's `navigate` to a
 *     project's section or typology leaves what to do there here, for the
 *     browser tab, and the page it loads takes it once.
 *   - It opens the microphone grant page in a tab of its own, when the grant
 *     made in the widget's frame did not hold (see `grant.ts`), and closes it
 *     once answered.
 *   - It keeps the visitor's language choice, in `chrome.storage.local`, so it
 *     holds on both origins (with and without `www.`) and the next visit.
 */

const HOLDER = "call.html";
const SITE_TABS = ["https://www.ssilva.cl/*", "https://ssilva.cl/*"];

/** Where the visitor's language choice is kept, in `chrome.storage.local`. */
const LANG_KEY = "lang";

/**
 * Where a tab Javier opens may point: Ssilva's own pages, and WhatsApp's chat
 * (a project's sales line). Nothing else, whatever the brain sends. The
 * extension does not run on WhatsApp, so that tab never joins the holder's
 * tab list.
 */
const OPENABLE = [/^https:\/\/((www\.)?ssilva\.cl|wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)(\/|$)/i];

/** How long a move kept for a tab's next page waits for it. */
const PENDING_MS = 60_000;

/** How long the grant tab waits for the visitor's answer. */
const GRANT_TAB_MS = 120_000;

// ─── The holder ──────────────────────────────────────────────────────────

let making: Promise<void> | null = null;
let closing: Promise<void> | null = null;

async function hasHolder(): Promise<boolean> {
  const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
  return contexts.length > 0;
}

/** Make the holder unless it is there; one at a time. */
async function ensureHolder(): Promise<void> {
  if (closing) await closing;
  if (await hasHolder()) return;
  making ??= chrome.offscreen
    .createDocument({
      url: HOLDER,
      reasons: [chrome.offscreen.Reason.USER_MEDIA, chrome.offscreen.Reason.WEB_RTC],
      justification: "Holds the voice call with Javier across Ssilva's page loads: the microphone, the WebRTC connection and his voice.",
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

/** Every Ssilva tab: the holder is up, open a port to it. */
async function holderUp(): Promise<void> {
  const open = await chrome.tabs.query({ url: SITE_TABS });
  for (const t of open) {
    if (t.id === undefined) continue;
    chrome.tabs.sendMessage(t.id, { k: "holder-up" }).catch(() => {
      /* A tab whose content script is not there (still loading, or older). */
    });
  }
}

// ─── The grant tab ───────────────────────────────────────────────────────

const grants = new Map<number, (result: string) => void>();

async function grantTab(opener: number | undefined, lang: string): Promise<{ result: string }> {
  const url = chrome.runtime.getURL(`grant.html?tab=1&lang=${lang === "en" ? "en" : "es"}`);
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

async function focus(tab: number): Promise<void> {
  const t = await chrome.tabs.update(tab, { active: true });
  if (t?.windowId !== undefined) await chrome.windows.update(t.windowId, { focused: true });
}

// ─── Requests ────────────────────────────────────────────────────────────

interface Ask {
  to: "sw";
  op: string;
  url?: string;
  tab?: number;
  lang?: string;
  result?: string;
  then?: unknown;
}

async function answer(ask: Ask, sender: chrome.runtime.MessageSender): Promise<unknown> {
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
      const url = ask.url ?? "";
      if (!OPENABLE.some((re) => re.test(url))) return { ok: false, error: `not a Ssilva or WhatsApp address: ${url}` };
      const created = await chrome.tabs.create({ url, active: true });
      return { ok: true, tab: created.id };
    }
    // A move for this tab's own next page: it is about to load another.
    case "pend":
      if (sender.tab?.id === undefined) return { ok: false };
      await chrome.storage.session.set({ [`pending:${sender.tab.id}`]: { then: ask.then, at: Date.now() } });
      return { ok: true };
    // The move this tab's last page left for this one, once. A page that never
    // came (the load failed, the visitor went elsewhere) leaves its move
    // behind; a stale one is not made on a later page.
    case "pending": {
      if (sender.tab?.id === undefined) return { then: null };
      const key = `pending:${sender.tab.id}`;
      const got = await chrome.storage.session.get(key);
      await chrome.storage.session.remove(key);
      const kept = got[key] as { then: unknown; at: number } | undefined;
      return { then: kept && Date.now() - kept.at < PENDING_MS ? kept.then : null };
    }
    case "focus_tab":
      if (ask.tab === undefined) return { ok: false };
      await focus(ask.tab);
      return { ok: true };
    case "grant_tab":
      return grantTab(sender.tab?.id, ask.lang ?? "es");
    case "grant_done":
      if (sender.tab?.id !== undefined) grants.get(sender.tab.id)?.(ask.result ?? "");
      return { ok: true };
    case "grant_url":
      return { url: chrome.runtime.getURL("grant.html") };
    case "open_settings":
      await chrome.tabs.create({ url: "chrome://settings/content/microphone", active: true });
      return { ok: true };
    // The visitor's language on the widget's toggle, for both origins: a
    // page's own storage is per origin.
    case "get_lang": {
      const got = await chrome.storage.local.get(LANG_KEY);
      const lang = got[LANG_KEY];
      return { lang: lang === "es" || lang === "en" ? lang : null };
    }
    case "set_lang":
      if (ask.lang !== "es" && ask.lang !== "en") return { ok: false };
      await chrome.storage.local.set({ [LANG_KEY]: ask.lang });
      return { ok: true };
    default:
      return { ok: false, error: `unknown request ${ask.op}` };
  }
}

chrome.runtime.onMessage.addListener((msg: Ask, sender, reply) => {
  if (msg?.to !== "sw") return;
  void answer(msg, sender)
    .catch((error: unknown) => ({ ok: false, error: String(error) }))
    .then(reply);
  return true;
});

// A closed tab: the holder forgets it, and any move kept for it.
chrome.tabs.onRemoved.addListener((tab) => {
  grants.get(tab)?.("closed");
  void chrome.storage.session.remove(`pending:${tab}`);
  void hasHolder().then((up) => {
    if (up) chrome.runtime.sendMessage({ to: "holder", op: "tab_removed", tab }).catch(() => {});
  });
});
