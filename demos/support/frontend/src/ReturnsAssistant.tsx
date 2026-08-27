/**
 * The Returns Assistant's voice layer — ambient presence, not a docked widget.
 *
 * The storefront is the star: the assistant announces itself as a glow around the
 * whole viewport ({@link AmbientPresence}) plus one small control that lives
 * *inside* Voqal Mobile's own top bar, so it reads as product chrome rather than a
 * bolted-on chat box. Status is carried by the ring's hue and motion; there is no
 * panel to read.
 *
 * **This is exactly the surface an external developer embeds, and it is almost
 * entirely pipecat's.** Voice-ui-kit's `PipecatAppBase` does pipecat's whole
 * two-step connect (`startBot` against the control plane, then `connect` the
 * transport) and owns the client's lifecycle; everything below it is a stock
 * `PipecatClient`: `usePipecatClientTransportState`/`usePipecatConnectionState`
 * report the call, RTVI events say who is speaking, and the brain's
 * `session.dispatch(...)` arrives on `RTVIEvent.UICommand` as
 * `{ command, payload }`. The only Voqalize-specific code on the page is the
 * request that starts the call and the one line over its answer, both in
 * `src/config.ts` — there is no client library to install.
 *
 * Two bridges tie the call to the on-screen store:
 *   - every `ui-command` replays onto the shared orders store, so the assistant
 *     drives the shopper's screen;
 *   - a client→bot channel is registered on the store so the return form can push
 *     the captured photo (`photo_upload`) and the final submission
 *     (`return_submitted`) back to the bot.
 *
 * The storefront is rendered through a `children` render-prop (like the Flowforge
 * demo) so the app keeps ownership of its own chrome and simply drops the
 * presence control into its header. Mounted once inside the `OrdersProvider`, so
 * the ring and store survive page changes. A call that ends fully unmounts its
 * `PipecatAppBase` rather than leaning on pipecat's own reconnect — the next tap
 * mints a fresh client on a fresh session, which is simpler than a client whose
 * connect/disconnect history has to be reasoned about.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from "@voqalize/demo-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import { connectRequest, withRealHeaders } from "./config";
import { useOrders } from "./store";

const BRAND = "#0f766e";

// Voqal Mobile's own chrome is indigo; the Returns Assistant has always been
// teal (the widget's brand, and the mic accessory's accent in the catalog). Keeping
// the ring teal says "the agent is present" without repainting the storefront's
// identity. While it reasons the ring jumps to the bright cyan that used to be the
// visualizer's second wave — a shift in both hue *and* brightness, so "thinking"
// reads at the edge of vision. Offline is the page's own hairline border grey.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: BRAND,
  listening: BRAND,
  thinking: "#22d3ee",
  speaking: BRAND,
  offline: "#e5e7eb",
};

const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── The one voice affordance, dropped into the storefront's top bar ────────────

function PresenceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="os-presence">
      {children}
      <style>{PRESENCE_CSS}</style>
    </div>
  );
}

// Not live: a short invitation, and a mic to start. Doubles as the error surface —
// the label carries the message, the button retries.
function BeginControl({
  connecting,
  error,
  onBegin,
}: {
  connecting: boolean;
  error: string;
  onBegin: () => void | Promise<void>;
}) {
  const label = connecting ? "Connecting…" : error || "Ask about a return";
  return (
    <PresenceFrame>
      <span className={`os-presence-label${error && !connecting ? " is-error" : ""}`} title={label}>
        {label}
      </span>
      {connecting ? (
        <button className="os-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="os-spin" />
        </button>
      ) : (
        <button
          className="os-presence-btn"
          onClick={onBegin}
          title={error ? "Try again" : "Talk to the Returns Assistant"}
        >
          <Mic size={16} />
        </button>
      )}
    </PresenceFrame>
  );
}

// Live: the mic doubles as a mute toggle; a small ghost control ends the call.
function LiveControls({ activity, onEnd }: { activity: AmbientPresenceActivity; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const label = isMicEnabled ? STATE_LABEL[activity] : "Muted";
  return (
    <PresenceFrame>
      <span className="os-presence-label" title={label}>
        {label}
      </span>
      <button
        className={`os-presence-btn is-live pstate-${activity}${isMicEnabled ? "" : " is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="os-presence-end" onClick={onEnd} title="End call">
        <PhoneOff size={13} />
      </button>
    </PresenceFrame>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

export function ReturnsAssistant({
  children,
}: {
  children: (presence: ReactNode) => ReactNode;
}) {
  // `joined`: the consent notice has been dismissed once — it never reappears
  // for a reconnect. `sessionKey` mints a fresh `PipecatAppBase` (and so a fresh
  // `PipecatClient`) for every call; `live` is whether one is currently mounted.
  const [joined, setJoined] = useState(false);
  const [live, setLive] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);

  const begin = useCallback(() => {
    setJoined(true);
    setSessionKey((k) => k + 1);
    setLive(true);
  }, []);

  if (!live) {
    return (
      <>
        <DemoGate
          open={!joined}
          title="Returns Assistant"
          blurb="Call a retailer about a return — say what went wrong with your order and watch the case move on screen."
          accent={PRESENCE.listening}
          onJoin={begin}
        />
        <AmbientPresence palette={PRESENCE} />
        {children(<BeginControl connecting={false} error="" onBegin={begin} />)}
      </>
    );
  }

  return (
    <CallSession key={sessionKey} onEnded={() => setLive(false)}>
      {children}
    </CallSession>
  );
}

/**
 * Mints the session and owns the client for one call. `PipecatAppBase` builds
 * the `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` — with its own `BotAudioOutput` — as soon as the
 * client exists.
 */
