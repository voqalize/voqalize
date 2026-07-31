/**
 * Docket — top-level layout and session wiring for the ambient contract-review
 * demo. A slim top bar carries the wordmark, matter breadcrumb, and the one
 * prominent presence control (not a bottom chat-widget dock — this is meant
 * to read as part of the product's own chrome, not a bolted-on assistant).
 * Left rail is matter detail + clause outline only. Main = DocumentViewer, ringed
 * by the shared `AmbientPresence` glow from `@voqalize/client-react` — the
 * catalog-wide voice treatment, in Docket's oxblood. TaskTray docked, quiet.
 * When the assistant points at a clause, the ring's beam layer travels from the
 * screen edge to it. Once connected the mic stays
 * open — no push-to-talk — the presence control doubles as a mute toggle,
 * with a small secondary "end" control beside it.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC
 * transport, mic control, bot-state — is the public SDK's {@link useVoqalSession};
 * this file is just the desk chrome plus two bridges that tie the call to the
 * shared store: the agent's `ui_command` server-messages replay onto the store
 * (so it drives the document), and the store's silent `clause_focus` reading
 * position is echoed back to the agent. This is exactly the surface an external
 * developer embeds: `useVoqalSession` from `@voqalize/client-react`, driven by a
 * publishable (`pk_`) key. Mounted once inside the `LegalProvider`.
 */

import { useCallback, useEffect, type ReactNode } from 'react';
import { PipecatClientProvider, usePipecatClientMicControl } from '@pipecat-ai/client-react';
import { BotAudioOutput } from '@pipecat-ai/voice-ui-kit';
import { Mic, MicOff, PhoneOff, Loader2 } from 'lucide-react';
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalConnectionState,
} from '@voqalize/client-react';
import { useLegal } from './store';
import { CLAUSES, DATA_ROOM, MATTER } from './content';
import { DocumentViewer } from './DocumentViewer';
import { TaskTray } from './TaskTray';
import { ObligationsPanel } from './ObligationsPanel';
import { config } from './config';

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const LEGAL = config;

type Status = 'idle' | 'connecting' | 'live' | 'error';

// Docket's reading of the shared presence ring: the oxblood of a law-office desk
// set, shifting to gold leaf while the assistant reasons. The beam that travels
// from the edge to a clause is the same oxblood — the agent reaching into the page.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: '#9A3324',
  listening: '#9A3324',
  thinking: '#B9862E',
  speaking: '#9A3324',
  offline: '#E4E1DB',
  beam: '#9A3324',
};

// The store's ConnectionState vocabulary uses `live`; the SDK hook reports
// `connected`/`disconnected`. Map the transport state onto the store's.
const CONNECTION_STATUS: Record<VoqalConnectionState, Status> = {
  idle: 'idle',
  connecting: 'connecting',
  connected: 'live',
  disconnected: 'idle',
  error: 'error',
};

