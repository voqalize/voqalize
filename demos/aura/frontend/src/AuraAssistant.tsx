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
 * while the customer reads the page. **The call has one door and one cockpit.**
 * The door is the corner launcher wearing Aria's portrait; the cockpit is the
 * tile, where the mic, the device picker and the end button sit directly under
 * her picture (`AuraDock`). The bank's own navigation row gets a status line
 * while a call is running and nothing at all before one — reached through the
 * `children` render-prop, so `pages.tsx` keeps owning its chrome. Controls in
 * the header and a transcript in a floating panel were two halves of one call in
 * two places; a second "Ask Aura Support" button beside the launcher was two
 * doors to the same microphone.
 *
 * `PipecatAppBase` mounts its `PipecatClientProvider` (and `BotAudioOutput`, via
 * `noThemeProvider`) as soon as the client exists, not when the call goes live —
 * Aria's audio track is announced once, from the remote track's `unmute` a few
 * hundred milliseconds after the peer connection is up, so a listener that
 * subscribes late finds nothing to read. `connectOnMount` is off: nothing opens
 * a microphone until the visitor has read the notice and joined.
 *
 * Mounted once at the route level; navigation is React state, so the call
 * survives screen changes.
 *
 * ## How a call starts, and why it starts that way
 *
 * The page loads as a bank site loads: nothing covering it, nothing asking for
 * anything. Aria is one launcher in the bottom-right corner — the position every
 * customer already reaches for, and the position the bank's *current* assistant
 * occupies — plus the same small control in the bank's own header. Either one
 * opens the pre-call sheet: what this is, which language, the recording notice,
 * one button. The microphone opens after that button and not before.
 *
 * That sheet used to be the *first* thing the page rendered, before the visitor
 * had asked for anything, which is a demo's habit rather than a bank's: it hid
 * the product behind a dark modal at the moment a stakeholder is deciding what
 * the product looks like. It is now `dismissible` for the same reason — the help
 * centre is genuinely usable without a call, so "Not now" has to be a real
 * answer.
 *
 * Three things sit on top of that base, and each is additive rather than a
 * replacement — the ring is the demo's argument and nothing here takes it away:
 *
 *   - **the language**, picked in the sheet before the call exists and sent in
 *     the connect request's `init`. The brain reads it once and moves the
 *     recognizer, the reference clip and the prompt together; the page names a
 *     language and configures nothing (see `language.tsx`, and `backend/brain.py`
 *     → the Language section, which is the authority);
 *   - **the meeting tile**, `@voqalize/avatar`'s `myna` rig driven by the
 *     runtime's own `avatar` messages on the data channel the transcript already
 *     rides, framed as the picture-in-picture window of a video call — name
 *     plate, running timer, captions, and the call's controls beneath it;
 *   - **the chat column** inside that tile, off by default, which shows both
 *     halves of the conversation in voice-ui-kit's karaoke rendering and lets the
 *     customer type into it.
 *
 * The last two live in `AuraDock`; `?avatar=0` and `?chat=1` move their
 * defaults, which is how you show the same demo with and without them in one
 * sitting.
 *
 * Aura's HMAC-authenticated sign-in handshake (the browser answering a
 * dispatched `open_auth` with a signed nonce) rides this same `ui-command` /
 * `client-message` pair and needs nothing extra here — the store's
 * `confirmAuth`/`cancelAuth` already echo the nonce back over `agentSend`.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { useAura } from './store';
import { connectRequest, withRealHeaders } from './config';
import { AuraDock } from './AuraDock';
import { DEFAULT_LANGUAGE, LanguagePicker, type LanguageName } from './language';

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

// ── What the bank's own navigation row says about the call ───────────────────

// Nothing, before one starts. The row used to carry a second "Ask Aura Support"
// button beside the corner launcher — two doors to the same microphone, a step
// apart, saying different things. The launcher is the door: it is the thing
// wearing Aria's face, it is where the eye goes, and the pre-call sheet it opens
// already reports connecting and failure states (`DemoGate`'s `busy`/`error`).

