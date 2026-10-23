/**
 * Javier on Explora — the whole browser half of the call.
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
 *   - the corner widget (`widget.ts`);
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/explora/backend/`.
 *
 * Every move on either host is a full page load. The call survives them:
 * `keepAcrossPageLoads` saves it in the page's `sessionStorage`, and Voqalize
 * holds the session for ten seconds while the next page dials it again. So:
 *
 *   - this script mounts at `document_idle`, without waiting for `load`
 *     (WordPress's trackers hold `load` back for seconds);
 *   - a page load Javier makes waits for his voice (`after_words`, below), so
 *     the visitor hears the sentence before the page goes;
 *   - `sessionStorage` is per origin, and the two hosts are two origins, so the
 *     holder also stashes the saved call with the hub, per browser tab, and a
 *     page on the other host takes it back before it looks for one;
 *   - a move for the next page (a heading on it, the booking step after a
 *     load) is kept by the hub and made once the call is back on that page;
 *   - the site follows the call's language (`site-language.ts`): when it moves,
 *     the page in front loads its twin in the new language once he has said
 *     so, and while the call is in Spanish an English `navigate` loads the
 *     page's Spanish twin.
 *
 * One site and one agent have one call, in every Explora tab of both hosts
 * (`tabs.ts` over the extension's hub, `hub.ts`). The tab it started in holds
 * it; every other Explora tab follows it: his face, the mute and the call's
 * state. The brain's Actions arrive at the holder, which performs each on the
 * tab in front — one tab, which loads between hosts, is the normal case.
 */

