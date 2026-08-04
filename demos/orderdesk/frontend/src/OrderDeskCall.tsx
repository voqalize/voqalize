/**
 * The OrderDesk call session — the live voice leg of the demo.
 *
 * The call *is* the UX: the pharmacist taps Join on the 9 AM push, this component
 * mounts, connects, and renders the slim in-call bar pinned to the top of the
 * order screen. Hanging up ends the phase (→ ended screen).
 *
 * Presence is ambient: the shared {@link AmbientPresence} ring from
 * `@voqalize/client-react` glows around the whole screen and carries the agent's
 * state (listening / thinking / speaking) peripherally — which matters more here
 * than in most demos, because the pharmacist is *reading the cart*, not watching
 * the agent. The bar keeps only the identity bits: who's on the line, the state
 * label + timer, and the end-call button.
 *
 * The session lifecycle — mint against the control plane, WebRTC transport, mic,
 * bot state — is the public SDK's {@link useVoqalSession}. Everything else here is
 * the two bridges that tie the call to the screen:
 *   - {@link useUiCommand} dispatches the brain's `ui_command`s onto the store's
 *     typed handler map (`OrderDeskCommands`), so line items resolve on screen;
 *   - a debounced `state_sync` echoes the store's `OrderSnapshot` back, so the
 *     agent's grounding always shows the authoritative cart — including the pills,
 *     quantities and deletes the pharmacist tapped by hand.
 */

import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { PipecatClientProvider } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import {
  AmbientPresence,
  useUiCommand,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
} from "@voqalize/client-react";
import { config } from "./config";
import { useOrderDesk } from "./store";
import { BODY, RED, SAFFRON } from "./theme";
import type { OrderDeskCommands } from "./uiCommands";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const ORDERDESK = config;

/** Who the pharmacist thinks is on the line. */
export const AGENT_NAME = "MedSetu Order Desk";

// The ring in MedSetu's own colours: navy-blue while the desk is listening or
// talking, saffron the moment it is working something out — the one state worth
// reading out of the corner of an eye while you scan the cart.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#2F5FA8",
  listening: "#2F5FA8",
  thinking: SAFFRON,
  speaking: "#2F5FA8",
  offline: "#C6D0DE",
};

const STATE_DOT: Record<VoqalBotState, string> = {
  idle: "#7FB2F2",
  listening: "#7FB2F2",
  thinking: "#F5B759",
  speaking: "#4E9BEF",
};

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Listening",
  listening: "Listening",
  thinking: "Checking catalog…",
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
 * The in-call bar pinned to the top of the order screen while the call is live,
 * plus all the invisible bridges. Mounted by pages.tsx when phase === 'call';
 * connects on mount, and hanging up moves the demo to the ended screen.
 */
export function OrderDeskCallSession() {
  const { endCall, uiCommands, handleUiCommand, registerAgentSend, rev, snapshot, brainPayload } =
    useOrderDesk();
  const startedRef = useRef(false);

  // The entire session lifecycle in one hook.
  const session = useVoqalSession({
    apiBase: ORDERDESK.apiBase,
    tenantSlug: ORDERDESK.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the bar's error state.
    publishableKey: ORDERDESK.publishableKey ?? "",
    agentId: ORDERDESK.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    // The scenario's PHARMACY CONTEXT rides the payload → the brain's init_payload.
    payload: { surface: "orderdesk-web", ...(brainPayload() as Record<string, unknown>) },
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  // The agent drives the cart: every `ui_command` goes to the store's typed
  // handler for that action. Subscription, envelope stripping and dispatch are the
  // hook's; the store only says what each command means.
  useUiCommand<OrderDeskCommands>(client, uiCommands);

  // The call IS the UX: connect on mount, once.
  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      connect();
    }
  }, [connect]);

  // Register the store's agent-send channel (the search bar's `catalog_search`
  // rides it) and open the mic once a session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Debounced snapshot push: on connect and after every change (rev), so the desk
  // stays in sync with taps the pharmacist makes by hand too. DESIGN §3: the brain
  // reads this snapshot as the authoritative cart.
  useEffect(() => {
    if (connectionState !== "connected") return;
    const t = setTimeout(() => sendMessage("state_sync", { screen: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, rev]);

  // Dev-only: drive the flow without a mic.
  //   window.__orderdesk.ui({action:'upsert_items', items:[{id:'li1', spoken_text:'volini spray', …}]})
  //   window.__orderdesk.sendText('do volini spray aur paanch telma chalis bhej do')
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __orderdesk?: unknown }).__orderdesk = {
      client,
      ui: handleUiCommand,
      snapshot,
      sendText: (t: string) => client.sendText(t),
    };
    return () => {
      delete (window as unknown as { __orderdesk?: unknown }).__orderdesk;
    };
  }, [client, handleUiCommand, snapshot]);

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
          padding: "9px 12px",
          background: "linear-gradient(135deg, #0B1B33 0%, #17325C 100%)",
          color: "#fff",
          borderRadius: 14,
          boxShadow: "0 8px 22px rgba(11,27,51,.30)",
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
        <button onClick={connect} style={pillBtn(SAFFRON)}>Retry</button>
        <button onClick={hangUp} style={pillBtn(RED)}>✕</button>
      </>,
    );
  }

  if (!client || !isLive) {
    return bar(
      <>
        <span className="od-blink" aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#7FB2F2" }} />
        <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>{AGENT_NAME}</span>
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
            <div style={{ fontSize: 12.5, fontWeight: 800, lineHeight: 1.15 }}>{AGENT_NAME}</div>
            <div style={{ fontSize: "var(--od-mini)", opacity: 0.82 }}>
              {STATE_LABEL[botState]} · <CallTimer />
            </div>
          </div>
          <button
            onClick={hangUp}
            style={{ ...pillBtn(RED), width: 32, height: 32, borderRadius: "50%", fontSize: 13, padding: 0 }}
            title="End call"
          >
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
    borderRadius: 9,
    padding: "6px 12px",
    fontWeight: 700,
    fontSize: 12,
    fontFamily: BODY,
    cursor: "pointer",
  };
}
