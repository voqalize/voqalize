/**
 * Javier on Santander Arena — the whole browser half of the call.
 *
 * Santander Arena's pages are theirs and we change nothing in them. This
 * script is injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on www.santanderarena.cl, and brings:
 *
 *   - the site adapter (`santander-actions.ts`), which turns the brain's page
 *     Actions into moves on the page in front and reports every page the
 *     visitor lands on, whoever took them there;
 *   - the corner widget (`widget.ts`), with the Español/English toggle;
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/santanderarena/backend/`.
 *
 * One site and one agent have one call, in every Santander Arena tab
 * (`tabs.ts` over the extension's hub, `hub.ts`). The tab it started in holds
 * it; every other tab follows it: his face, the mute and the call's state. A
 * tab that finds a call already held follows it rather than starting another.
 * The brain's Actions arrive at the holder, which sends each to the tab it
 * belongs on:
 *
 *   - a move on a page (a section, a card, an FAQ) to the tab in front;
 *   - a move to another page to a site tab — the one in front, else the
 *     visitor's other site tab, brought to the front, else a new one;
 *   - a ticket, parking or VIP link to a new Puntoticket tab, opened by the
 *     hub, since a move that arrives over the call is not a click and a page
 *     may not open a tab without one. The extension does not run there.
 *
 * Every move to another page is a full page load: the site has no client
 * router. The holder's next page rejoins the same session
 * (`keepAcrossPageLoads`) while the voice holds his sentence and plays it
 * after, and the cues he had not reached yet are carried over in
 * `sessionStorage`, so the screen keeps following him on the new page.
 */