import "./explora-actions";
import "./reservations-actions";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import {
  type AppEvent,
  asUiAction,
  type CheckAvailability,
  type Cue,
  type FillEnquiry,
  type Navigate,
  sendAppEvent,
  UI_ACTION_COMMANDS,
  type UiAction,
} from "./actions.gen";
import {
  focusTab, HubChannel, loadsStarted, loadThen, pendingMove, stashCall, stashLanguage, type Then, tabId, takeCall,
  unstashCall,
} from "./hub";
import { Narration } from "./narration";
import { type Lang, type Mapped, onSite, pageLanguage, pathLang, siteUrlIn } from "./site-language";
import {
  followCall, type Following, forgetCopiedCall, gestureContext, here, holdCall, type Holding,
  inFront, type Relay, type TabInfo,
} from "./tabs";
import { type Activity, type Language, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
const AGENT = __VOQALIZE__.agentId;
const SITE = "https://www.explora.com";
const BOOKING = "https://reservations.explora.com";
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeExploraJavier";
/** The language the visitor last chose on the toggle on this host, which the
 *  next call starts in and holds to; and how long the toggle waits for the
 *  brain to answer a switch before it shows the language the call is still in. */
const LANG_KEY = "voqalize.explora.lang";
const SWITCH_WAIT_MS = 4000;
/** The call's language, kept for this tab's next page from the moment the
 *  call starts: here per origin, and with the hub for a move across hosts.
 *  Never the page's own language, which a Spanish call's English page is not
 *  (prod call be1f5b9a: one English page, and every page after it was
 *  English). */
const CALL_LANG_KEY = "voqalize.explora.callLang";
/** How long the page waits for him to finish confirming a language switch
 *  aloud before it loads the page in the new language. */
// Short on purpose: on dev call 1f6cd8ce the site followed the call to
// Spanish 11.7 s late, after the visitor had asked again. A line cut by the
// load is not lost: Voqalize holds the call's audio and plays the rest on the
// next page.
const SITE_SWITCH_CAP_MS = 3000;
/** client-transport's record of this tab's call (`STORAGE_KEY` in its
 *  `transport.ts`), which the hub carries across the two hosts. */
const CALL_KEY = "voqalize-client-transport:call";

/** How long a follower waits for the holder to come back after it left for
 *  another page, and after a close the Navigation API did not see as one. */
const BACK_FROM_LOAD_MS = 12_000;
const BACK_FROM_CLOSE_MS = 1_500;

/** Pacing a page load against his voice (see `paced`). */
const WORDS_PER_S = 2.8;
const START_WAIT_MS = 4000;
const AFTER_WORDS_SLACK_MS = 6000;
const QUIET_WAIT_MS = 3000;
const QUIET_HOLD_MS = 300;
/** A move kept for this page waits for the call to come back on it this long,
 *  then is made anyway; with no call to wait for, this long after mounting. */
const MOVE_AFTER_REJOIN_MS = 10_000;
const MOVE_WITHOUT_CALL_MS = 800;
/** How long a `navigate` waits for its page's twin in the call's language
 *  before it loads the English page as named (the brain then asks for the
 *  twin from that page, whose own `<head>` names it). */
const TWIN_WAIT_MS = 2000;
/** A `navigate` that started a load and is still on this page this long
 *  after is reported as failed, so the brain never talks about a page that
 *  is not there. */
const UNLOAD_WAIT_MS = 8000;

/** The Actions that load a page of the other host when the tab in front is
 *  not on it: the booking steps from www.explora.com, a page from the
 *  booking site. */
const BOOKING_COMMANDS = new Set(["check_availability", "choose_room", "fill_enquiry", "send_enquiry"]);
/** The Actions www.explora.com's adapter performs (`explora-actions.ts`). */
const SITE_COMMANDS = ["navigate", "show_section", "open_faq"];
/** The Actions the holder performs itself rather than a page. */
const OURS = new Set(["cue", "focus_tab", "language_changed"]);

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

const onBooking = (url: string) => /^https:\/\/reservations\.explora\.com(\/|$)/i.test(url);
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function readCall(): string | null {
  try {
    return sessionStorage.getItem(CALL_KEY);
  } catch {
    return null;
  }
}

/** The page of the booking site a booking step starts on, so the step lands
 *  where the booking adapter would load it itself: one load, not two. */
function bookingUrl(command: string, payload: unknown, language: Language): string | null {
  const lang = language === "es" ? "ES" : "EN";
  if (command === "check_availability") {
    const p = payload as CheckAvailability;
    const q = new URLSearchParams({ hotel_code: p.hotel_code });
    if (p.date) q.set("check_in_date", p.date);
    q.set("language", lang);
    return `${BOOKING}/ibe/paso1?${q}`;
  }
  if (command === "fill_enquiry") {
    const p = payload as FillEnquiry;
    return `${BOOKING}/ibe/expeditions?expedition_request=${encodeURIComponent(p.expedition_code.toUpperCase())}&language=${lang}`;
  }
  return null;
}

async function start(): Promise<void> {
  const adapter = window.voqalizeExplora;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED] || !document.body) return;
  flags[MOUNTED] = true;
  if (!AGENT || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is named once here so it is found before a visitor finds it.
  // Each host's adapter performs its own; the other host's are a load away.
  const handled = new Set([...adapter.commands, ...OURS, ...SITE_COMMANDS, ...BOOKING_COMMANDS]);
  const missing = UI_ACTION_COMMANDS.filter((c) => !handled.has(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  const widget = mountWidget();
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine into Explora's page.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);

  // Every Explora tab, on both hosts, on one channel; see `tabs.ts`.
  const chan = new HubChannel();
  const me = await tabId();

  /** This tab's part in the call. */
  let role: "idle" | "holder" | "follower" = "idle";
  let client: PipecatClient | null = null;
  let holding: Holding | null = null;
  let following: Following | null = null;
  let avatar: AvatarInstance | null = null;
  let stopAdapter: (() => void) | null = null;
  /** The client the adapter is reporting to. */
  let reporting: PipecatClient | null = null;
  let status: Status = "idle";
  let activity: Activity | null = null;
  let muted = false;
  let leaving = false;
  /** The call's claim, while this tab holds the call. */
  let release: (() => void) | null = null;
  let spare: Prepared | null = null;
  let navigating = false;
  /** Held by the holder: every open Explora tab, and the one in front. */
  const tabs = new Map<string, TabInfo>();
  let active = me;
  let waiting: ReturnType<typeof setTimeout> | null = null;
  /** The call's language, or the next call's; the one the toggle asked for
   *  until the brain answers; and the wait for that answer. */
  let language: Language = storedLanguage() ?? pageLanguage() ?? "en";
  let asked: Language | null = null;
  let switchTimer: ReturnType<typeof setTimeout> | null = null;
  /** Whether his voice is playing now, and how many times it has started:
   *  what a page load waits on. */
  let botSpeaking = false;
  let botStarts = 0;
  /** Counts the page moves the brain sends, so a language switch still
   *  waiting for his voice gives way to a `navigate` that came after it. */
  let moves = 0;
  /** Settles once the call is up on this page and reporting to the brain,
   *  or will not be: what a move kept for this page waits on. */
  let rejoined: () => void = () => {};
  const up = new Promise<void>((resolve) => (rejoined = resolve));

  const post = (r: Relay) => chan.postMessage(r);

  function paint(next: Status, message?: string): void {
    status = next;
    if (next !== "live") activity = null;
    widget.paint(next, message);
    announce();
  }

  function setActivity(next: Activity): void {
    activity = next;
    widget.setActivity(next);
    announce();
  }

  function setMuted(next: boolean): void {
    muted = next;
    widget.setMuted(next);
    announce();
  }

  function showLanguage(next: Language): void {
    language = next;
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = null;
    asked = null;
    widget.setLanguage(next);
    announce();
  }

  /** The holder's state, for the followers: on every change. */
  function announce(): void {
    if (role === "holder") post({ k: "holder", from: me, status, muted, activity, language });
  }

  function watchActivity(on: PipecatClient): void {
    on.on("userStartedSpeaking" as never, (() => setActivity("listening")) as never);
    on.on("botLlmStarted" as never, (() => setActivity("thinking")) as never);
    on.on("botStartedSpeaking" as never, (() => {
      setActivity("speaking");
      // The brain answers `language_requested` by moving both legs and
      // confirming aloud in the new language, so his next words are the switch.
      if (asked && role === "holder") showLanguage(asked);
    }) as never);
    on.on("botStoppedSpeaking" as never, (() => setActivity("listening")) as never);
  }

  // ─── The holder ──────────────────────────────────────────────────────

  /** A page event for the brain; only the tab in front's reach it, except a
   *  move's failure, which is the brain's whichever tab made it. */
  function toBrain(from: string, event: AppEvent): void {
    if (role !== "holder" || !reporting) return;
    const anyTab = ["command_failed", "language_requested", "enquiry_sent"];
    if (from !== active && !anyTab.includes(event.event)) return;
    sendAppEvent(reporting.sendUIEvent.bind(reporting), event);
  }

  function sendTabs(): void {
    if (role !== "holder" || !reporting) return;
    tabs.set(me, here(me));
    if (!tabs.has(active)) active = me;
    sendAppEvent(reporting.sendUIEvent.bind(reporting), {
      event: "tabs_changed",
      payload: { tabs: [...tabs.values()], active },
    });
  }

  function setActive(id: string): void {
    if (id === active) return;
    active = id;
    sendTabs();
  }

  function reportPage(): void {
    const event = { event: "page_changed", payload: adapter!.context() } as AppEvent;
    if (role === "holder") toBrain(me, event);
    else if (role === "follower") post({ k: "app", from: me, event: event.event, payload: event.payload });
  }

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
        // The page reports once the brain can hear it, starting with where
        // the visitor is now: on Explora that is also the brain's sign that
        // the page it opened is up. Ready can arrive more than once.
        onBotReady: () => {
          if (client !== next || reporting === next) return;
          reporting = next;
          stopAdapter?.();
          stopAdapter = adapter!.start((event, payload) => {
            if (event === "page_changed") tabs.set(me, here(me));
            toBrain(me, { event, payload } as AppEvent);
          });
          // Every other tab says where it is, which fills the brain's list.
          post({ k: "holder", from: me, status, muted, activity, language });
          sendTabs();
          rejoined();
        },
        // The avatar draws and never plays a sound, so the bot's track is ours.
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio") return;
          widget.audio.srcObject = new MediaStream([track]);
          void widget.audio.play().catch(() => {});
        },
        // A microphone that never opened is a call Javier cannot hear: end it
        // and say why, rather than leave a widget that says "live".
        onDeviceError: (error) => {
          if (client !== next || !error.devices.includes("mic")) return;
          end();
          paint("error", micFailure(error.type));
        },
        onUICommand: ({ command, payload }) => void route(next, command, payload),
      },
    });
    return { client: next, transport };
  }

  async function connect(rejoin: boolean, made?: AudioContext): Promise<void> {
    if (role !== "idle" || status === "connecting") return void made?.close();
    if (!micAllowed()) {
      void made?.close();
      paint("error", MIC_BLOCKED);
      return;
    }
    const lock = await takeCall();
    if (!lock || role !== "idle") {
      lock?.();
      void made?.close();
      // A tab opened from the holder's link carries a copy of its call; the
      // holder answers the hello and this tab follows.
      forgetCopiedCall();
      spare = null;
      rejoined();
      if (role === "idle") post({ k: "hello", from: me });
      return;
    }
    release = lock;
    role = "holder";
    active = me;
    tabs.clear();
    paint("connecting", rejoin ? "Reconnecting" : undefined);
    if (rejoin) post({ k: "coming", from: me });

    const { client: next } = spare ?? prepare();
    spare = null;
    client = next;
    watchActivity(next);
    narrate(next);
    holding = holdCall(next, chan, () => active === me);
    void holding.pulse(made);

    try {
      avatar?.destroy();
      avatar = createAvatar({ mount: widget.face, client: holding.avatarClient, character: CHARACTER });
      if (rejoin) {
        await next.connect();
      } else {
        const ctx = adapter!.context();
        // `lang` only when the visitor chose it: the brain then holds to it
        // whatever they speak, and otherwise follows the language they speak.
        const chosen = storedLanguage();
        // `site_lang`: the language the site is followed in, from the start:
        // the visitor's choice, else the language of the page they are on
        // (a call started on /es/… is a Spanish visitor's).
        const callLang: Language = chosen ?? pageLanguage() ?? "en";
        const init = {
          surface: "explora-ext", site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title,
          site_lang: callLang,
          ...(chosen ? { lang: chosen } : {}),
        };
        // The call's language, for every page of it from now on.
        setCallLanguage(callLang);
        const started = await next.startBot(connectRequest(init));
        await next.connect(withRealHeaders(started));
      }
      // The saved call, for a load to the other host in this tab.
      if (client === next) void stashCall(readCall());
    } catch (error) {
      if (client !== next) return;
      client = null;
      holding?.stop();
      holding = null;
      avatar?.destroy();
      avatar = null;
      if (rejoin) paint("idle");
      else paint("error", reason(error));
      role = "idle";
      release?.();
      release = null;
      // A call that could not be rejoined is over: no page should try it again.
      void stashCall(null);
      rejoined();
      await next.disconnect().catch(() => {});
    }
  }

  // ─── Where each Action goes ───────────────────────────────────────────

  /** Perform an Action on tab `to`: this one, or another through the hub.
   *  The reason it failed, or `null`. Another tab reports its own failure
   *  through the hub, so its move resolves once it has had time to land. */
  async function performOn(to: string, command: string, payload: unknown): Promise<string | null> {
    if (to === me) {
      const failed = await perform(command, payload);
      return failed ? String((failed.payload as { reason?: string }).reason ?? "failed") : null;
    }
    post({ k: "perform", to, command, payload });
    await sleep(1200);
    return null;
  }

  /** Every page Action goes to the tab in front. The reason it failed, or `null`. */
  function dispatch(command: string, payload: unknown): Promise<string | null> {
    return performOn(tabs.has(active) ? active : me, command, payload);
  }

  /** The URL of the tab in front, as the holder knows it. */
  const frontUrl = () => tabs.get(active)?.url ?? location.href;

  /** A cue, as the page Action it stands for. Page cues are never cues on
   *  Explora: the brain paces them itself, as `navigate`. */
  function cueMove(cue: Cue): [string, unknown] {
    if (cue.faq) return ["open_faq", { question: cue.faq }];
    return ["show_section", { heading: cue.heading, text: cue.text }];
  }

  // The screen follows his voice; see `narration.ts`. A cue that misses is
  // reported as `cue`, which the brain takes quietly: he has spoken past it.
  const narration = new Narration(async (cue) => {
    const [command, payload] = cueMove(cue);
    const why = await dispatch(command, payload);
    if (why) toBrain(me, { event: "command_failed", payload: { command: "cue", reason: why } });
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
    on.on("botStartedSpeaking" as never, (() => {
      botSpeaking = true;
      botStarts++;
      narration.speaking();
    }) as never);
    on.on("botStoppedSpeaking" as never, (() => {
      botSpeaking = false;
      narration.stopped();
    }) as never);
    on.on("userStartedSpeaking" as never, (() => narration.interrupted()) as never);
  }

  async function until(test: () => boolean, ms: number): Promise<boolean> {
    const end = Date.now() + Math.max(0, ms);
    while (!test()) {
      if (Date.now() >= end) return false;
      await sleep(50);
    }
    return true;
  }

  /**
   * Hold a page load until his voice has said what came before it. The brain
   * sends `navigate` once it has *yielded* the `after_words` words before a
   * page cue, but those may not have started playing yet: wait for the voice
   * to start (up to four seconds), then to stop, held quiet for a moment so a
   * pause between two sentences is not the end, all within the time those
   * words take to say and some slack. With no words to wait for, only until
   * the voice is quiet. A load cuts the audio off, so late beats early.
   */
  async function paced(afterWords: number): Promise<void> {
    const cap = afterWords > 0 ? (afterWords / WORDS_PER_S) * 1000 + AFTER_WORDS_SLACK_MS : QUIET_WAIT_MS;
    await settle(cap, afterWords > 0);
  }

  /** Wait for his voice to start (when `waitStart`, up to four seconds) and
   *  then to stop and stay quiet, all within `cap`. Nothing to wait for off
   *  a call. */
  async function settle(cap: number, waitStart: boolean): Promise<void> {
    if (role !== "holder" || !client) return;
    const t0 = Date.now();
    const left = () => cap - (Date.now() - t0);
    if (waitStart) {
      const starts = botStarts;
      await until(() => botSpeaking || botStarts > starts, Math.min(START_WAIT_MS, left()));
    }
    while (left() > 0) {
      if (!(await until(() => !botSpeaking, left()))) break;
      await sleep(QUIET_HOLD_MS);
      if (!botSpeaking) break;
    }
  }

  async function route(on: PipecatClient, command: string, payload: unknown): Promise<void> {
    const action = asUiAction(command, payload);
    if (!action) {
      console.warn("voqalize: an Action this page does not know:", command);
      return;
    }
    if (action.command === "cue") {
      narration.add(action.payload);
      return;
    }
    if (action.command === "navigate") {
      moves++;
      // The page's twin in the call's language is looked up while his voice
      // plays, so the load does not wait on it after.
      if (language !== "en") void siteUrlIn(language, (action.payload as Navigate).path);
      await paced((action.payload as Navigate).after_words ?? 0);
    } else if (
      BOOKING_COMMANDS.has(action.command) &&
      !onBooking(frontUrl()) &&
      bookingUrl(action.command, action.payload, language)
    ) {
      // A booking step from www.explora.com loads the booking site: let him
      // finish the sentence he is on first. One that needs a page already
      // open there (`choose_room`, `send_enquiry`) fails at once instead.
      await paced(0);
    }
    const loads = loadsStarted();
    const why = OURS.has(action.command) ? await ours(action) : await dispatch(action.command, action.payload);
    if (why && client === on) toBrain(me, { event: "command_failed", payload: { command, reason: why } });
    // A load started here that never took the page away (prod call be1f5b9a:
    // a page from the booking site that never came) is the brain's to know.
    if (!why && action.command === "navigate" && loadsStarted() > loads) {
      setTimeout(() => {
        if (leaving || client !== on) return;
        toBrain(me, { event: "command_failed", payload: { command, reason: "the page did not load; the screen has not moved" } });
      }, UNLOAD_WAIT_MS);
    }
  }

  /** The Actions the call performs itself. A failure comes back as words. */
  async function ours(action: UiAction): Promise<string | null> {
    switch (action.command) {
      case "focus_tab":
        return (await focusTab(action.payload.tab_id)) ? null : `no tab ${action.payload.tab_id} to bring forward`;
      // The brain's word that the call's language moved, by the toggle, by
      // voice or on request: the toggle follows at once, on every tab. At the
      // call's start it is only recorded (`stay`); for a page that came up in
      // the other language, only that page's own twin is loaded (`twin`).
      case "language_changed": {
        const { language: next, site = "follow" } = action.payload;
        setCallLanguage(next);
        if (site !== "stay") void followSite(next, site === "twin");
        return null;
      }
      default:
        return `the call cannot ${action.command}`;
    }
  }

  /** The call's language moved: the toggle, every tab's, and this tab's next
   *  page remember it. */
  function setCallLanguage(next: Language): void {
    showLanguage(next);
    try {
      sessionStorage.setItem(CALL_LANG_KEY, next);
    } catch {
      /* Storage blocked: the hub still has it. */
    }
    void stashLanguage(next);
  }

  /**
   * The site follows the call's language: once he has confirmed the switch
   * aloud (he is speaking it as `language_changed` arrives; a load would cut
   * him off), the page in front loads its twin in that language. A `navigate`
   * that arrives meanwhile wins: it lands in the new language anyway.
   */
  async function followSite(next: Lang, twin = false): Promise<void> {
    const seq = moves;
    // A twin is asked for while he is quiet, waiting for it: no confirmation
    // to wait for, only the end of what he is saying.
    await settle(SITE_SWITCH_CAP_MS, !twin);
    if (moves !== seq || language !== next) return;
    const why = await dispatch("site_language", { language: next, ...(twin ? { twin } : {}) });
    if (!why) return;
    console.info("voqalize: the page stays in its language:", why);
    // The brain waits for the twin it asked for: tell it there is none.
    if (twin) toBrain(me, { event: "command_failed", payload: { command: "language_changed", reason: why } });
  }

  /** A `navigate`'s path in the call's language: the brain names the English
   *  page, and in Spanish the page's Spanish twin is loaded. */
  async function inCallLanguage(p: Navigate): Promise<Navigate> {
    if (typeof p.path !== "string" || !p.path || pathLang(p.path) === language) return p;
    const lang = language;
    const t0 = performance.now();
    // Never held up past a moment: on prod call be1f5b9a a page from the
    // booking site waited on the lookup and never loaded. Late, the English
    // page loads, and the twin is asked for from it.
    const late = sleep(TWIN_WAIT_MS).then((): Mapped => ({
      url: new URL(p.path, SITE).href, source: "fallback", ms: Math.round(performance.now() - t0), error: "timeout",
    }));
    const mapped = await Promise.race([siteUrlIn(lang, p.path), late]);
    // How it was found goes to the brain, so a wrong-language page is traced.
    toBrain(me, {
      event: "twin_lookup",
      payload: {
        path: p.path, language: lang, url: mapped.url, ms: mapped.ms, error: mapped.error ?? "",
        source: mapped.error === "timeout" && mapped.source === "fallback" ? "timeout" : mapped.source,
      },
    });
    return mapped.url === p.path ? p : { ...p, path: mapped.url };
  }

  /**
   * Perform an Action on this tab's page. A move that belongs on the other
   * host loads it, with the move kept for the page it lands on: a booking step
   * from www.explora.com, a www.explora.com page from the booking site. Never
   * waits on the visitor; a failure is returned for the brain so he never
   * claims it worked.
   */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const fail = (reason: string): AppEvent => ({ event: "command_failed", payload: { command, reason } });
    if (!adapter!.commands.includes(command)) {
      const there = BOOKING_COMMANDS.has(command) && !onBooking(location.href) ? bookingUrl(command, payload, language) : null;
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
    // Cues as the brain sends them, and speech as the voice plays it.
    narration,
    // The brain's `language_changed`, as if it had arrived (no voice to wait
    // for off a call), and the call's language as the page now has it.
    setLanguage: (next: Language) => ours({ command: "language_changed", payload: { language: next, site: "follow" } }),
    language: () => language,
    // A `navigate` path in the call's language, and what finding it cost.
    mapPath: (path: string) => siteUrlIn(language, path),
  };

  function end(): void {
    if (role === "follower") return post({ k: "end" });
    stopAdapter?.();
    stopAdapter = null;
    reporting = null;
    const live = client;
    client = null;
    holding?.stop();
    holding = null;
    avatar?.destroy();
    avatar = null;
    widget.audio.srcObject = null;
    setMuted(false);
    paint("idle");
    role = "idle";
    tabs.clear();
    release?.();
    release = null;
    botSpeaking = false;
    if (switchTimer) showLanguage(language);
    if (!leaving) {
      try {
        sessionStorage.removeItem(CALL_LANG_KEY);
      } catch {
        /* Storage blocked. */
      }
      // Ended, not left for the next page: no page of either host rejoins it.
      void stashCall(null);
      try {
        live?.disconnectBot();
      } catch {
        // Not connected: there is no call to end on the server's side.
      }
    }
    void live?.disconnect().catch(() => {});
  }

  function toggleMute(): void {
    if (role === "follower") return post({ k: "mute" });
    setMuted(!muted);
    client?.enableMic(!muted);
  }

  /** The toggle. Off a call it picks the next call's language. In a call it
   *  asks the brain, from whichever tab it was pressed on, and moves when
   *  Javier next speaks, which is his confirmation in the new language, or at
   *  once on the brain's `language_changed`, which also follows a switch made
   *  by voice. */
  function chooseLanguage(want: Language): void {
    storeLanguage(want);
    if (want === language && !switchTimer) return;
    if (role === "idle") return showLanguage(want);
    asked = want === language ? null : want;
    widget.setLanguagePending(want);
    const payload = { language: want };
    if (role === "holder") toBrain(me, { event: "language_requested", payload });
    else post({ k: "app", from: me, event: "language_requested", payload });
    if (switchTimer) clearTimeout(switchTimer);
    switchTimer = setTimeout(() => {
      switchTimer = null;
      asked = null;
      widget.setLanguage(language);
    }, SWITCH_WAIT_MS);
  }

  // ─── A follower ──────────────────────────────────────────────────────

  function follow(from: { status: Status; muted: boolean; activity: Activity | null; language?: Language }): void {
    role = "follower";
    following = followCall(chan, me);
    watchActivity(following.client);
    avatar?.destroy();
    avatar = createAvatar({ mount: widget.face, client: following.client, character: CHARACTER });
    stopAdapter?.();
    stopAdapter = adapter!.start((event, payload) => {
      if (event === "page_changed") post({ k: "tab", tab: here(me), front: inFront() });
      if (inFront() || event === "enquiry_sent") post({ k: "app", from: me, event, payload });
    });
    track(from);
    sayWhere();
  }

  function track(from: { status: Status; muted: boolean; activity: Activity | null; language?: Language }): void {
    if (from.status === "idle" || from.status === "error") return unfollow();
    if (waiting) clearTimeout(waiting);
    waiting = null;
    const wasLive = status === "live";
    widget.paint(from.status, from.status === "connecting" ? "Reconnecting" : undefined);
    status = from.status;
    widget.setMuted(from.muted);
    muted = from.muted;
    if (from.activity) widget.setActivity(from.activity);
    if (from.language && (from.language !== language || switchTimer)) showLanguage(from.language);
    if (from.status === "live" && !wasLive) following?.joined();
  }

  function unfollow(): void {
    if (role !== "follower") return;
    if (waiting) clearTimeout(waiting);
    waiting = null;
    stopAdapter?.();
    stopAdapter = null;
    following?.stop();
    following = null;
    avatar?.destroy();
    avatar = null;
    role = "idle";
    muted = false;
    widget.setMuted(false);
    status = "idle";
    widget.paint("idle");
  }

  function sayWhere(): void {
    if (role === "holder") {
      tabs.set(me, here(me));
      if (inFront()) {
        const changed = active !== me;
        setActive(me);
        if (changed) reportPage();
      }
      return;
    }
    if (role !== "follower") return;
    post({ k: "tab", tab: here(me), front: inFront() });
    if (inFront()) reportPage();
  }

  chan.onmessage = (e: MessageEvent) => {
    const r = e.data as Relay;
    switch (r.k) {
      case "hello":
        announce();
        if (role === "follower" && status === "connecting") post({ k: "away", from: me });
        return;
      case "away":
        if (role !== "idle") return;
        follow({ status: "connecting", muted: false, activity: null });
        waiting = setTimeout(unfollow, BACK_FROM_LOAD_MS);
        return;
      case "holder":
        if (role === "idle" && (r.status === "live" || r.status === "connecting")) follow(r);
        else if (role === "follower") {
          track(r);
          if (r.status === "live") post({ k: "tab", tab: here(me), front: inFront() });
        }
        return;
      case "bye":
        if (role !== "follower") return;
        following?.dropped();
        widget.paint("connecting", "Reconnecting");
        status = "connecting";
        if (waiting) clearTimeout(waiting);
        waiting = setTimeout(unfollow, r.navigating ? BACK_FROM_LOAD_MS : BACK_FROM_CLOSE_MS);
        return;
      case "coming":
        if (role !== "follower") return;
        if (waiting) clearTimeout(waiting);
        waiting = setTimeout(unfollow, BACK_FROM_LOAD_MS);
        return;
      case "perform":
        if (role !== "follower" || r.to !== me) return;
        void perform(r.command, r.payload).then((failed) => {
          if (failed) post({ k: "app", from: me, event: failed.event, payload: failed.payload });
        });
        return;
      case "tab":
        if (role !== "holder") return;
        tabs.set(r.tab.tab_id, r.tab);
        if (r.front) setActive(r.tab.tab_id);
        else sendTabs();
        return;
      case "gone":
        if (role !== "holder") return;
        tabs.delete(r.from);
        if (active === r.from) active = me;
        sendTabs();
        return;
      case "app":
        toBrain(r.from, { event: r.event, payload: r.payload } as AppEvent);
        return;
      case "report":
        if (role === "holder" && r.from === active) client?.sendClientMessage("avatar", r.data as never);
        return;
      case "mute":
        if (role === "holder") toggleMute();
        return;
      case "end":
        if (role === "holder") end();
        return;
    }
  };

  widget.onCall(() => void connect(false, gestureContext()));
  // His face builds once the visitor reaches for the invite, not at page load.
  widget.onReach(() => {
    if (!client) preloadAvatar(CHARACTER);
  });
  widget.onHang(end);
  widget.onMute(toggleMute);
  widget.setLanguage(language);
  widget.onLanguage(chooseLanguage);

  document.addEventListener("visibilitychange", sayWhere);
  window.addEventListener("focus", sayWhere);

  const navigation = (window as unknown as { navigation?: EventTarget }).navigation;
  navigation?.addEventListener("navigate", (e) => {
    const dest = (e as Event & { destination?: { sameDocument?: boolean } }).destination;
    if (dest && !dest.sameDocument) navigating = true;
  });

  window.addEventListener("pagehide", () => {
    leaving = true;
    if (role === "holder") {
      // Best effort: the stash made at connect already holds the same call.
      void stashCall(readCall());
      post({ k: "bye", from: me, navigating });
      role = "idle";
    } else if (role === "follower") post({ k: "gone", from: me });
    void client?.disconnect();
  });

  // His face on the button, from the avatar's own host, once the page settles.
  const idle = window.requestIdleCallback ?? ((fn: () => void) => setTimeout(fn, 1500));
  idle(() => {
    listCharacters()
      .then((all) => {
        const still = all.find((c) => c.name === CHARACTER)?.still;
        if (still) widget.setStill(still);
      })
      .catch(() => {});
  });

  // The move kept for this page (`loadThen`): asked for now, so the hub
  // forgets it, and made once the call is back on this page.
  const kept = pendingMove();

  // A call this tab held on the other host: its saved record is put where the
  // transport looks for it, before `prepare` asks whether there is one.
  const { call: stashed, lang: stashedLang } = await unstashCall();
  if (stashed && stashed !== readCall()) {
    try {
      sessionStorage.setItem(CALL_KEY, stashed);
    } catch {
      /* Storage blocked: no rejoin across hosts. */
    }
  }

  paint("idle");
  spare = prepare();
  const rejoining = spare.transport.hasLiveCall;
  if (rejoining) {
    // The call's language, as this tab knows it (the hub's crosses hosts),
    // never this page's: an English page in a Spanish call stays a Spanish call.
    const was = asLanguage(stashedLang) ?? callLanguage();
    if (was && was !== language) showLanguage(was);
    void connect(true);
  } else post({ k: "hello", from: me });

  void kept.then(async (then) => {
    if (!then) return;
    // The brain waits for this page's `page_changed` before it says more, so
    // the move is made after the page has been reported.
    if (rejoining) {
      await Promise.race([up, sleep(MOVE_AFTER_REJOIN_MS)]);
      await sleep(300);
    } else {
      await sleep(MOVE_WITHOUT_CALL_MS);
    }
    const failed = await perform(then.command, then.payload);
    if (!failed) return;
    if (role === "holder") toBrain(me, failed);
    else post({ k: "app", from: me, event: failed.event, payload: failed.payload });
  });
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

function asLanguage(v: string | null | undefined): Language | null {
  return v === "es" || v === "en" ? v : null;
}

/** The call's language as this tab's last page on this host knew it. */
function callLanguage(): Language | null {
  try {
    const v = sessionStorage.getItem(CALL_LANG_KEY);
    return v === "es" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

function storeLanguage(language: Language): void {
  try {
    localStorage.setItem(LANG_KEY, language);
  } catch {
    /* Storage blocked: the next call starts in English. */
  }
}

interface Prepared {
  client: PipecatClient;
  transport: ReturnType<typeof createVoqalizeTransport>;
}

const MIC_BLOCKED =
  "This page blocks the microphone, so Javier can't hear you. Start the call from a www.explora.com tab.";

/** Whether this document's Permissions-Policy lets it open the microphone. */
function micAllowed(): boolean {
  const policy = (document as { featurePolicy?: { allowsFeature(name: string): boolean } }).featurePolicy;
  return policy?.allowsFeature("microphone") ?? true;
}

function micFailure(type: string): string {
  if (!micAllowed()) return MIC_BLOCKED;
  if (type === "permissions")
    return "Javier can't hear you: microphone access was refused. Allow it for this site, then start again.";
  if (type === "in-use") return "Javier can't hear you: another app is using the microphone.";
  if (type === "not-found") return "Javier can't hear you: no microphone was found.";
  return "Javier can't hear you: the microphone did not open.";
}

function reason(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.trim() ? `Could not start the call: ${text}` : "Could not start the call.";
}

// Mount at once, at `document_idle`: never on `load`, which WordPress's
// trackers hold back for seconds, while Voqalize holds a call through a page
// load for ten. `start` mounts once.
if (document.body) void start();
else document.addEventListener("DOMContentLoaded", () => void start(), { once: true });
