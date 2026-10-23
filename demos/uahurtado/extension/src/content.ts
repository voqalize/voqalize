/**
 * Javier on the Universidad Alberto Hurtado's sites — the whole browser half
 * of the call.
 *
 * The university's pages are theirs and we change nothing in them. This script
 * is injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`) on admision.uahurtado.cl, postgrados.uahurtado.cl and
 * www.uahurtado.cl, and brings:
 *
 *   - the site adapter (`uah-actions.ts`), which turns the brain's page Actions
 *     into moves on the page in front, reads what the brain cannot (fees,
 *     weights, application windows), and reports every page the visitor lands
 *     on, whoever took them there;
 *   - the corner widget (`widget.ts`), with the Español/English toggle;
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/uahurtado/backend/`.
 *
 * Every move between the university's pages is a full page load, and a move
 * from admision to postgrados or www is a load to another origin. The call
 * survives both:
 *
 *   - `keepAcrossPageLoads` saves the call in the page's `sessionStorage`, and
 *     Voqalize holds the session for ten seconds while the next page dials it
 *     again; this script mounts at `document_idle` and dials at once, never
 *     waiting for `load` (the trackers hold it back for seconds);
 *   - `sessionStorage` is per origin, so the holder also keeps the saved call
 *     with the hub, per browser tab, and a page on another host puts it back
 *     before it asks whether there is one; the call's language goes the same
 *     way, so the toggle never falls back to Español mid English call;
 *   - a move for the next page (the tab to open on the career he loads, the
 *     fees to read there) and the cues his voice has not reached yet are kept
 *     by the hub and made once the call is back on that page;
 *   - while a call is live, a link to another page of the three sites that
 *     would open a new tab loads in this one instead, so the visitor stays in
 *     the call's tab; the microphone is allowed on all three hosts once a call
 *     is live (the hub), so Chrome does not ask again at the border.
 *
 * One site and one agent have one call, in every UAH tab (`tabs.ts` over the
 * extension's hub, `hub.ts`). The tab it started in holds it; every other tab
 * follows it: his face, the mute and the call's state. The brain's Actions
 * arrive at the holder, which performs each on the tab in front, one at a time.
 */

