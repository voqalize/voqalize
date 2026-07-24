/**
 * "Ada" — the Flowforge copilot, a floating voice widget.
 *
 * Same embedding surface every Voqalize demo uses: {@link useVoqalSession} from
 * `@voqalize/client-react`, minted with a publishable (`pk_`) key. This file is
 * widget chrome plus the two bridges that make the copilot an author:
 *   - the brain's `ui_command` server-messages replay onto the shared Flowforge
 *     store (add a block, insert a branch, run the tests, publish live…);
 *   - a compact workspace snapshot is echoed back (`state_sync`) on connect and
 *     after every change, so the copilot always knows the open workflow, its
 *     blocks, tests, and gaps — including edits the admin makes by hand.
 *
 * Mounted once inside `ForgeProvider`, so the call survives navigating between the
 * list and the editor. The signed-in admin rides the session payload so Ada greets
 * them by name.
 */

import { useCallback, useEffect, useState } from "react";
import { PipecatClientProvider, usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import { BotAudioOutput, CircularWaveform, UserAudioControl } from "@pipecat-ai/voice-ui-kit";
import { useVoqalSession, type VoqalBotState } from "@voqalize/client-react";
import { useForge } from "./store";
import { ADMIN } from "./data";
import { config } from "./config";

const FORGE = config;

// "Studio" brand: violet build-surface + cyan signal.
const VIOLET = "#7C3AED";
const VIOLET_L = "#A78BFA";
const VIOLET_D = "#4C1D95";
const INK = "#0B1020";

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Listening…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
};

function BotVisualizer({ botState }: { botState: VoqalBotState }) {
  const botTrack = usePipecatClientMediaTrack("audio", "bot");
  return (
    <CircularWaveform
      audioTrack={botTrack}
      isThinking={botState === "thinking"}
      size={120}
      color1={VIOLET}
      color2={VIOLET_L}
    />
  );
}

export function ForgeAssistant() {
  const [open, setOpen] = useState(false);
  const { handleUiCommand, registerAgentSend, snapshot, model } = useForge();

  const session = useVoqalSession({
    apiBase: FORGE.apiBase,
    tenantSlug: FORGE.tenantSlug,
    publishableKey: FORGE.publishableKey ?? "",
    agentId: FORGE.agentId,
    pipeline: FORGE.pipeline,
    payload: {
      surface: "forge-web",
      admin: { name: ADMIN.name, role: ADMIN.role },
    },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === "ui_command") handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } = session;

  // Register the store's agent-send channel and mic once a session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Debounced snapshot push: on connect and after every change (rev), so Ada stays
  // in sync with edits the admin makes by hand too.
  useEffect(() => {
    if (connectionState !== "connected") return;
    const t = setTimeout(() => sendMessage("state_sync", { workspace: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, model.rev]);

  // Dev-only: drive the flow from the console without a mic.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __forgeClient?: unknown }).__forgeClient = client;
    return () => {
      delete (window as unknown as { __forgeClient?: unknown }).__forgeClient;
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
          background: `linear-gradient(135deg, ${VIOLET_L} 0%, ${VIOLET} 100%)`,
          color: "#F5F3FF",
          border: "none",
          borderRadius: 28,
          padding: "12px 18px",
          fontWeight: 700,
          fontSize: 14,
          fontFamily: "system-ui, sans-serif",
          cursor: "pointer",
          boxShadow: "0 6px 24px rgba(124,58,237,.45)",
        }}
      >
        <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#67E8F9" }} />
        Build with Ada
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
        background: INK,
        borderRadius: 18,
        boxShadow: "0 16px 44px rgba(0,0,0,.55)",
        border: "1px solid #2A2350",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          background: `linear-gradient(135deg, ${VIOLET} 0%, ${VIOLET_D} 100%)`,
          color: "#F5F3FF",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTopLeftRadius: 18,
          borderTopRightRadius: 18,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 14 }}>
          <span aria-hidden>✦</span> Ada · Workflow Copilot
        </div>
        <button
          onClick={hangUp}
          title="Close"
          style={{
            background: "rgba(255,255,255,.18)",
            border: "none",
            color: "#F5F3FF",
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

      <div style={{ padding: "18px 16px 16px", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {isError ? (
          <>
            <div style={{ fontSize: 13, color: "#C4B5FD", textAlign: "center", lineHeight: 1.4 }}>
              {error || "Something went wrong."}
            </div>
            <button
              onClick={connect}
              style={{
                background: VIOLET,
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
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "#C4B5FD", height: 16 }}>
                  {STATE_LABEL[botState]}
                </div>
                <div style={{ fontSize: 11, color: "#8B84B0", textAlign: "center", lineHeight: 1.4 }}>
                  Assembling and testing workflows alongside you.
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
                      background: VIOLET_D,
                      border: "none",
                      cursor: "pointer",
                      color: "#F5F3FF",
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
                <CircularWaveform isThinking size={120} color1={VIOLET} color2={VIOLET_L} />
                <div style={{ fontSize: 12.5, color: "#8B84B0" }}>Connecting…</div>
              </>
            )}
          </PipecatClientProvider>
        ) : (
          <>
            <CircularWaveform isThinking size={120} color1={VIOLET} color2={VIOLET_L} />
            <div style={{ fontSize: 12.5, color: "#8B84B0" }}>Connecting…</div>
          </>
        )}
      </div>
    </div>
  );
}
