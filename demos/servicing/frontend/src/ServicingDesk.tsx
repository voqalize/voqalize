/**
 * The "Servicing Desk" floating voice widget for the Meridian Servicing Console.
 *
 * A bottom-right launcher that opens an embedded voice panel. The whole session
 * lifecycle — mint against the control plane, WebRTC transport, mic control,
 * bot-state — is the public SDK's {@link useVoqalSession}; this file is just the
 * widget chrome plus two bridges that tie the call to the on-screen console:
 *   - the assistant's `ui_command` server-messages replay onto the shared
 *     servicing store, so the assistant drives the console;
 *   - a compact workspace snapshot is echoed back to the assistant (`state_sync`)
 *     on connect and after every change — so it always knows where the advisor is
 *     and what's pending, including the advisor's own edits (approvals,
 *     assignments).
 *
 * This is exactly the surface an external developer embeds: `useVoqalSession`
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key. Mounted
 * once inside the `ServicingProvider`, so the call survives screen changes. The
 * logged-in advisor is passed into the session payload so the desk greets them by
 * name.
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
// The kit ships Tailwind — without its stylesheet its components render as raw
// browser defaults. We take the *scoped* bundle (everything under `.vkui-root`)
// so the kit's preflight can't reset this demo's hand-rolled page chrome.
import "@pipecat-ai/voice-ui-kit/styles.scoped";
import { useVoqalSession, type VoqalBotState } from "@voqalize/client-react";
import { useServicing } from "./store";
import { ADVISOR } from "./data";
import { config } from "./config";

// Per-environment tenant + agent + pk from this demo's local config
// (src/config.ts), driven by Vite env vars.
const SERVICING = config;

// Teal "Blueprint" brand: deep teal anchor + signal-orange accent.
const TEAL = "#0F766E";
const TEAL_L = "#14B8A6";
const TEAL_D = "#0B524C";

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
      color1={TEAL}
      color2={TEAL_L}
    />
  );
}

// ── Widget ─────────────────────────────────────────────────────────────────────
export function ServicingDesk() {
  const [open, setOpen] = useState(false);
  const { handleUiCommand, registerAgentSend, rev, activeRef, tab, snapshot } = useServicing();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: SERVICING.apiBase,
    tenantSlug: SERVICING.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the widget's error state.
    publishableKey: SERVICING.publishableKey ?? "",
    agentId: SERVICING.agentId,
    // STT/TTS come from this demo's config, so the pipeline is declared once.
    pipeline: SERVICING.pipeline,
    // The logged-in advisor — the desk greets them by name.
    payload: {
      surface: "servicing-web",
      advisor: { name: ADVISOR.name, role: ADVISOR.role },
    },
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

  // Debounced snapshot push: on connect and after every change (rev / active ref /
  // tab), so the assistant stays in sync with edits the advisor makes by hand too.
  useEffect(() => {
    if (connectionState !== "connected") return;
    const t = setTimeout(() => sendMessage("state_sync", { workspace: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, rev, activeRef, tab]);

  // Dev-only: expose the live client for driving the flow without a mic in tests.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __servicingDesk?: unknown }).__servicingDesk = client;
    return () => {
      delete (window as unknown as { __servicingDesk?: unknown }).__servicingDesk;
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
        onClick={openAndConnect}
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 1200,
          display: "flex",
          alignItems: "center",
          gap: 9,
          background: `linear-gradient(135deg, ${TEAL_L} 0%, ${TEAL} 100%)`,
          color: "#EAF6F4",
          border: "none",
          borderRadius: 28,
          padding: "12px 18px",
          fontWeight: 700,
          fontSize: 14,
          fontFamily: "Archivo, system-ui, sans-serif",
          cursor: "pointer",
          boxShadow: "0 6px 20px rgba(15,118,110,.40)",
        }}
      >
        <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#5EEAD4" }} />
        Ask the Servicing Desk
      </button>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 1200,
        width: 300,
        maxWidth: "calc(100vw - 32px)",
        background: "#FFFFFF",
        borderRadius: 18,
        boxShadow: "0 16px 40px rgba(11,61,57,.22)",
        overflow: "visible",
        border: "1px solid #D3E0DD",
        fontFamily: "Archivo, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          background: `linear-gradient(135deg, ${TEAL} 0%, ${TEAL_D} 100%)`,
          color: "#EAF6F4",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTopLeftRadius: 18,
          borderTopRightRadius: 18,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 14 }}>
          <span aria-hidden>✦</span> Servicing Desk
        </div>
        <button
          onClick={hangUp}
          title="Close"
          style={{
            background: "rgba(255,255,255,.2)",
            border: "none",
            color: "#EAF6F4",
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
            <div style={{ fontSize: 13, color: TEAL_D, textAlign: "center", lineHeight: 1.4 }}>
              {error || "Something went wrong."}
            </div>
            <button
              onClick={connect}
              style={{
                background: TEAL,
                color: "#fff",
                border: "none",
                borderRadius: 10,
                padding: "8px 18px",
                fontWeight: 700,
                fontSize: 13,
                cursor: "pointer",
                fontFamily: "inherit",
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
                <div style={{ fontSize: 12.5, fontWeight: 600, color: TEAL_D, height: 16 }}>
                  {STATE_LABEL[botState]}
                </div>
                <div style={{ fontSize: 11, color: "#5C6F6C", textAlign: "center", lineHeight: 1.4 }}>
                  Working alongside you on your case queue.
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 12,
                    marginTop: 6,
                    width: "100%",
                  }}
                >
                  {/* `vkui-root` scopes the kit's CSS to just this control;
                      `voice-ui-kit` is the element the kit portals its device
                      dropdown into, so the menu lands inside the scope too. */}
                  <div className="vkui-root voice-ui-kit" style={{ display: "flex" }}>
                    <UserAudioControl
                      size="lg"
                      dropdownMenuLabel="Audio devices"
                      microphoneLabel="Microphone"
                      speakerLabel="Speaker"
                    />
                  </div>
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
                      background: TEAL_D,
                      border: "none",
                      cursor: "pointer",
                      color: "#EAF6F4",
                      fontSize: 13,
                      fontWeight: 700,
                      fontFamily: "inherit",
                    }}
                  >
                    ✕ End
                  </button>
                </div>
              </>
            ) : (
              <>
                <CircularWaveform isThinking size={120} color1={TEAL} color2={TEAL_L} />
                <div style={{ fontSize: 12.5, color: "#5C6F6C" }}>Connecting…</div>
              </>
            )}
          </PipecatClientProvider>
        ) : (
          <>
            <CircularWaveform isThinking size={120} color1={TEAL} color2={TEAL_L} />
            <div style={{ fontSize: 12.5, color: "#5C6F6C" }}>Connecting…</div>
          </>
        )}
      </div>
    </div>
  );
}
