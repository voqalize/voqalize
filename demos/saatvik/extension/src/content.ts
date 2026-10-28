/**
 * Sunny on Saatvik's site — the whole browser half of the call.
 *
 * Saatvik's page is theirs and we change nothing in it beyond hiding their chat
 * launcher, which Sunny replaces. This script is injected into the page's own
 * JavaScript world (the manifest's `"world": "MAIN"`) because the site adapter
 * drives Saatvik through their client-side router, which only exists there. It
 * brings:
 *
 *   - the site adapter (`saatvik-actions.js`), which turns the brain's page
 *     Actions into moves on Saatvik's page and reports every route change, form
 *     and result back, whoever caused it;
 *   - their datasheets and manuals, opened in a tab of their own beside this
 *     one (`doc.html`, through the service worker in `background.ts`); when
 *     Sunny moves the site again, this tab comes back to the front;
 *   - the corner widget (`widget.ts`), with the language toggle and the lead
 *     brief;
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Sunny says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/saatvik/backend/`.
 *
 * Saatvik's navigation is client-side and keeps the call. A full page load
 * rejoins the same session on the next page (`keepAcrossPageLoads`), so the
 * conversation carries on. One tab holds the call: a Web Lock named for the
 * agent keeps a second tab — one opened from a link, which copies this tab's
 * record of the call — from taking it over.
 */

import "./saatvik-actions.js";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, type Cue, sendAppEvent, UI_ACTION_COMMANDS, type UiAction } from "./actions.gen";
import { Narration } from "./narration";
import { BRIDGE, type WorkerAnswer, type WorkerAsk } from "./tabs-protocol";
import { type Language, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "ananya";
const AGENT = __VOQALIZE__.agentId;
/** The language the next call starts in, as the toggle last left it in this
 *  tab: a call rejoined after a page load keeps its own. */
const LANG_KEY = "voqalize.saatvik.lang";
/** How long the toggle waits for the brain to answer a switch before it
 *  gives up and shows the language the call is still in. */
const SWITCH_WAIT_MS = 10_000;
/** The Actions the widget performs itself, rather than the page adapter. */
const OURS = ["open_document", "close_document", "lead_brief", "language_changed", "cue"];
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeSunny";

let asks = 0;

/** Ask the service worker, through the isolated bridge (`bridge.ts`). */
function askWorker(ask: WorkerAsk, ms = 5000): Promise<WorkerAnswer> {
  const id = ++asks;
  return new Promise((resolve) => {
    const done = (answer: WorkerAnswer) => {
      window.removeEventListener("message", on);
      clearTimeout(timer);
      resolve(answer);
    };
    const on = (e: MessageEvent) => {
      const d = e.data as { bridge?: string; id?: number; answer?: WorkerAnswer } | null;
      if (e.source === window && d?.bridge === BRIDGE && d.id === id && d.answer) done(d.answer);
    };
    const timer = setTimeout(() => done({ ok: false, error: "the extension did not answer" }), ms);
    window.addEventListener("message", on);
    window.postMessage({ bridge: BRIDGE, id, ask }, location.origin);
  });
}

/** This tab in front before Sunny moves it: the visitor may be reading a
 *  document in the tab beside it, and the move is shown, not made unseen. */
async function inFront(): Promise<void> {
  if (!document.hidden) return;
  await askWorker({ t: "focus_me" });
  const until = Date.now() + 1500;
  while (document.hidden && Date.now() < until) await new Promise((r) => setTimeout(r, 50));
}

/** The request that mints a session — see `docs/client/handshake`. */
function connectRequest(init: Record<string, unknown>): APIRequest {
  return {
    endpoint: `${__VOQALIZE__.apiBase}/sessions.connect`,
    // `Authorization` only: pipecat sets `Content-Type` itself, and a second
    // copy arrives as a doubled header the control plane cannot read as JSON.
    headers: new Headers({ Authorization: `Bearer ${__VOQALIZE__.publishableKey}` }),
    requestData: { agent_id: __VOQALIZE__.agentId, init } as APIRequest["requestData"],
  };
}

/** `sessions.connect` answers with the transport's argument; its `headers`
 *  arrive as JSON and pipecat reads them as a `Headers`. */
function withRealHeaders(response: unknown) {
  const body = response as {
    webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> };
    session_id?: string;
  };
  return {
    ...body,
    webrtc_request_params: {
      ...body.webrtc_request_params,
      headers: new Headers(body.webrtc_request_params?.headers ?? {}),
    },
  };
}

/** Take the agent's call for this tab: the release, or `null` when another tab
 *  holds it. Without Web Locks every tab may take it. */
