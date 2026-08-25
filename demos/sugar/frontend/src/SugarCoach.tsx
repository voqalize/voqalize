/**
 * The Sugar Coach call session — the live voice leg of the demo.
 *
 * Unlike the launcher-style widgets, this demo's call IS the UX: the patient taps
 * Join on the check-in notification, and this component mounts, connects, and
 * renders the slim in-call bar pinned to the top of the app screen. Hanging up
 * ends the phase (→ ended screen).
 *
 * Presence is ambient, not docked: the {@link AmbientPresence} ring glows around
 * the whole screen and carries the coach's state (listening / thinking /
 * speaking) peripherally, so the bar itself is left with only the identity bits —
 * the coach's name, the state label + call timer, a mute toggle and the end-call
 * button.
 *
 * **This is exactly the surface an external developer embeds, and it is almost
 * entirely pipecat's.** Voice-ui-kit's `PipecatAppBase` does pipecat's whole
 * two-step connect (`startBot` against the control plane, then `connect` the
 * transport) and owns the client's lifecycle; everything below it is a stock
 * `PipecatClient`: `usePipecatClientTransportState`/`usePipecatConnectionState`
 * report the call, RTVI events say who is speaking, `PipecatAppBase`'s own
 * `BotAudioOutput` plays the coach, and the brain's `session.dispatch(...)`
 * arrives on `RTVIEvent.UICommand` as `{ command, payload }`. The only
 * Voqalize-specific code on the page is the request that starts the call and
 * the one line over its answer, both in `src/config.ts` — there is no client
 * library to install.
 *
 * Two bridges tie the call to the screen:
 *   - every `ui-command` replays onto the shared sugar store, so the coach drives
 *     the screen;
 *   - a compact `{ screen: snapshot() }` is echoed back to the coach
 *     (`state_sync`) on connect and after every change — so she always knows
 *     what's logged, including taps the patient makes by hand.
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { usePipecatClient, usePipecatClientMicControl, usePipecatClientTransportState, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import { AmbientPresence, type AmbientPresenceActivity, type AmbientPresencePalette } from "@voqalize/demo-kit";
import { Mic, MicOff } from "lucide-react";
import { connectRequest, withRealHeaders } from "./config";
import { COACH_NAME } from "./data";
import { useSugar } from "./store";

const GREEN = "#0E7A5F";
const RED = "#D6453D";
const AMBER = "#C97F1E";

// Sugar's reading of the presence ring: the app's own evergreen while the coach
// is listening or talking, warming to the care-plan amber the moment she's
// working something out — the one state a patient reads out of the corner of the
// eye. Off the call it drops to a barely-there oat seam, the app's own line colour.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: GREEN,
  listening: GREEN,
  thinking: AMBER,
  speaking: GREEN,
  offline: "#D6D2C6",
};

// The bar's static state dot — the ring carries the motion, this just names it.
const STATE_DOT: Record<AmbientPresenceActivity, string> = {
  idle: "#7BD9BE",
  listening: "#7BD9BE",
  thinking: "#F2C063",
  speaking: "#2FA875",
};

const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Listening",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};

function CallTimer() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSec((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  const mm = String(Math.floor(sec / 60)).padStart(1, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return <>{mm}:{ss}</>;
}

/**
 * Mints the session and owns the client. `PipecatAppBase` builds the
 * `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` — with its own `BotAudioOutput` in place of a
 * hand-mounted `PipecatClientAudio` — as soon as the client exists, **not**
 * when the call goes live: the bot's audio track is announced once, from the
 * remote track's `unmute` a few hundred milliseconds after the peer
 * connection is up, and `client.tracks()` only ever reports the local ones. A
 * listener that subscribes late finds nothing to read, and the call plays
 * silently — RTP arriving, decoded by nobody. Only the bar chrome may depend
 * on the state.
 */
export function SugarCallSession() {
  const { brainPayload, sessionConfig } = useSugar();

  // The patient's LanguageToggle choice is one answer read by two layers, so it
  // rides both halves of the request. In `init` it reaches the coach, which
  // greets and reasons in it. In `config` it reaches the runtime, which listens
  // and speaks in it — both legs together, so the recognizer and the reference
  // clip cannot drift apart. The scenario's PATIENT CONTEXT rides `init` too.
  //
  // The page sends the language because the page is where it was chosen, before
  // the call existed: the session opens in it and the greeting is already right,
  // with no configure round trip to have ordered correctly ahead of the one
  // utterance nobody gets to re-run. Changing it mid-call stays the brain's, via
  // its `switch_language` tool.
  //
  // Memoized: this is a dependency of PipecatAppBase's connect-on-mount
  // effect, so an unmemoized object literal would re-fire that effect (and
  // re-mint a session) on every render.
  const params = useMemo(
    () =>
      connectRequest(
        { surface: "sugar-web", ...(brainPayload() as Record<string, unknown>) },
        sessionConfig(),
      ),
    [brainPayload, sessionConfig],
  );

  return (
    <PipecatAppBase
      transportType="smallwebrtc"
      connectOnMount
      noThemeProvider
      startBotParams={params}
      startBotResponseTransformer={withRealHeaders}
    >
      {({ error, handleConnect }) => <CallBar error={error ?? null} onRetry={handleConnect} />}
    </PipecatAppBase>
  );
}