function ClauseNav() {
  const { focusedClauseId } = useLegal();
  return (
    <nav className="desk-outline">
      {CLAUSES.map((c) => (
        <a
          key={c.id}
          href={`#clause-${c.id}`}
          className={`desk-outline-item ${focusedClauseId === c.id ? 'desk-outline-active' : ''}`}
          onClick={(e) => {
            e.preventDefault();
            document.getElementById(`clause-${c.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }}
        >
          <span className="desk-outline-num">{c.number}</span>
          {c.heading}
        </a>
      ))}
    </nav>
  );
}

// ── Top-bar presence control ──────────────────────────────────────────────────
// The one prominent affordance for the voice layer. Idle: click to begin.
// Live: doubles as a mute toggle; a small secondary control ends the session.
function BeginControl({ status, error, onBegin }: { status: Status; error: string; onBegin: () => void }) {
  return (
    <div className="desk-presence">
      {status === 'connecting' ? (
        <button className="desk-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={17} className="desk-spin" />
        </button>
      ) : (
        <button className="desk-presence-btn" onClick={onBegin} title="Begin Review">
          <Mic size={17} />
        </button>
      )}
      <span className="desk-presence-label">
        {status === 'connecting' ? 'Connecting…' : status === 'error' ? error || 'Connection issue' : 'Begin Review'}
      </span>
    </div>
  );
}

function LiveControls({ onEnd }: { onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const { botState } = useLegal();
  const label = { idle: 'Live', listening: 'Listening', thinking: 'Thinking', speaking: 'Speaking' }[botState];
  return (
    <div className="desk-presence">
      <span className="desk-presence-label">{isMicEnabled ? label : 'Muted'}</span>
      <button
        className={`desk-presence-btn is-live glow-${botState} ${isMicEnabled ? '' : 'is-muted'}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? 'Mute' : 'Unmute'}
      >
        {isMicEnabled ? <Mic size={17} /> : <MicOff size={17} />}
      </button>
      <button className="desk-presence-end" onClick={onEnd} title="End Review">
        <PhoneOff size={14} />
      </button>
    </div>
  );
}

function TopBar({ status, children }: { status: Status; children: ReactNode }) {
  return (
    <header className="desk-topbar">
      <div className="desk-topbar-left">
        <span className="desk-wordmark">Docket</span>
        <span className="desk-topbar-sep" aria-hidden>
          /
        </span>
        <span className="desk-topbar-matter">
          {MATTER.client} <span className="desk-topbar-dim">vs.</span> {MATTER.counterparty}
        </span>
      </div>
      <div className="desk-topbar-right">{children}</div>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');

        .desk-topbar {
          position: fixed;
          top: 0; left: 0; right: 0;
          height: 56px;
          z-index: 70;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 20px;
          background: rgba(250, 250, 249, 0.92);
          backdrop-filter: blur(10px);
          border-bottom: 1px solid #E4E1DB;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .desk-topbar-left {
          display: flex;
          align-items: baseline;
          gap: 10px;
          min-width: 0;
        }
        .desk-wordmark {
          font-family: 'Source Serif 4', Georgia, serif;
          font-weight: 700;
          font-size: 17px;
          color: #0F0E0D;
          letter-spacing: -0.01em;
          flex: none;
        }
        .desk-topbar-sep {
          color: #CCCAC6;
          font-size: 14px;
        }
        .desk-topbar-matter {
          font-size: 12.5px;
          color: #706D66;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .desk-topbar-dim { color: #8F8B85; }
        .desk-topbar-right { flex: none; }

        .desk-presence {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .desk-presence-label {
          font-size: 12px;
          font-weight: 600;
          color: #706D66;
          letter-spacing: 0.01em;
          min-width: 62px;
          text-align: right;
        }
        .desk-presence-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          border-radius: 50%;
          border: 1.5px solid #9A3324;
          background: #9A3324;
          color: #FAFAF9;
          cursor: pointer;
          transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
          flex: none;
        }
        .desk-presence-btn:hover { transform: scale(1.05); }
        .desk-presence-btn:active { transform: scale(0.97); }
        .desk-presence-btn.is-connecting {
          background: transparent;
          color: #9A3324;
          cursor: default;
        }
        .desk-presence-btn.is-connecting:hover { transform: none; }
        .desk-presence-btn.is-live {
          box-shadow: 0 0 0 4px rgba(154, 51, 36, 0.14);
        }
        .desk-presence-btn.is-live.glow-thinking { box-shadow: 0 0 0 4px rgba(154, 51, 36, 0.22); }
        .desk-presence-btn.is-live.glow-speaking { box-shadow: 0 0 0 5px rgba(154, 51, 36, 0.3); }
        .desk-presence-btn.is-muted {
          background: #FAFAF9;
          border-color: #CCCAC6;
          color: #706D66;
          box-shadow: none;
        }
        .desk-presence-end {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 26px;
          height: 26px;
          border-radius: 50%;
          border: none;
          background: transparent;
          color: #AFA9A0;
          cursor: pointer;
          transition: color 0.15s ease, background 0.15s ease;
          flex: none;
        }
        .desk-presence-end:hover { color: #9A3324; background: #F2F1F0; }
        .desk-spin { animation: legal-spin 0.9s linear infinite; }
        @keyframes legal-spin { to { transform: rotate(360deg); } }
      `}</style>
    </header>
  );
}

function LeftRail() {
  return (
    <aside className="desk-rail">
      <div className="desk-matter">
        <div className="desk-matter-label">Reviewing for</div>
        <div className="desk-matter-value">{MATTER.client}</div>
        <div className="desk-matter-sub">
          vs. {MATTER.counterparty} &middot; {MATTER.documentTitle}
        </div>
      </div>

      <div className="desk-outline-label">Sections</div>
      <ClauseNav />

      <div className="desk-outline-label">Data room</div>
      <div className="desk-dataroom">
        {DATA_ROOM.map((d) => (
          <div key={d.id} className="desk-dataroom-item" title={d.description}>
            {d.name}
          </div>
        ))}
      </div>

      <style>{`
        .desk-rail {
          position: fixed;
          top: 56px; left: 0; bottom: 0;
          width: 220px;
          z-index: 50;
          background: #FAFAF9;
          border-right: 1px solid #E4E1DB;
          padding: 20px 16px;
          display: flex;
          flex-direction: column;
          gap: 16px;
          font-family: 'Inter', system-ui, sans-serif;
          overflow-y: auto;
        }
        .desk-matter-label {
          font-size: 10.5px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #8F8B85;
        }
        .desk-matter-value {
          font-family: 'Source Serif 4', Georgia, serif;
          font-size: 15px;
          font-weight: 600;
          color: #0F0E0D;
          margin-top: 3px;
        }
        .desk-matter-sub {
          font-size: 11.5px;
          color: #706D66;
          margin-top: 3px;
          line-height: 1.4;
        }
        .desk-outline-label {
          font-size: 10.5px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #8F8B85;
        }
        .desk-outline {
          display: flex;
          flex-direction: column;
          gap: 1px;
          margin-top: -8px;
        }
        .desk-outline-item {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 6px 8px;
          border-radius: 6px;
          font-size: 12.5px;
          color: #33312C;
          text-decoration: none;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .desk-outline-item:hover { background: #F2F1F0; }
        .desk-outline-active {
          background: rgba(154, 51, 36, 0.08);
          color: #9A3324;
          font-weight: 600;
        }
        .desk-outline-num {
          font-variant-numeric: tabular-nums;
          color: #AFA9A0;
          width: 14px;
        }
        .desk-outline-active .desk-outline-num { color: #9A3324; }

        .desk-dataroom {
          display: flex;
          flex-direction: column;
          gap: 1px;
          margin-top: -8px;
        }
        .desk-dataroom-item {
          padding: 5px 8px;
          border-radius: 6px;
          font-size: 11.5px;
          color: #8F8B85;
          line-height: 1.4;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      `}</style>
    </aside>
  );
}

function LiveLayer() {
  const { setBotState, setConnectionState, handleUiCommand, registerAgentSend, pointer } =
    useLegal();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: LEGAL.apiBase,
    tenantSlug: LEGAL.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the presence control's error state.
    publishableKey: LEGAL.publishableKey ?? '',
    agentId: LEGAL.agentId,
    // STT/TTS come from this demo's config, so the pipeline is declared once.
    pipeline: LEGAL.pipeline,
    payload: { surface: 'legal-web' },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === 'ui_command') handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } =
    session;

  const status = CONNECTION_STATUS[connectionState];

  // Mirror the SDK's bot/connection state into the shared store — the live
  // presence control reads them from `useLegal()`. (The ambient ring itself takes
  // them as props, straight off the session.)
  useEffect(() => {
    setBotState(botState);
  }, [botState, setBotState]);
  useEffect(() => {
    setConnectionState(status);
  }, [status, setConnectionState]);

  // Register the store's agent-send channel (silent `clause_focus`) and open the
  // mic once the session is live.
  useEffect(() => {
    if (connectionState !== 'connected') return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  const begin = () => {
    connect();
  };

  const shell = (
    <>
      <AmbientPresence
        botState={botState}
        connectionState={connectionState}
        palette={PRESENCE}
        beam={pointer ? { id: pointer.nonce, targetId: `clause-${pointer.clauseId}` } : null}
      />
      <TopBar status={status}>
        {client ? <LiveControls onEnd={disconnect} /> : <BeginControl status={status} error={error ?? ''} onBegin={begin} />}
      </TopBar>
      <LeftRail />
      <TaskTray />
      <ObligationsPanel />
      <main className="desk-main">
        <DocumentViewer />
      </main>
      <style>{`
        .desk-main {
          position: fixed;
          top: 56px; right: 0; bottom: 0;
          left: 220px;
          overflow: hidden;
          background: #FAFAF9;
        }
      `}</style>
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

export function LegalDesk() {
  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', background: '#FAFAF9' }}>
      <LiveLayer />
    </div>
  );
}