function takeCall(agent: string): Promise<(() => void) | null> {
  if (!navigator.locks) return Promise.resolve(() => {});
  return new Promise((resolve) => {
    void navigator.locks.request(`voqalize.call.${agent}`, { ifAvailable: true }, (lock) => {
      if (!lock) return void resolve(null);
      return new Promise<void>((release) => resolve(() => release()));
    });
  });
}

/** client-transport's record of this tab's call, which a tab opened from a
 *  link may have copied. The key is the library's own (`STORAGE_KEY` in its
 *  `transport.ts`). */
function forgetCopiedCall(): void {
  try {
    sessionStorage.removeItem("voqalize-client-transport:call");
  } catch {
    /* Nothing stored. */
  }
}

function storedLanguage(): Language {
  try {
    return sessionStorage.getItem(LANG_KEY) === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

function storeLanguage(language: Language): void {
  try {
    sessionStorage.setItem(LANG_KEY, language);
  } catch {
    /* Storage blocked: the next call starts in English. */
  }
}

async function start(): Promise<void> {
  const adapter = window.voqalizeSaatvik;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED]) return;
  flags[MOUNTED] = true;
  if (!AGENT || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is reported back as `command_failed` when it arrives, and named
  // once here so it is found before a caller finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c) && !OURS.includes(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  const widget = mountWidget();
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine into Saatvik's page.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);

  let client: PipecatClient | null = null;
  let avatar: AvatarInstance | null = null;
  /** The client the page's events go to: set once the brain can hear them. */
  let reporting: PipecatClient | null = null;
  let status: Status = "idle";
  let muted = false;
  let leaving = false;
  let release: (() => void) | null = null;
  let spare: Prepared | null = null;
  let language: Language = storedLanguage();
  let switchTimer: ReturnType<typeof setTimeout> | null = null;
  /** The language the toggle asked for, until the call is heard in it. */
  let asked: Language | null = null;

  /** One event for the brain. Off a call there is nobody to hear it; it is
   *  logged instead, which is what driving the adapter from the console
   *  shows. */
  function report(event: AppEvent): void {
    if (reporting) sendAppEvent(reporting.sendUIEvent.bind(reporting), event);
    else console.info("voqalize (no call):", event.event, event.payload);
  }

  /** The document the tab beside this one shows, if any. */
  let openDoc: { url: string; page: number } | null = null;

  // The adapter reports from page load on: a form submitted before the call
  // reached the brain is logged, not lost silently.
  adapter.start((event, payload) => report({ event, payload } as AppEvent));

  function paint(next: Status, message?: string): void {
    status = next;
    widget.paint(next, message);
  }

  function showLanguage(next: Language): void {
    language = next;
    storeLanguage(next);
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = null;
    asked = null;
    widget.setLanguage(next);
  }

  /** A cue, as the page Action it stands for. */
  function cueMove(cue: Cue): [string, unknown] {
    if (cue.path) {
      return ["navigate", { path: cue.path, heading: cue.heading, text: cue.text, tab: cue.tab, faq: cue.faq }];
    }
    if (cue.faq) return ["open_faq", { question: cue.faq }];
    if (cue.tab) return ["open_tab", { label: cue.tab }];
    return ["show_section", { heading: cue.heading, text: cue.text }];
  }

  // The screen follows her voice; see `narration.ts`. A cue that misses is
  // reported as `cue`, which the brain takes quietly: she has spoken past it.
  const narration = new Narration(async (cue) => {
    const [command, payload] = cueMove(cue);
    await inFront();
    const result = await adapter!.run(command, payload);
    if (!result.ok) report({ event: "command_failed", payload: { command: "cue", reason: result.error ?? "failed" } });
  });

  /** Follow the call's speech for the cues: its spoken text, when it starts
   *  and stops, and when the visitor talks over it. */
  function narrate(on: PipecatClient): void {
    const heard = (data: unknown) => {
      const d = data as { text?: string; spoken?: boolean; will_be_spoken?: boolean } | undefined;
      if (!d?.text || d.spoken === false || d.will_be_spoken === false) return;
      narration.hear(d.text);
    };
    on.on("botOutput" as never, heard as never);
    on.on("botTtsText" as never, heard as never);
    on.on("botStartedSpeaking" as never, (() => narration.speaking()) as never);
    on.on("botStoppedSpeaking" as never, (() => narration.stopped()) as never);
    on.on("userStartedSpeaking" as never, (() => narration.interrupted()) as never);
  }

  function watchActivity(on: PipecatClient): void {
    on.on("userStartedSpeaking" as never, (() => widget.setActivity("listening")) as never);
    on.on("botLlmStarted" as never, (() => widget.setActivity("thinking")) as never);
    on.on("botStartedSpeaking" as never, (() => {
      widget.setActivity("speaking");
      // The brain answers `language_requested` by moving both legs and
      // confirming aloud in the new language, so her next words are the switch.
      if (asked) showLanguage(asked);
    }) as never);
    on.on("botStoppedSpeaking" as never, (() => widget.setActivity("listening")) as never);
  }

  /** A client for the next call, its transport keeping the call across this
   *  tab's page loads. */
  function prepare(): Prepared {
    const transport = createVoqalizeTransport({ mediaManager: media, keepAcrossPageLoads: true });
    const next: PipecatClient = new PipecatClient({
      transport,
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state: TransportState) => {
          if (client !== next) return;
          if ((state === "connected" || state === "ready") && status !== "live") paint("live");
          if (state === "disconnected" && status === "live") end();
        },
        // The page reports once the brain can hear it, starting with where the
        // person is now. Ready can arrive more than once for one client.
        onBotReady: () => {
          if (client !== next || reporting === next) return;
          reporting = next;
          report({ event: "page_changed", payload: adapter!.context() } as AppEvent);
        },
        // The avatar draws and never plays a sound, so the bot's track is ours
        // to attach.
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio") return;
          widget.audio.srcObject = new MediaStream([track]);
          void widget.audio.play().catch(() => {});
        },
        // A microphone that never opened is a call Sunny cannot hear: end it
        // and say why, rather than leave a widget that says "live".
        onDeviceError: (error) => {
          if (client !== next || !error.devices.includes("mic")) return;
          end();
          paint("error", micFailure(error.type));
        },
        onUICommand: ({ command, payload }) => {
          void perform(command, payload).then((failed) => {
            if (failed && client === next) report(failed);
          });
        },
      },
    });
    return { client: next, transport };
  }

  async function connect(rejoin: boolean): Promise<void> {
    if (client || status === "connecting") return;
    // A page whose Permissions-Policy forbids the microphone gives a call that
    // hears nothing and looks live. Say so instead of starting one.
    if (!micAllowed()) {
      paint("error", MIC_BLOCKED);
      return;
    }
    const lock = await takeCall(AGENT);
    if (!lock || client) {
      lock?.();
      // Another tab holds the call; this one's copy of it is not ours to take.
      forgetCopiedCall();
      spare = null;
      if (!rejoin) paint("error", "Sunny is already on a call in another tab.");
      return;
    }
    release = lock;
    paint("connecting", rejoin ? "Reconnecting" : undefined);

    const { client: next } = spare ?? prepare();
    spare = null;
    client = next;
    watchActivity(next);
    narrate(next);
    try {
      avatar?.destroy();
      avatar = createAvatar({ mount: widget.face, client: next, character: CHARACTER });
      if (rejoin) {
        await next.connect();
      } else {
        const init = { surface: "saatvik-ext", page: location.pathname, lang: language };
        const started = await next.startBot(connectRequest(init));
        await next.connect(withRealHeaders(started));
      }
    } catch (error) {
      if (client !== next) return;
      client = null;
      reporting = null;
      avatar?.destroy();
      avatar = null;
      // A rejoin the server refuses is a call that ended while the page was
      // away: the page simply starts idle.
      if (rejoin) paint("idle");
      else paint("error", reason(error));
      release?.();
      release = null;
      await next.disconnect().catch(() => {});
    }
  }

  /** Perform one of the brain's Actions. Never waits on the person; a failure
   *  is returned for the brain so she never claims it worked. */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const action = asUiAction(command, payload);
    if (!action) {
      console.warn("voqalize: an Action this page does not know:", command);
      return null;
    }
    const fail = (why: string): AppEvent => ({ event: "command_failed", payload: { command, reason: why } });
    try {
      switch (action.command) {
        // The brain's word that the call's language moved, by the toggle, by
        // voice or on request: the toggle follows at once.
        case "language_changed":
          showLanguage(action.payload.language);
          return null;
        case "open_document":
          {
            const opened = await askWorker({ t: "open_doc", req: action.payload });
            if (!opened.ok) return fail(opened.error ?? "the document tab did not open");
            openDoc = { url: action.payload.url, page: action.payload.page };
            report({ event: "document_opened", payload: openDoc });
          }
          return null;
        case "close_document":
          {
            const closed = await askWorker({ t: "close_doc" });
            if (!closed.ok) return fail(closed.error ?? "no document is open");
            report({ event: "document_closed", payload: openDoc ?? { url: "", page: 1 } });
            openDoc = null;
          }
          return null;
        case "lead_brief":
          widget.setBrief(action.payload);
          return null;
        // A move to make when her voice reaches its sentence.
        case "cue":
          narration.add(action.payload);
          return null;
        default: {
          const page: UiAction = action;
          await inFront();
          const result = await adapter!.run(page.command, page.payload);
          return result.ok ? null : fail(result.error ?? "failed");
        }
      }
    } catch (error) {
      return fail(error instanceof Error ? error.message : String(error));
    }
  }

  // Driving the page from the console, with no call: each Action as the brain
  // would send it, and each event logged (see the README).
  flags.__voqalizeSaatvik = {
    perform: async (command: string, payload: unknown) => {
      const failed = await perform(command, payload);
      if (failed) report(failed);
      return failed;
    },
    narration,
  };

  function end(): void {
    reporting = null;
    const live = client;
    client = null;
    avatar?.destroy();
    avatar = null;
    widget.audio.srcObject = null;
    muted = false;
    widget.setMuted(false);
    paint("idle");
    release?.();
    release = null;
    if (switchTimer) showLanguage(language);
    if (!leaving) {
      try {
        live?.disconnectBot();
      } catch {
        // Not connected: there is no call to end on the server's side.
      }
    }
    void live?.disconnect().catch(() => {});
  }

  function toggleMute(): void {
    muted = !muted;
    widget.setMuted(muted);
    client?.enableMic(!muted);
  }

  /** The toggle. Off a call it picks the next call's language. In a call it
   *  asks the brain and moves when Sunny next speaks, which is her confirmation
   *  in the new language, or at once on the brain's `language_changed`,
   *  which also follows a switch made by voice. */
  function chooseLanguage(want: Language): void {
    if (want === language && !switchTimer) return;
    if (!reporting) return showLanguage(want);
    asked = want === language ? null : want;
    widget.setLanguagePending(want);
    report({ event: "language_requested", payload: { language: want } });
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = setTimeout(() => {
      switchTimer = null;
      asked = null;
      widget.setLanguage(language);
    }, SWITCH_WAIT_MS);
  }

  widget.setLanguage(language);
  widget.onLanguage(chooseLanguage);
  widget.onCall(() => void connect(false));
  // Her face builds once the person reaches for the invite, not at page load:
  // this runs on every page of the site, and most visitors never call.
  widget.onReach(() => {
    if (!client) preloadAvatar(CHARACTER);
  });
  widget.onHang(end);
  widget.onMute(toggleMute);

  window.addEventListener("pagehide", () => {
    leaving = true;
    void client?.disconnect();
  });

  // Her face on the button, from the avatar's own host, once the page settles.
  const idle = window.requestIdleCallback ?? ((fn: () => void) => setTimeout(fn, 1500));
  idle(() => {
    listCharacters()
      .then((all) => {
        const still = all.find((c) => c.name === CHARACTER)?.still;
        if (still) widget.setStill(still);
      })
      .catch(() => {});
  });

  paint("idle");
  spare = prepare();
  if (spare.transport.hasLiveCall) void connect(true);
}

