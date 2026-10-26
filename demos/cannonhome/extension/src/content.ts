/**
 * Javier on Cannon Home — the page's half of the call.
 *
 * Cannon Home's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on cannonhome.cl (and www.cannonhome.cl, which
 * redirects to it), and brings:
 *
 *   - the site adapter (`cannonhome-actions.ts`), which makes the brain's page
 *     Actions on this page and reports every page the visitor lands on, the
 *     product, listing, search dropdown and bag on it, whoever put them there;
 *   - the corner widget (`widget.ts`), with the Español/English toggle;
 *   - his face: the avatar, drawn against a stand-in client fed by the holder
 *     (`follow.ts`).
 *
 * The call itself does not live here. It lives in the holder, an offscreen
 * document of the extension (`holder.ts`), which every Cannon Home page
 * follows over a port (`hub.ts`, through `bridge.ts`); so a full page load
 * here (Magento loads one for most moves) changes nothing on the call. The
 * holder sends this page the moves meant for it, and keeps them while the page
 * loads; this page answers with what it shows.
 *
 * On the call button this page does what the holder cannot: it asks the
 * visitor for the extension's microphone the first time (a frame of the
 * extension's own grant page, `grant.ts`), and mints the session with
 * `sessions.connect` (this page's fetch carries cannonhome.cl's Origin, which
 * the publishable key allows), then hands the answer to the holder.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/cannonhome/backend/`.
 *
 * The site's Content-Security-Policy would block the avatar runtime and our
 * API in the page's world; the extension removes that header on Cannon Home's
 * pages (`rules.json`).
 */

import "./cannonhome-actions";

import { type AvatarInstance, createAvatar, listCharacters, type PreloadedAvatar, preloadAvatar } from "@voqalize/avatar";

import { type AppEvent, UI_ACTION_COMMANDS } from "./actions.gen";
import { DONE_COMMANDS } from "./cannonhome-actions";
import { followCall, type Following } from "./follow";
import { askHolder, askWorker, onHolder, shareLanguage, sharedLanguage, tell } from "./hub";
import { clearKept, type Kept, transitions, writeKept } from "./persist";
import { ANY_TAB, type CallState, type MicState, OURS, type Where } from "./protocol";
import { type Language, mountWidget, type Widget } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeJavier";
/** The widget the early shell mounted at `document_start` (`shell.ts`), when
 *  the last page of this tab left a call on. */
const SHELL = "__voqalizeJavierShell";
/** How long a widget carried over from the last page waits for the holder's
 *  state before it believes the call is gone. */
const CARRIED_WAIT_MS = 8000;
/** How long the empty face slot waits for the live face to draw before it
 *  shows the face anyway. */
const UNVEIL_WAIT_MS = 10_000;
/** The language the visitor last chose on the toggle, which the next call
 *  starts in and holds to; and how long the toggle waits for the brain to
 *  answer a switch before it shows the language the call is still in. With no
 *  choice made the call opens in Spanish, as the site does. */
const LANG_KEY = "voqalize.cannonhome.lang";
const OPENING: Language = "es";
const SWITCH_WAIT_MS = 4000;
/** How long the visitor has to answer Chrome's microphone prompt. */
const GRANT_WAIT_MS = 90_000;

