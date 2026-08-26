/**
 * The Aura Bank support voice layer — "Aria" as an ambient property of the whole
 * help centre, not a docked chat widget.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC
 * transport, mic control — is stock pipecat's `PipecatAppBase`; this file is
 * just that plus the two bridges that tie the call to the on-screen help
 * centre:
 *   - the assistant's `ui-command` server messages (`{ command, payload }`)
 *     replay onto the shared Aura store, so the agent drives the help centre
 *     and the video;
 *   - a debounced `state_sync` echoes a compact `screen_state` snapshot back
 *     (via `client.sendClientMessage`) so the assistant always knows what's on
 *     screen.
 *
 * This is exactly the surface an external developer embeds: one `fetch` for
 * `sessions.connect`, handed to `PipecatAppBase`, driven by a publishable
 * (`pk_`) key — there is no client library to install, and everything after
 * `connect` is pipecat's own. See `docs/client/handshake` for the same shape
 * written out for a reader.
 *
 * Voice *status* lives in the shared `AmbientPresence` ring (the catalog-wide
 * treatment, in Aura's indigo) — a full-viewport edge glow, legible peripherally
 * while the customer reads the page. The only chrome is one small control in the
 * bank's own navigation row: a label, a mic button that begins the call and then
 * doubles as a mute toggle, and a small "end" beside it. It reaches the header
 * through the `children` render-prop, so `pages.tsx` keeps owning its own chrome.
 *
 * `PipecatAppBase` mounts its `PipecatClientProvider` (and `BotAudioOutput`, via
 * `noThemeProvider`) as soon as the client exists, not when the call goes live —
 * Aria's audio track is announced once, from the remote track's `unmute` a few
 * hundred milliseconds after the peer connection is up, so a listener that
 * subscribes late finds nothing to read. `connectOnMount` is off: nothing opens
 * a microphone until the visitor has read the notice and joined.
 *
 * Mounted once at the route level; navigation is React state, so the call
 * survives screen changes. Voqalize runs English STT with OmniVoice English TTS
 * (declared on this demo's brain — backend/brain.py — the only place voice and
 * language belong).
 *
 * Aura's HMAC-authenticated sign-in handshake (the browser answering a
 * dispatched `open_auth` with a signed nonce) rides this same `ui-command` /
 * `client-message` pair and needs nothing extra here — the store's
 * `confirmAuth`/`cancelAuth` already echo the nonce back over `agentSend`.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { RTVIEvent, type UICommandData } from '@pipecat-ai/client-js';
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from '@pipecat-ai/client-react';
import { PipecatAppBase, usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';
import { Loader2, Mic, MicOff, PhoneOff } from 'lucide-react';
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from '@voqalize/demo-kit';
import { useAura } from './store';
import { connectRequest, withRealHeaders } from './config';

const PRIMARY = '#4F46E5';
const ACCENT = '#8B5CF6';

// Aura's reading of the shared presence ring: the bank's own indigo while Aria
// listens, its violet accent while she answers, and the amber this demo has
// always used for the "working on it" dot while she reasons — a hue shift the
// customer catches at the edge of vision without looking away from the article.
// Offline is the page's own hairline border violet-grey: present, but asleep.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: PRIMARY,
  listening: PRIMARY,
  thinking: '#F0A020',
  speaking: ACCENT,
  offline: '#E6E2F2',
};

type Status = 'idle' | 'connecting' | 'live' | 'error';

const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: 'Listening',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
};

// ── The one voice control, in Aura's own navigation row ───────────────────────

function BeginControl({ status, error, onBegin }: { status: Status; error: string; onBegin: () => void }) {
  const connecting = status === 'connecting';
  return (
    <div className="aura-presence">
      <span className="aura-presence-label">
        {connecting ? 'Connecting…' : status === 'error' ? error || 'Connection issue' : 'Ask Aura Support'}
      </span>
      {connecting ? (
        <button className="aura-presence-btn is-connecting" disabled title="Connecting…">
          <Loader2 size={16} className="aura-spin" />
        </button>
      ) : (
        <button className="aura-presence-btn" onClick={onBegin} title="Ask Aura Support">
          <Mic size={16} />
        </button>
      )}
    </div>
  );
}

// Live: the mic doubles as a mute toggle; a small secondary control ends the call.
function LiveControls({ activity, onEnd }: { activity: AmbientPresenceActivity; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  return (
    <div className="aura-presence">
      <span className="aura-presence-label">{isMicEnabled ? STATE_LABEL[activity] : 'Muted'}</span>
      <button
        className={`aura-presence-btn is-live glow-${activity} ${isMicEnabled ? '' : 'is-muted'}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? 'Mute' : 'Unmute'}
      >
        {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button className="aura-presence-end" onClick={onEnd} title="End call">
        <PhoneOff size={13} />
      </button>
    </div>
  );
}

function PresenceStyles() {
  return (
    <style>{`
      .aura-presence {
        display: flex;
        align-items: center;
        gap: 9px;
        flex: none;
      }
      .aura-presence-label {
        font-size: 12.5px;
        font-weight: 700;
        color: #6E6470;
        white-space: nowrap;
      }
      .aura-presence-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 34px;
        height: 34px;
        border-radius: 50%;
        border: none;
        background: linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%);
        color: #fff;
        cursor: pointer;
        flex: none;
        transition: transform .15s ease, box-shadow .2s ease, background .15s ease;
      }
      .aura-presence-btn:hover { transform: scale(1.05); }
      .aura-presence-btn:active { transform: scale(0.97); }
      .aura-presence-btn.is-connecting {
        background: none;
        color: ${PRIMARY};
        cursor: default;
      }
      .aura-presence-btn.is-connecting:hover { transform: none; }
      .aura-presence-btn.is-live { box-shadow: 0 0 0 4px rgba(79,70,229,.16); }
      .aura-presence-btn.is-live.glow-thinking { box-shadow: 0 0 0 4px rgba(240,160,32,.28); }
      .aura-presence-btn.is-live.glow-speaking { box-shadow: 0 0 0 5px rgba(139,92,246,.30); }
      .aura-presence-btn.is-muted {
        background: #FFFFFF;
        border: 1.5px solid #E6E2F2;
        color: #6E6470;
        box-shadow: none;
      }
      .aura-presence-end {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        border: none;
        background: none;
        color: #A79FB2;
        cursor: pointer;
        flex: none;
        transition: color .15s ease, background .15s ease;
      }
      .aura-presence-end:hover { color: ${PRIMARY}; background: #EEF0FE; }
      .aura-spin { animation: aura-spin .9s linear infinite; }
      @keyframes aura-spin { to { transform: rotate(360deg); } }
    `}</style>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

/**
 * Mints the session and owns the client. No pipeline override: this agent's
 * voice and language are declared on its brain (backend/brain.py), the only
 * place they belong.
 */
