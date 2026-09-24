/**
 * The Vantage Bank branch kiosk — session plumbing, and nothing else.
 *
 * The call is stock pipecat: `PipecatAppBase` owns the WebRTC transport and the
 * mic, `connectRequest` (`src/config.ts`) is the one request that is ours, and
 * everything after connect is pipecat's own. Tess drives the totem over the
 * standard `ui-command` channel; the customer's taps leave over `ui-event`. Both
 * halves are typed in `actions.gen.ts` and replayed by the store.
 *
 * **The gate is mandatory, it comes first, and it is the one way in.** Its
 * button is Start: `PipecatAppBase` mounts with `connectOnMount`, so it is not
 * rendered at all until the visitor has read the notice and pressed it — the
 * microphone cannot open before that, by construction rather than by a flag —
 * and Tess's greeting is the first thing that happens after it. Nothing behind
 * the gate offers a second way to begin.
 *
 * Two things are held above `PipecatAppBase` on purpose, because it renders its
 * children bare while it builds the transport and wrapped in a provider once the
 * client exists — two trees, so anything below it is remounted a second into the
 * page. The consent tick is one (a tick made early would come back unticked);
 * the screen language is the other. The store is above it for the same reason,
 * so a reconnect does not throw the conversation away.
 *
 * There is no idle timer and no auto-reset. Start over, in the header, clears
 * the answers and puts the first question back; the call stays up.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TransportState, UICommandData } from '@pipecat-ai/client-js';
import { RTVIEvent } from '@pipecat-ai/client-js';
import {
  usePipecatClient,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from '@pipecat-ai/client-react';
import { PipecatAppBase } from '@pipecat-ai/voice-ui-kit';
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from '@voqalize/demo-kit';
import { COLOR } from './brand';
import { connectRequest, withRealHeaders } from './config';
import { KioskTotem } from './KioskTotem';
import { TessCaptions, TessPlate, TessTile } from './TessTile';
import { KioskProvider, useKiosk } from './store';
import type { Language } from './language';

/** Vantage's reading of the shared presence ring. */
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: COLOR.brand,
  listening: COLOR.accent,
  thinking: '#E0662A',
  speaking: COLOR.leaf,
  offline: 'rgba(252, 250, 249, 0.22)',
};

/** What the page tells the brain about the call, before the call exists. */
const INIT: Record<string, unknown> = { surface: 'branch-kiosk' };

export function KioskApp() {
  return (
    <KioskProvider>
      <Kiosk />
    </KioskProvider>
  );
}

function Kiosk() {
  const [joined, setJoined] = useState(false);
  const [agreed, setAgreed] = useState(false);
  // The store owns the screen's language: Tess changes it, when she hears the
  // customer speak another one, and the copy follows her action.
  const {
    state: { language },
  } = useKiosk();
  const [error, setError] = useState<string | null>(null);
  // What the ring outside the call renders. Lifted out of the live tree, whose
  // hooks are the only place a transport or activity value exists.
  const [transportState, setTransportState] = useState<TransportState>('disconnected');
  const [activity, setActivity] = useState<AmbientPresenceActivity>('idle');

  // A connect that failed puts the visitor back at the notice with the reason on
  // it — a gate that closes onto a dead call is worse than one that explains.
  const handleError = useCallback((message: string) => {
    setError(message || 'Could not connect. Please try again.');
    setJoined(false);
  }, []);

  const join = useCallback(() => {
    setError(null);
    setJoined(true);
  }, []);

  return (
    <>
      <DemoGate
        open={!joined}
        title="Vantage Bank card kiosk"
        blurb="Press Start and talk to Tess. She asks four quick questions, ranks three Vantage cards for you, and gives you a code for the banker's desk."
        joinLabel="Start"
        accent={COLOR.brand}
        agreed={agreed}
        onAgreedChange={setAgreed}
        error={error}
        onJoin={join}
      />
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />

      {joined ? (
        <CallSession
          language={language}
          onTransportState={setTransportState}
          onActivity={setActivity}
          onError={handleError}
        />
      ) : (
        // No client to embody yet, so Tess's place wears the plate.
        <KioskTotem
          language={language}
          live={false}
          tess={<TessPlate language={language} />}
        />
      )}
    </>
  );
}

interface SessionProps {
  language: Language;
  onTransportState: (state: TransportState) => void;
  onActivity: (activity: AmbientPresenceActivity) => void;
  onError: (message: string) => void;
}

function CallSession(props: SessionProps) {
  // Frozen for the life of the session: `startBotParams` is a dependency of
  // `PipecatAppBase`'s connect-on-mount effect, and a fresh object on every
  // render would re-mint the call on every render.
  const params = useMemo(() => connectRequest(INIT), []);
  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      connectOnMount
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error }) => <LiveKiosk {...props} error={error ?? null} />}
    </PipecatAppBase>
  );
}

/** Rendered inside `PipecatAppBase`'s provider, so every hook here sees the client. */
function LiveKiosk({
  language,
  onTransportState,
  onActivity,
  onError,
  error,
}: SessionProps & { error: string | null }) {
  const { handleUiCommand, registerAgentSend } = useKiosk();
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const [activity, setActivity] = useState<AmbientPresenceActivity>('idle');

  // Straight from pipecat's own turn-taking events, as `AmbientPresence`
  // prescribes.
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity('listening'), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setActivity('idle'), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity('thinking'), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity('speaking'), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity('idle'), []));

  // Screen ← Tess.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => handleUiCommand(command, payload),
      [handleUiCommand],
    ),
  );

  const sendEvent = useCallback(
    (event: string, payload?: unknown) => client?.sendUIEvent(event, payload),
    [client],
  );

  // Once live: open the mic and register the channel the taps leave by.
  const isConnected = transportState === 'connected' || transportState === 'ready';
  useEffect(() => {
    if (!isConnected) return;
    client?.enableMic(true);
    registerAgentSend(sendEvent);
    return () => registerAgentSend(null);
  }, [isConnected, client, registerAgentSend, sendEvent]);

  useEffect(() => onTransportState(transportState), [transportState, onTransportState]);
  useEffect(() => onActivity(activity), [activity, onActivity]);

  // `handleConnect` reports failure through `error` rather than rejecting, and
  // this fires once per distinct message.
  const reported = useRef<string | null>(null);
  useEffect(() => {
    if (error && reported.current !== error) {
      reported.current = error;
      onError(error);
    }
  }, [error, onError]);

  return (
    <KioskTotem
      language={language}
      live={isConnected}
      tess={<TessTile client={client ?? null} activity={activity} language={language} />}
      captions={<TessCaptions />}
    />
  );
}
