/**
 * The page's half of a site extension: the content script, in the page's own
 * JavaScript world (the manifest's `"world": "MAIN"`), on every page of the
 * site. It brings the widget, the character's face (drawn against a stand-in
 * client the holder feeds), and the site's adapter for this host: the moves it
 * registers with Stage, and what it reports.
 *
 * The call does not live here; it lives in the holder, which every page of
 * the site follows over a port. So a full page load, or a load to another host
 * of the site, changes nothing on the call. The holder sends this page the
 * jobs meant for it, and keeps them while the page loads; this page makes
 * each one and answers with its result.
 *
 * On the call button this page does what the holder cannot: it asks the
 * visitor for the extension's microphone the first time (a frame of the
 * extension's own grant page), and mints the session with `sessions.connect`
 * (this page's fetch carries the site's Origin, which the publishable key
 * allows), then hands the answer to the holder.
 */

import { type Carried, type Carrier, Moves } from "../moves";
import { Spotlight, type SpotlightTheme } from "../spotlight";
import type { StageResult } from "../wire.gen";
import { type FollowedClient, followCall, type Following } from "./follow";
import {
  askHolder, askWorker, loadThen, onHolder, pend, pendingMove, shareLanguage, sharedLanguage, tell, unpend,
} from "./hub";
import { clearKept, type Kept, transitions, writeKept } from "./persist";
import type { CallState, Job, MicState, Where } from "./protocol";
import { mountedFlag, type SiteConfig, shellFlag } from "./site";
import { DEFAULT_TRANSITION_NAME, type Language, mountWidget, watchObstacles, type Widget } from "./widget";

/** What a page's adapter can use. */
export interface PageKit {
  readonly moves: Moves;
  readonly spotlight: Spotlight;
  /** The call's language (or the next call's, off a call). */
  language(): Language;
  /** The call's state as this page has it. */
  state(): Readonly<CallState>;
  /** Report one of the site's events to the agent: sent while the call can
   *  hear this page and it is on screen (or the event is an any-tab one). */
  emit(event: string, payload: unknown): void;
  /** Load `url` in this tab, with a job for the page it lands on. */
  loadThen(url: string, then?: Job): Promise<void>;
}

/** What an adapter gives back, all optional. */
export interface SiteHooks {
  /** What the visitor is looking at, for the session's start. */
  context?(): Record<string, unknown>;
  /** Report the page as it stands through `emit` (`page_changed`, say). Run
   *  once the agent can hear this page, before `start`, and again each time
   *  the tab comes back to the front. */
  report?(emit: (event: string, payload: unknown) => void): void;
  /** Report what the page shows through `emit` as it changes, until the
   *  returned stop. Run once the agent can hear this page. */
  start?(emit: (event: string, payload: unknown) => void): () => void;
  /** One of the site's own Actions, sent to this page. */
  command?(command: string, payload: unknown): Promise<void> | void;
}

export type Adapter = (moves: Moves, kit: PageKit) => SiteHooks | void;

/** The stand-in client handed to `AvatarHooks.create`: a `FollowedClient`,
 *  assignable to any copy of pipecat's `PipecatClient` class (whose private
 *  members no structural type could match). */
export type AvatarClient = FollowedClient & any;

/** The avatar, as the site's package draws it. */
export interface AvatarHooks {
  /** Draw the face in `mount` against `client`: a stand-in the holder feeds,
   *  shaped as the avatar reads a `PipecatClient` (`FollowedClient`). Typed
   *  loosely on purpose, so it passes as the `PipecatClient` of whichever
   *  pipecat copy the site's avatar package was built against. */
  create(mount: HTMLElement, client: AvatarClient): { destroy(): void };
  /** Start building the face before it is shown. */
  preload?(): { ready?: Promise<unknown> } | void;
  /** The character's still, for the invite. */
  still?(): Promise<string | null>;
}

