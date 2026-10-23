/**
 * The extension's service worker: what neither a page nor the holder may do.
 *
 *   - It makes the holder, the offscreen document the call lives in
 *     (`call.html`, `holder.ts`), on the visitor's first press of the call
 *     button, one at a time however many tabs ask, and tells every UAH tab, on
 *     all three hosts, when it is up (`holder-up`), so each page opens its port to it: a
 *     port opened before the holder existed has no one at the other end. It
 *     closes the holder when the holder says no page is left.
 *     The reasons are USER_MEDIA and WEB_RTC, which keep the document alive
 *     through any silence; AUDIO_PLAYBACK alone closes it after 30 s without
 *     sound.
 *   - It opens and focuses tabs for Javier's moves (`chrome.tabs`, which an
 *     offscreen document has no access to): the PAES simulator, a malla PDF; a
 *     page may only open a tab from the visitor's own click, and his moves
 *     arrive over the call.
 *   - It opens the microphone grant page in a tab of its own, when the grant
 *     made in the widget's frame did not hold (see `grant.ts`), and closes it
 *     once answered.
 *   - It keeps the visitor's language choice, in `chrome.storage.local`, so it
 *     holds on every host and the next visit.
 *   - It keeps what a page leaves for the next page of its tab (`stash`/
 *     `take`: the move a page was loaded to make), because `sessionStorage`
 *     does not cross from one UAH host to another; in `chrome.storage.session`,
 *     so a worker that was stopped meanwhile forgets nothing.
 *   - It reads the site's own records (`rest`): the site's REST API answers
 *     CORS only for https://www.uahurtado.cl, so a page on admision cannot read
 *     postgrados, and the extension's `host_permissions` let the worker read
 *     both. One career or programme by slug, never a whole list (postgrados'
 *     takes two minutes), and never longer than four seconds.
 */

import { htmlText } from "./text";

const HOLDER = "call.html";
const SITE_TABS = [
  "https://admision.uahurtado.cl/*",
  "https://postgrados.uahurtado.cl/*",
  "https://www.uahurtado.cl/*",
  "https://uahurtado.cl/*",
];

/** Where the visitor's language choice is kept, in `chrome.storage.local`. */
const LANG_KEY = "voqalize.uahurtado.lang";

/** The pages Javier may open in a new tab: any host of uahurtado.cl — the
 *  three sites, the PAES simulator, a PDF on one of them. Nothing else,
 *  whatever the brain sends. */
const OPENABLE = [/^https:\/\/([a-z0-9-]+\.)*uahurtado\.cl(\/|$)/i];

/** How long a stashed move waits for its tab's next page. */
const STASH_MS = 60_000;
/** How long the site's record may take before the page reads without it. */
const REST_DEADLINE_MS = 4000;

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
      justification: "Holds the voice call with Javier across the Universidad Alberto Hurtado's page loads and hosts: the microphone, the WebRTC connection and his voice.",
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

/** Every UAH tab: the holder is up, open a port to it. */
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

// ─── The site's own records ───────────────────────────────────────────────

const RECORD_URL = {
  carrera: (slug: string) =>
    `https://admision.uahurtado.cl/wp-json/wp/v2/carreras?slug=${encodeURIComponent(slug)}&_fields=acf.aranceles_carrera`,
  programa: (slug: string) =>
    `https://postgrados.uahurtado.cl/wp-json/wp/v2/programa?slug=${encodeURIComponent(slug)}` +
    "&_fields=acf.postulacion_desde,acf.postulacion_hasta,acf.inicio_programa,acf.requisitos_program",
};

const asText = (v: unknown) => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");

async function readRecord(kind: "carrera" | "programa", slug: string): Promise<unknown> {
  if (!(kind in RECORD_URL) || !/^[a-z0-9_-]{1,160}$/i.test(slug)) return { ok: false, error: "bad slug" };
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), REST_DEADLINE_MS);
  try {
    const res = await fetch(RECORD_URL[kind](slug), { signal: abort.signal, credentials: "omit" });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const rows = (await res.json()) as { acf?: Record<string, unknown> }[];
    const acf = Array.isArray(rows) ? rows[0]?.acf : undefined;
    if (!acf) return { ok: false, error: "no such record" };
    if (kind === "carrera") return { ok: true, record: { fees_text: htmlText(asText(acf.aranceles_carrera)) } };
    return {
      ok: true,
      record: {
        postulacion_desde: asText(acf.postulacion_desde),
        postulacion_hasta: asText(acf.postulacion_hasta),
        inicio_programa: asText(acf.inicio_programa),
        requisitos_text: htmlText(asText(acf.requisitos_program)),
      },
    };
  } catch (error) {
    return { ok: false, error: String(error) };
  } finally {
    clearTimeout(timer);
  }
}

// ─── Requests ────────────────────────────────────────────────────────────

interface Ask {
  to: "sw";
  op: string;
  url?: string;
  tab?: number;
  lang?: string;
  result?: string;
  key?: string;
  value?: unknown;
  kind?: "carrera" | "programa";
  slug?: string;
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
    // What a page keeps for the next page of its tab, on whichever host.
    case "stash": {
      const tab = sender.tab?.id;
      if (tab === undefined || !ask.key) return { ok: false };
      await chrome.storage.session.set({ [`${ask.key}:${tab}`]: { value: ask.value, at: Date.now() } });
      return { ok: true };
    }
    case "take": {
      const tab = sender.tab?.id;
      if (tab === undefined || !ask.key) return { value: null };
      const key = `${ask.key}:${tab}`;
      const got = await chrome.storage.session.get(key);
      await chrome.storage.session.remove(key);
      const kept = got[key] as { value: unknown; at: number } | undefined;
      // A page that never came (the load failed, the visitor went elsewhere)
      // leaves its move behind; a stale one is not made on a later page.
      return { value: kept && Date.now() - kept.at < STASH_MS ? kept.value : null };
    }
    case "rest":
      return readRecord(ask.kind ?? "carrera", ask.slug ?? "");
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
