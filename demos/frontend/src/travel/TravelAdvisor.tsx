/**
 * The "Travel Desk" floating voice widget.
 *
 * A bottom-right launcher that opens an embedded voice panel. The whole session
 * lifecycle — mint against the control plane, WebRTC transport, mic control,
 * bot-state — is the public SDK's {@link useVoqalSession}; this file is just the
 * widget chrome plus two bridges that tie the call to the on-screen portal:
 *   - the agent's `ui_command` server-messages replay onto the shared travel
 *     store, so the agent drives the portal;
 *   - a compact snapshot of the active itinerary is echoed back to the agent
 *     (`state_sync`) on connect and after every change — so the AI always knows
 *     the current state, including edits the travel agent makes by hand.
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key. Mounted
 * once inside the `TravelProvider`, so the call survives screen changes.
 */

import { useCallback, useEffect, useState } from "react";
import {
  PipecatClientProvider,
  usePipecatClientMediaTrack,
} from "@pipecat-ai/client-react";
import {
  BotAudioOutput,
  CircularWaveform,
  UserAudioControl,
} from "@pipecat-ai/voice-ui-kit";
import { useVoqalSession, type VoqalBotState } from "@voqalize/client-react";
import { useTravel } from "./store";
import { DEMOS } from "../config";

// Tenant + agent + pk resolve per-environment from the shared demos config
// (src/config.ts), driven by Vite env vars.
const TRAVEL = DEMOS.travel;

// Voqalize brand: vermilion is the live/agent colour; --action carries labels.
const VERMILION = "#E24E2A";
const ACTION = "#C2331A";
const ACTION_DARK = "#972814";

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Listening…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
};

// ── Bot audio visualizer (inside the PipecatClientProvider) ────────────────────
function BotVisualizer({ botState }: { botState: VoqalBotState }) {
  const botTrack = usePipecatClientMediaTrack("audio", "bot");
  return (
    <CircularWaveform
      audioTrack={botTrack}
      isThinking={botState === "thinking"}
      size={120}
      color1={VERMILION}
      color2="#F0703F"
    />
  );
}

// ── Widget ─────────────────────────────────────────────────────────────────────
export function TravelAdvisor() {
  const [open, setOpen] = useState(false);
  const { handleUiCommand, registerAgentSend, rev, active, snapshot } = useTravel();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: TRAVEL.apiBase,
    tenantSlug: TRAVEL.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the widget's error state.
    publishableKey: TRAVEL.publishableKey ?? "",
    agentId: TRAVEL.agentId,
    // STT/TTS come from the manifest (via config), so the pipeline is declared once.
    pipeline: TRAVEL.pipeline,
    payload: { surface: "travel-web" },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === "ui_command") handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  // Register the store's agent-send channel and mic once a session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Debounced snapshot push: on connect and after every change (rev / active id),
  // so the agent stays in sync with edits the travel agent makes by hand too.
  useEffect(() => {
    if (connectionState !== "connected") return;
    const t = setTimeout(() => sendMessage("state_sync", { itinerary: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, rev, active?.id]);

  // Dev-only: expose the live client for driving the flow without a mic in tests.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __travelDesk?: unknown }).__travelDesk = client;
    return () => {
      delete (window as unknown as { __travelDesk?: unknown }).__travelDesk;
    };
  }, [client]);

  const openAndConnect = () => {
    setOpen(true);
    if (connectionState === "idle" || connectionState === "error") connect();
  };

  const hangUp = async () => {
    await disconnect();
    setOpen(false);
  };

  const isLive = connectionState === "connected";
  const isError = connectionState === "error";

  if (!open) {
    return (
      <button
        className="tv-assistant-launcher"
        onClick={openAndConnect}
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 1200,
          display: "flex",
          alignItems: "center",
          gap: 9,
          background: `linear-gradient(135deg, ${VERMILION} 0%, ${ACTION} 100%)`,
          color: "#FAF6F0",
          border: "none",
          borderRadius: 28,
          padding: "12px 18px",
          fontWeight: 700,
          fontSize: 14,
          cursor: "pointer",
          boxShadow: "0 6px 20px rgba(226,78,42,.40)",
        }}
      >
        <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#FAF6F0" }} />
        Ask the Travel Desk
      </button>
    );
  }

  return (
    <div
      className="tv-assistant-panel"
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 1200,
        width: 300,
        maxWidth: "calc(100vw - 32px)",
        background: "#FFFDFA",
        borderRadius: 18,
        boxShadow: "0 16px 40px rgba(26,22,19,.18)",
        overflow: "visible",
        border: "1px solid #E3DACD",
      }}
    >
      <div
        style={{
          background: `linear-gradient(135deg, ${VERMILION} 0%, ${ACTION} 100%)`,
          color: "#FAF6F0",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTopLeftRadius: 18,
          borderTopRightRadius: 18,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 14 }}>
          <span aria-hidden>✈</span> Travel Desk
        </div>
        <button
          onClick={hangUp}
          title="Close"
          style={{
            background: "rgba(255,255,255,.2)",
            border: "none",
            color: "#FAF6F0",
            borderRadius: 8,
            width: 24,
            height: 24,
            cursor: "pointer",
            fontSize: 14,
          }}
        >
          ✕
        </button>
      </div>

      <div
        style={{
          padding: "18px 16px 16px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
        }}
      >
        {isError ? (
          <>
            <div style={{ fontSize: 13, color: ACTION, textAlign: "center", lineHeight: 1.4 }}>
              {error || "Something went wrong."}
            </div>
            <button
              onClick={connect}
              style={{
                background: ACTION,
                color: "#FAF6F0",
                border: "none",
                borderRadius: 10,
                padding: "8px 18px",
                fontWeight: 700,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Try again
            </button>
          </>
        ) : client ? (
          <PipecatClientProvider client={client}>
            <BotAudioOutput />
            {isLive ? (
              <>
                <BotVisualizer botState={botState} />
                <div style={{ fontSize: 12.5, fontWeight: 600, color: ACTION, height: 16 }}>
                  {STATE_LABEL[botState]}
                </div>
                <div style={{ fontSize: 11, color: "#6E665C", textAlign: "center", lineHeight: 1.4 }}>
                  Tell me which trip to plan — हिंदी या English, दोनों चलेगा.
                </div>

                <div
                  className="tv-assistant-controls"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 12,
                    marginTop: 6,
                    width: "100%",
                  }}
                >
                  <UserAudioControl
                    size="lg"
                    dropdownMenuLabel="Audio devices"
                    microphoneLabel="Microphone"
                    speakerLabel="Speaker"
                  />
                  <button
                    onClick={hangUp}
                    title="End call"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      height: 40,
                      padding: "0 14px",
                      borderRadius: 10,
                      background: ACTION_DARK,
                      border: "none",
                      cursor: "pointer",
                      color: "#FAF6F0",
                      fontSize: 13,
                      fontWeight: 700,
                    }}
                  >
                    ✕ End
                  </button>
                </div>
              </>
            ) : (
              <>
                <CircularWaveform isThinking size={120} color1={VERMILION} color2="#F0703F" />
                <div style={{ fontSize: 12.5, color: "#6E665C" }}>Connecting…</div>
              </>
            )}
          </PipecatClientProvider>
        ) : (
          <>
            <CircularWaveform isThinking size={120} color1={VERMILION} color2="#F0703F" />
            <div style={{ fontSize: 12.5, color: "#6E665C" }}>Connecting…</div>
          </>
        )}
      </div>
    </div>
  );
}