import "./santander-actions";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, type Cue, sendAppEvent, UI_ACTION_COMMANDS, type UiAction } from "./actions.gen";
import { Narration } from "./narration";
import { focusTab, HubChannel, openTab, pendingMove, tabId, takeCall } from "./hub";
import {
  followCall, type Following, forgetCopiedCall, gestureContext, here, holdCall, type Holding,
  inFront, type Relay, type TabInfo,
} from "./tabs";
import { type Activity, type Language, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
const AGENT = __VOQALIZE__.agentId;
const SITE = "https://www.santanderarena.cl";
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeJavier";
/** The language the visitor last chose on the toggle, which the next call
 *  starts in and holds to; and how long the toggle waits for the brain to
 *  answer a switch before it shows the language the call is still in. With no
 *  choice made the call opens in Spanish, as the site does. */
const LANG_KEY = "voqalize.santander.lang";
const OPENING: Language = "es";
const SWITCH_WAIT_MS = 4000;

/** How long a follower waits for the holder to come back after it left for
 *  another page, and after a close the Navigation API did not see as one. */
const BACK_FROM_LOAD_MS = 12_000;
const BACK_FROM_CLOSE_MS = 1_500;

/** The cues the holder's last page had not reached when it unloaded, for the
 *  next page of the same tab; older than this, his sentence is over. */
const NARRATION_KEY = "voqalize.santander.narration";
/** The call's language, per tab, across its page loads. */
const CALL_LANG_KEY = "voqalize.santander.call-lang";
const NARRATION_MAX_AGE_MS = 30_000;

/** The Actions that open a page of the site, on a site tab. */
const SITE_COMMANDS = new Set(["navigate"]);
/** The Actions the holder performs itself rather than a page. */
const OURS = new Set(["open_tickets", "focus_tab", "cue", "language_changed"]);

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

const isSite = (url: string) => /^https:\/\/(www\.)?santanderarena\.cl(\/|$)/i.test(url);

async function start(): Promise<void> {
  const adapter = window.voqalizeSantander;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED]) return;
  flags[MOUNTED] = true;
  if (!AGENT || !__VOQALIZE__.publishableKey) {
    console.warn("voqalize: built without an agent id or publishable key; calls cannot start (see .env.example)");
  }
  // The brain and the extension ship separately; an Action nobody here can
  // perform is named once here so it is found before a visitor finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c) && !OURS.has(c));
  if (missing.length) console.warn("voqalize: nothing performs", missing);

  const widget = mountWidget();
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine into Santander Arena's page.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);

  // Every Santander Arena tab on one channel; see `tabs.ts`.
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
  /** Held by the holder: every open Santander Arena tab, and the one in front. */
  const tabs = new Map<string, TabInfo>();
  let active = me;
  /** The site tab most recently in front, for moves that belong on one. */
  let lastSiteTab: string | null = null;
  let waiting: ReturnType<typeof setTimeout> | null = null;
  /** The call's language, or the next call's; the one the toggle asked for
   *  until the brain answers; and the wait for that answer. */
  // A page loaded mid-call carries on in the call's language, which the brain
  // may have moved by what the visitor spoke; on dev the toggle fell back to
  // Español on the next page of an English call.
  let language: Language = callLanguage() ?? storedLanguage() ?? OPENING;
  let asked: Language | null = null;
  let switchTimer: ReturnType<typeof setTimeout> | null = null;

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
    keepCallLanguage(role === "idle" ? null : next);
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
    // After a page load the call rejoins mid-reply, with no fresh "started
    // speaking": his words arriving are the sign he is talking. On dev the
    // widget said "Escuchando" through every answer that moved the page.
    const talking = () => {
      if (activity !== "speaking") setActivity("speaking");
    };
    on.on("botOutput" as never, talking as never);
    on.on("botTtsText" as never, talking as never);
  }

  // ─── The holder ──────────────────────────────────────────────────────

  /** A page event for the brain; only the tab in front's reach it, except a
   *  move's failure, which is the brain's whichever tab made it. */
  function toBrain(from: string, event: AppEvent): void {
    if (role !== "holder" || !reporting) return;
    const anyTab = ["command_failed", "language_requested"];
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
    const t = tabs.get(id);
    if (t && isSite(t.url)) lastSiteTab = id;
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
        // the visitor is now. Ready can arrive more than once for one client.
        onBotReady: () => {
          if (client !== next || reporting === next) return;
          reporting = next;
          stopAdapter?.();
          stopAdapter = adapter!.start((event, payload) => {
            if (event === "page_changed") {
              tabs.set(me, here(me));
              if (isSite(location.href)) lastSiteTab = me;
            }
            toBrain(me, { event, payload } as AppEvent);
          });
          // Every other tab says where it is, which fills the brain's list.
          post({ k: "holder", from: me, status, muted, activity, language });
          sendTabs();
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
        const ctx = adapter!.context();
        // `lang` only when the visitor chose it: the brain then holds to it
        // whatever they speak, and otherwise opens in Spanish and follows the
        // language they speak.
        const chosen = storedLanguage();
        const init = {
          surface: "santanderarena-ext", path: ctx.path, url: ctx.url, title: ctx.title,
          ...(chosen ? { lang: chosen } : {}),
        };
        const started = await next.startBot(connectRequest(init));
        await next.connect(withRealHeaders(started));
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
      await next.disconnect().catch(() => {});
    }
  }

  // ─── Where each Action goes ───────────────────────────────────────────

  /** The tab a move to another page belongs on: the one in front, else the
   *  site tab last in front, else any site tab. */
  function siteTab(): string | null {
    const front = tabs.get(active);
    if (front && isSite(front.url)) return active;
    if (lastSiteTab && tabs.has(lastSiteTab)) return lastSiteTab;
    for (const [id, t] of tabs) if (isSite(t.url)) return id;
    // No tab list yet (the call is still reaching the brain, or there is no
    // call and the console is driving): this tab, when it is on the site.
    return isSite(location.href) ? me : null;
  }

  /** Perform an Action on tab `to`: this one, or another through the hub.
   *  The reason it failed, or `null`. Another tab reports its own failure
   *  through the hub, so its move resolves once it has had time to land. */
  async function performOn(to: string, command: string, payload: unknown): Promise<string | null> {
    if (to === me) {
      const failed = await perform(command, payload);
      return failed ? String((failed.payload as { reason?: string }).reason ?? "failed") : null;
    }
    post({ k: "perform", to, command, payload });
    await new Promise((r) => setTimeout(r, 1200));
    return null;
  }

  /** Send a page Action to the tab it belongs on: a move to another page to a
   *  site tab (brought to the front, or a new one), anything else to the tab
   *  in front. The reason it failed, or `null`. */
  async function dispatch(command: string, payload: unknown): Promise<string | null> {
    if (SITE_COMMANDS.has(command)) {
      const to = siteTab();
      if (to === null) {
        // No site tab is open: one opens, and makes the move once up.
        const { path } = payload as { path: string };
        return openTab(new URL(path, SITE).href, { command, payload });
      }
      if (to !== active) await focusTab(to);
      return performOn(to, command, payload);
    }
    return performOn(tabs.has(active) ? active : me, command, payload);
  }

  /** A cue, as the page Action it stands for. */
  function cueMove(cue: Cue): [string, unknown] {
    if (cue.path) return ["navigate", { path: cue.path, heading: cue.heading, text: cue.text, faq: cue.faq }];
    if (cue.faq) return ["open_faq", { question: cue.faq }];
    return ["show_section", { heading: cue.heading, text: cue.text }];
  }

  // The screen follows his voice; see `narration.ts`. A cue that misses is
  // reported as `cue`, which the brain takes quietly: he has spoken past it.
  // A cue that opens another page in this tab unloads it mid-sentence; the
  // cues after it are saved on `pagehide` and the next page takes them up.
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
    const why = OURS.has(action.command) ? await ours(action) : await dispatch(action.command, action.payload);
    if (why && client === on) toBrain(me, { event: "command_failed", payload: { command, reason: why } });
  }

  /** The Actions the call performs itself. A failure comes back as words. */
  async function ours(action: UiAction): Promise<string | null> {
    switch (action.command) {
      // Tickets, parking and VIP are bought on Puntoticket, in a tab of its
      // own: the visitor's site tab stays where it is, and the call with it.
      case "open_tickets":
        return openTab(action.payload.url);
      case "focus_tab":
        return (await focusTab(action.payload.tab_id)) ? null : `no tab ${action.payload.tab_id} to bring forward`;
      // The brain's word that the call's language moved, by the toggle, by
      // voice or on request: the toggle follows at once, on every tab.
      case "language_changed":
        showLanguage(action.payload.language);
        return null;
      default:
        return `the call cannot ${action.command}`;
    }
  }

  /** Perform an Action on this tab's page. Never waits on the visitor; a
   *  failure is returned for the brain so he never claims it worked. */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const result = await adapter!.run(command, payload);
    if (result.ok) return null;
    return { event: "command_failed", payload: { command, reason: result.error ?? "failed" } };
  }

  // Driving the page from the console, with no call (see the README).
  flags.__voqalizeSantander = {
    perform: async (command: string, payload: unknown) => {
      const failed = await perform(command, payload);
      if (failed) console.info("voqalize (no call):", failed.event, failed.payload);
      return failed;
    },
    // Cues as the brain sends them, and speech as the voice plays it.
    narration,
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
    // Leaving for another page closes the connection too, and that is no
    // hang-up: the next page carries on in the call's language.
    if (!leaving) keepCallLanguage(null);
    tabs.clear();
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
      if (inFront()) post({ k: "app", from: me, event, payload });
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
        if (lastSiteTab === r.from) lastSiteTab = null;
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
      saveNarration(narration.pending());
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

  paint("idle");
  spare = prepare();
  if (spare.transport.hasLiveCall) {
    // The last page of this tab held the call and left mid-sentence: the cues
    // it had not reached wait for the rest of that sentence, played here.
    narration.restore(takeNarration());
    void connect(true);
  } else {
    forgetNarration();
    keepCallLanguage(null);
    post({ k: "hello", from: me });
  }

  // A tab Javier opened may have a move to make once its page is up: the
  // section of the page he opened it for.
  void pendingMove().then(async (then) => {
    if (!then) return;
    await new Promise((r) => setTimeout(r, 1200));
    const failed = await perform(then.command, then.payload);
    if (failed) post({ k: "app", from: me, event: failed.event, payload: failed.payload });
  });
}

