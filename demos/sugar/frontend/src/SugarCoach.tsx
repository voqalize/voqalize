/**
 * The Sugar Coach call session — the live voice leg of the demo.
 *
 * Unlike the launcher-style widgets, this demo's call IS the UX: the patient taps
 * Join on the check-in notification, and this component mounts, connects, and
 * renders the slim in-call bar pinned to the top of the app screen. Hanging up
 * ends the phase (→ ended screen).
 *
 * Presence is ambient, not docked: the shared {@link AmbientPresence} ring from
 * `@voqalize/client-react` glows around the whole screen and carries the coach's
 * state (listening / thinking / speaking) peripherally, so the bar itself is left
 * with only the identity bits — the coach's name, the state label + call timer,
 * and the end-call button.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC transport,
 * mic control, bot-state — is the public SDK's {@link useVoqalSession}; this file
 * is just the in-call bar chrome plus two bridges that tie the call to the screen:
 *   - the agent's `ui_command` server-messages replay onto the shared sugar store,
 *     so the coach drives the screen;
 *   - a compact `{ screen: snapshot() }` snapshot is echoed back to the agent
 *     (`state_sync`) on connect and after every change — so the coach always
 *     knows what's logged, including taps the patient makes by hand.
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key.
 */

import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { PipecatClientProvider } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
} from "@voqalize/client-react";
import { config } from "./config";
import { COACH_NAME } from "./data";
import { useSugar } from "./store";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const SUGAR = config;

const GREEN = "#0E7A5F";
const RED = "#D6453D";
const AMBER = "#C97F1E";

// Sugar's reading of the shared presence ring: the app's own evergreen while the
// coach is listening or talking, warming to the care-plan amber the moment she's
// working something out — the one state a patient reads out of the corner of the
// eye. Off the call it drops to a barely-there oat seam, the app's own line colour.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: GREEN,
  listening: GREEN,
  thinking: AMBER,
  speaking: GREEN,
  offline: "#D6D2C6",
};

// The bar's static state dot — the ring carries the motion, this just names it.
const STATE_DOT: Record<VoqalBotState, string> = {
  idle: "#7BD9BE",
  listening: "#7BD9BE",
  thinking: "#F2C063",
  speaking: "#2FA875",
};

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Listening",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};

function CallTimer() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSec((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  const mm = String(Math.floor(sec / 60)).padStart(1, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return <>{mm}:{ss}</>;
}

/**
 * The in-call bar pinned to the top of the app screen while the call is live,
 * plus all the invisible bridges. Mounted by pages.tsx when phase === 'call';
 * connects on mount, and hanging up moves the demo to the ended screen.
 */
export function SugarCallSession() {
  const { endCall, handleUiCommand, registerAgentSend, rev, snapshot, brainPayload } = useSugar();
  const startedRef = useRef(false);

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: SUGAR.apiBase,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the bar's error state.
    publishableKey: SUGAR.publishableKey ?? "",
    agentId: SUGAR.agentId,
    // No pipeline override. The patient's LanguageToggle choice rides the payload
    // below (`language`), and the brain applies it with one configure_language
    // call at session start — so the recognizer and the TTS voice can't drift
    // apart, which is what happens when the browser sets one half of the pair.
    // The scenario's PATIENT CONTEXT rides the payload → the brain's init_payload.
    payload: { surface: "sugar-web", ...(brainPayload() as Record<string, unknown>) },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === "ui_command") handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  // The call IS the UX: connect on mount, once.
  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      connect();
    }
  }, [connect]);

  // Register the store's agent-send channel and mic once a session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Debounced snapshot push: on connect and after every change (rev), so the
  // coach stays in sync with taps the patient makes by hand too. The sugar brain
  // reads `data.screen` (see SugarBrain._ingest_state).
  useEffect(() => {
    if (connectionState !== "connected") return;
    const t = setTimeout(() => sendMessage("state_sync", { screen: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, rev]);

  // Dev-only: drive the flow without a mic.
  //   window.__sugar.ui({action:'log_meal', meal_type:'dinner', time_label:'8 PM', items:[...], total_calories: 500})
  //   window.__sugar.sendText('I had two rotis and dal for dinner')
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __sugar?: unknown }).__sugar = {
      client,
      ui: handleUiCommand,
      sendText: (t: string) => client.sendText(t),
    };
    return () => {
      delete (window as unknown as { __sugar?: unknown }).__sugar;
    };
  }, [client, handleUiCommand]);

  const isLive = connectionState === "connected";
  const isError = connectionState === "error";

  const hangUp = async () => {
    await disconnect();
    endCall();
  };

  // The ring is `position: fixed` and self-positioning — it rides alongside the
  // bar in the tree, but paints around the whole screen.
  const bar = (inner: ReactNode) => (
    <>
      <AmbientPresence botState={botState} connectionState={connectionState} palette={PRESENCE} />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 14px",
          background: "linear-gradient(135deg, #0F2B23 0%, #123A2E 100%)",
          color: "#fff",
          borderRadius: 16,
          boxShadow: "0 8px 24px rgba(10,40,30,.35)",
        }}
      >
        {inner}
      </div>
    </>
  );

  if (isError) {
    return bar(
      <>
        <span style={{ fontSize: 12.5, flex: 1, lineHeight: 1.35 }}>{error || "Call failed."}</span>
        <button onClick={connect} style={pillBtn(GREEN)}>Retry</button>
        <button onClick={hangUp} style={pillBtn(RED)}>✕</button>
      </>,
    );
  }

  if (!client || !isLive) {
    return bar(
      <>
        <span className="sugar-pulse" aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#7BD9BE" }} />
        <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>{COACH_NAME}</span>
        <span style={{ fontSize: 12, opacity: 0.85 }}>Connecting…</span>
        <button onClick={hangUp} style={pillBtn(RED)} title="End call">✕</button>
      </>,
    );
  }

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {bar(
        <>
          <span
            aria-hidden
            style={{ flex: "none", width: 9, height: 9, borderRadius: "50%", background: STATE_DOT[botState] }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 800, lineHeight: 1.15 }}>{COACH_NAME}</div>
            <div style={{ fontSize: "var(--sugar-mini)", opacity: 0.8 }}>
              {STATE_LABEL[botState]} · <CallTimer />
            </div>
          </div>
          <button onClick={hangUp} style={{ ...pillBtn(RED), width: 34, height: 34, borderRadius: "50%", fontSize: 13 }} title="End call">
            ⏻
          </button>
        </>,
      )}
    </PipecatClientProvider>
  );
}

function pillBtn(bg: string): CSSProperties {
  return {
    background: bg,
    color: "#fff",
    border: "none",
    borderRadius: 10,
    padding: "6px 12px",
    fontWeight: 700,
    fontSize: 12,
    cursor: "pointer",
  };
}
