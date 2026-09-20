/**
 * Docket — top-level layout and session wiring for the ambient contract-review
 * demo. A slim top bar carries the wordmark and the matter breadcrumb, and
 * nothing else: the assistant and every control for her are in the bottom-left
 * corner, at the foot of the left rail (`CounselDock`). That corner is where the
 * orientation column already is — matter, sections, data room — and the right of
 * the screen is spoken for by the work she produces: the task tray at the top of
 * it, the obligations ledger at the bottom. Main = DocumentViewer, ringed by the
 * shared `AmbientPresence` glow — the catalog-wide voice treatment, in Docket's
 * oxblood. When the assistant points at a clause, the ring's beam layer travels
 * from the screen edge to it. Once connected the mic stays open — no
 * push-to-talk — the presence control doubles as a mute toggle, with a small
 * secondary "end" control beside it.
 *
 * **This is exactly the surface an external developer embeds, and it is almost
 * entirely pipecat's.** Voice-ui-kit's `PipecatAppBase` does pipecat's whole
 * two-step connect (`startBot` against the control plane, then `connect` the
 * transport) and owns the client's lifecycle; everything below it is a stock
 * `PipecatClient`: `usePipecatClientTransportState`/`usePipecatConnectionState`
 * report the call, RTVI events say who is speaking, `PipecatAppBase`'s own
 * `BotAudioOutput` plays counsel, and the brain's `session.dispatch(...)`
 * arrives on `RTVIEvent.UICommand` as `{ command, payload }`. The only
 * Voqalize-specific code on the page is the request that starts the call and
 * the one line over its answer, both in `src/config.ts` — there is no client
 * library to install.
 *
 * Two bridges tie the call to the shared store: every `ui-command` replays onto
 * it (so the assistant drives the document), and the store's silent
 * `clause_focus` reading position goes back the other way as a typed RTVI
 * `ui-event`. Mounted once inside the `LegalProvider`.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { RTVIEvent, type UICommandData } from '@pipecat-ai/client-js';
import {
  usePipecatClient,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from '@pipecat-ai/client-react';
import { PipecatAppBase, usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from '@voqalize/demo-kit';
import { useLegal } from './store';
import { CLAUSES, DATA_ROOM, MATTER } from './content';
import { CounselDock, type DockStatus } from './CounselDock';
import { DocumentViewer } from './DocumentViewer';
import { TaskTray } from './TaskTray';
import { ObligationsPanel } from './ObligationsPanel';
import { connectRequest, withRealHeaders } from './config';

/** The dock renders the phase, so the phase is named where it is rendered. */
type Status = DockStatus;

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

