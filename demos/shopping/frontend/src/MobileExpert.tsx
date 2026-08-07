/**
 * The Mobile Expert voice layer — ambient presence, not a docked chat widget.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC
 * transport, mic control, bot-state — is the public SDK's {@link useVoqalSession};
 * this file owns the session plus one bridge that ties the call to the on-screen
 * store: the agent's `ui_command` server-messages replay onto the shared shopping
 * store, so the agent drives the very page the shopper is looking at.
 *
 * Voice *status* lives in the shared {@link AmbientPresence} ring — a
 * full-viewport glow around the store, readable out of the corner of your eye —
 * so there is no panel, no visualizer, no status card. The only affordance is a
 * single mic control handed up to the store's own top bar through the `children`
 * render-prop (the shop owns its chrome), which begins the call and then doubles
 * as a mute toggle with a small "end" beside it. When the agent points at a spec
 * on the product page, the ring's beam layer travels from the screen edge to it.
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key. Mounted
 * once inside the `MobileShopProvider`, so the call survives page changes.
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
  type VoqalConnectionState,
} from "@voqalize/client-react";
import { DemoGate } from "@voqalize/demo-kit";
import { useMobileShop } from "./store";
import { config } from "./config";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const MOBILE = config;

const BRAND = "#4f46e5";

// Voqal Mobile's reading of the shared presence ring: the store's own indigo
// (#4f46e5 — the header mark, the price, every primary button) is the expert
// being present, and the cyan that used to be the visualizer's second colour is
// now the "computing" hue, so a shopper glancing at the screen can tell the
// expert is looking something up without reading a word. Offline is the store's
// hairline border grey — a seam, not a colour.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: BRAND,
  listening: BRAND,
  thinking: "#06b6d4",
  speaking: BRAND,
  offline: "#e5e7eb",
  beam: "#06b6d4",
};

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Top-bar presence control ──────────────────────────────────────────────────
// The one voice affordance in the store's chrome. Idle: click to begin.

function BeginControl({
  connectionState,
  error,
  onBegin,
}: {
  connectionState: VoqalConnectionState;
  error: string;
  onBegin: () => void;
}) {
  const connecting = connectionState === "connecting";
  const label = connecting
    ? "Connecting…"
    : connectionState === "error"
      ? error || "Connection issue"
      : "Ask the Mobile Expert";
  return (
    <div className="ms-presence">
      <span className="ms-presence-label">{label}</span>
      {connecting ? (
        <button className="ms-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="ms-spin" />
        </button>
      ) : (
        <button className="ms-presence-btn" onClick={onBegin} title="Ask the Mobile Expert">
          <Mic size={16} />
        </button>
      )}
    </div>
  );
}

// Live: the mic doubles as a mute toggle; a small secondary control ends the call.
function LiveControls({ botState, onEnd }: { botState: VoqalBotState; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const label = isMicEnabled ? STATE_LABEL[botState] : "Muted";
  return (
    <div className="ms-presence">
      <span className="ms-presence-label">{label}</span>
      <button
        className={`ms-presence-btn is-live pstate-${botState} ${isMicEnabled ? "" : "is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="ms-presence-end" onClick={onEnd} title="End">
        <PhoneOff size={13} />
      </button>
    </div>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────
export function MobileExpert({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { handleUiCommand, highlight } = useMobileShop();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: MOBILE.apiBase,
    tenantSlug: MOBILE.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the presence control's error state.
    publishableKey: MOBILE.publishableKey ?? "",
    agentId: MOBILE.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    payload: { surface: "mobile-web" },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === "ui_command") handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic } = session;

  // Turn the mic on once the session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
  }, [connectionState, enableMic]);

  // Dev-only: expose the live client for driving the flow without a mic in tests.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __mobileExpert?: unknown }).__mobileExpert = client;
    return () => {
      delete (window as unknown as { __mobileExpert?: unknown }).__mobileExpert;
    };
  }, [client]);

  const isLive = client !== null && connectionState === "connected";

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const presence = isLive ? (
    <LiveControls botState={botState} onEnd={disconnect} />
  ) : (
    <BeginControl connectionState={connectionState} error={error ?? ""} onBegin={connect} />
  );

  const shell = (
    <>
      <DemoGate
        open={!joined}
        title="Mobile Expert"
        blurb="Shop for a phone out loud — say what you actually need it for and watch the shortlist narrow on screen."
        accent={PRESENCE.listening}
        busy={connectionState === "connecting"}
        error={connectionState === "error" ? error || "Connection issue" : null}
        onJoin={async () => {
          await connect();
          setJoined(true);
        }}
      />
      <AmbientPresence
        botState={botState}
        connectionState={connectionState}
        palette={PRESENCE}
        // The agent reaching into the page: when it calls out a spec, a beam
        // travels from the edge of the screen to that spec block.
        beam={highlight ? { id: highlight.nonce, targetId: `feature-${highlight.feature}` } : null}
      />
      {children(presence)}
      <style>{PRESENCE_STYLES}</style>
    </>
  );

  if (!client) return shell;

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {shell}
    </PipecatClientProvider>
  );
}

const PRESENCE_STYLES = `
.ms-presence {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}
.ms-presence-label {
  font-size: 12.5px;
  font-weight: 600;
  color: #6b7280;
  white-space: nowrap;
}
.ms-presence-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1.5px solid ${BRAND};
  background: ${BRAND};
  color: white;
  cursor: pointer;
  flex: none;
  transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
}
.ms-presence-btn:hover { transform: scale(1.05); }
.ms-presence-btn:active { transform: scale(.97); }
.ms-presence-btn.is-connecting {
  background: white;
  color: ${BRAND};
  cursor: default;
}
.ms-presence-btn.is-connecting:hover { transform: none; }
.ms-presence-btn.is-live { box-shadow: 0 0 0 4px rgba(79,70,229,.15); }
.ms-presence-btn.is-live.pstate-thinking {
  background: #06b6d4;
  border-color: #06b6d4;
  box-shadow: 0 0 0 4px rgba(6,182,212,.22);
}
.ms-presence-btn.is-live.pstate-speaking { box-shadow: 0 0 0 5px rgba(79,70,229,.28); }
.ms-presence-btn.is-muted {
  background: white;
  border-color: #e5e7eb;
  color: #9ca3af;
  box-shadow: none;
}
.ms-presence-end {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  flex: none;
  transition: color .15s ease, background .15s ease;
}
.ms-presence-end:hover { color: #dc2626; background: #f3f4f6; }
.ms-spin { animation: ms-spin 0.9s linear infinite; }
@keyframes ms-spin { to { transform: rotate(360deg); } }

/* On a phone the store's top bar has no room for prose — the ring carries the
   status, so the control collapses to the mic itself. */
@media (max-width: 640px) {
  .ms-presence { gap: 6px; }
  .ms-presence-label { display: none; }
  .ms-presence-btn { width: 34px; height: 34px; }
}
`;
