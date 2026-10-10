/**
 * Trisha on Qween's site — the whole browser half of the call.
 *
 * Qween's page is theirs and we change nothing in it. This script is injected
 * into the page's own JavaScript world (the manifest's `"world": "MAIN"`)
 * because the site adapter drives Qween through their client-side router, which
 * only exists there. The same bundle is also built as a plain script Qween can
 * embed before `</body>` (see the README); it runs in the page either way, on
 * whichever of Qween's hosts serves it, so nothing here names a domain. It brings three things:
 *
 *   - the site adapter (`qween-actions.js`), which turns each of the brain's
 *     Actions into a move on Qween's page and reports every route change and
 *     dialog back, whoever caused it;
 *   - the corner widget (`widget.ts`);
 *   - the call: stock pipecat on `@voqalize/client-transport`'s media, one
 *     `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Trisha says or shows. The prompt, the tools and the
 * catalogue live in the brain, `demos/qween/backend/`.
 *
 * One store and one agent have one call, in every tab (`tabs.ts`). The tab it
 * started in holds it; every other open tab follows it: her face, the mute and
 * the call's state, relayed from the holder. A tab that finds a call already
 * held follows it rather than starting another. The brain's Actions are
 * performed by whichever tab is in front, and that tab's page is the one she
 * sees. Closing the call's tab ends the call everywhere.
 *
 * Most of Qween's navigation is client-side and keeps the call. A full page
 * load in the holder rejoins the same session on the next page
 * (`keepAcrossPageLoads`), so the conversation carries on.
 */

