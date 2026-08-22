/**
 * The Aura Bank support voice layer — "Aria" as an ambient property of the whole
 * help centre, not a docked chat widget.
 *
 * The entire session lifecycle — mint against the control plane, WebRTC
 * transport, mic control, bot-state — is the public SDK's {@link useVoqalSession}
 * from `@voqalize/client-react`, driven by a publishable (`pk_`) key. While live:
 *   - the hook's `onServerMessage` replays the assistant's `ui_command` messages
 *     onto the shared Aura store, so the agent drives the help centre + video;
 *   - a debounced `state_sync` echoes a compact `screen_state` snapshot back
 *     (via `sendMessage`) so the assistant always knows what's on screen.
 *
 * Voice *status* lives in the shared `AmbientPresence` ring (the catalog-wide
 * treatment, in Aura's indigo) — a full-viewport edge glow, legible peripherally
 * while the customer reads the page. The only chrome is one small control in the
 * bank's own navigation row: a label, a mic button that begins the call and then
 * doubles as a mute toggle, and a small "end" beside it. It reaches the header
 * through the `children` render-prop, so `pages.tsx` keeps owning its own chrome.
 *
 * Mounted once at the route level; navigation is React state, so the call
 * survives screen changes. Voqalize runs English STT with OmniVoice English TTS
 * (pipeline declared in this demo's src/config.ts).
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { PipecatClientProvider, usePipecatClientMicControl } from '@pipecat-ai/client-react';
import { BotAudioOutput } from '@pipecat-ai/voice-ui-kit';
import { Loader2, Mic, MicOff, PhoneOff } from 'lucide-react';
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
  type VoqalConnectionState,
} from '@voqalize/client-react';
import { DemoGate } from '@voqalize/demo-kit';
import { useAura } from './store';
import { config } from './config';

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const AURA = config;

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

// The control's chrome speaks the source's `live` vocabulary; the SDK hook
// reports `connected`/`disconnected`. Map the transport state onto the chrome's.
// (The ring itself takes the SDK's own states straight off the hook.)
const CONNECTION_STATUS: Record<VoqalConnectionState, Status> = {
  idle: 'idle',
  connecting: 'connecting',
  // `awaiting-microphone` folds into `connecting`: the browser's own permission
  // prompt is on screen at that moment and is the thing to answer, so the chrome
  // should keep saying "wait" rather than invent a state of its own.
  'awaiting-microphone': 'connecting',
  connected: 'live',
  disconnected: 'idle',
  error: 'error',
};

// The hook's resting `idle` is, from the customer's side, still "she's hearing
// me" — fold it into this demo's long-standing default label.
const STATE_LABEL: Record<VoqalBotState, string> = {
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
function LiveControls({ botState, onEnd }: { botState: VoqalBotState; onEnd: () => void }) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  return (
    <div className="aura-presence">
      <span className="aura-presence-label">{isMicEnabled ? STATE_LABEL[botState] : 'Muted'}</span>
      <button
        className={`aura-presence-btn is-live glow-${botState} ${isMicEnabled ? '' : 'is-muted'}`}
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

export function AuraAssistant({ children }: { children: (presence: ReactNode) => ReactNode }) {
  const { handleUiCommand, registerAgentSend, snapshot, rev } = useAura();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: AURA.apiBase,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the presence control's error state.
    publishableKey: AURA.publishableKey ?? '',
    agentId: AURA.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    payload: { surface: 'aura-web' },
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type === 'ui_command') handleUiCommand(msg);
      },
      [handleUiCommand],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic, sendMessage } = session;
  const status = CONNECTION_STATUS[connectionState];

  // Once live: open the mic and register the store's agent-send channel
  // (the store echoes `card_selected` / `auth_complete` / etc. through it).
  useEffect(() => {
    if (connectionState !== 'connected') return;
    enableMic(true);
    registerAgentSend((type, data) => sendMessage(type, data as Record<string, unknown>));
    return () => registerAgentSend(null);
  }, [connectionState, enableMic, registerAgentSend, sendMessage]);

  // Debounced `state_sync`: whenever the on-screen state revision bumps, echo a
  // compact snapshot back to the assistant so it always knows what's on screen.
  useEffect(() => {
    if (connectionState !== 'connected') return;
    const t = setTimeout(() => {
      sendMessage('state_sync', { screen_state: snapshot() });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, connectionState]);

  // Dev-only: drive the flow without a mic.
  //   window.__aura.ui({action:'open_article', article_id:'interest-certificate'})
  //   window.__aura.sendText('where do I download my interest certificate for tax filing?')
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as { __aura?: unknown }).__aura = {
      client,
      ui: handleUiCommand,
      sendText: (t: string) => client?.sendText(t),
    };
    return () => {
      delete (window as unknown as { __aura?: unknown }).__aura;
    };
  }, [client, handleUiCommand]);

  // Nothing opens a microphone until the visitor has read the notice and joined.
  const [joined, setJoined] = useState(false);

  const presence = client ? (
    <LiveControls botState={botState} onEnd={disconnect} />
  ) : (
    <BeginControl status={status} error={error ?? ''} onBegin={connect} />
  );

  const shell = (
    <>
      <DemoGate
        open={!joined}
        title="Aura Support"
        blurb="Call your bank's support line — ask about your account and watch Aura work the answer out on screen."
        accent={PRESENCE.listening}
        busy={status === 'connecting'}
        error={status === 'error' ? error || 'Connection issue' : null}
        onJoin={async () => {
          await connect();
          setJoined(true);
        }}
      />
      <AmbientPresence botState={botState} connectionState={connectionState} palette={PRESENCE} />
      <PresenceStyles />
      {children(presence)}
    </>
  );

  // The bot audio lives inside the provider and must stay mounted for the whole
  // live call — the page chrome renders *below* it, so navigating never drops it.
  if (!client) return shell;

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {shell}
    </PipecatClientProvider>
  );
}
