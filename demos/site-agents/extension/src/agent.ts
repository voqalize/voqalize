/**
 * The Site Agent, as a page of the site reaches it: the agent's
 * configuration and the session's `init`.
 *
 *   1. The key: the site's own publishable key (its `site_live` key, which
 *      the owner rotates in the console), baked into this script at build
 *      time from `.env`. It is allowed on the site's origins only.
 *   2. The configuration: `GET {api}/embed.config` with the key, from this
 *      page's own world, so the request carries the site's Origin, which the
 *      key's allowlist checks; `credentials: "omit"`. It is the Site Agent's
 *      published state: the site, the live agent, the version, the settings
 *      and the adapter (page types, pages, listings, regions, tools,
 *      navigation, goals), the same answer the paste-in snippet runs on. The
 *      agent, the site and the version are taken from it, never written down
 *      here.
 *   3. The session: `sessions.connect {agent_id, init}` (the shared page host
 *      sends it), with `init` exactly as the snippet's (`call/request.ts`):
 *      `{site_id, version, path, page_type, preview}`, plus `language` when the
 *      call opens in one the site serves. No `record`: a publishable key
 *      cannot turn it on, and the agent records by default.
 */

import type { Language } from "@voqalize/stage/extension";
import type { EmbedConfig } from "@snippet/api.gen";
import { fetchEmbedConfig } from "@snippet/loader/config";
import { pageTypeFromUrl, type SessionInit } from "@snippet/call/request";
import { onPrivatePage, privatePath } from "@snippet/private";
import { PRIVATE_PAGE_TYPE } from "@snippet/refused.gen";

import { newCall } from "./call-store";
import { codeOf } from "./languages";
import { type Blocker, LANGUAGES } from "./site";

declare const __VOQALIZE__: { apiBase: string; publishableKey: string; agentId: string };

let config: EmbedConfig | null = null;
let blocker: Blocker | null = null;

/** What the shared page host mints the session with, read when the call
 *  starts: the agent is embed.config's. */
export const api = {
  apiBase: __VOQALIZE__.apiBase,
  publishableKey: __VOQALIZE__.publishableKey,
  /** Not empty while embed.config is on its way (the host only checks that
   *  there is one; `sessionInit` refuses a call without the configuration). */
  get agentId(): string {
    return config?.agent_id ?? (blocker ? "" : "pending");
  },
};

/** The API's origin: the snippet's paths carry their own `/api/v1`. */
const apiOrigin = () => new URL(__VOQALIZE__.apiBase).origin;

async function load(): Promise<void> {
  config = null;
  if (!api.publishableKey) {
    blocker = "no_key";
    return;
  }
  const res = await fetchEmbedConfig(apiOrigin(), api.publishableKey);
  if (!res.ok) {
    console.warn(`voqalize: embed.config answered ${res.status} ${res.code}`);
    blocker = "no_config";
    return;
  }
  if (!res.config.enabled) {
    blocker = "unavailable";
    return;
  }
  config = res.config;
  blocker = null;
  // The agent id in .env, if any, is a cross-check only.
  if (__VOQALIZE__.agentId && __VOQALIZE__.agentId !== config.agent_id) {
    console.warn(`voqalize: embed.config serves agent ${config.agent_id}, not the ${__VOQALIZE__.agentId} in .env; using embed.config's`);
  }
}

let loading: Promise<void> = load().catch((error: unknown) => {
  console.warn("voqalize: the Site Agent could not be reached", error);
  blocker = "no_config";
});

export const agent = {
  /** Settles once the configuration is in (or is known not to come). */
  get ready(): Promise<void> {
    return loading;
  },
  get config(): EmbedConfig | null {
    return config;
  },
  get blocker(): Blocker | null {
    return blocker;
  },
  /** Read the configuration again (it was refused, or never came), for the
   *  next press. */
  reload(): Promise<void> {
    loading = load().catch(() => {
      blocker = "no_config";
    });
    return loading;
  },
};

/** The toggle's languages the site serves (settings.voice), in the toggle's
 *  order; all of them before the configuration is in. */
export function servedLanguages(): Language[] {
  const voice = config?.settings.voice;
  if (!voice) return [...LANGUAGES];
  const names = [...(voice.languages ?? []), ...(voice.default_language ? [voice.default_language] : [])];
  const codes = new Set(names.map(codeOf).filter((c): c is string => c !== null));
  if (!codes.size) codes.add("en");
  return LANGUAGES.filter((c) => codes.has(c));
}

/** The language a call opens in when the site does not serve the one asked
 *  for: the site's default, as the brain falls back to it. */
export function fallbackLanguage(): Language {
  const d = config?.settings.voice?.default_language;
  const code = d ? codeOf(d) : null;
  if (code && (LANGUAGES as readonly string[]).includes(code)) return code;
  return servedLanguages()[0] ?? "en";
}

/** The settings' own spelling of a toggle code, as `init.language` and the
 *  snippet carry it; the code itself when the settings spell it so. */
function settingsName(code: Language): string {
  const names = config?.settings.voice?.languages ?? [];
  return names.find((n) => codeOf(n) === code) ?? code;
}

/** This page's path and type, as the snippet reports them at the start (the
 *  visitor's own pages are cut after their private segment). */
function where(): { path: string; page_type: string } {
  if (!config) return { path: "/", page_type: "other" };
  const priv = onPrivatePage(location);
  const path = priv ? privatePath(location.pathname) : location.pathname;
  return { path, page_type: priv ? PRIVATE_PAGE_TYPE : pageTypeFromUrl(config.adapter, path) };
}

/** The session's `init`, built as the page starts a call; this page's
 *  button started it, so the call's ledgers start afresh. */
export function sessionInit(language: Language): SessionInit {
  if (!config) throw new Error("no agent configured");
  newCall();
  const init: SessionInit = {
    site_id: config.site_id,
    version: config.version,
    ...where(),
    preview: config.mode === "preview",
  };
  if (servedLanguages().includes(language)) init.language = settingsName(language);
  return init;
}
