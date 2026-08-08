/**
 * The "Travel Desk" voice layer — the desk as a property of the whole portal,
 * not a widget parked in the corner.
 *
 * There is no panel and no launcher. The agent's state is the page itself: the
 * shared `AmbientPresence` ring from `@voqalize/client-react` glows around the
 * viewport in Trip Studio's vermilion, shifting to itinerary gold while the desk
 * reasons, and firing a short beam at whatever section the agent just moved the
 * travel agent's eye to. The only affordance is one small control handed up into
 * the portal's own top bar (via the `children` render-prop, so the portal keeps
 * ownership of its chrome): begin, then mute-toggle, plus a quiet "end".
 *
 * The whole session lifecycle — mint against the control plane, WebRTC transport,
 * mic control, bot-state — is the public SDK's {@link useVoqalSession}; this file
 * is just that control plus two bridges that tie the call to the on-screen portal:
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

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { PipecatClientProvider, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  useUiCommand,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
  type VoqalConnectionState,
} from "@voqalize/client-react";
import { DemoGate } from "@voqalize/demo-kit";
import { useTravel } from "./store";
import type { TravelCommands } from "./uiCommands";
import { config } from "./config";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const TRAVEL = config;

// Trip Studio's reading of the shared presence ring, straight off the portal's own
// tokens: `--vermilion` (#E24E2A) is the live/agent colour everywhere in this demo,
// so it carries idle / listening / speaking. Thinking shifts to the five-star gold
// used for hotel ratings (`.tv-stars`, #C9A227) — a warm but unmistakably different
// hue, readable at the edge of vision while the travel agent is scanning fares.
// Offline is `--warm-300`, the same faint paper tone as the portal's card borders,
// so a dead session reads as a hairline seam rather than a signal. The beam that
// travels to a highlighted section is vermilion: the desk reaching into the page.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#E24E2A",
  listening: "#E24E2A",
  thinking: "#C9A227",
  speaking: "#E24E2A",
  offline: "#D2C6B2",
  beam: "#E24E2A",
};

// The mic stays open once live, so `idle` is still "listening" to the user.
const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Listening",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Top-bar presence control ──────────────────────────────────────────────────
// Not connected / connecting / failed: one invitation, one button.
function BeginControl({
  connectionState,
  error,
  onBegin,
}: {
  connectionState: VoqalConnectionState;
  error: string;
  onBegin: () => void;
}) {
  const connecting = connectionState === "connecting";
  const label = connecting
    ? "Connecting…"
    : connectionState === "error"
      ? error || "Connection issue"
      : "Ask the Travel Desk";
  return (
    <div className="tv-presence">
      <span className="tv-presence-label" title={label}>
        {label}
      </span>
      {connecting ? (
        <button className="tv-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="tv-presence-spin" />
        </button>
      ) : (
        <button
          className="tv-presence-btn"
          onClick={onBegin}
          title={connectionState === "error" ? "Try again" : "Talk to the Travel Desk"}
        >
          <Mic size={16} />
        </button>
      )}
    </div>
  );
}

// Live: the mic doubles as a mute toggle; a small secondary control ends the call.
function LiveControls({ botState, onEnd }: { botState: VoqalBotState; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  return (
    <div className="tv-presence">
      <span className="tv-presence-label">{isMicEnabled ? STATE_LABEL[botState] : "Muted"}</span>
      <button
        className={`tv-presence-btn is-live pstate-${botState} ${isMicEnabled ? "" : "is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="tv-presence-end" onClick={onEnd} title="End call">
        <PhoneOff size={13} />
      </button>
    </div>
  );
}

// The control lives inside `.tv-root`, so it can just read the portal's own
// design tokens (`--action`, `--vermilion`, …) instead of restating hexes.
const PRESENCE_STYLES = `
.tv-presence{display:flex;align-items:center;gap:9px;flex:0 0 auto}
.tv-presence-label{font-size:12px;font-weight:600;color:var(--muted-foreground);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px;text-align:right}
.tv-presence-btn{display:flex;align-items:center;justify-content:center;flex:0 0 36px;
  width:36px;height:36px;border-radius:50%;border:1.5px solid var(--action);
  background:var(--action);color:var(--on-action);cursor:pointer;
  transition:transform .15s,box-shadow .25s,background .15s}
.tv-presence-btn:hover{transform:scale(1.05)}
.tv-presence-btn:active{transform:scale(.97)}
.tv-presence-btn.is-connecting{background:transparent;color:var(--vermilion-text);cursor:default}
.tv-presence-btn.is-connecting:hover{transform:none}
.tv-presence-btn.is-live{box-shadow:0 0 0 4px rgba(226,78,42,.16)}
.tv-presence-btn.is-live.pstate-thinking{background:#A8861F;border-color:#A8861F;
  box-shadow:0 0 0 4px rgba(201,162,39,.26)}
.tv-presence-btn.is-live.pstate-speaking{box-shadow:0 0 0 5px rgba(226,78,42,.30)}
.tv-presence-btn.is-muted{background:var(--card);border-color:var(--border-strong);
  color:var(--muted-foreground);box-shadow:none}
.tv-presence-end{display:flex;align-items:center;justify-content:center;flex:0 0 26px;
  width:26px;height:26px;border-radius:50%;border:none;background:transparent;
  color:var(--warm-400);cursor:pointer;transition:color .15s,background .15s}
.tv-presence-end:hover{color:var(--vermilion-text);background:var(--muted)}
.tv-presence-spin{animation:tv-spin .9s linear infinite}

@media(max-width:640px){
  .tv-presence{gap:7px}
  .tv-presence-label{font-size:11.5px;max-width:120px}
  .tv-presence-btn{flex:0 0 34px;width:34px;height:34px}
  .tv-presence-end{flex:0 0 24px;width:24px;height:24px}
}
`;

// ── Session owner ─────────────────────────────────────────────────────────────
export function TravelAdvisor({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { uiCommands, registerAgentSend, rev, active, snapshot, highlighted } = useTravel();

  // The entire session lifecycle in one hook.
  const session = useVoqalSession({
    apiBase: TRAVEL.apiBase,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the presence control's error state.
    publishableKey: TRAVEL.publishableKey ?? "",
    agentId: TRAVEL.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    payload: { surface: "travel-web" },
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  // The agent drives the screen: every `ui_command` goes to the store's typed
  // handler for that action. Subscription, envelope stripping and dispatch are the
  // hook's; the store only says what each command means.
  useUiCommand<TravelCommands>(client, uiCommands);

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

  // A hung-up session leaves the hook's client behind; clear it before redialling.
  const begin = async () => {
    if (connectionState === "disconnected") await disconnect();
    await connect();
  };

  // Nothing opens a microphone until the visitor has read the notice and joined.
  // The gate is the first thing on screen; `begin` runs from inside it, so the
  // demo's own control only ever appears to someone who has already consented.
  const [joined, setJoined] = useState(false);

  const presence =
    connectionState === "connected" ? (
      <LiveControls botState={botState} onEnd={disconnect} />
    ) : (
      <BeginControl connectionState={connectionState} error={error ?? ""} onBegin={begin} />
    );

  const shell = (
    <>
      <DemoGate
        open={!joined}
        title="Travel Desk"
        blurb="Plan a trip out loud — say where you want to go and watch the itinerary build itself on screen."
        accent={PRESENCE.listening}
        busy={connectionState === "connecting"}
        error={connectionState === "error" ? error || "Connection issue" : null}
        onJoin={async () => {
          await begin();
          setJoined(true);
        }}
      />
      <AmbientPresence
        botState={botState}
        connectionState={connectionState}
        palette={PRESENCE}
        // The desk points at the section it just moved the agent's eye to.
        beam={highlighted ? { id: highlighted.nonce, targetId: `tv-sec-${highlighted.section}` } : null}
      />
      <style dangerouslySetInnerHTML={{ __html: PRESENCE_STYLES }} />
      {children(presence)}
    </>
  );

  if (!client) return shell;

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {shell}
    </PipecatClientProvider>
  );
}
