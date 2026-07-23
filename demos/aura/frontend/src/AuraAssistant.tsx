/**
 * The Aura Bank support voice widget.
 *
 * A bottom-right launcher that opens an embedded voice panel. The entire session
 * lifecycle — mint against the control plane, WebRTC transport, mic control,
 * bot-state — is the public SDK's {@link useVoqalSession} from
 * `@voqalize/client-react`, driven by a publishable (`pk_`) key. While live:
 *   - the hook's `onServerMessage` replays the assistant's `ui_command` messages
 *     onto the shared Aura store, so the agent drives the help centre + video;
 *   - a debounced `state_sync` echoes a compact `screen_state` snapshot back
 *     (via `sendMessage`) so the assistant always knows what's on screen.
 *
 * Mounted once at the route level; navigation is React state, so the call
 * survives screen changes. Voice runs English STT with OmniVoice English TTS
 * (pipeline declared in this demo's src/config.ts).
 */

import { useCallback, useEffect, useState } from 'react';
import { PipecatClientProvider, usePipecatClientMediaTrack } from '@pipecat-ai/client-react';
import { BotAudioOutput, CircularWaveform, UserAudioControl } from '@pipecat-ai/voice-ui-kit';
import {
  useVoqalSession,
  type VoqalBotState,
  type VoqalConnectionState,
} from '@voqalize/client-react';
import { useAura } from './store';
import { config } from './config';

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const AURA = config;

const PRIMARY = '#4F46E5';
const PRIMARY_DARK = '#3730A3';
const ACCENT = '#8B5CF6';

type Status = 'idle' | 'connecting' | 'live' | 'error';
type BotState = 'listening' | 'thinking' | 'speaking';

// The widget chrome speaks the source's `live` vocabulary; the SDK hook reports
// `connected`/`disconnected`. Map the transport state onto the chrome's.
const CONNECTION_STATUS: Record<VoqalConnectionState, Status> = {
  idle: 'idle',
  connecting: 'connecting',
  connected: 'live',
  disconnected: 'idle',
  error: 'error',
};

// The hook's bot state adds an `idle` the chrome never rendered; fold it into the
// source's default resting state (`listening`).
const chromeBot = (b: VoqalBotState): BotState => (b === 'idle' ? 'listening' : b);

function BotVisualizer({ botState }: { botState: BotState }) {
  const botTrack = usePipecatClientMediaTrack('audio', 'bot');
  return <CircularWaveform audioTrack={botTrack} isThinking={botState === 'thinking'} size={116} color1={PRIMARY} color2={ACCENT} />;
}

// UI chrome and the assistant both speak English.
const STATE_LABEL: Record<BotState, string> = {
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking',
};
const STATE_DOT: Record<BotState, string> = {
  listening: '#34C759',
  thinking: '#F0A020',
  speaking: ACCENT,
};

