/**
 * The Flowforge voice layer — "Ada" as ambient studio presence, not a docked
 * chat widget.
 *
 * Same embedding surface every Voqalize demo uses: {@link useVoqalSession} from
 * `@voqalize/client-react`, minted with a publishable (`pk_`) key. This layer owns
 * the whole session lifecycle and wires it to the studio through the shared store:
 *   - it mirrors the SDK's bot/connection state into the store, so the header
 *     presence control reads it (the ring itself takes the state as props, from
 *     the shared `AmbientPresence` in `@voqalize/client-react`);
 *   - the brain's `ui_command` server-messages replay onto the store (add a step,
 *     insert a decision, run the tests, publish live…);
 *   - a compact workspace snapshot is echoed back (`state_sync`) on connect and
 *     after every change, so Ada always knows the open workflow, its steps, tests,
 *     and gaps — including edits the admin makes by hand.
 *
 * The presence control lives in the app's top bar (rendered via the `children`
 * render-prop so the studio owns its own chrome): a single mic affordance that
 * begins the call, then doubles as a mute toggle, with a small "end" beside it —
 * the same shape a customer would embed. Mounted once inside `ForgeProvider`, so
 * the call survives navigating between the list and the editor.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { PipecatClientProvider, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalConnectionState,
} from "@voqalize/client-react";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import { DemoGate } from "@voqalize/demo-kit";
import { useForge, type BotState, type ConnStatus } from "./store";
import { ActivityFeed } from "./ActivityFeed";
import { ADMIN } from "./data";
import { config } from "./config";

const FORGE = config;

// The store's ConnStatus vocabulary uses `live`; the SDK hook reports
// `connected`/`disconnected`. Map the transport state onto the store's.
const CONNECTION_STATUS: Record<VoqalConnectionState, ConnStatus> = {
  idle: "idle",
  connecting: "connecting",
  // `awaiting-microphone` folds into `connecting`: the browser's own permission
  // prompt is on screen at that moment and is the thing to answer, so the chrome
  // should keep saying "wait" rather than invent a state of its own.
  "awaiting-microphone": "connecting",
  connected: "live",
  disconnected: "idle",
  error: "error",
};

// Flowforge's reading of the shared presence ring: violet is the build surface,
// cyan is the machine computing — so Ada's ring shifts to cyan the moment she's
// thinking, echoing "plain workflows backed by executable rigor". The studio is a
// calm room, so it breathes slower and thinner than the house default.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#7C3AED",
  listening: "#7C3AED",
  thinking: "#22D3EE",
  speaking: "#7C3AED",
  offline: "#7C3AED",
};

const STATE_LABEL: Record<BotState, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Header presence control ───────────────────────────────────────────────────
// The one voice affordance, in the studio's own top bar. Idle: click to begin.

function BeginControl({
  status,
  error,
  onBegin,
}: {
  status: ConnStatus;
  error: string;
  onBegin: () => void;
}) {
  const connecting = status === "connecting";
  return (
    <div className="ff-presence">
      <span className="ff-presence-label">
        {connecting ? "Connecting…" : status === "error" ? error || "Connection issue" : "Build with Ada"}
      </span>
      {connecting ? (
        <button className="ff-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="ff-spin" />
        </button>
      ) : (
        <button className="ff-presence-btn" onClick={onBegin} title="Start talking to Ada">
          <Mic size={16} />
        </button>
      )}
    </div>
  );
}

// Live: the mic doubles as a mute toggle; a small secondary control ends the call.
function LiveControls({ onEnd }: { onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const { botState } = useForge();
  const label = isMicEnabled ? STATE_LABEL[botState] : "Muted";
  return (
    <div className="ff-presence">
      <span className="ff-presence-label">{label}</span>
      <button
        className={`ff-presence-btn is-live pstate-${botState} ${isMicEnabled ? "" : "is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="ff-presence-end" onClick={onEnd} title="End">
        <PhoneOff size={13} />
      </button>
    </div>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

export function VoiceLayer({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { setBotState, setConnectionState, handleUiCommand, registerAgentSend, snapshot, model } = useForge();

  const session = useVoqalSession({
    apiBase: FORGE.apiBase,
    publishableKey: FORGE.publishableKey ?? "",
    agentId: FORGE.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
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
  const status = CONNECTION_STATUS[connectionState];

  // Mirror the SDK's bot/connection state into the store — the header presence
  // control reads them from `useForge()`. (The ambient ring itself takes them as
  // props, straight off the session.)
  useEffect(() => {
    setBotState(botState);
  }, [botState, setBotState]);
  useEffect(() => {
    setConnectionState(status);
  }, [status, setConnectionState]);

  // Register the store's agent-send channel and open the mic once live.
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

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const presence = client ? (
    <LiveControls onEnd={disconnect} />
  ) : (
    <BeginControl status={status} error={error ?? ""} onBegin={connect} />
  );

  const shell = (
    <>
      <DemoGate
        open={!joined}
        title="Forge"
        blurb="Build an internal app by talking to Ada — describe what you want and watch the flow assemble itself on screen."
        accent={PRESENCE.listening}
        busy={status === "connecting"}
        error={status === "error" ? error || "Connection issue" : null}
        onJoin={async () => {
          await connect();
          setJoined(true);
        }}
      />
      <AmbientPresence
        botState={botState}
        connectionState={connectionState}
        palette={PRESENCE}
        weight={0.8}
        tempo={1.5}
        radius={2}
      />
      {children(presence)}
      <ActivityFeed />
    </>
  );

  if (!client) return <>{shell}</>;

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {shell}
    </PipecatClientProvider>
  );
}
