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
 * A full page load ends the call — a WebRTC session does not survive the
 * document. Most of Qween's navigation is client-side and keeps it, and the
 * adapter reroutes the one link we found that reloads. For the rest, the widget
 * remembers for this tab that a call was live and dials again on the next page,
 * with `rejoin` in its init so her opener says what happened.
 *
 * Every other open tab of the store follows the call (`tabs.ts`): her face, the
 * mute and the call's state, relayed from the tab that holds it. The brain's
 * Actions are performed by whichever tab is in front, and that tab's page is
 * the one she sees. Closing the call's tab ends the call everywhere.
 */

import "./qween-actions.js";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { type AvatarInstance, createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import { type AppEvent, asUiAction, sendAppEvent, UI_ACTION_COMMANDS } from "./actions.gen";
import { watchDialogs } from "./dialogs";
import {
  followCall, type Following, here, holdCall, type Holding, inFront, openChannel, type Relay,
  type TabInfo, tabId,
} from "./tabs";
import { type Activity, mountWidget, type Status } from "./widget";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "trisha";
/** Set while a call is live in this tab; read on the next page load. */
const LIVE_FLAG = "voqalize.qween.live";

function remembered(): boolean {
  try {
    return sessionStorage.getItem(LIVE_FLAG) === "1";
  } catch {
    return false;
  }
}

function remember(live: boolean): void {
  try {
    if (live) sessionStorage.setItem(LIVE_FLAG, "1");
    else sessionStorage.removeItem(LIVE_FLAG);
  } catch {
    /* Storage blocked: the call still works, it just will not rejoin. */
  }
}

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
/** How long a page load waits to hear of a call held elsewhere before it dials
 *  again on its own. */
const ASK_MS = 300;

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
  const chan = openChannel();
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

  async function connect(rejoin: boolean): Promise<void> {
    if (role !== "idle" || status === "connecting") return;
    role = "holder";
    active = me;
    tabs.clear();
    paint("connecting", rejoin ? "Reconnecting" : undefined);
    if (rejoin) post({ k: "coming", from: me });

    const next: PipecatClient = new PipecatClient({
      transport: createVoqalizeTransport({ mediaManager: media }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state: TransportState) => {
          if (client !== next) return;
          if ((state === "connected" || state === "ready") && status !== "live") {
            paint("live");
            remember(true);
          }
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
    client = next;
    watchActivity(next);
    holding = holdCall(next, chan, () => active === me);
    // Before the first await, so the AudioContext is made inside the click.
    void holding.pulse();

    try {
      // Mounted on the press. It takes the face the reach preloaded, or builds
      // one during call setup, in time for the greeting's first audio.
      avatar?.destroy();
      avatar = createAvatar({ mount: widget.face, client: holding.avatarClient, character: CHARACTER });
      const init: Record<string, unknown> = {
        site: location.host,
        path: location.pathname + location.search,
      };
      if (rejoin) init.rejoin = true;
      const started = await next.startBot(connectRequest(init));
      await next.connect(withRealHeaders(started));
    } catch (error) {
      if (client !== next) return;
      client = null;
      holding?.stop();
      holding = null;
      avatar?.destroy();
      avatar = null;
      remember(false);
      paint("error", reason(error));
      role = "idle";
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
    // A call that ends because the page is going away is one to pick up on the
    // next page; one the shopper or the brain ended is over.
    if (!leaving) remember(false);
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
      case "hello":
        if (r.from === me && r.instance !== instance) post({ k: "dup", id: me, instance: r.instance });
        announce();
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

  widget.onCall(() => void connect(false));
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
  // A call held in another tab answers this; this tab then follows it.
  post({ k: "hello", from: me, instance });
  if (remembered()) {
    // A tab opened from the holder's link can carry a copy of its live flag:
    // only a tab that hears of no call elsewhere dials again.
    setTimeout(() => {
      if (role === "idle") void connect(true);
      else remember(false);
    }, ASK_MS);
  }
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
