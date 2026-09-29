/**
 * Trisha on www.qween.com — the whole browser half of the call.
 *
 * Qween's page is theirs and we change nothing in it. This script is injected
 * into the page's own JavaScript world (the manifest's `"world": "MAIN"`)
 * because the site adapter drives Qween through their client-side router, which
 * only exists there. It brings three things:
 *
 *   - the site adapter (`qween-actions.js`), which turns each of the brain's
 *     Actions into a move on Qween's page and reports every route change and
 *     dialog back, whoever caused it;
 *   - the corner widget (`widget.ts`);
 *   - the call: stock pipecat, one `sessions.connect`, and the avatar.
 *
 * Nothing here decides what Trisha says or shows. The prompt, the tools and the
 * catalogue live in the brain, `demos/qween/backend/`.
 *
 * A full page load ends the call — a WebRTC session does not survive the
 * document. Most of Qween's navigation is client-side and keeps it, and the
 * adapter reroutes the one link we found that reloads. For the rest, the widget
 * remembers for this tab that a call was live and dials again on the next page,
 * with `rejoin` in its init so her opener says what happened.
 */

import "./qween-actions.js";

import { type APIRequest, PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { type AvatarInstance, createAvatar, listCharacters } from "@voqalize/avatar";

import { type AppEvent, asUiAction, sendAppEvent, UI_ACTION_COMMANDS } from "./actions.gen";
import { mountWidget, type Status } from "./widget";

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

function start(): void {
  const adapter = window.voqalizeQween;
  if (!adapter) return;
  // The brain and the extension ship separately; an Action the adapter cannot
  // perform is reported back as `command_failed` when it arrives, and named
  // here once so it is found before a shopper finds it.
  const missing = UI_ACTION_COMMANDS.filter((c) => !adapter.commands.includes(c));
  if (missing.length) console.warn("voqalize: the adapter cannot perform", missing);

  const widget = mountWidget();
  let client: PipecatClient | null = null;
  let avatar: AvatarInstance | null = null;
  let stopAdapter: (() => void) | null = null;
  /** The client the adapter is reporting to. */
  let reporting: PipecatClient | null = null;
  let status: Status = "idle";
  let muted = false;
  let leaving = false;

  function paint(next: Status, message?: string): void {
    status = next;
    widget.paint(next, message);
  }

  async function connect(rejoin: boolean): Promise<void> {
    if (status === "connecting" || status === "live") return;
    paint("connecting", rejoin ? "Reconnecting" : undefined);

    const next: PipecatClient = new PipecatClient({
      transport: new SmallWebRTCTransport(),
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
          stopAdapter = adapter!.start((event, payload) =>
            sendAppEvent(next.sendUIEvent.bind(next), { event, payload } as AppEvent),
          );
        },
        onUserStartedSpeaking: () => widget.setActivity("listening"),
        onBotLlmStarted: () => widget.setActivity("thinking"),
        onBotStartedSpeaking: () => widget.setActivity("speaking"),
        onBotStoppedSpeaking: () => widget.setActivity("listening"),
        // The avatar draws and never plays a sound, so the bot's track is ours
        // to attach.
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio") return;
          widget.audio.srcObject = new MediaStream([track]);
          void widget.audio.play().catch(() => {});
        },
        onUICommand: ({ command, payload }) => void perform(next, command, payload),
      },
    });
    client = next;

    try {
      // Mounted on the press so the face downloads during call setup and is
      // there for the greeting's first audio.
      avatar?.destroy();
      avatar = createAvatar({ mount: widget.face, client: next, character: CHARACTER });
      const init: Record<string, unknown> = {
        site: "www.qween.com",
        path: location.pathname + location.search,
      };
      if (rejoin) init.rejoin = true;
      const started = await next.startBot(connectRequest(init));
      await next.connect(withRealHeaders(started));
    } catch (error) {
      if (client !== next) return;
      client = null;
      avatar?.destroy();
      avatar = null;
      remember(false);
      paint("error", reason(error));
      await next.disconnect().catch(() => {});
    }
  }

  /** One of the brain's Actions, performed on Qween's page. Never waits on the
   *  shopper; a failure goes back to the brain so she never claims it worked. */
  async function perform(on: PipecatClient, command: string, payload: unknown): Promise<void> {
    const action = asUiAction(command, payload);
    if (!action) return;
    const result = await adapter!.run(action.command, action.payload);
    if (!result.ok && client === on) {
      sendAppEvent(on.sendUIEvent.bind(on), {
        event: "command_failed",
        payload: { command, error: result.error ?? "failed" },
      });
    }
  }

  function end(): void {
    stopAdapter?.();
    stopAdapter = null;
    reporting = null;
    // A call that ends because the page is going away is one to pick up on the
    // next page; one the shopper or the brain ended is over.
    if (!leaving) remember(false);
    const live = client;
    client = null;
    avatar?.destroy();
    avatar = null;
    widget.audio.srcObject = null;
    muted = false;
    widget.setMuted(false);
    paint("idle");
    void live?.disconnect().catch(() => {});
  }

  widget.onCall(() => void connect(false));
  widget.onHang(end);
  widget.onMute(() => {
    muted = !muted;
    client?.enableMic(!muted);
    widget.setMuted(muted);
  });

  window.addEventListener("pagehide", () => {
    leaving = true;
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
  if (remembered()) void connect(true);
}

function reason(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.trim() ? `Could not start the call: ${text}` : "Could not start the call.";
}

start();