function CallSession({
  children,
  onEnded,
}: {
  children: (presence: ReactNode) => ReactNode;
  onEnded: () => void;
}) {
  // No pipeline override: this agent's voice and language are declared on its
  // brain (backend/brain.py), which is the only place they belong.
  //
  // Memoized: this is a dependency of PipecatAppBase's connect-on-mount effect,
  // so an unmemoized object literal would re-fire that effect (and re-start the
  // call) on every render.
  const params = useMemo(() => connectRequest({ surface: "orders-web" }), []);

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      connectOnMount
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect }) => (
        <CallBridge error={error ?? null} onRetry={handleConnect} onEnded={onEnded}>
          {children}
        </CallBridge>
      )}
    </PipecatAppBase>
  );
}

/** The ring, the presence control, and the two bridges to the store. */
function CallBridge({
  error,
  onRetry,
  onEnded,
  children,
}: {
  error: string | null;
  onRetry?: () => void | Promise<void>;
  onEnded: () => void;
  children: (presence: ReactNode) => ReactNode;
}) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected: isLive } = usePipecatConnectionState();
  const { handleUiCommand, registerAgentSend } = useOrders();
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");

  // Screen ← assistant. The brain's `session.dispatch(HighlightItem(...))`
  // lands here as `{ command: "highlight_item", payload: {...} }`.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) =>
        handleUiCommand(command, (payload ?? {}) as Record<string, unknown>),
      [handleUiCommand],
    ),
  );

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("idle"), []));

  // Register the store's assistant-send channel once the call is live, so the
  // return form can push the captured photo + submission back to the bot.
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((type, data) => client.sendClientMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Dev-only: expose the live client for driving the flow without a mic.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __returnsExpert?: unknown }).__returnsExpert = client;
    return () => {
      delete (window as unknown as { __returnsExpert?: unknown }).__returnsExpert;
    };
  }, [client]);

  const hangUp = async () => {
    await client?.disconnect();
    onEnded();
  };

  const connecting = !isLive && !error && transportState !== "error";
  const presence = isLive ? (
    <LiveControls activity={activity} onEnd={hangUp} />
  ) : (
    <BeginControl
      connecting={connecting}
      error={error || (transportState === "error" ? "Something went wrong." : "")}
      onBegin={() => onRetry?.()}
    />
  );

  return (
    <>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
      {children(presence)}
    </>
  );
}

const PRESENCE_CSS = `
.os-presence {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.os-presence-label {
  font-size: 12px;
  font-weight: 700;
  color: #6b7280;
  text-align: right;
  min-width: 62px;
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.os-presence-label.is-error { color: #dc2626; }
.os-presence-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1.5px solid ${BRAND};
  background: ${BRAND};
  color: white;
  cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
}
.os-presence-btn:hover { transform: scale(1.05); }
.os-presence-btn:active { transform: scale(.97); }
.os-presence-btn.is-connecting {
  background: transparent;
  color: ${BRAND};
  cursor: default;
}
.os-presence-btn.is-connecting:hover { transform: none; }
.os-presence-btn.is-live { box-shadow: 0 0 0 4px rgba(15,118,110,.14); }
.os-presence-btn.is-live.pstate-thinking {
  background: #22d3ee;
  border-color: #22d3ee;
  box-shadow: 0 0 0 4px rgba(34,211,238,.24);
}
.os-presence-btn.is-live.pstate-speaking { box-shadow: 0 0 0 5px rgba(15,118,110,.3); }
.os-presence-btn.is-muted {
  background: white;
  border-color: #d1d5db;
  color: #6b7280;
  box-shadow: none;
}
.os-presence-end {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  transition: color .15s ease, background .15s ease;
}
.os-presence-end:hover { color: #dc2626; background: #f3f4f6; }
.os-spin { animation: os-presence-spin .9s linear infinite; }
@keyframes os-presence-spin { to { transform: rotate(360deg); } }

/* Phone: the ring already carries status, so the label yields space first. */
@media (max-width: 640px) {
  .os-presence { gap: 6px; }
  .os-presence-label {
    font-size: 11.5px;
    min-width: 0;
    max-width: 108px;
  }
  .os-presence-btn { width: 34px; height: 34px; }
}
@media (prefers-reduced-motion: reduce) {
  .os-spin { animation: none; }
  .os-presence-btn { transition: none; }
}
`;
