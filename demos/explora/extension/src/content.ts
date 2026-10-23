/**
 * Javier on Explora — the page's half of the call.
 *
 * Explora's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on www.explora.com and on reservations.explora.com, and
 * brings:
 *
 *   - the site adapters: `explora-actions.ts` on www.explora.com (pages,
 *     sections, tabs, accordions) and `reservations-actions.ts` on the booking
 *     engine (a lodge's availability, an expedition's enquiry). Whichever host
 *     this page is on registers `window.voqalizeExplora`;
 *   - the corner widget (`widget.ts`), with the English/Español toggle;
 *   - his face: the avatar, drawn against a stand-in client fed by the holder
 *     (`follow.ts`).
 *
 * The call itself does not live here. It lives in the holder, an offscreen
 * document of the extension (`holder.ts`), which every Explora page on both
 * hosts follows over a port (`hub.ts`, through `bridge.ts`); so a full page
 * load here, and a load from one host to the other (every move on Explora is
 * one), changes nothing on the call. The holder sends this page the moves
 * meant for it, and keeps them while the page loads; this page answers with
 * what it shows.
 *
 * A move that belongs on the other host (a booking step from www.explora.com,
 * a www.explora.com page from the booking site) loads it from here, with the
 * rest of the move kept by the service worker for the page it lands on
 * (`loadThen`); that page makes it once the call is up on it.
 *
 * On the call button this page does what the holder cannot: it asks the
 * visitor for the extension's microphone the first time (a frame of the
 * extension's own grant page, `grant.ts`), and mints the session with
 * `sessions.connect` (this page's fetch carries an Explora Origin, which the
 * publishable key allows), then hands the answer to the holder.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/explora/backend/`.
 */

import "./explora-actions";
import "./reservations-actions";

import { type AvatarInstance, createAvatar, listCharacters, type PreloadedAvatar, preloadAvatar } from "@voqalize/avatar";

import { type AppEvent, type Navigate, UI_ACTION_COMMANDS } from "./actions.gen";
import { followCall, type Following } from "./follow";
import { askHolder, askWorker, loadThen, onHolder, pendingMove, type Then, tell } from "./hub";
import { clearKept, type Kept, transitions, writeFace, writeKept } from "./persist";
import {
  ANY_TAB, BOOKING_COMMANDS, bookingUrl, type CallState, type MicState, onBooking, OURS, SITE, SITE_COMMANDS,
  type Where,
} from "./protocol";
import { onSite, pageLanguage, pathLang, siteUrlIn } from "./site-language";
import { type Language, mountWidget, type Widget } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeExploraJavier";
/** The widget the early shell mounted at `document_start` (`shell.ts`), when
 *  the last page of this tab, on this host, left a call on. */
const SHELL = "__voqalizeExploraJavierShell";
/** How long a widget carried over from the last page waits for the holder's
 *  state before it believes the call is gone. */
const CARRIED_WAIT_MS = 8000;
/** How often, in a call, the last frame of his face is kept for the next page. */
const FRAME_EVERY_MS = 3000;
/** How long the still waits for the live face before it gives way anyway. */
const UNVEIL_WAIT_MS = 10_000;
/** The language the visitor last chose on the toggle on this host, which the
 *  next call starts in and holds to; and how long the toggle waits for the
 *  brain to answer a switch before it shows the language the call is still in. */
const LANG_KEY = "voqalize.explora.lang";
const SWITCH_WAIT_MS = 4000;
/** How long the visitor has to answer Chrome's microphone prompt. */
const GRANT_WAIT_MS = 90_000;
/** A move kept for this page is made this long after the call is up on it
 *  (the brain waits for this page's `page_changed`, which goes first); with
 *  no call, this long after the page knows there is none; and, whatever
 *  happens, no later than the last. */
const MOVE_AFTER_READY_MS = 300;
const MOVE_WITHOUT_CALL_MS = 800;
const MOVE_AT_THE_LATEST_MS = 10_000;

