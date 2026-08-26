/**
 * The OrderDesk call session — the live voice leg of the demo.
 *
 * The call *is* the UX: the pharmacist taps Join on the 9 AM push, this component
 * mounts, connects, and renders the slim in-call bar pinned to the top of the
 * order screen. Hanging up ends the phase (→ ended screen).
 *
 * Presence is ambient: the shared {@link AmbientPresence} ring from
 * `@voqalize/demo-kit` glows around the whole screen and carries the agent's
 * state (listening / thinking / speaking) peripherally — which matters more here
 * than in most demos, because the pharmacist is *reading the cart*, not watching
 * the agent. The bar keeps only the identity bits: who's on the line, the state
 * label + timer, and the end-call button.
 *
 * **This is exactly the surface an external developer embeds, and it is almost
 * entirely pipecat's.** Voice-ui-kit's `PipecatAppBase` does pipecat's whole
 * two-step connect (`startBot` against the control plane, then `connect` the
 * transport) and owns the client's lifecycle — including its own
 * `BotAudioOutput` — so this file is the two bridges that tie the call to the
 * screen, and nothing else:
 *   - every `ui-command` (`RTVIEvent.UICommand`, `{ command, payload }`) replays
 *     onto the store's one reducer, typed against `actions.gen.ts`, so line
 *     items resolve on screen;
 *   - a debounced `state_sync` echoes the store's `OrderSnapshot` back, so the
 *     agent's grounding always shows the authoritative cart — including the pills,
 *     quantities and deletes the pharmacist tapped by hand.
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { usePipecatClient, usePipecatClientTransportState, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import { AmbientPresence, type AmbientPresenceActivity, type AmbientPresencePalette } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "./config";
import { useOrderDesk } from "./store";
import { BODY, RED, SAFFRON } from "./theme";

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

const STATE_DOT: Record<AmbientPresenceActivity, string> = {
  idle: "#7FB2F2",
  listening: "#7FB2F2",
  thinking: "#F5B759",
  speaking: "#4E9BEF",
};

const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
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
 * Mints the session and owns the client. Mounted by pages.tsx when
 * phase === 'call'; connects on mount, and hanging up moves the demo to the
 * ended screen.
 */
export function OrderDeskCallSession() {
  const { brainPayload } = useOrderDesk();

  // No pipeline override: this agent's voice and language are declared on
  // its brain (backend/brain.py), which is the only place they belong. The
  // scenario's PHARMACY CONTEXT rides `init` → the brain's `session.init`.
  //
  // Memoized: this is a dependency of PipecatAppBase's connect-on-mount
  // effect, so an unmemoized object literal would re-fire that effect (and
  // re-mint a session) on every render.
  const params = useMemo(
    () => connectRequest({ surface: "orderdesk-web", ...(brainPayload() as Record<string, unknown>) }),
    [brainPayload],
  );

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      connectOnMount
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect }) => <CallBar error={error ?? null} onRetry={handleConnect} />}
    </PipecatAppBase>
  );
}

/** The in-call bar, the presence ring, and the two bridges to the store. */
function CallBar({ error, onRetry }: { error: string | null; onRetry?: () => void | Promise<void> }) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected: isLive } = usePipecatConnectionState();
  const { endCall, handleUiCommand, registerAgentSend, rev, snapshot } = useOrderDesk();
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");

  // Screen ← desk. The brain's `session.dispatch(UpsertItems(...))` lands here as
  // `{ command: "upsert_items", payload: {...} }`. Subscribing to the event
  // rather than registering six `useUICommandHandler`s: the store is one
  // reducer, and an unknown command is a no-op there by design.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => handleUiCommand(command, payload),
      [handleUiCommand],
    ),
  );

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("idle"), []));

  // Register the store's agent-send channel once the call is live (the search
  // bar's `catalog_search` and a row's `list_variants` ride it).
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((type, data) => client.sendClientMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Debounced snapshot push: on connect and after every change (rev), so the desk
  // stays in sync with taps the pharmacist makes by hand too. DESIGN §3: the brain
  // reads this snapshot as the authoritative cart.
  useEffect(() => {
    if (!isLive || !client) return;
    const t = setTimeout(() => client.sendClientMessage("state_sync", { screen: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, client, rev]);

  // Dev-only: drive the flow without a mic.
  //   window.__orderdesk.ui('upsert_items', {items:[{id:'li1', spoken_text:'volini spray', …}]})
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

  const hangUp = async () => {
    await client?.disconnect();
    endCall();
  };

  // The ring is `position: fixed` and self-positioning — it rides alongside the
  // bar in the tree, but paints around the whole screen.
  const bar = (inner: ReactNode) => (
    <>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
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

  if (error || transportState === "error") {
    return bar(
      <>
        <span style={{ fontSize: 12.5, flex: 1, lineHeight: 1.35 }}>{error || "Call failed."}</span>
        <button onClick={onRetry} style={pillBtn(SAFFRON)}>Retry</button>
        <button onClick={hangUp} style={pillBtn(RED)}>✕</button>
      </>,
    );
  }

  if (!isLive) {
    return bar(
      <>
        <span className="od-blink" aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#7FB2F2" }} />
        <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>{AGENT_NAME}</span>
        <span style={{ fontSize: 12, opacity: 0.85 }}>Connecting…</span>
        <button onClick={hangUp} style={pillBtn(RED)} title="End call">✕</button>
      </>,
    );
  }

  return bar(
    <>
      <span
        aria-hidden
        style={{ flex: "none", width: 9, height: 9, borderRadius: "50%", background: STATE_DOT[activity] }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 800, lineHeight: 1.15 }}>{AGENT_NAME}</div>
        <div style={{ fontSize: "var(--od-mini)", opacity: 0.82 }}>
          {STATE_LABEL[activity]} · <CallTimer />
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
