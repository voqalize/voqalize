/**
 * The "Returns Assistant" floating voice widget.
 *
 * A bottom-right launcher that opens an embedded voice panel. The whole session
 * lifecycle — mint against the control plane, WebRTC transport, mic control,
 * bot-state — is the public SDK's {@link useVoqalSession}; this file is just the
 * widget chrome plus two bridges that tie the call to the on-screen store:
 *   - the agent's `ui_command` server-messages replay onto the shared orders
 *     store, so the agent drives the shopper's screen;
 *   - a client→bot channel is registered on the store so the return form can push
 *     the captured photo (`photo_upload`) and the final submission
 *     (`return_submitted`) back to the bot.
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key. Mounted
 * once inside the `OrdersProvider`, so the call survives page changes.
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
import { useOrders } from "./store";
import { DEMOS } from "../config";

// Tenant + agent + pk resolve per-environment from the shared demos config
// (src/config.ts), driven by Vite env vars.
const SUPPORT = DEMOS.support;

const BRAND = "#0f766e";
const BRAND_DARK = "#134e4a";

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
      color1={BRAND}
      color2="#22d3ee"
    />
  );
}

// ── Widget ────────────────────────────────────────────────────────────────────
export function ReturnsAssistant() {
  const [open, setOpen] = useState(false);
  const { handleUiCommand, registerAgentSend } = useOrders();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: SUPPORT.apiBase,
    tenantSlug: SUPPORT.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the widget's error state.
    publishableKey: SUPPORT.publishableKey ?? "",
    agentId: SUPPORT.agentId,
    // STT/TTS come from the manifest (via config), so the pipeline is declared once.
    pipeline: SUPPORT.pipeline,
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
        className="os-assistant-launcher"
        onClick={openAndConnect}
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 50,
          display: "flex",
          alignItems: "center",
          gap: 9,
          background: `linear-gradient(135deg, ${BRAND} 0%, ${BRAND_DARK} 100%)`,
          color: "white",
          border: "none",
          borderRadius: 28,
          padding: "12px 18px",
          fontWeight: 700,
          fontSize: 14,
          cursor: "pointer",
          boxShadow: "0 6px 20px rgba(15,118,110,.45)",
        }}
      >
        <span style={{ fontSize: 18 }}>↩️</span>
        Returns Assistant
      </button>
    );
  }

  return (
    <div
      className="os-assistant-panel"
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 50,
        width: 300,
        maxWidth: "calc(100vw - 32px)",
        background: "white",
        borderRadius: 18,
        boxShadow: "0 12px 40px rgba(0,0,0,.25)",
        overflow: "visible",
        border: "1px solid #e5e7eb",
      }}
    >
      <div style={{ background: `linear-gradient(135deg, ${BRAND} 0%, ${BRAND_DARK} 100%)`, color: "white", padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", borderTopLeftRadius: 18, borderTopRightRadius: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 14 }}>
          <span>↩️</span> Returns Assistant
        </div>
        <button onClick={hangUp} title="Close" style={{ background: "rgba(255,255,255,.2)", border: "none", color: "white", borderRadius: 8, width: 24, height: 24, cursor: "pointer", fontSize: 14 }}>
          ✕
        </button>
      </div>

      <div style={{ padding: "18px 16px 16px", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {isError ? (
          <>
            <div style={{ fontSize: 13, color: "#dc2626", textAlign: "center", lineHeight: 1.4 }}>{error || "Something went wrong."}</div>
            <button onClick={connect} style={{ background: BRAND, color: "white", border: "none", borderRadius: 10, padding: "8px 18px", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
              Try again
            </button>
          </>
        ) : client ? (
          <PipecatClientProvider client={client}>
            <BotAudioOutput />
            {isLive ? (
              <>
                <BotVisualizer botState={botState} />
                <div style={{ fontSize: 12.5, fontWeight: 600, color: BRAND, height: 16 }}>{STATE_LABEL[botState]}</div>
                <div style={{ fontSize: 11, color: "#9ca3af", textAlign: "center", lineHeight: 1.4 }}>
                  Tell me what's wrong with an order — I'll help you return it.
                </div>

                <div
                  className="os-assistant-controls"
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 6, width: "100%" }}
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
                    style={{ display: "flex", alignItems: "center", gap: 6, height: 40, padding: "0 14px", borderRadius: 10, background: "#dc2626", border: "none", cursor: "pointer", color: "white", fontSize: 13, fontWeight: 700 }}
                  >
                    ✕ End
                  </button>
                </div>
              </>
            ) : (
              <>
                <CircularWaveform isThinking size={120} color1={BRAND} color2="#22d3ee" />
                <div style={{ fontSize: 12.5, color: "#6b7280" }}>Connecting…</div>
              </>
            )}
          </PipecatClientProvider>
        ) : (
          <>
            <CircularWaveform isThinking size={120} color1={BRAND} color2="#22d3ee" />
            <div style={{ fontSize: 12.5, color: "#6b7280" }}>Connecting…</div>
          </>
        )}
      </div>
    </div>
  );
}