interface Prepared {
  client: PipecatClient;
  transport: ReturnType<typeof createVoqalizeTransport>;
}

const MIC_BLOCKED =
  "This page blocks the microphone, so Sunny can't hear you. Reload the extension in chrome://extensions, then refresh this page.";

/** Whether this document's Permissions-Policy lets it open the microphone. */
function micAllowed(): boolean {
  const policy = (document as { featurePolicy?: { allowsFeature(name: string): boolean } })
    .featurePolicy;
  return policy?.allowsFeature("microphone") ?? true;
}

function micFailure(type: string): string {
  if (!micAllowed()) return MIC_BLOCKED;
  if (type === "permissions")
    return "Sunny can't hear you: microphone access was refused. Allow it for this site, then start again.";
  if (type === "in-use") return "Sunny can't hear you: another app is using the microphone.";
  if (type === "not-found") return "Sunny can't hear you: no microphone was found.";
  return "Sunny can't hear you: the microphone did not open.";
}

function reason(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.trim() ? `Could not start the call: ${text}` : "Could not start the call.";
}

// Mount on `load`, but never wait on it for long: a third-party resource on
// the site can hold `load` back for over a minute, and Sunny would not appear.
// `start` mounts once, so whichever comes first wins.
if (document.readyState === "complete") void start();
else {
  window.addEventListener("load", () => void start(), { once: true });
  setTimeout(() => void start(), 3000);
}
