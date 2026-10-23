/**
 * The hub: one call across every UAH tab, on all three of the university's
 * hosts.
 *
 * Qween's tabs relay a call over a `BroadcastChannel` and claim it with a Web
 * Lock, and both are scoped to one origin. The university is three:
 * admision.uahurtado.cl (undergraduate admission), postgrados.uahurtado.cl and
 * www.uahurtado.cl, and every link between them is a full page load to another
 * origin. So the relay runs here, in the extension's service worker, which
 * every tab of every host reaches through `bridge.ts`:
 *
 *   - every message a tab posts is sent to every other tab, as a
 *     `BroadcastChannel` would, origin notwithstanding;
 *   - the call's claim (`lock`) is held here, by browser tab id, so a tab that
 *     loads another page — on any host — takes its own call back and no other
 *     tab can take it meanwhile;
 *   - what a page keeps for its tab's next page is held here, because
 *     `sessionStorage` does not cross hosts: once (`stash`/`take`) the move
 *     Javier sent before a load and the cues his voice had not reached; and
 *     until replaced (`keep`/`peek`) the transport's saved call and the
 *     call's language;
 *   - a page Javier opens in a new tab opens from here (`chrome.tabs.create`):
 *     the PAES simulator, a malla PDF; a page may only open a tab from the
 *     visitor's own click, and his move arrives over the call;
 *   - the site's own records are read from here (`rest`): the site's REST API
 *     answers CORS only for https://www.uahurtado.cl, so a page on admision
 *     cannot read postgrados, and the extension's `host_permissions` let the
 *     worker read both. One career or programme by slug, never a whole list
 *     (postgrados' takes two minutes), and never longer than four seconds.
 *
 * The worker may be stopped while nothing is happening; its state is kept in
 * `chrome.storage.session` so a restart forgets nothing. The visitor's choice
 * of language is in `chrome.storage.local`, for every host and every visit.
 */

import { htmlText } from "./text";

interface Port extends chrome.runtime.Port {}

/** Requests a tab makes of the hub, answered on the same port with `re`. */
type Ask =
  | { op: "whoami" }
  | { op: "lock" }
  | { op: "unlock" }
  | { op: "open_tab"; url: string; active?: boolean; then?: unknown }
  | { op: "focus_tab"; tab: number }
  | { op: "stash"; key: string; value: unknown }
  | { op: "take"; key: string }
  | { op: "keep"; key: string; value: unknown }
  | { op: "peek"; key: string }
  | { op: "get_lang" }
  | { op: "set_lang"; lang: "es" | "en" }
  | { op: "rest"; kind: "carrera" | "programa"; slug: string };

interface FromTab {
  /** A relay message for every other tab. */
  relay?: unknown;
  /** A request for the hub, with the id its answer carries. */
  ask?: Ask;
  id?: number;
}

const ports = new Map<number, Set<Port>>();

/** The pages Javier may open in a new tab: any host of uahurtado.cl — the
 *  three sites, the PAES simulator, a PDF on one of them. */
const OPENABLE = /^https:\/\/([a-z0-9-]+\.)*uahurtado\.cl(\/|$)/i;

/** The hosts a call moves between, as content-setting patterns. */
const UAH_HOSTS = [
  "https://admision.uahurtado.cl/*",
  "https://postgrados.uahurtado.cl/*",
  "https://www.uahurtado.cl/*",
  "https://uahurtado.cl/*",
];

/** How long a stashed move waits for its tab's next page. */
const STASH_MS = 60_000;
/** How long the site's record may take before the page reads without it. */
const REST_DEADLINE_MS = 4000;
const LANG_KEY = "voqalize.uahurtado.lang";

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
      if (!OPENABLE.test(ask.url)) return { ok: false, error: `not a uahurtado.cl address: ${ask.url}` };
      const created = await chrome.tabs.create({ url: ask.url, active: ask.active ?? true, openerTabId: tab });
      // A move for the new page once it is up: kept until that tab asks.
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
    case "stash":
      await chrome.storage.session.set({ [`${ask.key}:${tab}`]: { value: ask.value, at: Date.now() } });
      return { ok: true };
    case "take": {
      const key = `${ask.key}:${tab}`;
      const got = await chrome.storage.session.get(key);
      await chrome.storage.session.remove(key);
      const kept = got[key] as { value: unknown; at: number } | undefined;
      // A page that never came (the load failed, the visitor went elsewhere)
      // leaves its move behind; a stale one is not made on a later page.
      return { value: kept && Date.now() - kept.at < STASH_MS ? kept.value : null };
    }
    case "keep": {
      const key = `keep:${ask.key}:${tab}`;
      if (ask.value === null || ask.value === undefined) await chrome.storage.session.remove(key);
      else await chrome.storage.session.set({ [key]: ask.value });
      // A call is live: the visitor let one UAH host hear them. The other
      // hosts are other origins, which Chrome would ask again mid-call as the
      // tab moves between them, so the microphone is allowed on all now.
      if (ask.key === "call" && ask.value) await allowMicrophone();
      return { ok: true };
    }
    case "peek": {
      const key = `keep:${ask.key}:${tab}`;
      const got = await chrome.storage.session.get(key);
      return { value: got[key] ?? null };
    }
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
    case "rest":
      return readRecord(ask.kind, ask.slug);
  }
}

let micAllowed = false;

async function allowMicrophone(): Promise<void> {
  if (micAllowed || !chrome.contentSettings?.microphone) return;
  micAllowed = true;
  for (const primaryPattern of UAH_HOSTS) {
    try {
      await chrome.contentSettings.microphone.set({ primaryPattern, setting: "allow" });
    } catch (error) {
      console.warn("voqalize: could not allow the microphone on", primaryPattern, error);
    }
  }
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

// ─── Ports ────────────────────────────────────────────────────────────────

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
  void chrome.storage.session.remove([
    `pending:${tab}`, `cues:${tab}`, `keep:call:${tab}`, `keep:call-lang:${tab}`,
  ]);
  void holder().then((h) => {
    if (h?.tab === tab) void setHolder(null);
  });
});
