/**
 * Javier on SendPotion — the whole browser half of the call.
 *
 * SendPotion's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on sendpotion.com and on blog.sendpotion.com, and brings:
 *
 *   - the site adapter (`sendpotion-actions.ts`), which turns the brain's page
 *     Actions into moves on the page in front and reports every route change
 *     and booking step back, whoever caused it;
 *   - the corner widget (`widget.ts`), with the reading list;
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/sendpotion/backend/`.
 *
 * One site and one agent have one call, in every tab of both hosts (`tabs.ts`
 * over the extension's hub, `hub.ts`). The tab it started in holds it; every
 * other SendPotion tab follows it: his face, the mute and the call's state. A
 * tab that finds a call already held follows it rather than starting another.
 * The brain's Actions arrive at the holder, which sends each to the tab it
 * belongs on:
 *
 *   - a move on a page (a section, an FAQ) to the tab in front;
 *   - a move to a sendpotion.com page or the demo calendar to a sendpotion.com
 *     tab — the one in front, else the visitor's other site tab, brought to the
 *     front, else a new one;
 *   - blog posts to new tabs, opened by the hub, since a move that arrives over
 *     the call is not a click and a page may not open a tab without one;
 *   - the reading list to every tab's widget.
 *
 * Moving between pages keeps the call: both hosts route client-side. A full
 * page load in the holder rejoins the same session on the next page
 * (`keepAcrossPageLoads`), so the conversation carries on.
 */