import "./uah-actions";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, type Cue, sendAppEvent, UI_ACTION_COMMANDS, type UiAction } from "./actions.gen";
import {
  focusTab, HubChannel, keep, openTab, peek, pendingMove, shareLanguage, sharedLanguage, stash, type Then, tabId,
  take, takeCall,
} from "./hub";
import { Narration, type Rest } from "./narration";
import {
  followCall, type Following, forgetCopiedCall, gestureContext, here, holdCall, type Holding,
  inFront, type Relay, type TabInfo,
} from "./tabs";
import { elsewhere, type RunResult, takeLocalPending } from "./uah-actions";
import { type Activity, type Language, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
const AGENT = __VOQALIZE__.agentId;
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeUahJavier";
/** The language the visitor last chose on the toggle, which the next call
 *  starts in and holds to; and how long the toggle waits for the brain to
 *  answer a switch before it shows the language the call is still in. With no
 *  choice made the call opens in Spanish, as the site does. */
const LANG_KEY = "voqalize.uahurtado.lang";
const OPENING: Language = "es";
const SWITCH_WAIT_MS = 4000;

/** How long a follower waits for the holder to come back after it left for
 *  another page, and after a close the Navigation API did not see as one. */
const BACK_FROM_LOAD_MS = 12_000;
const BACK_FROM_CLOSE_MS = 1_500;

/** The cues the holder's last page had not reached when it unloaded, for the
 *  next page of the same tab on this host; the hub carries them to another. */
const NARRATION_KEY = "voqalize.uahurtado.narration";
const NARRATION_MAX_AGE_MS = 30_000;
/** client-transport's record of this tab's call (`STORAGE_KEY` in its
 *  `transport.ts`), which the hub carries across the three hosts. */
const CALL_KEY = "voqalize-client-transport:call";

/** A move kept for this page waits for the call to come back on it this long,
 *  then is made anyway; with no call to wait for, this long after mounting. */
const MOVE_AFTER_REJOIN_MS = 10_000;
const MOVE_WITHOUT_CALL_MS = 800;
/** How long after Javier filled the lead form a cue to another page is dropped
 *  rather than pulling the visitor off the form. */
const FORM_HOLD_MS = 10_000;

/** The Actions the holder performs itself rather than a page. */
const OURS = new Set(["focus_tab", "cue", "language_changed", "open_link"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's outcome, a read's answer, the toggle, the form, the audiomalla. */
const ANY_TAB = new Set([
  "command_failed", "command_done", "language_requested", "admission_read", "program_read",
  "lead_form_state", "lead_submitted", "audiomalla_ended",
]);
/** The moves whose success is reported as `command_done`, which the brain
 *  waits on before it says they happened. */
const DONE_COMMANDS = new Set(["open_career_menu", "play_audiomalla", "fill_lead_form", "show_signup"]);
/** A follower's word to the holder: hold its microphone for an audiomalla. */
const HOLD_MIC = "__hold_mic";

/** The three sites, whose pages this extension runs on and whose links stay
 *  in the call's tab. */
const SITE_LINK = /^https:\/\/((admision|postgrados|www)\.)?uahurtado\.cl(\/|$)/i;

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

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function readCall(): string | null {
  try {
    return sessionStorage.getItem(CALL_KEY);
  } catch {
    return null;
  }
}

/** One move at a time: a move waits for the one before it, so a page arrives
 *  before the section on it is looked for and two moves never race (clini, dev
 *  call 2fd742d5). */
let running: Promise<unknown> = Promise.resolve();
function oneAtATime<A extends unknown[], R>(move: (...args: A) => Promise<R>): (...args: A) => Promise<R> {
  return (...args: A) => {
    const turn = running.then(() => move(...args));
    running = turn.catch(() => undefined);
    return turn;
  };
}

async function start(): Promise<void> {
  const adapter = window.voqalizeUah;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED] || !document.body) return;
  flags[MOUNTED] = true;
  if (!AGENT || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is named once here so it is found before a visitor finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c) && !OURS.has(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  const widget = mountWidget();
  watchCorners(widget, () => adapter.obstacles());
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine into the university's page.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);

  // Every UAH tab on one channel; see `tabs.ts`.
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
  /** The audiomalla is playing: the microphone is held muted, whatever `muted`. */
  let micHeld = false;
  let leaving = false;
  /** The call's claim, while this tab holds the call. */
  let release: (() => void) | null = null;
  let spare: Prepared | null = null;
  let navigating = false;
  /** Held by the holder: every open UAH tab, and the one in front. */
  const tabs = new Map<string, TabInfo>();
  let active = me;
  let waiting: ReturnType<typeof setTimeout> | null = null;
  /** The call's language, or the next call's; the one the toggle asked for
   *  until the brain answers; and the wait for that answer. */
  let language: Language = storedLanguage() ?? OPENING;
  let asked: Language | null = null;
  let switchTimer: ReturnType<typeof setTimeout> | null = null;
  /** When Javier last filled the lead form. */
  let formMovedAt = 0;
  /** Resolves once the call is up on this page and the page has been reported. */
  let markUp: () => void = () => {};
  const up = new Promise<void>((r) => (markUp = r));

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
    // The call's language, for this tab's next page on any host.
    if (role === "holder") void keep("call-lang", next);
    announce();
  }

  /** The holder's state, for the followers: on every change. */
  function announce(): void {
    if (role === "holder") post({ k: "holder", from: me, status, muted, activity, language });
  }

  function watchActivity(on: PipecatClient): void {
    on.on("userStartedSpeaking" as never, (() => setActivity("listening")) as never);
    on.on("botLlmStarted" as never, (() => setActivity("thinking")) as never);
    const talking = () => {
      if (activity !== "speaking") setActivity("speaking");
      // The brain answers `language_requested` by moving both legs and
      // confirming aloud in the new language, so his next words are the switch.
      if (asked && role === "holder") showLanguage(asked);
    };
    on.on("botStartedSpeaking" as never, talking as never);
    // After a rejoin mid-reply there is no fresh "started speaking": his words
    // arriving say he is talking (santanderarena, dev).
    on.on("botOutput" as never, (() => activity !== "speaking" && status === "live" && setActivity("speaking")) as never);
    on.on("botTtsText" as never, (() => activity !== "speaking" && status === "live" && setActivity("speaking")) as never);
    on.on("botStoppedSpeaking" as never, (() => setActivity("listening")) as never);
  }

  /** The microphone as it should be: the visitor's mute, or held for the audiomalla. */
  function applyMic(): void {
    if (role === "holder") client?.enableMic(!muted && !micHeld);
  }

  // ─── The holder ──────────────────────────────────────────────────────

  /** A page event for the brain; only the tab in front's reach it, except the
   *  ones that are the brain's whichever tab made them. */
  function toBrain(from: string, event: AppEvent): void {
    if (role !== "holder" || !reporting) return;
    if (from !== active && !ANY_TAB.has(event.event)) return;
    sendAppEvent(reporting.sendUIEvent.bind(reporting), event);
  }

  /** An outcome from this tab, to the brain: directly as the holder, through
   *  the holder as a follower. */
  function report(event: AppEvent): void {
    if (role === "holder") toBrain(me, event);
    else if (role === "follower") post({ k: "app", from: me, event: event.event, payload: event.payload });
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
    report({ event: "page_changed", payload: adapter!.context() });
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
        // the visitor is now. Ready can arrive more than once for one client.
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
          applyMic();
          markUp();
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
          paint("error", micFailure(error.type, language));
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
      paint("error", MIC_BLOCKED[language]);
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
      if (role === "idle") post({ k: "hello", from: me });
      return;
    }
    release = lock;
    role = "holder";
    active = me;
    tabs.clear();
    paint("connecting", rejoin ? RECONNECTING[language] : undefined);
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
        // `lang` only when the visitor chose it: the brain then holds to it
        // whatever they speak, and otherwise opens in Spanish and follows the
        // language they speak.
        const chosen = (await sharedLanguage()) ?? storedLanguage();
        const init = {
          surface: "uahurtado-ext",
          url: location.href.split("#")[0],
          path: location.pathname,
          title: document.title,
          ...(chosen ? { lang: chosen } : {}),
        };
        const started = await next.startBot(connectRequest(init));
        await next.connect(withRealHeaders(started));
      }
      // The saved call, for a load to another UAH host in this tab.
      if (client === next) {
        void keep("call", readCall());
        void keep("call-lang", language);
      }
    } catch (error) {
      if (client !== next) return;
      client = null;
      holding?.stop();
      holding = null;
      avatar?.destroy();
      avatar = null;
      if (rejoin) paint("idle");
      else paint("error", reason(error, language));
      role = "idle";
      release?.();
      release = null;
      // A call that could not be rejoined is over: no page should try it again.
      void keep("call", null);
      await next.disconnect().catch(() => {});
    }
  }

  // ─── Where each Action goes ───────────────────────────────────────────

  /** The tab moves are made on: the one in front, if the holder knows it. */
  const front = () => (tabs.has(active) ? active : me);

  /** Perform an Action on tab `to`: this one, or another through the hub.
   *  The reason it failed, or `null`. Another tab reports its own outcome
   *  through the hub, so its move resolves once it has had time to land. */
  async function performOn(to: string, command: string, payload: unknown): Promise<string | null> {
    if (to === me) {
      const outcome = await perform(command, payload);
      if (outcome?.event === "command_failed") return String(outcome.payload.reason ?? "failed");
      if (outcome) toBrain(me, outcome);
      return null;
    }
    post({ k: "perform", to, command, payload });
    await sleep(1200);
    return null;
  }

  /** A cue, as the page Action it stands for. */
  function cueMove(cue: Cue): [string, unknown] {
    if (cue.url) return ["navigate", { url: cue.url, heading: cue.heading, text: cue.text, faq: cue.faq, via_cue: true }];
    if (cue.faq) return ["open_faq", { question: cue.faq }];
    return ["show_section", { heading: cue.heading, text: cue.text }];
  }

  // The screen follows his voice; see `narration.ts`. A cue that misses is
  // reported as `cue`, which the brain takes quietly: he has spoken past it.
  // A cue that opens another page in this tab ends it mid-sentence: the cues
  // after it go to the hub first, for the next page, on whichever host.
  const narration = new Narration(async (cue) => {
    const [command, payload] = cueMove(cue);
    if (command === "navigate" && cue.url && elsewhere(cue.url) && Date.now() - formMovedAt < FORM_HOLD_MS) {
      console.info("voqalize: kept the lead form in front; dropped the cue to", cue.url);
      toBrain(me, {
        event: "command_failed",
        payload: { command: "cue", reason: `not moved to ${cue.url}: the visitor is on the lead form Javier just filled` },
      });
      return;
    }
    const to = front();
    if (command === "navigate" && to === me && cue.url && elsewhere(cue.url)) {
      const rest = narration.drain();
      if (rest.ready.length || rest.waiting.length) await stash("cues", { ...rest, at: Date.now() });
    }
    const why = await performOn(to, command, payload);
    if (why) toBrain(me, { event: "command_failed", payload: { command: "cue", reason: why } });
  }, elsewhere);

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
    if (action.command === "fill_lead_form") formMovedAt = Date.now();
    const why = OURS.has(action.command) ? await ours(action) : await performOn(front(), action.command, action.payload);
    if (why && client === on) toBrain(me, { event: "command_failed", payload: { command, reason: why } });
  }

  /** The Actions the call performs itself. A failure comes back as words. */
  async function ours(action: UiAction): Promise<string | null> {
    switch (action.command) {
      case "focus_tab":
        return (await focusTab(action.payload.tab_id)) ? null : `no tab ${action.payload.tab_id} to bring forward`;
      // The PAES simulator, a malla PDF: a tab of their own (the hub opens
      // only uahurtado.cl addresses), or the one already showing it. Nothing
      // runs there: on simula a form is a lead.
      case "open_link": {
        const { url } = action.payload;
        if (!url) return "no address to open";
        for (const [id, t] of tabs) if (t.url === url) return (await focusTab(id)) ? null : "that tab could not be brought forward";
        return openTab(url);
      }
      // The brain's word that the call's language moved, by the toggle, by
      // voice or on request: the toggle follows at once, on every tab.
      case "language_changed":
        showLanguage(action.payload.language);
        return null;
      default:
        return `the call cannot ${action.command}`;
    }
  }

  /** Perform an Action on this tab's page, one at a time. Never waits on the
   *  visitor. Its outcome for the brain, so he never claims what did not
   *  happen: a failure; a read's answer; for a move he waits on, what it left
   *  on screen; `null` for anything else, and for a move that goes on on
   *  another page, which reports from there. */
  const perform = oneAtATime(async (command: string, payload: unknown): Promise<AppEvent | null> => {
    const result: RunResult = await adapter!.run(command, payload);
    if (!result.ok) return { event: "command_failed", payload: { command, reason: result.error ?? "failed" } };
    if (result.moved) return null;
    if (result.event) return result.event;
    if (!DONE_COMMANDS.has(command)) return null;
    return { event: "command_done", payload: { command, detail: result.detail ?? "" } };
  });

  // The audiomalla holds the microphone muted while it plays (the call would
  // take the director's recording for the visitor). A follower asks the holder.
  adapter.configure({
    holdMic: (on) => {
      if (role === "follower") return post({ k: "app", from: me, event: HOLD_MIC, payload: { on } });
      micHeld = on;
      applyMic();
    },
  });

  // Driving the page from the console, with no call (see the README).
  flags.__voqalizeUah = {
    perform: async (command: string, payload: unknown) => {
      const outcome = await perform(command, payload);
      if (outcome) console.info("voqalize (no call):", outcome.event, outcome.payload);
      return outcome;
    },
    // Cues as the brain sends them, and speech as the voice plays it.
    narration,
    context: () => adapter.context(),
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
    micHeld = false;
    paint("idle");
    role = "idle";
    tabs.clear();
    release?.();
    release = null;
    if (switchTimer) showLanguage(language);
    if (!leaving) {
      // Ended, not left for the next page: no page of any host rejoins it.
      void keep("call", null);
      void keep("call-lang", null);
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
    applyMic();
  }

  /** The toggle. Off a call it picks the next call's language. In a call it
   *  asks the brain, from whichever tab it was pressed on, and moves when
   *  Javier next speaks, which is his confirmation in the new language, or at
   *  once on the brain's `language_changed`, which also follows a switch made
   *  by voice. */
  function chooseLanguage(want: Language): void {
    storeLanguage(want);
    shareLanguage(want);
    if (want === language && !switchTimer) return;
    if (role === "idle") return showLanguage(want);
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
      if (inFront() || ANY_TAB.has(event)) post({ k: "app", from: me, event, payload });
    });
    track(from);
    sayWhere();
  }

  function track(from: { status: Status; muted: boolean; activity: Activity | null; language?: Language }): void {
    if (from.status === "idle" || from.status === "error") return unfollow();
    if (waiting) clearTimeout(waiting);
    waiting = null;
    const wasLive = status === "live";
    widget.paint(from.status, from.status === "connecting" ? RECONNECTING[language] : undefined);
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
        widget.paint("connecting", RECONNECTING[language]);
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
        void perform(r.command, r.payload).then((outcome) => {
          if (outcome) post({ k: "app", from: me, event: outcome.event, payload: outcome.payload });
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
        if (r.event === HOLD_MIC) {
          if (role === "holder") {
            micHeld = Boolean((r.payload as { on?: boolean } | null)?.on);
            applyMic();
          }
          return;
        }
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

  // In a call, a link to another page of the three sites that would open a
  // new tab (the site's career cards and menus open many with
  // `target="_blank"`) loads in this tab instead, so the visitor stays in the
  // call's tab. A PDF or a download still opens on its own. Off a call the
  // site behaves as it always does.
  document.addEventListener(
    "click",
    (e) => {
      if (role === "idle" || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || !a.target || a.target === "_self" || a.hasAttribute("download")) return;
      let to: URL;
      try {
        to = new URL(a.href, location.href);
      } catch {
        return;
      }
      if (!SITE_LINK.test(to.href) || /\.(pdf|docx?|xlsx?|pptx?|zip|mp3)$/i.test(to.pathname)) return;
      e.preventDefault();
      location.assign(to.href);
    },
    true,
  );

  const navigation = (window as unknown as { navigation?: EventTarget }).navigation;
  navigation?.addEventListener("navigate", (e) => {
    const nav = e as Event & { destination?: { sameDocument?: boolean }; downloadRequest?: string | null };
    if (nav.destination && !nav.destination.sameDocument) {
      navigating = true;
      // This page is going: a cue still to come waits for the next one. A
      // download leaves the page where it is.
      if (!nav.downloadRequest) narration.hold();
    }
  });

  // A page load is not the end of the call (`bye` says `navigating`, and the
  // followers wait for the next page); the cues he has not reached go with it.
  window.addEventListener("pagehide", () => {
    leaving = true;
    narration.hold();
    if (role === "holder") {
      const rest = narration.pending();
      saveNarration(rest);
      // Best effort, for a page on another host: a cue's own load stashed
      // its rest before it left.
      if (rest.ready.length || rest.waiting.length) void stash("cues", { ...rest, at: Date.now() });
      // Best effort too: the record kept at connect is the same call.
      void keep("call", readCall());
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

  // What the last page of this tab left, on whichever host: the move it was
  // loaded to make, and the cues his voice had not reached. Asked for now, so
  // the hub forgets them, and made once the call is back on this page.
  const kept = Promise.all([pendingMove(), take<Rest & { at?: number }>("cues")]);

  // A call this tab held on another host: its saved record is put where the
  // transport looks for it, before `prepare` asks whether there is one.
  const [stashed, callLang, shared] = await Promise.all([
    peek<string>("call"),
    peek<Language>("call-lang"),
    sharedLanguage(),
  ]);
  if (stashed && stashed !== readCall()) {
    try {
      sessionStorage.setItem(CALL_KEY, stashed);
    } catch {
      /* Storage blocked: no rejoin across hosts. */
    }
  }
  // The visitor's choice made on another host holds here.
  if (shared) {
    storeLanguage(shared);
    if (shared !== language) showLanguage(shared);
  }

  paint("idle");
  spare = prepare();
  const rejoining = spare.transport.hasLiveCall;
  if (rejoining) {
    // The call's language, as the brain last said it on any host: an English
    // call stays English on the next page.
    if ((callLang === "es" || callLang === "en") && callLang !== language) {
      language = callLang;
      widget.setLanguage(callLang);
    }
    void connect(true);
  } else {
    forgetNarration();
    post({ k: "hello", from: me });
  }

  void kept.then(async ([then, hubCues]) => {
    const move: Then | null = then ?? takeLocalPending();
    const cues = rejoining ? (hubCues ?? takeNarration()) : null;
    if (!move && !cues) return;
    // The brain waits for this page's `page_changed` before it says more, so
    // the move is made after the page has been reported.
    if (rejoining) {
      await Promise.race([up, sleep(MOVE_AFTER_REJOIN_MS)]);
      await sleep(300);
    } else {
      await sleep(MOVE_WITHOUT_CALL_MS);
    }
    if (move) {
      const outcome = await perform(move.command, move.payload);
      // A cue's section that is not on the page it loaded is the cue's miss,
      // which the brain takes quietly: he has spoken past it.
      const viaCue = Boolean((move.payload as { via_cue?: boolean } | null)?.via_cue);
      if (outcome?.event === "command_failed" && viaCue) outcome.payload.command = "cue";
      if (outcome) report(outcome);
    }
    if (cues) narration.restore(cues);
  });
}

/** What the university pins over its pages, for the widget to keep clear of:
 *  UserWay's accessibility button (bottom-right on every host), and the lead
 *  form while Javier fills it. Read again every moment. */
function watchCorners(widget: ReturnType<typeof mountWidget>, obstacles: () => Element[]): void {
  let last = "";
  const read = () => {
    const rects = obstacles()
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight)
      .map((r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom }));
    const key = JSON.stringify(rects.map((r) => [r.left, r.top, r.right, r.bottom].map(Math.round)));
    if (key === last) return;
    last = key;
    widget.avoid(rects);
  };
  read();
  setInterval(read, 1500);
  window.addEventListener("resize", read);
  window.addEventListener("scroll", read, { passive: true });
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

function saveNarration(rest: Rest): void {
  try {
    if (rest.ready.length || rest.waiting.length) {
      sessionStorage.setItem(NARRATION_KEY, JSON.stringify({ ...rest, at: Date.now() }));
    } else sessionStorage.removeItem(NARRATION_KEY);
  } catch {
    /* Storage blocked: the next page moves only for what he says there. */
  }
}

/** The cues the last page of this origin left, once, if it left them moments ago. */
function takeNarration(): Rest | null {
  try {
    const raw = sessionStorage.getItem(NARRATION_KEY);
    sessionStorage.removeItem(NARRATION_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<Rest> & { at?: number };
    if (typeof saved.at !== "number" || Date.now() - saved.at > NARRATION_MAX_AGE_MS) return null;
    return { ready: saved.ready ?? [], waiting: saved.waiting ?? [] };
  } catch {
    return null;
  }
}

function forgetNarration(): void {
  try {
    sessionStorage.removeItem(NARRATION_KEY);
  } catch {
    /* Nothing stored. */
  }
}

interface Prepared {
  client: PipecatClient;
  transport: ReturnType<typeof createVoqalizeTransport>;
}

const MIC_BLOCKED: Record<Language, string> = {
  es: "Esta página bloquea el micrófono, así que Javier no te escucha. Recarga la página con la extensión activa e inténtalo otra vez.",
  en: "This page blocks the microphone, so Javier can't hear you. Reload the page with the extension on and try again.",
};

const RECONNECTING: Record<Language, string> = { es: "Reconectando", en: "Reconnecting" };

/** Whether this document's Permissions-Policy lets it open the microphone.
 *  The three hosts send `microphone=()`; `rules.json` rewrites it to
 *  `microphone=(self)`, and this catches a page loaded before that rule. */
function micAllowed(): boolean {
  const policy = (document as { featurePolicy?: { allowsFeature(name: string): boolean } }).featurePolicy;
  return policy?.allowsFeature("microphone") ?? true;
}

function micFailure(type: string, language: Language): string {
  if (!micAllowed()) return MIC_BLOCKED[language];
  const es = language === "es";
  if (type === "permissions")
    return es
      ? "Javier no te escucha: se rechazó el acceso al micrófono. Permítelo para este sitio y vuelve a empezar."
      : "Javier can't hear you: microphone access was refused. Allow it for this site, then start again.";
  if (type === "in-use")
    return es
      ? "Javier no te escucha: otra aplicación está usando el micrófono."
      : "Javier can't hear you: another app is using the microphone.";
  if (type === "not-found")
    return es ? "Javier no te escucha: no se encontró un micrófono." : "Javier can't hear you: no microphone was found.";
  return es ? "Javier no te escucha: el micrófono no se abrió." : "Javier can't hear you: the microphone did not open.";
}

function reason(error: unknown, language: Language): string {
  const text = error instanceof Error ? error.message : String(error);
  const lead = language === "es" ? "No se pudo iniciar la llamada" : "Could not start the call";
  return text.trim() ? `${lead}: ${text}` : `${lead}.`;
}

// Mount at once, at `document_idle`: never on `load`, which the site's
// trackers hold back for seconds, while Voqalize holds a call through a page
// load for ten. `start` mounts once.
if (document.body) void start();
else document.addEventListener("DOMContentLoaded", () => void start(), { once: true });
