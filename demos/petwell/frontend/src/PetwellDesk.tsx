/**
 * The Petwell site's voice layer — a glow around the viewport and Tushar's dock.
 *
 * The website is the star. The call shows itself two ways: a glow around the
 * whole viewport ({@link AmbientPresence}) whose hue and motion carry its state,
 * and Tushar's dock at the bottom right (`DeskDock.tsx`), which holds every
 * control the call has — the button that starts it, his face, mute and end.
 *
 * Everything here is stock pipecat: `PipecatAppBase` does the two-step connect
 * and owns the client; the brain's `session.dispatch(...)` arrives on
 * `RTVIEvent.UICommand` as `{ command, payload }`. The only Voqalize-specific
 * code is the connect request and the one line over its answer, in
 * `src/config.ts`.
 *
 * Two bridges tie the call to the booking store:
 *   - every `ui-command` replays onto the store, so the assistant drives the screen;
 *   - a client→bot channel is registered on the store, so the owner's taps and
 *     the final Send Request reach the brain as typed app events.
 *
 * A call that ends fully unmounts its `PipecatAppBase`; the next tap mints a
 * fresh client on a fresh session.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
  useVoqalizeMedia,
} from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "./config";
import { DeskInvite, DeskLive } from "./DeskDock";
import { useSite } from "./store";

/** The page, handed the one thing the call contributes: Tushar's dock — the call
 * button, his face, and the mute and end controls, bottom right. */
type RenderDesk = (dock: ReactNode) => ReactNode;

const BRAND = "#5c42bf";

// Petwell's own purple, so the ring reads as the hospital's desk. While it reasons
// the ring lifts to a pale lavender — a shift in brightness, so "thinking" reads at
// the edge of vision. Offline is the page's own tint.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: BRAND,
  listening: BRAND,
  thinking: "#a78bfa",
  speaking: BRAND,
  offline: "#e4defa",
};

// ── Session owner ─────────────────────────────────────────────────────────────

export function PetwellDesk({
  children,
}: {
  children: RenderDesk;
}) {
  // `joined`: the consent notice has been dismissed once — it never reappears
  // for a reconnect. `sessionKey` mints a fresh `PipecatAppBase` (and so a fresh
  // `PipecatClient`) for every call; `live` is whether one is currently mounted.
  const [joined, setJoined] = useState(false);
  const [live, setLive] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);

  const begin = useCallback(() => {
    setJoined(true);
    setSessionKey((k) => k + 1);
    setLive(true);
  }, []);

  if (!live) {
    return (
      <>
        <DemoGate
          open={!joined}
          title="Petwell Appointment Desk"
          blurb="Talk to Tushar, the hospital's AI front desk, in English, Hindi or eight more Indian languages — he finds a branch, answers from the Health Hub and books the visit on screen as you speak."
          accent={PRESENCE.listening}
          onJoin={begin}
        />
        <AmbientPresence palette={PRESENCE} />
        {children(<DeskInvite connecting={false} error="" onStart={begin} />)}
      </>
    );
  }

  return (
    <CallSession key={sessionKey} onEnded={() => setLive(false)}>
      {children}
    </CallSession>
  );
}

/**
 * Mints the session and owns the client for one call. `PipecatAppBase` builds
 * the `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` as soon as the client exists. The media is ours —
 * `@voqalize/client-transport` through `useVoqalizeMedia` — so the base is told
 * `noAudioOutput`, or Tushar would play twice.
 */
function CallSession({
  children,
  onEnded,
}: {
  children: RenderDesk;
  onEnded: () => void;
}) {
  // No pipeline override: this agent's voice and language are declared on its
  // brain (backend/brain.py), which is the only place they belong.
  //
  // Memoized: this is a dependency of PipecatAppBase's connect-on-mount effect,
  // so an unmemoized object literal would re-fire that effect (and re-start the
  // call) on every render.
  // No language rides the request: every call opens in English, and Tushar
  // switches by himself the moment he hears another language.
  const params = useMemo(() => connectRequest({ surface: "petwell-web" }), []);
  const media = useVoqalizeMedia();

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      transportOptions={media.transportOptions}
      onClient={media.onClient}
      noAudioOutput
      connectOnMount
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect }) => (
        <CallBridge error={error ?? null} onRetry={handleConnect} onEnded={onEnded}>
          {children}
        </CallBridge>
      )}
    </PipecatAppBase>
  );
}

/** The ring, the presence control, and the two bridges to the store. */
function CallBridge({
  error,
  onRetry,
  onEnded,
  children,
}: {
  error: string | null;
  onRetry?: () => void | Promise<void>;
  onEnded: () => void;
  children: RenderDesk;
}) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected: isLive } = usePipecatConnectionState();
  const { handleUiCommand, registerAgentSend } = useSite();
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");

  // Screen ← assistant. The brain's `session.dispatch(HighlightItem(...))`
  // lands here as `{ command: "highlight_item", payload: {...} }`.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) =>
        handleUiCommand(command, (payload ?? {}) as Record<string, unknown>),
      [handleUiCommand],
    ),
  );

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("idle"), []));

  // Register the store's assistant-send channel once the call is live, so the
  // owner's taps and Send Request reach the bot.
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((event, payload) => client.sendUIEvent(event, payload));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Dev-only: expose the live client for driving the flow without a mic.
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __petwellDesk?: unknown }).__petwellDesk = client;
    return () => {
      delete (window as unknown as { __petwellDesk?: unknown }).__petwellDesk;
    };
  }, [client]);

  const hangUp = async () => {
    await client?.disconnect();
    onEnded();
  };

  const connecting = !isLive && !error && transportState !== "error";
  // Tushar's face mounts as soon as there is a client, hidden while the call
  // connects: its first frame — a new GPU context and every shader compiled —
  // then lands behind the connecting bar rather than on his greeting.
  const dock = (
    <>
      {client ? (
        <DeskLive client={client} activity={activity} onEnd={hangUp} live={isLive} />
      ) : null}
      {isLive ? null : (
        <DeskInvite
          connecting={connecting}
          error={error || (transportState === "error" ? "Something went wrong." : "")}
          onStart={() => onRetry?.()}
        />
      )}
    </>
  );

  return (
    <>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
      {children(dock)}
    </>
  );
}
