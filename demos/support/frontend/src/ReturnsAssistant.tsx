/**
 * The Returns Assistant's voice layer — ambient presence, not a docked widget.
 *
 * The storefront is the star: the assistant announces itself as a glow around the
 * whole viewport (the shared `AmbientPresence` from `@voqalize/client-react`) plus
 * one small control that lives *inside* Voqal Mobile's own top bar, so it reads as
 * product chrome rather than a bolted-on chat box. Status is carried by the ring's
 * hue and motion; there is no panel to read.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC transport,
 * mic control, bot-state — is the public SDK's {@link useVoqalSession}; this file
 * is that hook plus two bridges that tie the call to the on-screen store:
 *   - the agent's `ui_command` server-messages replay onto the shared orders
 *     store, so the agent drives the shopper's screen;
 *   - a client→bot channel is registered on the store so the return form can push
 *     the captured photo (`photo_upload`) and the final submission
 *     (`return_submitted`) back to the bot.
 *
 * The storefront is rendered through a `children` render-prop (like the Flowforge
 * demo) so the app keeps ownership of its own chrome and simply drops the presence
 * control into its header. This is exactly the surface an external developer
 * embeds: `useVoqalSession` from `@voqalize/client-react`, driven by a publishable
 * (`pk_`) key. Mounted once inside the `OrdersProvider`, so the call survives page
 * changes.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { PipecatClientProvider, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
} from "@voqalize/client-react";
import { DemoGate } from "@voqalize/demo-kit";
import { useOrders } from "./store";
import { config } from "./config";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const SUPPORT = config;

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

const STATE_LABEL: Record<VoqalBotState, string> = {
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
  onBegin: () => void;
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
function LiveControls({ botState, onEnd }: { botState: VoqalBotState; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const label = isMicEnabled ? STATE_LABEL[botState] : "Muted";
  return (
    <PresenceFrame>
      <span className="os-presence-label" title={label}>
        {label}
      </span>
      <button
        className={`os-presence-btn is-live pstate-${botState}${isMicEnabled ? "" : " is-muted"}`}
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
  const { handleUiCommand, registerAgentSend } = useOrders();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: SUPPORT.apiBase,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the presence control's label.
    publishableKey: SUPPORT.publishableKey ?? "",
    agentId: SUPPORT.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    payload: { surface: "orders-web" },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === "ui_command") handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  // Register the store's agent-send channel and mic once a session is live, so
  // the return form can push the captured photo + submission back to the bot.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Dev-only: expose the live client for driving the flow without a mic in tests.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __returnsExpert?: unknown }).__returnsExpert = client;
    return () => {
      delete (window as unknown as { __returnsExpert?: unknown }).__returnsExpert;
    };
  }, [client]);

  const isLive = connectionState === "connected";

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const presence = isLive ? (
    <LiveControls botState={botState} onEnd={disconnect} />
  ) : (
    <BeginControl
      connecting={connectionState === "connecting"}
      error={connectionState === "error" ? error || "Something went wrong." : ""}
      onBegin={connect}
    />
  );

  const shell = (
    <>
      <DemoGate
        open={!joined}
        title="Returns Assistant"
        blurb="Call a retailer about a return — say what went wrong with your order and watch the case move on screen."
        accent={PRESENCE.listening}
        busy={connectionState === "connecting"}
        error={connectionState === "error" ? error || "Something went wrong." : null}
        onJoin={async () => {
          await connect();
          setJoined(true);
        }}
      />
      <AmbientPresence botState={botState} connectionState={connectionState} palette={PRESENCE} />
      {children(presence)}
    </>
  );

  if (!client) return <>{shell}</>;

  return (
    <PipecatClientProvider client={client}>
      {/* Headless — plays the bot's audio track; no voice-ui-kit stylesheet needed. */}
      <BotAudioOutput />
      {shell}
    </PipecatClientProvider>
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
