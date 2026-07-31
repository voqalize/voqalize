/**
 * The "Servicing Desk" voice layer for the Meridian Servicing Console.
 *
 * Not a docked chat widget: the desk is ambient. The shared `AmbientPresence`
 * ring from `@voqalize/client-react` paints the whole viewport in Meridian's
 * teal, so the desk's state (listening / thinking / speaking) is legible
 * peripherally while the advisor keeps working the case queue. The only chrome
 * is one small control in the console's own top bar — a label, a mic button, and
 * a quiet "end" — handed to the app through a render-prop so `pages.tsx` keeps
 * ownership of its header.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC
 * transport, mic control, bot-state — is the public SDK's {@link useVoqalSession};
 * this file is just that control plus two bridges that tie the call to the
 * on-screen console:
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

import { useCallback, useEffect, type ReactNode } from "react";
import { PipecatClientProvider, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
  type VoqalConnectionState,
} from "@voqalize/client-react";
import { useServicing } from "./store";
import { ADVISOR } from "./data";
import { config } from "./config";

// Per-environment tenant + agent + pk from this demo's local config
// (src/config.ts), driven by Vite env vars.
const SERVICING = config;

// Meridian's reading of the shared presence ring: the console's own "Blueprint"
// palette — deep teal at rest, its brighter teal while the desk hears and
// answers, and the console's signal-orange (the same hue that marks "needs your
// approval") the moment the desk is reasoning, so a working desk is unmistakable
// from the corner of the eye. Offline is the console's hairline border colour, so
// a dead session reads as ordinary window trim.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#0F766E",
  listening: "#14B8A6",
  thinking: "#EA580C",
  speaking: "#14B8A6",
  offline: "#D3E0DD",
};

type Status = "idle" | "connecting" | "live" | "error";

// The SDK hook reports `connected`/`disconnected`; the control's vocabulary is
// the shorter one below.
const CONNECTION_STATUS: Record<VoqalConnectionState, Status> = {
  idle: "idle",
  connecting: "connecting",
  connected: "live",
  disconnected: "idle",
  error: "error",
};

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Top-bar presence control ──────────────────────────────────────────────────
// One affordance, sitting in the console's own header. Idle: click to begin.

function BeginControl({
  status,
  error,
  onBegin,
}: {
  status: Status;
  error: string;
  onBegin: () => void;
}) {
  const connecting = status === "connecting";
  return (
    <div className="svc-presence">
      <span className="svc-presence-label">
        {connecting
          ? "Connecting…"
          : status === "error"
            ? error || "Connection issue"
            : "Ask the Servicing Desk"}
      </span>
      {connecting ? (
        <button className="svc-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="svc-presence-spin" />
        </button>
      ) : (
        <button className="svc-presence-btn" onClick={onBegin} title="Talk to the Servicing Desk">
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
    <div className="svc-presence">
      <span className="svc-presence-label">{isMicEnabled ? STATE_LABEL[botState] : "Muted"}</span>
      <button
        className={`svc-presence-btn is-live pstate-${botState} ${isMicEnabled ? "" : "is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="svc-presence-end" onClick={onEnd} title="End call">
        <PhoneOff size={13} />
      </button>
    </div>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

export function ServicingDesk({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { handleUiCommand, registerAgentSend, rev, activeRef, tab, snapshot } = useServicing();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: SERVICING.apiBase,
    tenantSlug: SERVICING.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the control's error state.
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

  const status = CONNECTION_STATUS[connectionState];

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

  const presence = client ? (
    <LiveControls botState={botState} onEnd={disconnect} />
  ) : (
    <BeginControl status={status} error={error ?? ""} onBegin={connect} />
  );

  const shell = (
    <>
      {/* The desk as a property of the whole console — a calm, slightly thinner
          ring than the house default, because this screen is dense with work. */}
      <AmbientPresence
        botState={botState}
        connectionState={connectionState}
        palette={PRESENCE}
        weight={0.9}
        tempo={1.15}
      />
      {children(presence)}
      <PresenceStyles />
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

// The control sits on the console's dark-teal header, so it is styled against
// that bar rather than the page.
function PresenceStyles() {
  return <style dangerouslySetInnerHTML={{ __html: PRESENCE_STYLES }} />;
}

const PRESENCE_STYLES = `
.svc-presence{ display:flex; align-items:center; gap:9px; flex:0 0 auto;
  font-family:'Archivo',system-ui,sans-serif; }
.svc-presence-label{ font-size:12px; font-weight:600; color:#9FD4CD; letter-spacing:.2px;
  white-space:nowrap; max-width:190px; overflow:hidden; text-overflow:ellipsis; text-align:right; }
.svc-presence-btn{ display:flex; align-items:center; justify-content:center; width:34px; height:34px;
  border-radius:50%; border:1px solid #7fe6da55; color:#04211E; cursor:pointer; flex:0 0 auto;
  background:linear-gradient(135deg,#14B8A6,#0F766E);
  transition:transform .15s ease, box-shadow .15s ease, background .15s ease; }
.svc-presence-btn:hover{ transform:scale(1.05); }
.svc-presence-btn:active{ transform:scale(.97); }
.svc-presence-btn.is-connecting{ background:transparent; border-color:#ffffff2e; color:#9FD4CD; cursor:default; }
.svc-presence-btn.is-connecting:hover{ transform:none; }
.svc-presence-btn.is-live{ box-shadow:0 0 0 3px #14b8a633; }
.svc-presence-btn.is-live.pstate-thinking{ background:linear-gradient(135deg,#FB923C,#EA580C); color:#3a1402;
  border-color:#fdba7455; box-shadow:0 0 0 4px #ea580c33; }
.svc-presence-btn.is-live.pstate-speaking{ box-shadow:0 0 0 5px #14b8a640; }
.svc-presence-btn.is-muted{ background:#ffffff14; border-color:#ffffff2e; color:#9FD4CD; box-shadow:none; }
.svc-presence-end{ display:flex; align-items:center; justify-content:center; width:26px; height:26px;
  border-radius:50%; border:none; background:transparent; color:#7FA9A4; cursor:pointer; flex:0 0 auto;
  transition:color .15s ease, background .15s ease; }
.svc-presence-end:hover{ color:#EAF6F4; background:#ffffff1f; }
.svc-presence-spin{ animation:svc-presence-spin .9s linear infinite; }
@keyframes svc-presence-spin{ to{ transform:rotate(360deg); } }

/* Phone: the ring carries the state, so the label steps aside and only the
   affordances stay. */
@media (max-width:640px){
  .svc-presence{ gap:6px; }
  .svc-presence-label{ display:none; }
  .svc-presence-btn{ width:32px; height:32px; }
}
`;
