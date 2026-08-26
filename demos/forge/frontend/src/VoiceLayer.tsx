/**
 * The Flowforge voice layer — "Ada" as ambient studio presence, not a docked
 * chat widget.
 *
 * Stock pipecat, the same embedding surface every Voqalize demo uses:
 * `PipecatAppBase` (from `@pipecat-ai/voice-ui-kit`) creates and holds the
 * client; a render-prop child owns everything that needs it. This layer wires
 * that child to the studio through the shared store:
 *   - it mirrors pipecat's own bot-activity and connection state into the
 *     store, so the header presence control reads it (the ring itself takes
 *     the state as props, from the shared `AmbientPresence` in
 *     `@voqalize/demo-kit`);
 *   - the brain's `ui-command` RTVI messages replay onto the store (add a
 *     step, insert a decision, run the tests, publish live…);
 *   - a compact workspace snapshot is echoed back (`state_sync`) on connect
 *     and after every change, so Ada always knows the open workflow, its
 *     steps, tests, and gaps — including edits the admin makes by hand.
 *
 * The presence control lives in the app's top bar (rendered via the `children`
 * render-prop so the studio owns its own chrome): a single mic affordance that
 * begins the call, then doubles as a mute toggle, with a small "end" beside it —
 * the same shape a customer would embed. `PipecatAppBase` is mounted once
 * inside `ForgeProvider`, so the call survives navigating between the list and
 * the editor; nothing opens a microphone until the visitor has read the notice
 * and joined through `DemoGate`.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { AmbientPresence, DemoGate, type AmbientPresencePalette } from "@voqalize/demo-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import { useForge, type BotState, type ConnStatus } from "./store";
import { ActivityFeed } from "./ActivityFeed";
import { ADMIN } from "./data";
import { connectRequest, withRealHeaders } from "./config";

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
  onBegin: () => void | Promise<void>;
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
function LiveControls({ onEnd }: { onEnd?: () => void | Promise<void> }) {
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
// Runs inside PipecatAppBase's own PipecatClientProvider, so every pipecat hook
// here has a client from the first render — connectOnMount is deliberately
// off; DemoGate's `onJoin` is what actually starts the call.

function CallInner({
  error,
  onConnect,
  onDisconnect,
  children,
}: {
  error: string | null;
  onConnect?: () => void | Promise<void>;
  onDisconnect?: () => void | Promise<void>;
  children: (presence: ReactNode) => ReactNode;
}) {
  const { setBotState, setConnectionState, handleUiCommand, registerAgentSend, snapshot, model } = useForge();

  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected, isConnecting } = usePipecatConnectionState();

  // Bot activity: derived straight from pipecat's own events, the same mapping
  // AmbientPresence documents (listening → thinking → speaking → idle).
  const [activity, setActivity] = useState<BotState>("idle");
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setActivity("idle"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("idle"), []));

  // The brain's ui-commands replay straight onto the store.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => handleUiCommand(command, payload),
      [handleUiCommand],
    ),
  );

  const status: ConnStatus = error ? "error" : isConnecting ? "connecting" : isConnected ? "live" : "idle";

  // Mirror pipecat's state into the store — the header presence control and
  // ActivityFeed read them from `useForge()`.
  useEffect(() => {
    setBotState(activity);
  }, [activity, setBotState]);
  useEffect(() => {
    setConnectionState(status);
  }, [status, setConnectionState]);

  // Open the mic and register the store's agent-send channel once live.
  useEffect(() => {
    if (!isConnected || !client) return;
    client.enableMic(true);
    registerAgentSend((type, data) => client.sendClientMessage(type, data));
    return () => registerAgentSend(null);
  }, [isConnected, client, registerAgentSend]);

  // Debounced snapshot push: on connect and after every change (rev), so Ada stays
  // in sync with edits the admin makes by hand too.
  useEffect(() => {
    if (!isConnected || !client) return;
    const t = setTimeout(() => client.sendClientMessage("state_sync", { workspace: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, client, model.rev]);

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

  const presence = isConnected ? (
    <LiveControls onEnd={onDisconnect} />
  ) : (
    <BeginControl status={status} error={error ?? ""} onBegin={onConnect ?? (() => {})} />
  );

  return (
    <>
      <DemoGate
        open={!joined}
        title="Forge"
        blurb="Build an internal app by talking to Ada — describe what you want and watch the flow assemble itself on screen."
        accent={PRESENCE.listening}
        busy={status === "connecting"}
        error={status === "error" ? error || "Connection issue" : null}
        onJoin={async () => {
          await onConnect?.();
          setJoined(true);
        }}
      />
      <AmbientPresence
        activity={activity}
        transportState={transportState}
        palette={PRESENCE}
        weight={0.8}
        tempo={1.5}
        radius={2}
      />
      {children(presence)}
      <ActivityFeed />
    </>
  );
}

export function VoiceLayer({ children }: { children: (presence: ReactNode) => ReactNode }) {
  // No pipeline override: this agent's voice and language are declared on its
  // brain (backend/brain.py), which is the only place they belong.
  const params = useMemo(
    () => connectRequest({ surface: "forge-web", admin: { name: ADMIN.name, role: ADMIN.role } }),
    [],
  );

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect, handleDisconnect }) => (
        <CallInner error={error ?? null} onConnect={handleConnect} onDisconnect={handleDisconnect}>
          {children}
        </CallInner>
      )}
    </PipecatAppBase>
  );
}