export interface SiteExtensionConfig {
  site: SiteConfig;
  /** The session's mint: the API base, the agent and the publishable key. */
  api: { apiBase: string; agentId: string; publishableKey: string };
  /** The adapters, by host name (`www.example.com`); `*` for any other. */
  adapters: Record<string, Adapter>;
  spotlight: SpotlightTheme;
  /** Selectors of the site's pinned bars, for scrolling under them. */
  fixed?: readonly string[];
  avatar?: AvatarHooks;
  /** The session's `init`: `surface` and anything else the agent reads. */
  sessionInit(ctx: { language: Language; chosen: Language | null; context: Record<string, unknown> }): Record<string, unknown>;
  /** The page's own language, for the toggle off a call when the visitor has
   *  chosen none. */
  pageLanguage?(): Language | null;
  /** A Stage move this host has no performer for: the address on another
   *  host to load, where the move is made once the call is up there; `null`
   *  fails the move. */
  elsewhere?(job: Extract<Job, { kind: "stage" }>, kit: PageKit): string | null | Promise<string | null>;
  /** The site's events the agent takes from any tab. */
  anyTab?: readonly string[];
  /** What the page pins over its corners, for the widget to keep clear of. */
  obstacles?: readonly { selector: string; fixedOnly?: boolean }[];
  /** While a call is live, links to these addresses lose `target="_blank"`,
   *  so the visitor's own clicks load in the tab the agent moves. */
  keepLinksInTab?: RegExp;
  /** Called on every call state, for a site that marks the page (an
   *  attribute that hides a second microphone, say). */
  onCallState?(on: boolean): void;
  /** The name of the console handle (`__voqalize<Site>`) that drives the
   *  page's moves with no call. */
  consoleName?: string;
  /** Words for a call that did not start. */
  failure?(text: string, language: Language): string;
}

/** How long a widget carried over from the last page waits for the holder. */
const CARRIED_WAIT_MS = 8000;
/** How long the empty face slot waits for the live face to draw. */
const UNVEIL_WAIT_MS = 10_000;
const SWITCH_WAIT_MS = 4000;
const GRANT_WAIT_MS = 90_000;
/** A job kept for this page is made this long after the call is up on it
 *  (the agent waits for this page's report, which goes first); with no call,
 *  this long after the page knows there is none; and no later than the last. */
const MOVE_AFTER_READY_MS = 300;
const MOVE_WITHOUT_CALL_MS = 800;
const MOVE_AT_THE_LATEST_MS = 10_000;
/** A move that started a load and is still on this page this long after
 *  failed: the screen has not moved. */
const UNLOAD_WAIT_MS = 8000;
/** A tab back in front reports again, once for its `visibilitychange` and
 *  `focus` together. */