import "./sendpotion-actions";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, type Cue, sendAppEvent, UI_ACTION_COMMANDS, type UiAction } from "./actions.gen";
import { Narration } from "./narration";
import { focusTab, HubChannel, openTab, pendingMove, type Then, tabId, takeCall } from "./hub";
import {
  followCall, type Following, forgetCopiedCall, gestureContext, here, holdCall, type Holding,
  inFront, type Relay, type TabInfo,
} from "./tabs";
import { type Activity, type Language, mountWidget, type Read, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";
const AGENT = __VOQALIZE__.agentId;
const SITE = "https://sendpotion.com";
const SIGNUP = "https://app.sendpotion.com/?utm_campaign=inbound&utm_source=website";
/** Set once the widget is up, so a second copy of this script on the page
 *  puts up no second widget. */
const MOUNTED = "__voqalizeJavier";
/** The language the visitor last chose on the toggle on this host, which the
 *  next call starts in and holds to; and how long the toggle waits for the brain to answer a switch before
 *  it shows the language the call is still in. */
const LANG_KEY = "voqalize.sendpotion.lang";
const SWITCH_WAIT_MS = 4000;

/** How long a follower waits for the holder to come back after it left for
 *  another page, and after a close the Navigation API did not see as one. */
const BACK_FROM_LOAD_MS = 12_000;
const BACK_FROM_CLOSE_MS = 1_500;

/** The Actions that belong on a sendpotion.com tab, wherever the visitor is. */
const SITE_COMMANDS = new Set(["navigate", "book_demo"]);
/** The Actions the holder performs itself rather than a page. */
const OURS = new Set(["open_posts", "open_post", "open_signup", "focus_tab", "cue", "language_changed"]);

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

const isSite = (url: string) => /^https:\/\/(www\.)?sendpotion\.com(\/|$)/i.test(url);
const sameDoc = (a: string, b: string) => {
  const f = (u: string) => {
    try {
      const x = new URL(u);
      return `${x.host.replace(/^www\./, "")}${x.pathname.replace(/\/+$/, "")}`.toLowerCase();
    } catch {
      return u;
    }
  };
  return f(a) === f(b);
};

async function start(): Promise<void> {
  const adapter = window.voqalizeSendPotion;
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
  // loads a third-party call machine into SendPotion's page.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);

  // Every SendPotion tab, on both hosts, on one channel; see `tabs.ts`.
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
  /** Held by the holder: every open SendPotion tab, and the one in front. */
  const tabs = new Map<string, TabInfo>();
  let active = me;
  /** The tab most recently in front on each host, for moves that belong there. */
  let lastSiteTab: string | null = null;
  let waiting: ReturnType<typeof setTimeout> | null = null;
  /** The reading list, kept by every tab so a newcomer can be told. */
  let reads: { heading: string; posts: Read[] } | null = null;
  /** The call's language, or the next call's; the one the toggle asked for
   *  until the brain answers; and the wait for that answer. */
  let language: Language = storedLanguage() ?? "en";
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

  function showReads(next: { heading: string; posts: Read[] } | null, tell: boolean): void {
    reads = next;
    widget.setReads(next?.heading ?? "", next?.posts ?? []);
    // An empty list is news too: closed here, it closes on every tab.
    if (tell) post({ k: "reads", heading: next?.heading ?? "", posts: next?.posts ?? [] });
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
    const anyTab = ["command_failed", "demo_state", "language_requested"];
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
        const init = {
          surface: "sendpotion-ext", site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title,
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
      else paint("error", reason(error));
      role = "idle";
      release?.();
      release = null;
      await next.disconnect().catch(() => {});
    }
  }

  // ─── Where each Action goes ───────────────────────────────────────────

  /** The tab showing `url`, if one does. */
  function tabShowing(url: string): string | null {
    for (const [id, t] of tabs) if (sameDoc(t.url, url)) return id;
    return null;
  }

  /** The tab a sendpotion.com move belongs on: the one in front, else the
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

  /** Send a page Action to the tab it belongs on: a sendpotion.com move to a
   *  sendpotion.com tab (brought to the front, or a new one), anything else
   *  to the tab in front. The reason it failed, or `null`. */
  async function dispatch(command: string, payload: unknown): Promise<string | null> {
    if (SITE_COMMANDS.has(command)) {
      const to = siteTab();
      if (to === null) {
        // No sendpotion.com tab is open: one opens, and makes the move once up.
        const path = command === "navigate" ? (payload as { path: string }).path : "/demo/";
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
      case "open_posts": {
        const { heading, posts, open } = action.payload;
        showReads({ heading, posts: posts.map((p) => ({ url: p.url, title: p.title, why: p.why })) }, true);
        if (!open) return null;
        const there = tabShowing(open);
        if (there) return (await focusTab(there)) ? null : "that post's tab could not be brought to the front";
        return openTab(open);
      }
      case "open_post": {
        const { url, heading } = action.payload;
        const then: Then | undefined = heading
          ? { command: "show_section", payload: { heading, text: null } }
          : undefined;
        const there = tabShowing(url);
        if (there) {
          await focusTab(there);
          if (then) void performOn(there, then.command, then.payload);
          return null;
        }
        return openTab(url, then);
      }
      case "open_signup":
        return openTab(SIGNUP);
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
  flags.__voqalizeSendPotion = {
    perform: async (command: string, payload: unknown) => {
      const failed = await perform(command, payload);
      if (failed) console.info("voqalize (no call):", failed.event, failed.payload);
      return failed;
    },
    reads: (heading: string, posts: Read[]) => showReads({ heading, posts }, false),
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
      if (inFront() || event === "demo_state") post({ k: "app", from: me, event, payload });
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
        if (reads) post({ k: "reads", heading: reads.heading, posts: reads.posts });
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
      case "reads":
        showReads({ heading: r.heading, posts: r.posts }, false);
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
  // A post in the reading list: its own tab if one shows it, else a new one.
  widget.onCloseReads(() => showReads(null, true));
  widget.onRead((url) => {
    const there = role === "holder" ? tabShowing(url) : null;
    if (there) void focusTab(there);
    else void openTab(url);
  });

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
  if (spare.transport.hasLiveCall) void connect(true);
  else post({ k: "hello", from: me });

  // A tab Javier opened may have a move to make once its page is up: a section
  // of the post he opened it for.
  void pendingMove().then(async (then) => {
    if (!then) return;
    await new Promise((r) => setTimeout(r, 1200));
    const failed = await perform(then.command, then.payload);
    if (failed) post({ k: "app", from: me, event: failed.event, payload: failed.payload });
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
  "This page blocks the microphone, so Javier can't hear you. Start the call from a sendpotion.com tab.";

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

// Mount on `load`, but never wait on it for long: a third-party resource can
// hold `load` back, and Javier would not appear. `start` mounts once.
if (document.readyState === "complete") void start();
else {
  window.addEventListener("load", () => void start(), { once: true });
  setTimeout(() => void start(), 3000);
}