const IDLE: CallState = { status: "idle", muted: false, activity: null, language: "en", ready: false };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Mint the session from this page: see `docs/client/handshake`. */
async function mintSession(init: Record<string, unknown>): Promise<unknown> {
  const res = await fetch(`${__VOQALIZE__.apiBase}/sessions.connect`, {
    method: "POST",
    headers: { Authorization: `Bearer ${__VOQALIZE__.publishableKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: __VOQALIZE__.agentId, init }),
  });
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!res.ok) {
    const error = body?.error as { message?: string } | string | undefined;
    const detail = typeof error === "string" ? error : (error?.message ?? (body?.detail as string | undefined));
    throw new Error(detail ? String(detail) : `HTTP ${res.status}`);
  }
  return body;
}

function inFront(): boolean {
  return document.visibilityState === "visible" && document.hasFocus();
}

function where(): Where {
  return { url: location.href, title: document.title, front: inFront() };
}

async function start(): Promise<void> {
  const adapter = window.voqalizeExplora;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED]) return;
  flags[MOUNTED] = true;
  if (!__VOQALIZE__.agentId || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is named once here so it is found before a visitor finds it.
  // Each host's adapter performs its own; the other host's are a load away.
  const handled = new Set([...adapter.commands, ...OURS, ...SITE_COMMANDS]);
  const missing = UI_ACTION_COMMANDS.filter((c) => !handled.has(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  // The move the last page of this tab left for this one (`loadThen`): asked
  // for now, so the worker forgets it, and made once the call is up here.
  const keptMove = pendingMove();

  // A call carried over from the last page: the shell has the widget up
  // already, as that page left it. Otherwise it mounts now, as always.
  const shell = flags[SHELL] as { widget: Widget; kept: Kept } | undefined;
  const widget = shell?.widget ?? mountWidget();
  // His face starts building now, to take over from the still.
  const preloaded: PreloadedAvatar | null = shell ? preloadAvatar(CHARACTER) : null;
  let still: string | null = shell?.kept.still ?? null;
  let heard = false;
  let frames: ReturnType<typeof setInterval> | null = null;

  let state: CallState = { ...IDLE, language: shell?.kept.language ?? storedLanguage() ?? pageLanguage() ?? "en" };
  let following: Following | null = null;
  let avatar: AvatarInstance | null = null;
  let stopAdapter: (() => void) | null = null;
  /** The visitor pressed the call button and the call is not up yet. */
  let calling = false;
  /** The toggle's wait for the brain to answer a switch. */
  let switchTimer: ReturnType<typeof setTimeout> | null = null;
  /** Whether the kept move has been taken up. */
  let keptTaken = false;

  const hello = () => tell({ k: "hello", ...where() });

  function showLanguage(next: Language): void {
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = null;
    widget.setLanguage(next);
  }

  /** The holder's state, as this page shows it. */
  function apply(next: CallState): void {
    const was = state;
    state = next;
    const on = next.status === "live" || next.status === "connecting";
    // The press on this page is still on its way to the holder.
    if (calling && !on) return;
    // In a call, the next page of this tab on this host gets the widget back
    // at once, and the load is a view transition under it.
    transitions(on);
    if (!on) clearKept();
    if (on) follow();
    else unfollow();
    widget.paint(next.status, next.message);
    widget.setMuted(next.muted);
    if (next.activity) widget.setActivity(next.activity);
    if (next.language !== was.language || !switchTimer) showLanguage(next.language);
    if (next.status === "live" && was.status !== "live") following?.joined();
    keep();
    // The page reports once the brain can hear it, starting with where the
    // visitor is now (on Explora that is also the brain's sign that the page
    // it opened is up), and then makes the move the last page left for it.
    if (next.ready && !stopAdapter) {
      stopAdapter = adapter!.start((event, payload) => {
        if (inFront() || ANY_TAB.has(event)) tell({ k: "app", event, payload });
      });
      takeKept(MOVE_AFTER_READY_MS);
    }
    if (!on && heard) takeKept(MOVE_WITHOUT_CALL_MS);
  }

  function follow(): void {
    if (following) return;
    following = followCall();
    avatar?.destroy();
    avatar = createAvatar({ mount: widget.face, client: following.client, character: CHARACTER });
    if (shell) handOver();
    frames ??= setInterval(keepFrame, FRAME_EVERY_MS);
  }

  function unfollow(): void {
    stopAdapter?.();
    stopAdapter = null;
    following?.stop();
    following = null;
    avatar?.destroy();
    avatar = null;
    if (frames) clearInterval(frames);
    frames = null;
    widget.setPoster(null);
  }

  /** The call as this page shows it, for the next page of this tab. */
  function keep(): void {
    if (state.status !== "live" && state.status !== "connecting") return;
    writeKept({
      status: state.status, muted: state.muted, activity: state.activity, language: state.language, still,
      ...widget.layout(),
    });
  }

  /** The still the shell put up gives way once the live face has drawn. */
  function handOver(): void {
    const since = Date.now();
    let built = !preloaded;
    void preloaded?.ready.catch(() => {}).then(() => {
      built = true;
    });
    const look = () => {
      if (!avatar) return;
      if (Date.now() - since > UNVEIL_WAIT_MS) return widget.unveil();
      if (!built) return void setTimeout(look, 50);
      const img = widget.face.querySelector("img");
      if (img?.complete && img.naturalWidth) return widget.unveil();
      void lastFrame().then((frame) => (frame ? widget.unveil() : setTimeout(look, 50)));
    };
    look();
  }

  /** Keep the last frame of his face for the next page's still. */
  function keepFrame(): void {
    if (!following) return;
    void lastFrame("image/webp").then((frame) => {
      if (frame && following) writeFace(frame);
    });
  }

  /** The frame the avatar has just drawn, as a data URL (with `type`; else
   *  `"drawn"`), or `null` while it has drawn nothing. Read in an animation
   *  frame, after the avatar's own: a WebGL canvas keeps its picture only
   *  until the frame is shown. */
  function lastFrame(type?: string): Promise<string | null> {
    return new Promise((resolve) =>
      requestAnimationFrame(() => {
        const canvas = widget.face.querySelector("canvas");
        if (!canvas?.width || !canvas.height) return resolve(null);
        try {
          const probe = document.createElement("canvas");
          probe.width = probe.height = 8;
          const g = probe.getContext("2d", { willReadFrequently: true });
          if (!g) return resolve(null);
          g.drawImage(canvas, 0, 0, 8, 8);
          const px = g.getImageData(0, 0, 8, 8).data;
          let seen = false;
          for (let i = 3; i < px.length; i += 4) if (px[i] > 0) seen = true;
          if (!seen) return resolve(null);
          resolve(type ? canvas.toDataURL(type, 0.85) : "drawn");
        } catch {
          // A canvas that cannot be read: the character's still stands in.
          resolve(null);
        }
      }),
    );
  }

  /** Make the move the last page left for this one, once: `delay` from now. A
   *  failure goes to the brain in a call, as any move's would. */
  function takeKept(delay: number): void {
    if (keptTaken) return;
    keptTaken = true;
    void keptMove.then(async (then) => {
      if (!then) return;
      await sleep(delay);
      const failed = await perform(then.command, then.payload);
      if (!failed) return;
      if (state.ready) tell({ k: "app", event: failed.event, payload: failed.payload });
      else console.info("voqalize (no call):", failed.event, failed.payload);
    });
  }

  /** A `navigate`'s path in the call's language: the brain names the English
   *  page, and in Spanish the page's Spanish twin is loaded. */
  async function inCallLanguage(p: Navigate): Promise<Navigate> {
    if (typeof p.path !== "string" || !p.path || pathLang(p.path) === state.language) return p;
    const mapped = await siteUrlIn(state.language, p.path);
    return mapped.url === p.path ? p : { ...p, path: mapped.url };
  }

  /**
   * Perform an Action on this page. A move that belongs on the other host
   * loads it, with the move kept for the page it lands on: a booking step
   * from www.explora.com, a www.explora.com page from the booking site. Never
   * waits on the visitor; a failure is returned for the brain so he never
   * claims it worked. `null` for anything else, and for a move that goes on
   * on another page, which reports from there.
   */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const fail = (reason: string): AppEvent => ({ event: "command_failed", payload: { command, reason } });
    if (!adapter!.commands.includes(command)) {
      const there = BOOKING_COMMANDS.has(command) && !onBooking(location.href) ? bookingUrl(command, payload, state.language) : null;
      if (there) {
        await loadThen(there, { command, payload });
        return null;
      }
      if (command === "send_enquiry" && !onBooking(location.href)) return fail("no expedition enquiry form is open");
      if (command === "choose_room" && !onBooking(location.href)) {
        return fail("the rooms are not open: check a lodge's availability through to its rooms first");
      }
      if (command === "navigate" && onBooking(location.href)) {
        const p = await inCallLanguage(payload as Navigate);
        // On a translated page the English names may not be there: skipped.
        const lenient = pathLang(p.path) !== "en";
        const then: Then | undefined = p.faq
          ? { command: "open_faq", payload: { question: p.faq, ...(lenient ? { lenient } : {}) } }
          : p.heading || p.text
            ? { command: "show_section", payload: { heading: p.heading, text: p.text, ...(lenient ? { lenient } : {}) } }
            : undefined;
        try {
          await loadThen(new URL(p.path, SITE).href, then);
        } catch (error) {
          return fail(`not a page: ${p.path} (${String(error)})`);
        }
        return null;
      }
    }
    if (command === "navigate" && onSite()) payload = await inCallLanguage(payload as Navigate);
    const result = await adapter!.run(command, payload);
    if (result.ok) return null;
    return fail(result.error ?? "failed");
  }

  // Driving the page from the console, with no call (see the README).
  flags.__voqalizeExplora = {
    perform: async (command: string, payload: unknown) => {
      const failed = await perform(command, payload);
      if (failed) console.info("voqalize (no call):", failed.event, failed.payload);
      return failed;
    },
    // As if the call's language had moved: the page loads its twin in it.
    setLanguage: async (next: Language) => {
      state = { ...state, language: next };
      showLanguage(next);
      const failed = await perform("site_language", { language: next });
      if (failed) console.info("voqalize (no call):", failed.event, failed.payload);
      return failed;
    },
    language: () => state.language,
    // A `navigate` path in the call's language, and what finding it cost.
    mapPath: (path: string) => siteUrlIn(state.language, path),
  };

  onHolder((msg) => {
    switch (msg.k) {
      case "holder-up":
        return hello();
      case "holder-down":
        return apply({ ...IDLE, language: state.language });
      case "state":
        heard = true;
        return apply(msg);
      case "perform":
        void perform(msg.command, msg.payload).then((outcome) =>
          tell({ k: "done", id: msg.id, outcome: outcome as { event: string; payload: Record<string, unknown> } | null }),
        );
        return;
    }
  });

  // ─── The call button ───────────────────────────────────────────────────

  /** The extension's microphone, asked for the first time if need be: in a
   *  frame of the extension's own page, then, should that grant not hold, in
   *  a tab of its own. */
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
      widget.grant(`${page}?lang=${lang}`);
      await answered;
      widget.grant(null);
      mic = await read();
      if (mic === "granted") return "ok";
      if (mic === "denied") return "denied";
    }
    // The grant made in the frame did not reach the extension (or was for
    // that once): the same page in a tab of its own, closed once answered.
    await askWorker({ op: "grant_tab", lang }, 130_000);
    mic = await read();
    return mic === "denied" ? "denied" : "ok";
  }

  async function call(): Promise<void> {
    if (calling || state.status === "live" || state.status === "connecting") return;
    calling = true;
    const lang = state.language;
    widget.paint("connecting");
    try {
      if (!__VOQALIZE__.agentId || !__VOQALIZE__.publishableKey) throw new Error("no agent configured");
      const up = await askWorker<{ ok: boolean; error?: string }>({ op: "ensure" }, 10_000);
      if (!up?.ok) throw new Error(up?.error ?? "the extension did not answer; reload the page");
      hello();
      if ((await micReady(lang)) === "denied") {
        calling = false;
        widget.blocked();
        return;
      }
      const ctx = adapter!.context();
      // `lang` only when the visitor chose it: the brain then holds to it
      // whatever they speak, and otherwise follows the language they speak.
      const chosen = storedLanguage();
      // `site_lang`: the language the site is followed in, from the start:
      // the visitor's choice, else the language of the page they are on (a
      // call started on /es/… is a Spanish visitor's).
      const session = await mintSession({
        surface: "explora-ext", site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title,
        site_lang: chosen ?? pageLanguage() ?? "en",
        ...(chosen ? { lang: chosen } : {}),
      });
      const got = await askHolder<{ ok: boolean; error?: string }>({ op: "call", session, language: lang }, 30_000);
      if (!got?.ok) throw new Error(got?.error ?? "the call did not start");
      calling = false;
      apply(state);
    } catch (error) {
      calling = false;
      widget.paint("error", reason(error));
    }
  }

  /** The toggle. Off a call it picks the next call's language. In a call it
   *  asks the brain, through the holder, and moves when Javier next speaks
   *  (his confirmation in the new language), or at once on the brain's
   *  `language_changed`, which also follows a switch made by voice. */
  function chooseLanguage(want: Language): void {
    storeLanguage(want);
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
  // His face builds once the visitor reaches for the invite, not at page load.
  widget.onReach(() => {
    if (!following) preloadAvatar(CHARACTER);
  });
  widget.onHang(() => tell({ k: "end" }));
  widget.onMute(() => tell({ k: "mute" }));
  widget.onSettings(() => void askWorker({ op: "open_settings" }));
  widget.setLanguage(state.language);
  widget.onLanguage(chooseLanguage);

  /** Where this tab is, and the page in front for the brain. */
  const sayWhere = () => {
    tell({ k: "where", ...where() });
    if (state.ready && inFront()) tell({ k: "app", event: "page_changed", payload: adapter!.context() });
  };
  document.addEventListener("visibilitychange", sayWhere);
  window.addEventListener("focus", sayWhere);

  // A load of another document has started: the holder keeps the moves that
  // come meanwhile for the next page. Should the load not happen after all (a
  // download, a 204), this page says hello again.
  const leaving = () => {
    tell({ k: "leaving" });
    keep();
    keepFrame();
    setTimeout(hello, 5000);
  };
  const navigation = (window as unknown as { navigation?: EventTarget }).navigation;
  navigation?.addEventListener("navigate", (e) => {
    const nav = e as Event & { destination?: { sameDocument?: boolean }; downloadRequest?: string | null };
    if (nav.destination && !nav.destination.sameDocument && !nav.downloadRequest) leaving();
  });
  window.addEventListener("pagehide", () => {
    tell({ k: "leaving" });
    keep();
  });
  widget.onLayout(() => keep());

  // His face on the button, from the avatar's own host, once the page settles.
  const idle = window.requestIdleCallback ?? ((fn: () => void) => setTimeout(fn, 1500));
  idle(() => {
    listCharacters()
      .then((all) => {
        const found = all.find((c) => c.name === CHARACTER)?.still;
        if (!found) return;
        still = found;
        widget.setStill(found);
        keep();
      })
      .catch(() => {});
  });

  // No holder, no call: the kept move is made at once. With one, the holder's
  // state settles it (`apply`), and the move waits no longer than this.
  void askWorker<{ up: boolean }>({ op: "has_holder" }).then((got) => {
    if (!got?.up) takeKept(MOVE_WITHOUT_CALL_MS);
  });
  setTimeout(() => takeKept(0), MOVE_AT_THE_LATEST_MS);

  if (shell) {
    // The widget the shell carried over says a call is on. The holder's state
    // settles it; with no holder, or no word from it, the call is gone.
    const gone = () => {
      if (!heard) apply({ ...IDLE, language: state.language });
    };
    void askWorker<{ up: boolean }>({ op: "has_holder" }).then((got) => {
      if (!got?.up) gone();
    });
    setTimeout(gone, CARRIED_WAIT_MS);
  } else {
    widget.paint("idle");
  }
  // A call already on: the holder answers with its state, and with any move
  // it kept for this tab while this page loaded.
  hello();
}

/** The language the visitor chose on the toggle, or `null` if they never have. */
function storedLanguage(): Language | null {
  try {
    const v = localStorage.getItem(LANG_KEY);
    return v === "es" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

function storeLanguage(language: Language): void {
  try {
    localStorage.setItem(LANG_KEY, language);
  } catch {
    /* Storage blocked: the next call starts in the page's language. */
  }
}

function reason(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.trim() ? `Could not start the call: ${text}` : "Could not start the call.";
}

// Mount once the page is parsed, never on `load`, which WordPress's trackers
// hold back for seconds. `start` mounts once.
if (document.readyState !== "loading") void start();
else document.addEventListener("DOMContentLoaded", () => void start(), { once: true });