// ── The top bar ───────────────────────────────────────────────────────────────
// Where the matter is named, and nothing more. The voice layer used to end up
// here on the argument that it should read as the product's own chrome rather
// than a bolted-on chat widget — which was an argument about the *shape* of a
// bottom-right bubble, not about the corner. It is in `CounselDock` now, beside
// the face it controls.
function TopBar() {
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

        /* On a phone the bar carries the wordmark alone — the matter caption is
           already on the document header. */
        @media (max-width: 720px) {
          .desk-topbar {
            padding: 0 14px;
          }
          .desk-topbar-sep,
          .desk-topbar-matter {
            display: none;
          }
        }
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
          /* The counsel dock is pinned to this column's floor and is a sibling,
             not a child — it has to outrank the ambient ring, and a child of a
             z-50 rail cannot. So the rail's own scrolling content stops above
             it: the dock's picture, its control row, the rule between them, and
             a gap. Keep this in step with CounselDock.tsx. */
          padding: 20px 16px calc(132px + 50px + 1px + 20px);
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

        /* On a phone the document is the whole product, so the 220px rail
           becomes a thin horizontal clause strip beneath the top bar: the
           reading position stays visible and jumpable, and the matter block and
           data room — desktop orientation, not review work — drop away. */
        @media (max-width: 720px) {
          .desk-rail {
            top: 56px;
            right: 0;
            bottom: auto;
            width: auto;
            height: 42px;
            padding-bottom: 0;
            flex-direction: row;
            align-items: center;
            gap: 0;
            padding: 0 12px;
            border-right: none;
            border-bottom: 1px solid #E4E1DB;
            overflow-x: auto;
            overflow-y: hidden;
            scrollbar-width: none;
          }
          .desk-rail::-webkit-scrollbar { display: none; }
          .desk-matter,
          .desk-outline-label,
          .desk-dataroom {
            display: none;
          }
          .desk-outline {
            flex-direction: row;
            gap: 6px;
            margin-top: 0;
          }
          .desk-outline-item {
            flex: none;
            white-space: nowrap;
            padding: 5px 10px;
            border: 1px solid #E4E1DB;
            font-size: 12px;
          }
          .desk-outline-active {
            border-color: rgba(154, 51, 36, 0.3);
          }
        }
      `}</style>
    </aside>
  );
}

/**
 * Mints the session and owns the client. `PipecatAppBase` builds the
 * `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` — with its own `BotAudioOutput` — as soon as the
 * client exists, **not** when the call goes live: counsel's audio track is
 * announced once, from the remote track's `unmute` a few hundred milliseconds
 * after the peer connection is up, and a listener that subscribes late finds
 * nothing to read. `connectOnMount` is off: nothing opens a microphone until
 * the visitor has read the notice and joined.
 */
function LiveLayer() {
  // Memoized: a fresh object every render would re-fire the connect effect and
  // re-mint a session. No pipeline override — this agent's voice and language
  // are declared on its brain (backend/brain.py), the only place they belong.
  const params = useMemo(() => connectRequest({ surface: 'legal-web' }), []);
  const [joined, setJoined] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const gate = useMemo(() => ({ joined, setJoined, agreed, setAgreed }), [joined, agreed]);

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect, handleDisconnect }) => (
        <Desk error={error ?? null} onBegin={handleConnect} onEnd={handleDisconnect} gate={gate} />
      )}
    </PipecatAppBase>
  );
}

// Nothing opens a microphone until the visitor has read the notice and joined.
// The gate's state is held above `PipecatAppBase`, because everything below it
// remounts once, when the client arrives — and on a cold load a visitor has
// ticked the box by then.
interface GateState {
  joined: boolean;
  setJoined: (joined: boolean) => void;
  agreed: boolean;
  setAgreed: (agreed: boolean) => void;
}

/** The desk chrome, the presence ring, and the two bridges to the store. */
function Desk({
  error,
  onBegin,
  onEnd,
  gate,
}: {
  error: string | null;
  onBegin?: () => void | Promise<void>;
  onEnd?: () => void | Promise<void>;
  gate: GateState;
}) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected: isLive, isConnecting } = usePipecatConnectionState();
  const { handleUiCommand, registerAgentSend, pointer } = useLegal();
  const [activity, setActivity] = useState<AmbientPresenceActivity>('idle');

  const status: Status =
    error || transportState === 'error' ? 'error' : isLive ? 'live' : isConnecting ? 'connecting' : 'idle';

  // Screen ← assistant. The brain's `session.dispatch(PointToClause(...))` lands
  // here as `{ command: "point_to_clause", payload: {...} }`. Subscribing to the
  // event rather than registering eight `useUICommandHandler`s: the store is one
  // reducer, and an unknown command is a no-op there by design.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) =>
        handleUiCommand(command, (payload ?? {}) as Record<string, unknown>),
      [handleUiCommand],
    ),
  );

  // Presence is derived from pipecat's own events, never stored twice.
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity('listening'), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity('thinking'), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity('speaking'), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity('idle'), []));

  // Assistant ← screen. The store's silent `clause_focused` rides RTVI's
  // `ui-event` once the call is live.
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((event, payload) => client.sendUIEvent(event, payload));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Dev-only: drive the review without a mic.
  //   window.__legal.sendText('what is risky about the liability cap?')
  //   window.__legal.ui('point_to_clause', { clause_id: 'c8' })
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __legal?: unknown }).__legal = {
      client,
      ui: handleUiCommand,
      sendText: (t: string) => client.sendText(t),
    };
    return () => {
      delete (window as unknown as { __legal?: unknown }).__legal;
    };
  }, [client, handleUiCommand]);

  return (
    <>
      <DemoGate
        open={!gate.joined}
        title="Legal Desk"
        blurb="Review a contract with counsel out loud — ask what's risky in it and watch the clauses and obligations light up on screen."
        accent={PRESENCE.listening}
        agreed={gate.agreed}
        onAgreedChange={gate.setAgreed}
        ready={onBegin !== undefined}
        busy={status === 'connecting'}
        error={status === 'error' ? error || 'Connection issue' : null}
        onJoin={async () => {
          await onBegin?.();
          gate.setJoined(true);
        }}
      />
      <AmbientPresence
        activity={activity}
        transportState={transportState}
        palette={PRESENCE}
        beam={pointer ? { id: pointer.nonce, targetId: `clause-${pointer.clauseId}` } : null}
      />
      <TopBar />
      <LeftRail />
      <CounselDock
        status={status}
        activity={activity}
        error={error ?? ''}
        onBegin={() => void onBegin?.()}
        onEnd={() => void onEnd?.()}
      />
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
        /* The rail is a 42px strip above the document, not a column beside it. */
        @media (max-width: 720px) {
          .desk-main {
            top: 98px;
            left: 0;
          }
        }
      `}</style>
    </>
  );
}

export function LegalDesk() {
  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', background: '#FAFAF9' }}>
      <LiveLayer />
    </div>
  );
}
