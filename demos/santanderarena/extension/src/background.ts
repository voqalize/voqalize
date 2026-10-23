/**
 * The extension's service worker: what neither a page nor the holder may do.
 *
 *   - It makes the holder, the offscreen document the call lives in
 *     (`call.html`, `holder.ts`), on the visitor's first press of the call
 *     button, one at a time however many tabs ask, and tells every Santander
 *     Arena tab when it is up (`holder-up`), so each page opens its port to it: a
 *     port opened before the holder existed has no one at the other end. It
 *     closes the holder when the holder says no page is left.
 *     The reasons are USER_MEDIA and WEB_RTC, which keep the document alive
 *     through any silence; AUDIO_PLAYBACK alone closes it after 30 s without
 *     sound.
 *   - It opens and focuses tabs for Javier's moves (`chrome.tabs`, which an
 *     offscreen document has no access to): a page may only open a tab from
 *     the visitor's own click, and his moves arrive over the call.
 *   - It opens the microphone grant page in a tab of its own, when the grant
 *     made in the widget's frame did not hold (see `grant.ts`), and closes it
 *     once answered.
 *   - It keeps the visitor's language choice, in `chrome.storage.local`, so it
 *     holds on both origins (with and without `www.`) and the next visit.
 */

const HOLDER = "call.html";
const SITE_TABS = ["https://www.santanderarena.cl/*", "https://santanderarena.cl/*"];

/** Where the visitor's language choice is kept, in `chrome.storage.local`. */
const LANG_KEY = "lang";

/**
 * Where a tab Javier opens may point: the site's own pages; Puntoticket's,
 * where its tickets, parking and VIP experiences are sold; and the arena's
 * reservations site for private events, which keeps the arena's old name.
 * Nothing else, whatever the brain sends. The extension does not run on
 * Puntoticket or the reservations site.
 */
const OPENABLE = [
  /^https:\/\/((www\.)?(santanderarena\.cl|puntoticket\.com)|reservas\.movistararena\.cl)(\/|$)/i,
];

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
      justification: "Holds the voice call with Javier across Santander Arena's page loads: the microphone, the WebRTC connection and his voice.",
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

/** Every Santander Arena tab: the holder is up, open a port to it. */
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
      if (!OPENABLE.some((re) => re.test(url))) return { ok: false, error: `not an address Javier opens: ${url}` };
      const created = await chrome.tabs.create({ url, active: true });
      return { ok: true, tab: created.id };
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
  void hasHolder().then((up) => {
    if (up) chrome.runtime.sendMessage({ to: "holder", op: "tab_removed", tab }).catch(() => {});
  });
});