/** The language of the call this tab holds or follows, kept across its page
 *  loads; `null` when no call is on. */
function callLanguage(): Language | null {
  try {
    const v = sessionStorage.getItem(CALL_LANG_KEY);
    return v === "es" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

function keepCallLanguage(language: Language | null): void {
  try {
    if (language) sessionStorage.setItem(CALL_LANG_KEY, language);
    else sessionStorage.removeItem(CALL_LANG_KEY);
  } catch {
    /* Storage blocked: the next page shows the toggle's own choice. */
  }
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

function saveNarration(cues: Cue[]): void {
  try {
    if (cues.length) sessionStorage.setItem(NARRATION_KEY, JSON.stringify({ cues, at: Date.now() }));
    else sessionStorage.removeItem(NARRATION_KEY);
  } catch {
    /* Storage blocked: the next page moves only for what he says there. */
  }
}

/** The cues the last page left, once, if it left them moments ago. */
function takeNarration(): Cue[] {
  try {
    const raw = sessionStorage.getItem(NARRATION_KEY);
    sessionStorage.removeItem(NARRATION_KEY);
    if (!raw) return [];
    const saved = JSON.parse(raw) as { cues?: Cue[]; at?: number };
    if (typeof saved.at !== "number" || Date.now() - saved.at > NARRATION_MAX_AGE_MS) return [];
    return Array.isArray(saved.cues) ? saved.cues : [];
  } catch {
    return [];
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
  es: "Esta página bloquea el micrófono, así que Javier no te escucha. Inicia la llamada desde una pestaña de santanderarena.cl.",
  en: "This page blocks the microphone, so Javier can't hear you. Start the call from a santanderarena.cl tab.",
};

const RECONNECTING: Record<Language, string> = { es: "Reconectando", en: "Reconnecting" };

/** Whether this document's Permissions-Policy lets it open the microphone. */
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

// Mount on `load`, but never wait on it for long: a third-party resource can
// hold `load` back, and Javier would not appear. `start` mounts once.
if (document.readyState === "complete") void start();
else {
  window.addEventListener("load", () => void start(), { once: true });
  setTimeout(() => void start(), 3000);
}