const IDLE: CallState = { status: "idle", muted: false, activity: null, language: OPENING, ready: false };

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
  const adapter = window.voqalizeCannonhome;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED]) return;
  flags[MOUNTED] = true;
  if (!__VOQALIZE__.agentId || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is named once here so it is found before a visitor finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c) && !OURS.has(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  // A call carried over from the last page: the shell has the widget up
  // already, as that page left it. Otherwise it mounts now, as always.
  const shell = flags[SHELL] as { widget: Widget; kept: Kept } | undefined;
  const widget = shell?.widget ?? mountWidget();
  watchCorners(widget);
  // His face starts building now; its slot stays empty until it has drawn.
  const preloaded: PreloadedAvatar | null = shell ? preloadAvatar(CHARACTER) : null;
  let still: string | null = shell?.kept.still ?? null;
  let heard = false;

  let state: CallState = { ...IDLE, language: shell?.kept.language ?? storedLanguage() ?? OPENING };
  let following: Following | null = null;
  let avatar: AvatarInstance | null = null;
  let stopAdapter: (() => void) | null = null;
  /** The visitor pressed the call button and the call is not up yet. */
  let calling = false;
  /** The toggle's wait for the brain to answer a switch. */
  let switchTimer: ReturnType<typeof setTimeout> | null = null;

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
    // One microphone on the page: GoPersonal's voice search hides while he listens.
    document.documentElement.toggleAttribute("data-voqalize-call", on);
    // In a call, the next page of this tab gets the widget back at once, and
    // the load is a view transition under it.
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
    // visitor is now, and with a move the last page left for this one.
    if (next.ready && !stopAdapter) {
      stopAdapter = adapter!.start((event, payload) => {
        if (inFront() || ANY_TAB.has(event)) tell({ k: "app", event, payload });
      });
    }
  }

  function follow(): void {
    if (following) return;
    following = followCall();
    avatar?.destroy();
    avatar = createAvatar({ mount: widget.face, client: following.client, character: CHARACTER });
    if (shell) handOver();
  }

  function unfollow(): void {
    stopAdapter?.();
    stopAdapter = null;
    following?.stop();
    following = null;
    avatar?.destroy();
    avatar = null;
    widget.unveil();
  }

  /** The call as this page shows it, for the next page of this tab. */
  function keep(): void {
    if (state.status !== "live" && state.status !== "connecting") return;
    writeKept({
      status: state.status, muted: state.muted, activity: state.activity, language: state.language, still,
      ...widget.layout(),
    });
  }

  /** The face's slot the shell left empty: the live face fades in once it
   *  has drawn. */
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
      void drawn().then((yes) => (yes ? widget.unveil() : setTimeout(look, 50)));
    };
    look();
  }

  /** Whether the avatar has drawn a frame yet. Read in an animation frame,
   *  after the avatar's own: a WebGL canvas keeps its picture only until the
   *  frame is shown. */
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
          let seen = false;
          for (let i = 3; i < px.length; i += 4) if (px[i] > 0) seen = true;
          if (!seen) return resolve(false);
          resolve(true);
        } catch {
          // A canvas that cannot be read: the wait runs out (`UNVEIL_WAIT_MS`).
          resolve(false);
        }
      }),
    );
  }

  /** Perform an Action on this page. Never waits on the visitor. Its outcome
   *  for the brain, so he never claims what did not happen: a failure, or for
   *  a move he waits on, what it left on screen; `null` for anything else, and
   *  for a move that goes on on another page, which reports from there. */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const result = await adapter!.run(command, payload);
    if (!result.ok) return { event: "command_failed", payload: { command, error: result.error ?? "failed" } };
    if (result.moved || !DONE_COMMANDS.has(command)) return null;
    return { event: "command_done", payload: { command, detail: result.detail ?? "" } };
  }

  // Driving the page from the console, with no call (see the README).
  flags.__voqalizeCannonhome = {
    perform: async (command: string, payload: unknown) => {
      const outcome = await perform(command, payload);
      if (outcome) console.info("voqalize (no call):", outcome.event, outcome.payload);
      return outcome;
    },
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
    document.documentElement.toggleAttribute("data-voqalize-call", true);
    try {
      if (!__VOQALIZE__.agentId || !__VOQALIZE__.publishableKey) throw new Error("no agent configured");
      const up = await askWorker<{ ok: boolean; error?: string }>({ op: "ensure" }, 10_000);
      if (!up?.ok) throw new Error(up?.error ?? "the extension did not answer; reload the page");
      hello();
      if ((await micReady(lang)) === "denied") {
        calling = false;
        document.documentElement.toggleAttribute("data-voqalize-call", false);
        widget.blocked();
        return;
      }
      const ctx = adapter!.context();
      // `lang` only when the visitor chose it: the brain then holds to it
      // whatever they speak, and otherwise opens in Spanish and follows the
      // language they speak.
      const chosen = (await sharedLanguage()) ?? storedLanguage();
      const session = await mintSession({
        surface: "cannonhome-ext", site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title,
        ...(chosen ? { lang: chosen } : {}),
      });
      const got = await askHolder<{ ok: boolean; error?: string }>({ op: "call", session, language: chosen ?? OPENING }, 30_000);
      if (!got?.ok) throw new Error(got?.error ?? "the call did not start");
      calling = false;
      apply(state);
    } catch (error) {
      calling = false;
      document.documentElement.toggleAttribute("data-voqalize-call", false);
      widget.paint("error", reason(error, lang));
    }
  }

  /** The toggle. Off a call it picks the next call's language. In a call it
   *  asks the brain, through the holder, and moves when Javier next speaks
   *  (his confirmation in the new language), or at once on the brain's
   *  `language_changed`. */
  function chooseLanguage(want: Language): void {
    storeLanguage(want);
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
  // His face builds once the visitor reaches for the invite, not at page load.
  widget.onReach(() => {
    if (!following) preloadAvatar(CHARACTER);
  });
  widget.onHang(() => tell({ k: "end" }));
  widget.onMute(() => tell({ k: "mute" }));
  widget.onSettings(() => void askWorker({ op: "open_settings" }));
  widget.setLanguage(state.language);
  widget.onLanguage(chooseLanguage);
  // The choice made on the other origin (with or without www.) holds here.
  void sharedLanguage().then((shared) => {
    if (!shared) return;
    storeLanguage(shared);
    if (state.status === "idle" && shared !== state.language) {
      state = { ...state, language: shared };
      showLanguage(shared);
    }
  });

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

/** What Cannon Home pins over its own pages, for the widget to keep clear
 *  of, read again every moment: the WhatsApp button (bottom-right on a
 *  desktop, a left-edge tab on a phone), the bag drawer (the right ~400 px,
 *  after every add), the filters drawer (a 380 px left panel), and on a phone
 *  the sticky add-to-cart bar along the bottom. */
const OBSTACLES: { selector: string; fixedOnly: boolean }[] = [
  { selector: "#whatsapp-link, .whatsapp-link-mobile, .new-whatsapp-mobile", fixedOnly: false },
  { selector: "aside.content-minicart-modal._show .modal-inner-wrap", fixedOnly: false },
  { selector: "#layered-filter-block.active", fixedOnly: false },
  { selector: "#sticky-addtocart-bar, .product-info-main .box-tocart", fixedOnly: true },
];

function watchCorners(widget: ReturnType<typeof mountWidget>): void {
  let last = "";
  const read = () => {
    const rects = OBSTACLES.flatMap(({ selector, fixedOnly }) =>
      [...document.querySelectorAll<HTMLElement>(selector)].filter((el) => {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") return false;
        return !fixedOnly || style.position === "fixed" || style.position === "sticky";
      }),
    )
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight)
      .map((r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom }));
    const key = JSON.stringify(rects.map((r) => [r.left, r.top, r.right, r.bottom].map(Math.round)));
    if (key === last) return;
    last = key;
    widget.avoid(rects);
  };
  read();
  setInterval(read, 1000);
  window.addEventListener("resize", read);
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
    /* Storage blocked: the next call opens in Spanish. */
  }
}


function reason(error: unknown, language: Language): string {
  const text = error instanceof Error ? error.message : String(error);
  const lead = language === "es" ? "No se pudo iniciar la llamada" : "Could not start the call";
  return text.trim() ? `${lead}: ${text}` : `${lead}.`;
}

// Mount once the page is parsed, never on `load`: Cannon Home's trackers
// hold `load` back for more than 15 s. `start` mounts once.
if (document.readyState !== "loading") void start();
else document.addEventListener("DOMContentLoaded", () => void start(), { once: true });