// Collapsed pill — keeps the call fully live (provider + hook stay mounted in
// the parent), just frees the screen. Click to expand.
function MinimizedBar({
  botState,
  live,
  onExpand,
  onEnd,
}: {
  botState: BotState;
  live: boolean;
  onExpand: () => void;
  onEnd: () => void;
}) {
  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 1200, display: 'flex', alignItems: 'center' }}>
      <button
        onClick={onExpand}
        title="Expand"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`,
          color: '#fff',
          border: 'none',
          borderRadius: '24px 0 0 24px',
          padding: '11px 14px 11px 16px',
          fontWeight: 800,
          fontSize: 13.5,
          cursor: 'pointer',
          boxShadow: '0 6px 20px rgba(79,70,229,.40)',
        }}
      >
        <span
          aria-hidden
          className={live && botState !== 'listening' ? 'aura-step-active' : undefined}
          style={{ width: 9, height: 9, borderRadius: '50%', background: live ? STATE_DOT[botState] : '#fff' }}
        />
        Aura Support
        <span style={{ fontWeight: 600, opacity: 0.9 }}>· {live ? STATE_LABEL[botState] : 'Connecting…'}</span>
        <span aria-hidden style={{ marginLeft: 4, fontSize: 12, opacity: 0.9 }}>⤢</span>
      </button>
      <button
        onClick={onEnd}
        title="End call"
        style={{
          background: PRIMARY_DARK,
          color: '#fff',
          border: 'none',
          borderRadius: '0 24px 24px 0',
          padding: '11px 14px',
          fontWeight: 800,
          fontSize: 13.5,
          cursor: 'pointer',
          boxShadow: '0 6px 20px rgba(79,70,229,.40)',
        }}
      >
        ✕
      </button>
    </div>
  );
}

export function AuraAssistant() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const { handleUiCommand, registerAgentSend, snapshot, rev } = useAura();

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type` directly.
  const session = useVoqalSession({
    apiBase: AURA.apiBase,
    tenantSlug: AURA.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the panel's error state.
    publishableKey: AURA.publishableKey ?? '',
    agentId: AURA.agentId,
    // STT/TTS come from this demo's config, so the pipeline is declared once.
    pipeline: AURA.pipeline,
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
  const chrome = chromeBot(botState);

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

  const openAndConnect = () => {
    setOpen(true);
    setMinimized(false);
    if (status === 'idle' || status === 'error') connect();
  };
  const hangUp = async () => {
    await disconnect();
    setOpen(false);
    setMinimized(false);
  };

  if (!open) {
    return (
      <button
        onClick={openAndConnect}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 1200,
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`,
          color: '#fff',
          border: 'none',
          borderRadius: 28,
          padding: '12px 18px',
          fontWeight: 800,
          fontSize: 14,
          cursor: 'pointer',
          boxShadow: '0 6px 20px rgba(79,70,229,.40)',
        }}
      >
        <span aria-hidden style={{ width: 9, height: 9, borderRadius: '50%', background: '#fff' }} /> Ask Aura Support
      </button>
    );
  }

  // The bot audio + visualizer live inside the provider and must stay mounted
  // whether the panel is expanded or minimized — so minimizing never drops the
  // call. We render the provider once and switch only the visible chrome below
  // it. (The ui_command-in / state_sync-out bridges are the hook's effects
  // above, so they persist regardless of this panel's open/minimized chrome.)
  const liveControls = client && (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      {minimized ? (
        <MinimizedBar botState={chrome} live={status === 'live'} onExpand={() => setMinimized(false)} onEnd={hangUp} />
      ) : (
        <div
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 1200,
            width: 300,
            maxWidth: 'calc(100vw - 32px)',
            background: '#fff',
            borderRadius: 18,
            boxShadow: '0 16px 40px rgba(26,22,32,.20)',
            border: '1px solid #E6E2F2',
          }}
        >
          <div
            style={{
              background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`,
              color: '#fff',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderTopLeftRadius: 18,
              borderTopRightRadius: 18,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14 }}>Aura Support</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                onClick={() => setMinimized(true)}
                title="Minimize (keep talking)"
                style={{ background: 'rgba(255,255,255,.2)', border: 'none', color: '#fff', borderRadius: 8, width: 24, height: 24, cursor: 'pointer', fontSize: 16, lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                —
              </button>
              <button
                onClick={hangUp}
                title="End call"
                style={{ background: 'rgba(255,255,255,.2)', border: 'none', color: '#fff', borderRadius: 8, width: 24, height: 24, cursor: 'pointer', fontSize: 14 }}
              >
                ✕
              </button>
            </div>
          </div>

          <div style={{ padding: '18px 16px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
            {status === 'live' ? (
              <>
                <BotVisualizer botState={chrome} />
                <div style={{ fontSize: 12.5, fontWeight: 700, color: PRIMARY, height: 16 }}>{STATE_LABEL[chrome]}</div>
                <div style={{ fontSize: 11, color: '#6E6470', textAlign: 'center', lineHeight: 1.4 }}>
                  Ask anything — e.g. “Where do I download my interest certificate for tax filing?”
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 6, width: '100%' }}>
                  <UserAudioControl size="lg" dropdownMenuLabel="Audio devices" microphoneLabel="Microphone" speakerLabel="Speaker" />
                  <button
                    onClick={hangUp}
                    title="End call"
                    style={{ display: 'flex', alignItems: 'center', gap: 6, height: 40, padding: '0 14px', borderRadius: 10, background: PRIMARY_DARK, border: 'none', cursor: 'pointer', color: '#fff', fontSize: 13, fontWeight: 700 }}
                  >
                    ✕ End
                  </button>
                </div>
              </>
            ) : (
              <>
                <CircularWaveform isThinking size={116} color1={PRIMARY} color2={ACCENT} />
                <div style={{ fontSize: 12.5, color: '#6E6470' }}>Connecting…</div>
              </>
            )}
          </div>
        </div>
      )}
    </PipecatClientProvider>
  );

  if (liveControls) return liveControls;

  // No client yet: error or initial connecting (no provider chrome to keep mounted).
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 1200,
        width: 300,
        maxWidth: 'calc(100vw - 32px)',
        background: '#fff',
        borderRadius: 18,
        boxShadow: '0 16px 40px rgba(26,22,32,.20)',
        border: '1px solid #E6E2F2',
      }}
    >
      <div
        style={{
          background: `linear-gradient(135deg, ${PRIMARY} 0%, ${ACCENT} 100%)`,
          color: '#fff',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderTopLeftRadius: 18,
          borderTopRightRadius: 18,
        }}
      >
        <div style={{ fontWeight: 800, fontSize: 14 }}>Aura Support</div>
        <button
          onClick={hangUp}
          title="Close"
          style={{ background: 'rgba(255,255,255,.2)', border: 'none', color: '#fff', borderRadius: 8, width: 24, height: 24, cursor: 'pointer', fontSize: 14 }}
        >
          ✕
        </button>
      </div>
      <div style={{ padding: '18px 16px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
        {status === 'error' ? (
          <>
            <div style={{ fontSize: 13, color: PRIMARY, textAlign: 'center', lineHeight: 1.4 }}>{error || 'Something went wrong.'}</div>
            <button onClick={connect} style={{ background: PRIMARY, color: '#fff', border: 'none', borderRadius: 10, padding: '8px 18px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
              Try again
            </button>
          </>
        ) : (
          <>
            <CircularWaveform isThinking size={116} color1={PRIMARY} color2={ACCENT} />
            <div style={{ fontSize: 12.5, color: '#6E6470' }}>Connecting…</div>
          </>
        )}
      </div>
    </div>
  );
}