/** The in-call bar, the presence ring, and the two bridges to the store. */
function CallBar({ error, onRetry }: { error: string | null; onRetry?: () => void | Promise<void> }) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected: isLive } = usePipecatConnectionState();
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const { endCall, handleUiCommand, registerAgentSend, rev, snapshot } = useSugar();
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");

  // Screen ← coach. The brain's `session.dispatch(LogMeal(...))` lands here as
  // `{ command: "log_meal", payload: {...} }`. Subscribing to the event rather
  // than registering thirteen `useUICommandHandler`s: the store is one reducer,
  // and an unknown command is a no-op there by design — the brain and this page
  // ship separately.
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

  // Register the store's coach-send channel once the call is live.
  useEffect(() => {
    if (!isLive || !client) return;
    registerAgentSend((type, data) => client.sendClientMessage(type, data));
    return () => registerAgentSend(null);
  }, [isLive, client, registerAgentSend]);

  // Debounced snapshot push: on connect and after every change (rev), so the
  // coach stays in sync with taps the patient makes by hand too. The sugar brain
  // reads `data.screen` (see SugarBrain._ingest_state).
  useEffect(() => {
    if (!isLive || !client) return;
    const t = setTimeout(() => client.sendClientMessage("state_sync", { screen: snapshot() }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, client, rev]);

  // Dev-only: drive the flow without a mic.
  //   window.__sugar.ui('log_meal', {meal_type:'dinner', time_label:'8 PM', items:[...], total_calories: 500})
  //   window.__sugar.sendText('I had two rotis and dal for dinner')
  useEffect(() => {
    if (!import.meta.env.DEV || !client) return;
    (window as unknown as { __sugar?: unknown }).__sugar = {
      client,
      ui: handleUiCommand,
      sendText: (t: string) => client.sendText(t),
    };
    return () => {
      delete (window as unknown as { __sugar?: unknown }).__sugar;
    };
  }, [client, handleUiCommand]);

  const hangUp = async () => {
    await client?.disconnect();
    endCall();
  };

  // The ring is `position: fixed` and self-positioning — it rides alongside the
  // bar in the tree, but paints around the whole screen.
  const bar = (inner: ReactNode) => (
    <>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 14px",
          background: "linear-gradient(135deg, #0F2B23 0%, #123A2E 100%)",
          color: "#fff",
          borderRadius: 16,
          boxShadow: "0 8px 24px rgba(10,40,30,.35)",
        }}
      >
        {inner}
      </div>
    </>
  );

  if (error || transportState === "error") {
    return bar(
      <>
        <span style={{ fontSize: 12.5, flex: 1, lineHeight: 1.35 }}>{error || "Call failed."}</span>
        <button onClick={onRetry} style={pillBtn(GREEN)}>Retry</button>
        <button onClick={hangUp} style={pillBtn(RED)}>✕</button>
      </>,
    );
  }

  if (!isLive) {
    return bar(
      <>
        <span className="sugar-pulse" aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#7BD9BE" }} />
        <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>{COACH_NAME}</span>
        <span style={{ fontSize: 12, opacity: 0.85 }}>Connecting…</span>
        <button onClick={hangUp} style={pillBtn(RED)} title="End call">✕</button>
      </>,
    );
  }

  return bar(
    <>
      <span
        aria-hidden
        style={{ flex: "none", width: 9, height: 9, borderRadius: "50%", background: STATE_DOT[activity] }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 800, lineHeight: 1.15 }}>{COACH_NAME}</div>
        <div style={{ fontSize: "var(--sugar-mini)", opacity: 0.8 }}>
          {STATE_LABEL[activity]} · <CallTimer />
        </div>
      </div>
      <button
        onClick={() => enableMic(!isMicEnabled)}
        style={{
          ...pillBtn(isMicEnabled ? "rgba(255,255,255,.14)" : AMBER),
          width: 34,
          height: 34,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        title={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={15} /> : <MicOff size={15} />}
      </button>
      <button onClick={hangUp} style={{ ...pillBtn(RED), width: 34, height: 34, borderRadius: "50%", fontSize: 13 }} title="End call">
        ⏻
      </button>
    </>,
  );
}

function pillBtn(bg: string): CSSProperties {
  return {
    background: bg,
    color: "#fff",
    border: "none",
    borderRadius: 10,
    padding: "6px 12px",
    fontWeight: 700,
    fontSize: 12,
    cursor: "pointer",
  };
}