/**
 * Live: a status, and only a status.
 *
 * The mic, the device picker and the end button used to be here, in the bank's
 * own navigation row, while the transcript sat in a panel at the other end of
 * the page — two halves of one call in two places. They are now in the tile,
 * directly under Aria's picture, where a decade of video calls has taught
 * everyone to look for them (`AuraDock`).
 *
 * What stays is one non-interactive line saying a call is running, because a
 * bank site that gives no sign of it in its own chrome is worse than one that
 * does. It reads the same `activity` the ring and the tile read.
 */
function LiveStatus({ activity }: { activity: AmbientPresenceActivity }) {
  return (
    <div className="aura-presence">
      <span className={`aura-presence-live is-${activity}`} aria-hidden />
      <span className="aura-presence-label">Live with Aria · {STATE_LABEL[activity]}</span>
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
      /* The live pip: the header's whole share of a running call. */
      .aura-presence-live {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #34D399;
        flex: none;
        box-shadow: 0 0 0 3px rgba(52,211,153,.20);
        transition: background .2s ease, box-shadow .2s ease;
      }
      .aura-presence-live.is-thinking { background: #F0A020; box-shadow: 0 0 0 3px rgba(240,160,32,.22); }
      .aura-presence-live.is-speaking { background: ${ACCENT}; box-shadow: 0 0 0 3px rgba(139,92,246,.24); }
    `}</style>
  );
}

// ── Session owner ─────────────────────────────────────────────────────────────

/** What this page tells the brain about the call, before the call exists. */
interface AuraInit extends Record<string, unknown> {
  surface: string;
  language: LanguageName;
}

/**
 * Mints the session and owns the client. No `config`: the page names a language
 * and the brain resolves it, because that one choice also has to move the prompt
 * — one layer owns it, and it is the brain (backend/brain.py).
 */
export function AuraAssistant({ children }: { children: (presence: ReactNode) => ReactNode }) {
  // One object for the life of the page, and the sheet's picker **mutates it in
  // place**. That is deliberate and it is not a shortcut: `startBotParams` is a
  // dependency of `PipecatAppBase`'s client-creation effect, so handing it a
  // fresh object when the customer picks a language tears the `PipecatClient`
  // down and builds another one — on the click before the join, and again on the
  // join itself. Nothing reads this object until `connect` serializes it, which
  // is after the picker has written to it, so the mutation is invisible to
  // everything except the request that carries it.
  const init = useRef<AuraInit>({ surface: 'aura-web', language: DEFAULT_LANGUAGE }).current;
  const params = useMemo(() => connectRequest(init), [init]);

  // **Everything the customer has decided lives here, above `PipecatAppBase`,
  // and that placement is load-bearing.** `PipecatAppBase` renders its children
  // bare while it builds the transport and wrapped in `PipecatClientProvider`
  // once the client exists — two different trees, so React unmounts and remounts
  // everything below it the moment the client arrives, a second or so into the
  // page. Any state held down there is silently reset by that.
  //
  // That is what the sheet's old `joined` flag was: press the button early
  // enough — while `handleConnect` is still undefined, so the click connects
  // nothing — and the remount hands you back the notice you just accepted, with
  // no call running. The intent (`wantCall`) is kept up here instead and the
  // session below reconciles toward it, which also means a click that lands
  // before the client is ready is answered when it *is* ready rather than
  // dropped.
  const [language, setLanguage] = useState<LanguageName>(init.language);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [wantCall, setWantCall] = useState(false);
  const flags = useMemo(readFlags, []);

  const openSheet = useCallback(() => setSheetOpen(true), []);
  const pickLanguage = useCallback(
    (name: LanguageName) => {
      init.language = name;
      setLanguage(name);
    },
    [init],
  );
  // Live: the sheet has done its job. Failed: it stays open with the reason on
  // it — a modal that closes onto a dead call is worse than one that explains.
  const onLive = useCallback(() => {
    setSheetOpen(false);
    setWantCall(false);
  }, []);
  const onFailed = useCallback(() => setWantCall(false), []);

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
          onConnect={handleConnect}
          onDisconnect={handleDisconnect ?? (async () => {})}
          flags={flags}
          language={language}
          onPickLanguage={pickLanguage}
          sheetOpen={sheetOpen}
          onOpenSheet={openSheet}
          onCloseSheet={() => setSheetOpen(false)}
          wantCall={wantCall}
          onWantCall={() => setWantCall(true)}
          onLive={onLive}
          onFailed={onFailed}
        >
          {children}
        </AuraSession>
      )}
    </PipecatAppBase>
  );
}

/**
 * The two switches this demo is shown with, read once from the query string.
 *
 * Both surfaces are new next to the ambient ring the demo has always had, and a
 * room comparing them wants the same page with each one off — so they are query
 * flags rather than a rebuild. The avatar is on by default because it is the
 * thing being shown; the chat is off, because a text box the visitor never asked
 * for reads as an admission that the voice is not enough.
 */
function readFlags(): { avatar: boolean; chat: boolean } {
  const q = new URLSearchParams(window.location.search);
  const off = (v: string | null) => v === '0' || v === 'false';
  const on = (v: string | null) => v === '' || v === '1' || v === 'true';
  return { avatar: !off(q.get('avatar')), chat: q.has('chat') && on(q.get('chat')) };
}

// Rendered inside `PipecatAppBase`'s own `PipecatClientProvider`, so every
// pipecat hook below sees the live client the moment one exists.
function AuraSession({
  error,
  onConnect,
  onDisconnect,
  flags,
  language,
  onPickLanguage,
  sheetOpen,
  onOpenSheet,
  onCloseSheet,
  wantCall,
  onWantCall,
  onLive,
  onFailed,
  children,
}: {
  error: string | null;
  /** `undefined` until `PipecatAppBase` has a client — see the reconciler below. */
  onConnect: (() => void | Promise<void>) | undefined;
  onDisconnect: () => void | Promise<void>;
  flags: { avatar: boolean; chat: boolean };
  language: LanguageName;
  onPickLanguage: (name: LanguageName) => void;
  sheetOpen: boolean;
  onOpenSheet: () => void;
  onCloseSheet: () => void;
  wantCall: boolean;
  onWantCall: () => void;
  onLive: () => void;
  onFailed: () => void;
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

  // ── The reconciler ──────────────────────────────────────────────────────────
  //
  // The customer says *whether they want a call*; this says when one can start.
  // `onConnect` is `PipecatAppBase`'s `handleConnect`, and it is `undefined`
  // until the transport module has been imported and the client built — a real
  // window on a cold load, and long enough for someone to have already pressed
  // the button. Holding the intent and firing it on readiness is the difference
  // between "the notice came back and nothing happened" and a call.
  //
  // `attempt` keeps it to one connect per intent. A remount resets it, which is
  // exactly right: a remount is the client arriving, and the attempt it forgets
  // is the one that connected nothing.
  const connect = useRef(onConnect);
  connect.current = onConnect;
  const attempt = useRef(false);
  useEffect(() => {
    if (!wantCall) {
      attempt.current = false;
      return;
    }
    if (!client || attempt.current) return;
    attempt.current = true;
    void connect.current?.();
  }, [wantCall, client]);

  // `handleConnect` catches its own failures and reports them through `error`
  // rather than rejecting, so the sheet learns how it went from these two and
  // not from awaiting the click.
  useEffect(() => {
    if (isConnected) onLive();
  }, [isConnected, onLive]);
  useEffect(() => {
    if (error) onFailed();
  }, [error, onFailed]);

  const presence = isConnected ? <LiveStatus activity={activity} /> : null;

  return (
    <>
      <DemoGate
        open={sheetOpen}
        title="Talk to Aria"
        blurb="Aura's support line, answered by voice. Ask a question and watch the help centre work the answer out on screen."
        accent={PRESENCE.listening}
        theme="light"
        joinLabel="Start call"
        busy={wantCall || status === 'connecting'}
        error={status === 'error' ? error || 'Connection issue' : null}
        dismissible
        dismissLabel="Not now"
        onDismiss={onCloseSheet}
        onJoin={onWantCall}
      >
        <LanguagePicker value={language} onChange={onPickLanguage} />
      </DemoGate>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
      <PresenceStyles />
      <AuraDock
        client={client ?? null}
        activity={activity}
        avatar={flags.avatar}
        chat={flags.chat}
        phase={isConnected ? 'live' : status === 'connecting' || wantCall ? 'connecting' : 'idle'}
        onStart={onOpenSheet}
        onEnd={() => void onDisconnect()}
      />
      {children(presence)}
    </>
  );
}
