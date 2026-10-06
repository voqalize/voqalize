/**
 * The Petwell Appointment Desk's voice layer — ambient presence, not a docked widget.
 *
 * The booking page is the star: the assistant announces itself as a glow around
 * the whole viewport ({@link AmbientPresence}) plus one small control inside
 * Petwell's own top bar. Status is carried by the ring's hue and motion.
 *
 * Everything here is stock pipecat: `PipecatAppBase` does the two-step connect
 * and owns the client; the brain's `session.dispatch(...)` arrives on
 * `RTVIEvent.UICommand` as `{ command, payload }`. The only Voqalize-specific
 * code is the connect request and the one line over its answer, in
 * `src/config.ts`.
 *
 * Two bridges tie the call to the booking store:
 *   - every `ui-command` replays onto the store, so the assistant drives the screen;
 *   - a client→bot channel is registered on the store, so the owner's taps and
 *     the final Send Request reach the brain as typed app events.
 *
 * A call that ends fully unmounts its `PipecatAppBase`; the next tap mints a
 * fresh client on a fresh session.
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
import { useBooking } from "./store";

const BRAND = "#5c42bf";

// Petwell's own purple, so the ring reads as the hospital's desk. While it reasons
// the ring lifts to a pale lavender — a shift in brightness, so "thinking" reads at
// the edge of vision. Offline is the page's own tint.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: BRAND,
  listening: BRAND,
  thinking: "#a78bfa",
  speaking: BRAND,
  offline: "#e4defa",
};

const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── The one voice affordance, dropped into the booking page's top bar ────────────

function PresenceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="pw-presence">
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
  const label = connecting ? "Connecting…" : error || "Book by voice";
  return (
    <PresenceFrame>
      <span className={`pw-presence-label${error && !connecting ? " is-error" : ""}`} title={label}>
        {label}
      </span>
      {connecting ? (
        <button className="pw-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="pw-spin" />
        </button>
      ) : (
        <button
          className="pw-presence-btn"
          onClick={onBegin}
          title={error ? "Try again" : "Talk to the Appointment Desk"}
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
      <span className="pw-presence-label" title={label}>
        {label}
      </span>
      <button
        className={`pw-presence-btn is-live pstate-${activity}${isMicEnabled ? "" : " is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="pw-presence-end" onClick={onEnd} title="End call">
        <PhoneOff size={13} />
      </button>
    </PresenceFrame>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

export function PetwellDesk({
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
          title="Petwell Appointment Desk"
          blurb="Book a vet visit for your pet by voice — say what you need and watch the booking fill in on screen."
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
  const params = useMemo(() => connectRequest({ surface: "petwell-web" }), []);

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
  const { handleUiCommand, registerAgentSend } = useBooking();
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
  // owner's taps and Send Request reach the bot.
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((event, payload) => client.sendUIEvent(event, payload));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Dev-only: expose the live client for driving the flow without a mic.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __petwellDesk?: unknown }).__petwellDesk = client;
    return () => {
      delete (window as unknown as { __petwellDesk?: unknown }).__petwellDesk;
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
.pw-presence {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.pw-presence-label {
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
.pw-presence-label.is-error { color: #dc2626; }
.pw-presence-btn {
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
.pw-presence-btn:hover { transform: scale(1.05); }
.pw-presence-btn:active { transform: scale(.97); }
.pw-presence-btn.is-connecting {
  background: transparent;
  color: ${BRAND};
  cursor: default;
}
.pw-presence-btn.is-connecting:hover { transform: none; }
.pw-presence-btn.is-live { box-shadow: 0 0 0 4px rgba(92,66,191,.14); }
.pw-presence-btn.is-live.pstate-thinking {
  background: #a78bfa;
  border-color: #a78bfa;
  box-shadow: 0 0 0 4px rgba(167,139,250,.24);
}
.pw-presence-btn.is-live.pstate-speaking { box-shadow: 0 0 0 5px rgba(92,66,191,.3); }
.pw-presence-btn.is-muted {
  background: white;
  border-color: #d1d5db;
  color: #6b7280;
  box-shadow: none;
}
.pw-presence-end {
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
.pw-presence-end:hover { color: #dc2626; background: #f3f4f6; }
.pw-spin { animation: pw-presence-spin .9s linear infinite; }
@keyframes pw-presence-spin { to { transform: rotate(360deg); } }

/* Phone: the ring already carries status, so the label yields space first. */
@media (max-width: 640px) {
  .pw-presence { gap: 6px; }
  .pw-presence-label {
    font-size: 11.5px;
    min-width: 0;
    max-width: 108px;
  }
  .pw-presence-btn { width: 34px; height: 34px; }
}
@media (prefers-reduced-motion: reduce) {
  .pw-spin { animation: none; }
  .pw-presence-btn { transition: none; }
}
`;