import "./qween-actions.js";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, sendAppEvent, UI_ACTION_COMMANDS } from "./actions.gen";
import { watchDialogs } from "./dialogs";
import {
  followCall, type Following, forgetCopiedCall, gestureContext, here, holdCall, type Holding,
  inFront, openChannel, type Relay, type TabInfo, tabId, takeCall,
} from "./tabs";
import { type Activity, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "trisha";
/** The call is one per store and agent: the channel and the lock are named
 *  for the agent. */
const AGENT = __VOQALIZE__.agentId;

/** The request that mints a session — see `docs/client/handshake`. */
function connectRequest(init: Record<string, unknown>): APIRequest {
  return {
    endpoint: `${__VOQALIZE__.apiBase}/sessions.connect`,
    // `Authorization` only: pipecat sets `Content-Type` itself, and a second
    // copy arrives as a doubled header the control plane cannot read as JSON.
    headers: new Headers({ Authorization: `Bearer ${__VOQALIZE__.publishableKey}` }),
    // Cast, not check: pipecat types this as its `Serializable`, which it does
    // not export, and the object is about to be `JSON.stringify`d either way.
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

/** Set once the widget is up, so the extension and Qween's own embed of this
 *  bundle, both on one page, put up one widget between them. */
const MOUNTED = "__voqalizeTrisha";

/** How long a follower waits for the holder to come back after it left for
 *  another page, and after a close the Navigation API did not see as one. */
const BACK_FROM_LOAD_MS = 12_000;
const BACK_FROM_CLOSE_MS = 1_500;

async function start(): Promise<void> {
  const adapter = window.voqalizeQween;
  const flags = window as unknown as Record<string, unknown>;
  if (!adapter || flags[MOUNTED]) return;
  flags[MOUNTED] = true;
  // The brain and the extension ship separately; an Action the adapter cannot
  // perform is reported back as `command_failed` when it arrives, and named
  // here once so it is found before a shopper finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c));
  if (missing.length) console.warn("voqalize: the adapter cannot perform", missing);

  const widget = mountWidget();
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine into Qween's page. One manager for the
  // page's life, each call's transport takes it: it owns the widget's element,
  // so it routes the speaker and re-attaches her track when the element stops
  // playing it (Android Chrome does, on a call another page was carrying).
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(widget.audio);
  // Qween's drawers open over the corner the widget sits in; it steps aside.
  watchDialogs((open) => widget.avoid(open));

  // Every tab of the store on one channel; see `tabs.ts`.
  const chan = openChannel(AGENT);
  const { id: me, instance } = await tabId(chan);

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
  /** The agent's call lock, while this tab holds the call. */
  let release: (() => void) | null = null;
  /** A client built ahead of the call: at load, to ask its transport whether
   *  this tab has a call to rejoin. */
  let spare: Prepared | null = null;
  /** Set when this page is leaving for another document, not closing. */
  let navigating = false;
  /** Held by the holder: every open tab of the store, and the one in front. */
  const tabs = new Map<string, TabInfo>();
  let active = me;
  /** A follower's wait for the holder to come back. */
  let waiting: ReturnType<typeof setTimeout> | null = null;

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

  /** The holder's state, for the followers: on every change. */
  function announce(): void {
    if (role === "holder") post({ k: "holder", from: me, status, muted, activity });
  }

  /** What she is doing, read off a client's events: the real one in the
   *  holder, the relayed stand-in in a follower. */
  function watchActivity(on: PipecatClient): void {
    on.on("userStartedSpeaking" as never, (() => setActivity("listening")) as never);
    on.on("botLlmStarted" as never, (() => setActivity("thinking")) as never);
    on.on("botStartedSpeaking" as never, (() => setActivity("speaking")) as never);
    on.on("botStoppedSpeaking" as never, (() => setActivity("listening")) as never);
  }

  // ─── The holder ──────────────────────────────────────────────────────

  /** A page event for the brain; only the tab in front's reach it. */
  function toBrain(from: string, event: AppEvent): void {
    if (role !== "holder" || !reporting || from !== active) return;
    sendAppEvent(reporting.sendUIEvent.bind(reporting), event);
  }

  /** The brain's memory of the tabs: the whole list each time, so a message
   *  lost while the holder was between pages cannot leave it wrong. */
  function sendTabs(): void {
    if (role !== "holder" || !reporting) return;
    tabs.set(me, here(me));
    if (!tabs.has(active)) active = me;
    sendAppEvent(reporting.sendUIEvent.bind(reporting), {
      event: "tabs_changed",
      payload: { tabs: [...tabs.values()], active },
    });
  }

  /** The tab in front changed: it becomes the one the brain sees and acts on. */
  function setActive(id: string): void {
    if (id === active) return;
    active = id;
    sendTabs();
  }

  /** Report this tab's page to the brain, as the tab now in front. */
  function reportPage(): void {
    const event = { event: "page_changed", payload: adapter!.context() } as AppEvent;
    if (role === "holder") toBrain(me, event);
    else if (role === "follower") post({ k: "app", from: me, event: event.event, payload: event.payload });
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
        // The page reports only once the brain can hear it; before that an
        // event has nobody to reach. Ready can arrive more than once for one
        // client, and each start would report the page again.
        onBotReady: () => {
          if (client !== next || reporting === next) return;
          reporting = next;
          stopAdapter?.();
          stopAdapter = adapter!.start((event, payload) => {
            if (event === "page_changed") tabs.set(me, here(me));
            toBrain(me, { event, payload } as AppEvent);
          });
          // Every other tab says where it is, which fills the brain's list.
          post({ k: "holder", from: me, status, muted, activity });
          sendTabs();
        },
        // The avatar draws and never plays a sound, so the bot's track is ours
        // to attach.
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio") return;
          widget.audio.srcObject = new MediaStream([track]);
          void widget.audio.play().catch(() => {});
        },
        onUICommand: ({ command, payload }) => void route(next, command, payload),
      },
    });
    return { client: next, transport };
  }

  /**
   * Hold the agent's call in this tab: a new one, or, after a page load, the
   * one this tab was holding. Another tab holding it already wins, and this
   * tab follows that call instead.
   */
  async function connect(rejoin: boolean, made?: AudioContext): Promise<void> {
    if (role !== "idle" || status === "connecting") return void made?.close();
    const lock = await takeCall(AGENT);
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
    holding = holdCall(next, chan, () => active === me);
    void holding.pulse(made);

    try {
      // Mounted on the press. It takes the face the reach preloaded, or builds
      // one during call setup, in time for the greeting's first audio.
      avatar?.destroy();
      avatar = createAvatar({ mount: widget.face, client: holding.avatarClient, character: CHARACTER });
      if (rejoin) {
        // The same session: the transport remembers the request for this tab.
        await next.connect();
      } else {
        const init = { site: location.host, path: location.pathname + location.search };
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
      // A rejoin the server refuses is a call that ended while the page was
      // away: the page simply starts idle.
      if (rejoin) paint("idle");
      else paint("error", reason(error));
      role = "idle";
      release?.();
      release = null;
      await next.disconnect().catch(() => {});
    }
  }

  /** One of the brain's Actions: performed by the tab in front, which is the
   *  one the shopper sees. */
  async function route(on: PipecatClient, command: string, payload: unknown): Promise<void> {
    if (active !== me && tabs.has(active)) {
      post({ k: "perform", to: active, command, payload });
      return;
    }
    const failed = await perform(command, payload);
    if (failed && client === on) toBrain(me, failed);
  }

  /** Perform an Action on this tab's page. Never waits on the shopper; a
   *  failure is returned for the brain so she never claims it worked. */
  async function perform(command: string, payload: unknown): Promise<AppEvent | null> {
    const action = asUiAction(command, payload);
    if (!action) return null;
    const result = await adapter!.run(action.command, action.payload);
    if (result.ok) return null;
    return { event: "command_failed", payload: { command, error: result.error ?? "failed" } };
  }

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
    // A call that ends because the page is going away is picked up on the next
    // page; one the shopper or the brain ended is over, and `disconnectBot`
    // ends it at once and tells the transport to forget it.
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

  // ─── A follower ──────────────────────────────────────────────────────

  /** Another tab holds a live call: follow it here. */
  function follow(from: { status: Status; muted: boolean; activity: Activity | null }): void {
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

  /** Mirror the holder's state; a call it no longer holds is gone here too. */
  function track(from: { status: Status; muted: boolean; activity: Activity | null }): void {
    if (from.status === "idle" || from.status === "error") return unfollow();
    if (waiting) clearTimeout(waiting);
    waiting = null;
    const wasLive = status === "live";
    widget.paint(from.status, from.status === "connecting" ? "Reconnecting" : undefined);
    status = from.status;
    widget.setMuted(from.muted);
    muted = from.muted;
    if (from.activity) widget.setActivity(from.activity);
    if (from.status === "live" && !wasLive) following?.joined();
  }

  /** The call is over: her face goes, as though there had been none. */
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

  /** Tell the holder where this tab is, and, in front, what it shows. */
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
      case "id?":
        if (r.from === me && r.instance !== instance) post({ k: "dup", id: me, instance: r.instance });
        return;
      case "hello":
        announce();
        // The holder is between pages: the call is still there.
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
          // A holder that has just reached the brain asks where every tab is.
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
  // Her face builds once the shopper reaches for the invite, and the call's
  // mount takes it. Not at page load: this runs on every page of the store, and
  // most shoppers never call. Reaching again after a call builds the next one.
  widget.onReach(() => {
    if (!client) preloadAvatar(CHARACTER);
  });
  widget.onHang(end);
  widget.onMute(toggleMute);

  // In front again: this tab becomes the one the brain sees.
  document.addEventListener("visibilitychange", sayWhere);
  window.addEventListener("focus", sayWhere);

  // Chrome and Safari 26 say, through the Navigation API, that the page is
  // leaving for another document; a closed tab says nothing. Same-document
  // moves (most of Qween's) never unload the page and do not count.
  const navigation = (window as unknown as { navigation?: EventTarget }).navigation;
  navigation?.addEventListener("navigate", (e) => {
    const dest = (e as Event & { destination?: { sameDocument?: boolean } }).destination;
    if (dest && !dest.sameDocument) navigating = true;
  });

  window.addEventListener("pagehide", () => {
    leaving = true;
    if (role === "holder") {
      post({ k: "bye", from: me, navigating });
      // The disconnect below ends the call here; the followers have their
      // `bye` and must not hear "idle" on top of it.
      role = "idle";
    } else if (role === "follower") post({ k: "gone", from: me });
    void client?.disconnect();
  });

  // Her face on the button. The roster comes from the avatar's own host, so
  // it is fetched once the page has settled rather than competing with it.
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
  // This tab held the call before its page load, or a tab opened from the
  // holder's link copied that: the lock tells them apart.
  if (spare.transport.hasLiveCall) void connect(true);
  // A call held in another tab answers this; this tab then follows it.
  else post({ k: "hello", from: me });
}

interface Prepared {
  client: PipecatClient;
  transport: ReturnType<typeof createVoqalizeTransport>;
}

function reason(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.trim() ? `Could not start the call: ${text}` : "Could not start the call.";
}

// Qween's embed runs this from `</body>`, before React has hydrated the
// document; the widget joins the page once that is done, which is when the
// extension's `document_idle` runs it anyway.
if (document.readyState === "complete") void start();
else window.addEventListener("load", () => void start(), { once: true });