const REPORT_AGAIN_MS = 250;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Run the content script: mounts once the page is parsed (never on `load`,
 *  which a site's trackers can hold back for many seconds). */
export function defineSiteExtension(config: SiteExtensionConfig): void {
  if (document.readyState !== "loading") void start(config);
  else document.addEventListener("DOMContentLoaded", () => void start(config), { once: true });
}

async function start(config: SiteExtensionConfig): Promise<void> {
  const { site } = config;
  const flags = window as unknown as Record<string, unknown>;
  const adapterFor = config.adapters[location.hostname] ?? config.adapters["*"];
  if (!adapterFor || flags[mountedFlag(site)]) return;
  flags[mountedFlag(site)] = true;
  const api = config.api;
  if (!api.agentId || !api.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start");
  }
  const langKey = `voqalize.${site.id}.lang`;
  const anyTab = new Set(["stage_result", ...(config.anyTab ?? [])]);
  const idle = (language: Language): CallState => ({ status: "idle", muted: false, activity: null, language, ready: false });

  const keptMove = pendingMove();
  const shell = flags[shellFlag(site)] as { widget: Widget; kept: Kept } | undefined;
  const widget = shell?.widget ?? mountWidget(site.widget);
  const preloaded = shell ? (config.avatar?.preload?.() ?? null) : null;
  let still: string | null = shell?.kept.still ?? null;
  let heard = false;
  watchObstacles(widget, config.obstacles ?? []);

  const offCall = () => storedLanguage(langKey) ?? config.pageLanguage?.() ?? site.opening;
  let state: CallState = idle(shell?.kept.language ?? offCall());
  let following: Following | null = null;
  let avatar: { destroy(): void } | null = null;
  let stopAdapter: (() => void) | null = null;
  let restoreLinks: (() => void) | null = null;
  let calling = false;
  let switchTimer: ReturnType<typeof setTimeout> | null = null;
  let keptTaken = false;
  let gone = false;

  const showing = () => document.visibilityState === "visible";
  const where = (): Where => ({ url: location.href, title: document.title, front: showing() && document.hasFocus() });
  const hello = () => tell({ k: "hello", ...where() });

  // ─── Stage on this page ────────────────────────────────────────────────

  const spotlight = new Spotlight(config.spotlight);
  /** The move last carried to this tab's next page. */
  let lastCarried: Carried | null = null;
  /** Carries a move to this tab's next page: kept by the service worker (the
   *  next page may be on another host), and owed to the holder from there. */
  const carrier: Carrier = {
    async keep(c: Carried) {
      lastCarried = c;
      tell({ k: "carried", call_ref: c.call_ref, move: c.move });
      await pend(c);
    },
    async drop(callRef: string) {
      await unpend(callRef);
      tell({ k: "uncarried", call_ref: callRef });
    },
    load(url: string) {
      void loadThen(url);
      watchUnload(lastCarried);
    },
  };
  const moves = new Moves(spotlight, { fixed: config.fixed, carrier });

  /** A move that loaded another page and is still here a while after: the
   *  agent is told the screen has not moved, and the next page owes nothing. */
  function watchUnload(c: Carried | null): void {
    if (!c) return;
    setTimeout(() => {
      if (gone) return;
      void unpend(c.call_ref);
      const result: StageResult = {
        call_ref: c.call_ref, move: c.move, outcome: "failed", detail: "the page did not load; the screen has not moved",
        refused: [], moved: false, ms: UNLOAD_WAIT_MS,
      };
      if (state.ready) tell({ k: "result", result });
    }, UNLOAD_WAIT_MS);
  }

  const kit: PageKit = {
    moves,
    spotlight,
    language: () => state.language,
    state: () => state,
    emit: (event, payload) => {
      if (state.ready && (showing() || anyTab.has(event))) tell({ k: "app", event, payload });
    },
    loadThen,
  };
  const hooks: SiteHooks = adapterFor(moves, kit) ?? {};

  function send(result: StageResult): void {
    if (state.ready) tell({ k: "result", result });
    else console.info("voqalize (no call):", result);
  }

  /** Make one Stage job here, or load the host it belongs on, where the same
   *  move is made. `null` when its result is the next page's. */
  async function makeStage(job: Extract<Job, { kind: "stage" }>): Promise<StageResult | null> {
    if (!moves.has(job.move)) {
      const url = await config.elsewhere?.(job, kit);
      if (url) {
        await carrier.keep({ kind: "carried", call_ref: job.call_ref, move: job.move, then: { move: job.move, args: job.args } });
        spotlight.clear();
        carrier.load(url);
        return null;
      }
    }
    return moves.run(job.move, job.args, job.call_ref);
  }

  async function perform(job: Job): Promise<StageResult | null> {
    if (job.kind === "site") {
      try {
        await hooks.command?.(job.command, job.payload);
      } catch (error) {
        console.warn("voqalize:", job.command, error);
      }
      return null;
    }
    if (job.kind === "carried") return moves.resume(job);
    return makeStage(job);
  }

  // Driving the page from the console, with no call.
  flags[config.consoleName ?? `__voqalize_${site.id}`] = {
    move: (move: string, args: unknown) => perform({ kind: "stage", move, args, call_ref: `console-${Date.now()}` }),
    command: (command: string, payload: unknown) => perform({ kind: "site", command, payload }),
    moves: () => moves.ids,
    language: () => state.language,
  };

  // ─── The call's state on this page ─────────────────────────────────────

  function showLanguage(next: Language): void {
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = null;
    widget.setLanguage(next);
  }

  function apply(next: CallState): void {
    const on = next.status === "live" || next.status === "connecting";
    // In a call the language is the call's, as the holder keeps it; off a
    // call, the visitor's own choice for the next call.
    if (!on) next = { ...next, language: offCall() };
    const was = state;
    state = next;
    if (calling && !on) return;
    transitions(on, site.widget.transitionName ?? DEFAULT_TRANSITION_NAME);
    config.onCallState?.(on);
    if (!on) clearKept(site.id);
    if (on) follow();
    else unfollow();
    widget.paint(next.status, next.message);
    widget.setMuted(next.muted);
    if (next.activity) widget.setActivity(next.activity);
    if (next.language !== was.language || !switchTimer) showLanguage(next.language);
    if (next.status === "live" && was.status !== "live") following?.joined();
    if (next.status === "live" && config.keepLinksInTab && !restoreLinks) restoreLinks = keepLinksInTab(config.keepLinksInTab);
    keep();
    // The page reports once the agent can hear it, then makes the job the
    // last page left for it.
    if (next.ready && !stopAdapter) {
      report();
      stopAdapter = hooks.start?.((event, payload) => kit.emit(event, payload)) ?? (() => {});
      takeKept(MOVE_AFTER_READY_MS);
    }
    if (!on && heard) takeKept(MOVE_WITHOUT_CALL_MS);
  }

  function follow(): void {
    if (following) return;
    following = followCall();
    avatar?.destroy();
    avatar = config.avatar?.create(widget.face, following.client) ?? null;
    if (shell) handOver();
  }

  function unfollow(): void {
    stopAdapter?.();
    stopAdapter = null;
    restoreLinks?.();
    restoreLinks = null;
    following?.stop();
    following = null;
    avatar?.destroy();
    avatar = null;
    spotlight.clear();
    widget.unveil();
  }

  function keep(): void {
    if (state.status !== "live" && state.status !== "connecting") return;
    writeKept(site.id, {
      status: state.status, muted: state.muted, activity: state.activity, language: state.language, still,
      ...widget.layout(),
    });
  }

  /** The face's slot the shell left empty: the live face fades in once it
   *  has drawn. */
  function handOver(): void {
    const since = Date.now();
    let built = !preloaded?.ready;
    void preloaded?.ready?.catch(() => {}).then(() => {
      built = true;
    });
    const look = () => {
      if (!avatar) return;
      if (Date.now() - since > UNVEIL_WAIT_MS) return widget.unveil();
      if (!built) return void setTimeout(look, 50);
      const img = widget.face.querySelector("img");
      if (img?.complete && img.naturalWidth) return widget.unveil();
      void drawn().then((yes) => (yes ? widget.unveil() : setTimeout(look, 50)));
    };
    look();
  }

  /** Whether the face has drawn a frame yet, read after the avatar's own
   *  frame: a WebGL canvas keeps its picture only until the frame is shown. */
  function drawn(): Promise<boolean> {
    return new Promise((resolve) =>
      requestAnimationFrame(() => {
        const canvas = widget.face.querySelector("canvas");
        if (!canvas?.width || !canvas.height) return resolve(false);
        try {
          const probe = document.createElement("canvas");
          probe.width = probe.height = 8;
          const g = probe.getContext("2d", { willReadFrequently: true });
          if (!g) return resolve(false);
          g.drawImage(canvas, 0, 0, 8, 8);
          const px = g.getImageData(0, 0, 8, 8).data;
          for (let i = 3; i < px.length; i += 4) if (px[i]! > 0) return resolve(true);
          resolve(false);
        } catch {
          resolve(false);
        }
      }),
    );
  }

  /** Make the job the last page left for this one, once, `delay` from now. */
  function takeKept(delay: number): void {
    if (keptTaken) return;
    keptTaken = true;
    void keptMove.then(async (then) => {
      if (!then) return;
      await sleep(delay);
      const result = await perform(then);
      if (result) send(result);
    });
  }

  onHolder((msg) => {
    switch (msg.k) {
      case "holder-up":
        return hello();
      case "holder-down":
        return apply(idle(state.language));
      case "state":
        heard = true;
        return apply(msg);
      case "perform":
        void perform(msg.job).then((result) => {
          // A move handed to the next page: its result is that page's.
          if (msg.job.kind !== "site" && result === null) return tell({ k: "done", id: msg.id, result: null, deferred: true });
          tell({ k: "done", id: msg.id, result });
        });
        return;
    }
  });

  // ─── The call button ───────────────────────────────────────────────────

  async function micReady(lang: Language): Promise<"ok" | "denied"> {
    const read = async () => (await askHolder<{ state: MicState }>({ op: "mic" }))?.state ?? "prompt";
    let mic = await read();
    if (mic === "granted") return "ok";
    if (mic === "denied") return "denied";
    const page = (await askWorker<{ url: string }>({ op: "grant_url" }))?.url;
    if (page) {
      const origin = new URL(page).origin;
      const answered = new Promise<void>((resolve) => {
        const timer = setTimeout(done, GRANT_WAIT_MS);
        function done() {
          clearTimeout(timer);
          window.removeEventListener("message", on);
          resolve();
        }
        function on(e: MessageEvent) {
          if (e.origin === origin && (e.data as { voqalizeGrant?: unknown } | null)?.voqalizeGrant) done();
        }
        window.addEventListener("message", on);
      });
      widget.grant(`${page}?lang=${encodeURIComponent(lang)}`);
      await answered;
      widget.grant(null);
      mic = await read();
      if (mic === "granted") return "ok";
      if (mic === "denied") return "denied";
    }
    // The grant made in the frame did not reach the extension: the same page
    // in a tab of its own, closed once answered.
    await askWorker({ op: "grant_tab", lang }, 130_000);
    mic = await read();
    return mic === "denied" ? "denied" : "ok";
  }

  async function mintSession(init: Record<string, unknown>): Promise<unknown> {
    const res = await fetch(`${api.apiBase}/sessions.connect`, {
      method: "POST",
      headers: { Authorization: `Bearer ${api.publishableKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: api.agentId, init }),
    });
    const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    if (!res.ok) {
      const error = body?.error as { message?: string } | string | undefined;
      const detail = typeof error === "string" ? error : (error?.message ?? (body?.detail as string | undefined));
      throw new Error(detail ? String(detail) : `HTTP ${res.status}`);
    }
    return body;
  }

  async function call(): Promise<void> {
    if (calling || state.status === "live" || state.status === "connecting") return;
    calling = true;
    const lang = state.language;
    widget.paint("connecting");
    config.onCallState?.(true);
    try {
      if (!api.agentId || !api.publishableKey) throw new Error("no agent configured");
      const up = await askWorker<{ ok: boolean; error?: string }>({ op: "ensure" }, 10_000);
      if (!up?.ok) throw new Error(up?.error ?? "the extension did not answer; reload the page");
      hello();
      if ((await micReady(lang)) === "denied") {
        calling = false;
        config.onCallState?.(false);
        widget.blocked();
        return;
      }
      // `chosen` only when the visitor chose it: the agent then holds to it.
      const chosen = (await sharedLanguage()) ?? storedLanguage(langKey);
      const language = chosen ?? config.pageLanguage?.() ?? site.opening;
      const session = await mintSession(config.sessionInit({ language, chosen, context: hooks.context?.() ?? {} }));
      const got = await askHolder<{ ok: boolean; error?: string }>({ op: "call", session, language }, 30_000);
      if (!got?.ok) throw new Error(got?.error ?? "the call did not start");
      calling = false;
      apply(state);
    } catch (error) {
      calling = false;
      config.onCallState?.(false);
      const text = error instanceof Error ? error.message : String(error);
      widget.paint("error", config.failure?.(text, lang) ?? (text.trim() ? `Could not start the call: ${text}` : "Could not start the call."));
    }
  }

  /** The toggle: off a call it picks the next call's language; in a call it
   *  asks the agent, through the holder. */
  function chooseLanguage(want: Language): void {
    storeLanguage(langKey, want);
    shareLanguage(want);
    if (state.status !== "live") {
      state = { ...state, language: want };
      return showLanguage(want);
    }
    if (want === state.language && !switchTimer) return;
    widget.setLanguagePending(want);
    tell({ k: "lang", language: want });
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = setTimeout(() => {
      switchTimer = null;
      widget.setLanguage(state.language);
    }, SWITCH_WAIT_MS);
  }

  widget.onCall(() => void call());
  widget.onReach(() => {
    if (!following) config.avatar?.preload?.();
  });
  widget.onHang(() => tell({ k: "end" }));
  widget.onMute(() => tell({ k: "mute" }));
  widget.onSettings(() => void askWorker({ op: "open_settings" }));
  widget.setLanguage(state.language);
  widget.onLanguage(chooseLanguage);

  // A choice made on another host of the site holds here.
  void sharedLanguage().then((shared) => {
    if (!shared) return;
    storeLanguage(langKey, shared);
    if (state.status === "idle" && shared !== state.language) {
      state = { ...state, language: shared };
      showLanguage(shared);
    }
  });

  /** The page as it stands, to the agent: once it can hear this page, and
   *  again each time the tab comes back to the front. */
  let reportedAt = 0;
  function report(): void {
    if (!hooks.report || !state.ready || !showing()) return;
    if (Date.now() - reportedAt < REPORT_AGAIN_MS) return;
    reportedAt = Date.now();
    hooks.report((event, payload) => kit.emit(event, payload));
  }

  const sayWhere = () => {
    tell({ k: "where", ...where() });
    if (stopAdapter) report();
  };
  document.addEventListener("visibilitychange", sayWhere);
  window.addEventListener("focus", sayWhere);

  // A load of another document has started: the holder keeps the jobs that
  // come meanwhile for the next page. Should the load not happen after all,
  // this page says hello again.
  const leaving = () => {
    tell({ k: "leaving" });
    keep();
    setTimeout(hello, 5000);
  };
  const navigation = (window as unknown as { navigation?: EventTarget }).navigation;
  navigation?.addEventListener("navigate", (e) => {
    const nav = e as Event & { destination?: { sameDocument?: boolean }; downloadRequest?: string | null };
    if (nav.destination && !nav.destination.sameDocument && !nav.downloadRequest) leaving();
  });
  window.addEventListener("pagehide", () => {
    gone = true;
    tell({ k: "leaving" });
    keep();
  });
  widget.onLayout(() => keep());

  const whenIdle = window.requestIdleCallback ?? ((fn: () => void) => setTimeout(fn, 1500));
  whenIdle(() => {
    void config.avatar?.still?.().then((found) => {
      if (!found) return;
      still = found;
      widget.setStill(found);
      keep();
    }).catch(() => {});
  });

  // No holder, no call: the kept job is made at once. With one, the holder's
  // state settles it, and the job waits no longer than this.
  void askWorker<{ up: boolean }>({ op: "has_holder" }).then((got) => {
    if (!got?.up) takeKept(MOVE_WITHOUT_CALL_MS);
  });
  setTimeout(() => takeKept(0), MOVE_AT_THE_LATEST_MS);

  if (shell) {
    const lost = () => {
      if (!heard) apply(idle(state.language));
    };
    void askWorker<{ up: boolean }>({ op: "has_holder" }).then((got) => {
      if (!got?.up) lost();
    });
    setTimeout(lost, CARRIED_WAIT_MS);
  } else {
    widget.paint("idle");
  }
  hello();
}

function storedLanguage(key: string): Language | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeLanguage(key: string, language: Language): void {
  try {
    localStorage.setItem(key, language);
  } catch {
    /* Storage blocked: the next call starts in the page's language. */
  }
}

const TARGET = "data-voqalize-target";

/** While a call is live, links to the site lose `target="_blank"`. */
function keepLinksInTab(ours: RegExp): () => void {
  const keep = (a: HTMLAnchorElement) => {
    if (a.target !== "_blank" || !ours.test(a.href)) return;
    a.setAttribute(TARGET, a.target);
    a.removeAttribute("target");
  };
  document.querySelectorAll<HTMLAnchorElement>("a[target=_blank]").forEach(keep);
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === "attributes" && r.target instanceof HTMLAnchorElement) keep(r.target);
      for (const n of r.addedNodes) {
        if (!(n instanceof Element)) continue;
        if (n instanceof HTMLAnchorElement) keep(n);
        n.querySelectorAll?.<HTMLAnchorElement>("a[target=_blank]").forEach(keep);
      }
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["target", "href"] });
  return () => {
    obs.disconnect();
    document.querySelectorAll<HTMLAnchorElement>(`a[${TARGET}]`).forEach((a) => {
      a.target = a.getAttribute(TARGET) ?? "_blank";
      a.removeAttribute(TARGET);
    });
  };
}
