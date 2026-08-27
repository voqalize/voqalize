/**
 * The Mobile Expert voice layer — ambient presence, not a docked chat widget.
 *
 * The whole session lifecycle — start against the control plane, WebRTC
 * transport, mic control, activity — is stock pipecat's `PipecatAppBase`; this
 * file owns the connect request plus one bridge that ties the call to the
 * on-screen store: the agent's `ui-command` RTVI events replay onto the shared
 * shopping store, so the agent drives the very page the shopper is looking at.
 *
 * Voice *status* lives in the shared {@link AmbientPresence} ring — a
 * full-viewport glow around the store, readable out of the corner of your eye —
 * so there is no panel, no visualizer, no status card. The only affordance is a
 * single mic control handed up to the store's own top bar through the `children`
 * render-prop (the shop owns its chrome), which begins the call and then doubles
 * as a mute toggle with a small "end" beside it. When the agent points at a spec
 * on the product page, the ring's beam layer travels from the screen edge to it.
 *
 * `DemoGate` covers the store until the shopper has read the notice and joined —
 * `PipecatAppBase` (and the microphone it opens) does not mount until then.
 */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useRTVIClientEvent, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState, type PipecatBaseChildProps } from "@pipecat-ai/voice-ui-kit";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import { AmbientPresence, DemoGate, type AmbientPresenceActivity, type AmbientPresencePalette } from "@voqalize/demo-kit";
import { useMobileShop, type Highlight } from "./store";
import { connectRequest, withRealHeaders } from "./config";

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

const ACTIVITY_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Top-bar presence control ──────────────────────────────────────────────────
// The one voice affordance in the store's chrome. Idle: click to begin.

function BeginControl({
  connecting,
  error,
  onBegin,
}: {
  connecting: boolean;
  error: string;
  onBegin: () => void;
}) {
  const label = connecting ? "Connecting…" : error || "Ask the Mobile Expert";
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
function LiveControls({ activity, onEnd }: { activity: AmbientPresenceActivity; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const label = isMicEnabled ? ACTIVITY_LABEL[activity] : "Muted";
  return (
    <div className="ms-presence">
      <span className="ms-presence-label">{label}</span>
      <button
        className={`ms-presence-btn is-live pstate-${activity} ${isMicEnabled ? "" : "is-muted"}`}
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

// ── The live call ─────────────────────────────────────────────────────────────
// Rendered inside PipecatAppBase's provider, so its hooks always see a real
// (if not yet connected) client.

interface CallSessionProps extends PipecatBaseChildProps {
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
  highlight: Highlight | null;
  children: (presence: ReactNode) => ReactNode;
}

function CallSession({ error, handleConnect, handleDisconnect, handleUiCommand, highlight, children }: CallSessionProps) {
  const { isConnected, isConnecting } = usePipecatConnectionState();
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");

  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      (data: UICommandData) => handleUiCommand(data.command, (data.payload ?? {}) as Record<string, unknown>),
      [handleUiCommand],
    ),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setActivity("idle"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("idle"), []));

  const presence = isConnected ? (
    <LiveControls activity={activity} onEnd={() => handleDisconnect?.()} />
  ) : (
    <BeginControl connecting={isConnecting} error={error ?? ""} onBegin={() => handleConnect?.()} />
  );

  return (
    <>
      <AmbientPresence
        activity={activity}
        transportState={isConnected ? "ready" : isConnecting ? "connecting" : "disconnected"}
        palette={PRESENCE}
        // The agent reaching into the page: when it calls out a spec, a beam
        // travels from the edge of the screen to that spec block.
        beam={highlight ? { id: highlight.nonce, targetId: `feature-${highlight.feature}` } : null}
      />
      {children(presence)}
    </>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────
export function MobileExpert({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { handleUiCommand, highlight } = useMobileShop();

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const params = useMemo(() => connectRequest({ surface: "mobile-web" }), []);

  return (
    <>
      <DemoGate
        open={!joined}
        title="Mobile Expert"
        blurb="Shop for a phone out loud — say what you actually need it for and watch the shortlist narrow on screen."
        accent={PRESENCE.listening}
        onJoin={() => setJoined(true)}
      />
      {joined ? (
        <PipecatAppBase
          transportType="smallwebrtc"
          connectOnMount
          noThemeProvider
          startBotParams={params}
          startBotResponseTransformer={withRealHeaders}
        >
          {(props) => (
            <CallSession {...props} handleUiCommand={handleUiCommand} highlight={highlight}>
              {children}
            </CallSession>
          )}
        </PipecatAppBase>
      ) : (
        <>
          <AmbientPresence activity="idle" transportState="disconnected" palette={PRESENCE} beam={null} />
          {children(<BeginControl connecting={false} error="" onBegin={() => setJoined(true)} />)}
        </>
      )}
      <style>{PRESENCE_STYLES}</style>
    </>
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