export function AuraAssistant({ children }: { children: (presence: ReactNode) => ReactNode }) {
  // Memoized: a fresh object every render would re-fire `PipecatAppBase`'s
  // connect-on-mount dependency and re-mint a session.
  const params = useMemo(() => connectRequest({ surface: 'aura-web' }), []);

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect, handleDisconnect }) => (
        <AuraSession
          error={error ?? null}
          onConnect={handleConnect ?? (async () => {})}
          onDisconnect={handleDisconnect ?? (async () => {})}
        >
          {children}
        </AuraSession>
      )}
    </PipecatAppBase>
  );
}

// Rendered inside `PipecatAppBase`'s own `PipecatClientProvider`, so every
// pipecat hook below sees the live client the moment one exists.
function AuraSession({
  error,
  onConnect,
  onDisconnect,
  children,
}: {
  error: string | null;
  onConnect: () => void | Promise<void>;
  onDisconnect: () => void | Promise<void>;
  children: (presence: ReactNode) => ReactNode;
}) {
  const { handleUiCommand, registerAgentSend, snapshot, rev } = useAura();
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected, isConnecting } = usePipecatConnectionState();

  const status: Status = isConnecting ? 'connecting' : isConnected ? 'live' : error ? 'error' : 'idle';

  // Ambient ring activity: derived straight from pipecat's own turn-taking
  // events, exactly as `AmbientPresence`'s own doc prescribes.
  const [activity, setActivity] = useState<AmbientPresenceActivity>('idle');
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity('listening'), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity('thinking'), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity('speaking'), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity('idle'), []));

  // Screen ← agent. The brain's `session.dispatch(OpenAuth(...))` etc. lands
  // here as `{ command, payload }`; the store's reducer keys on one flat object
  // with an `action` field, so fold the two back together rather than touching
  // the store (which every other command already matches exactly).
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => handleUiCommand(command, payload),
      [handleUiCommand],
    ),
  );

  const sendMessage = useCallback((type: string, data: unknown) => client?.sendClientMessage(type, data), [client]);

  // Once live: open the mic and register the store's agent-send channel (the
  // store echoes `auth_complete` / `card_selected` / etc. through it — including
  // Aura's HMAC sign-in nonce).
  useEffect(() => {
    if (!isConnected) return;
    client?.enableMic(true);
    registerAgentSend(sendMessage);
    return () => registerAgentSend(null);
  }, [isConnected, client, registerAgentSend, sendMessage]);

  // Debounced `state_sync`: whenever the on-screen state revision bumps, echo a
  // compact snapshot back to the assistant so it always knows what's on screen.
  useEffect(() => {
    if (!isConnected) return;
    const t = setTimeout(() => sendMessage('state_sync', { screen_state: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, rev]);

  // Dev-only: drive the flow without a mic.
  //   window.__aura.ui('open_article', {article_id: 'interest-certificate'})
  //   window.__aura.sendText('where do I download my interest certificate for tax filing?')
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __aura?: unknown }).__aura = {
      client,
      ui: handleUiCommand,
      sendText: (t: string) => client.sendText(t),
    };
    return () => {
      delete (window as unknown as { __aura?: unknown }).__aura;
    };
  }, [client, handleUiCommand]);

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const presence = isConnected ? (
    <LiveControls activity={activity} onEnd={onDisconnect} />
  ) : (
    <BeginControl status={status} error={error ?? ''} onBegin={onConnect} />
  );

  return (
    <>
      <DemoGate
        open={!joined}
        title="Aura Support"
        blurb="Call your bank's support line — ask about your account and watch Aura work the answer out on screen."
        accent={PRESENCE.listening}
        busy={status === 'connecting'}
        error={status === 'error' ? error || 'Connection issue' : null}
        onJoin={async () => {
          await onConnect();
          setJoined(true);
        }}
      />
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
      <PresenceStyles />
      {children(presence)}
    </>
  );
}
