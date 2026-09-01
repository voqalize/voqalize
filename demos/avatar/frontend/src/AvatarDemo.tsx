/**
 * The avatar demo — the open-source talking head explaining itself.
 *
 * One page, one call, one face. The visitor asks how the thing works; the brain
 * brings up a slide, answers against it, and demonstrates whatever it has just
 * described on the face they are already looking at. The call is capped at two
 * minutes **in the brain** — a page is not a place to keep a limit — and this
 * file only shows the clock running down.
 *
 * **The whole browser half of a call is pipecat's.** `PipecatAppBase` does
 * pipecat's two-step connect and owns the client; everything below it is a stock
 * `PipecatClient`. The only Voqalize-specific code on the page is the request
 * that starts the call and the one line over its answer, both in `src/config.ts`.
 * The avatar is `@voqalize/avatar` from npm, handed that same client and nothing
 * else — it reads the state, the gestures and the visemes off the data channel
 * that is already open.
 *
 * Two directions of traffic reach this file:
 *
 *   * **brain → screen**, as RTVI `ui-command`s: the slide, the avatar switch,
 *     the working strip, the end card (`actions.gen.ts` is the generated shape).
 *   * **screen → brain**, as two RTVI `client-message`s. `ready` says the data
 *     channel exists, which is what the opening wave waits for — a brain is
 *     dialled before this page has one, and a gesture sent then goes nowhere.
 *     `pick_avatar` says the visitor chose a face off the strip: the page swaps
 *     the drawing immediately — it owns its own rendering and should not wait a
 *     round trip to redraw — and tells the brain, which is the only end that can
 *     move the voice and the model's context.
 *
 * The face the brain drives and the face a click mounts are the same component;
 * both paths write one piece of state.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import { Avatar } from "@voqalize/avatar/react";
import type { AvatarFactory, AvatarOptions } from "@voqalize/avatar";
import { Github, Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from "@voqalize/demo-kit";
import { asUiAction, unhandledUiAction, type ShowSlide } from "./actions.gen";
import { connectRequest, demo, withRealHeaders } from "./config";
import { DEFAULT_AVATAR, ROSTER, ROSTER_BY_KEY } from "./roster";
import { STYLES } from "./styles";

/** Two minutes, and the page only *reports* it — the brain enforces it. Kept
 *  here so the clock reads the same as the one that will actually hang up. */
const LIMIT_S = 120;

/** Where a visitor goes next. The demo exists to be the front door of an
 *  open-source library, so the links are the point rather than the footer. */
export const LINKS = {
  repo: "https://github.com/voqalize/avatar",
  npm: "https://www.npmjs.com/package/@voqalize/avatar",
  docs: "https://docs.voqalize.com/build/avatar/",
  voqalize: "https://voqalize.com",
};

// The ring's reading for this demo: the avatar's own ink on paper. Violet while
// the model reasons, because it is the one hue that reads as "working" against a
// near-black page without competing with the face.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#8b5cf6",
  listening: "#8b5cf6",
  thinking: "#22d3ee",
  speaking: "#8b5cf6",
  offline: "#3f3f46",
};

const ACTIVITY_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

/** What to say, for a visitor who has never met a voice demo and has two
 *  minutes. Four prompts, each of which lands a different mechanism. */
const OPENERS = [
  "How does the lipsync work?",
  "Show me what thinking looks like.",
  "What else can you look like?",
  "Wave at me.",
];

// ── The face ────────────────────────────────────────────────────────────────

/**
 * The mounted avatar. Every entry in the roster resolves to the same published
 * interface — `createAvatar({mount, client}) -> {destroy()}` — so swapping one
 * is a remount and nothing else. `key` forces that remount: `<Avatar>` reads its
 * options once, at mount, which is the interface being honest about what an
 * avatar is rather than a limitation to work around.
 */
function Face({ avatarKey, client }: { avatarKey: string; client: ReturnType<typeof usePipecatClient> }) {
  const [factory, setFactory] = useState<{ key: string; create: AvatarFactory<AvatarOptions> } | null>(
    null,
  );

  useEffect(() => {
    let live = true;
    const entry = ROSTER_BY_KEY[avatarKey];
    if (!entry) return;
    void entry.load().then((create) => {
      if (live) setFactory({ key: avatarKey, create });
    });
    return () => {
      live = false;
    };
  }, [avatarKey]);

  // Hold the previous face while the next one loads, rather than blanking: a
  // gap where the avatar was is the one thing a talking-head demo cannot do.
  if (!factory) return <div className="av-face is-loading" aria-hidden />;
  return (
    <Avatar
      key={factory.key}
      className="av-face"
      client={client}
      create={factory.create}
      aria-label={`${ROSTER_BY_KEY[factory.key]?.name ?? "The"} avatar`}
    />
  );
}

// ── The panel beside it ─────────────────────────────────────────────────────

/** The slide the brain put up, or the invitation before it has put one up. */
function Panel({ slide, opener }: { slide: ShowSlide | null; opener: boolean }) {
  if (!slide) {
    return (
      <section className="av-panel is-empty">
        <p className="av-panel-kicker">A 2-D talking head for AI voice calls</p>
        <h2>Ask it how it works.</h2>
        <p className="av-panel-lede">
          It draws the architecture on this side of the screen and answers against it. Everything it
          describes, it can also do — because it is the library it is describing.
        </p>
        <ul className="av-openers">
          {OPENERS.map((line) => (
            <li key={line}>“{line}”</li>
          ))}
        </ul>
        {opener ? <p className="av-panel-foot">Two minutes on the clock. Say hello.</p> : null}
      </section>
    );
  }
  return (
    <section className="av-panel" key={slide.id}>
      <p className="av-panel-kicker">{slide.subtitle}</p>
      <h2>{slide.title}</h2>
      <ul className="av-beats">
        {slide.beats.map((beat) => (
          <li key={beat}>{beat}</li>
        ))}
      </ul>
    </section>
  );
}

/** Where to go next, once the two minutes are up. */
function EndCard({ reason, onAgain }: { reason: string; onAgain: () => void }) {
  return (
    <div className="av-end">
      <div className="av-end-card">
        <h2>{reason === "time_limit" ? "That's the two minutes." : "Call ended."}</h2>
        <p>
          The face, the wire format and the lipsync are one MIT-licensed library. Install it, mount it
          in your own pipecat app, and it works against any pipeline.
        </p>
        <div className="av-end-links">
          <a className="av-cta" href={LINKS.repo} target="_blank" rel="noopener noreferrer">
            <Github size={15} /> voqalize/avatar
          </a>
          <a href={LINKS.npm} target="_blank" rel="noopener noreferrer">
            @voqalize/avatar on npm
          </a>
          <a href={LINKS.docs} target="_blank" rel="noopener noreferrer">
            Drive the face from your brain
          </a>
        </div>
        <p className="av-end-foot">
          The voice on that call was <a href={LINKS.voqalize}>Voqalize</a> — the voice tier for an
          agent you already have. The avatar is yours either way.
        </p>
        <button type="button" className="av-again" onClick={onAgain}>
          Call again
        </button>
      </div>
    </div>
  );
}

// ── The live call ───────────────────────────────────────────────────────────

function Stage({
  error,
  onBegin,
  onEnd,
}: {
  error: string | null;
  onBegin?: () => void | Promise<void>;
  onEnd?: () => void | Promise<void>;
}) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected, isConnecting } = usePipecatConnectionState();
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();

  const [avatarKey, setAvatarKey] = useState<string>(DEFAULT_AVATAR);
  const [slide, setSlide] = useState<ShowSlide | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [ended, setEnded] = useState<string | null>(null);
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");
  const [left, setLeft] = useState(LIMIT_S);
  const startedAt = useRef<number | null>(null);

  // Screen ← brain. One subscription rather than four `useUICommandHandler`s:
  // the page is one small state machine, and a command it does not know is a
  // no-op here by design (a page and a brain ship separately).
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(({ command, payload }: UICommandData) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case "show_slide":
          setWorking(null);
          setSlide(action.payload);
          break;
        case "switch_avatar":
          setAvatarKey(action.payload.key);
          break;
        case "working_on":
          setWorking(action.payload.topic);
          break;
        case "show_end_card":
          setEnded(action.payload.reason);
          break;
        default:
          unhandledUiAction(action);
      }
    }, []),
  );

  // Presence, derived from pipecat's own events and never stored twice. This is
  // the page's copy; the face has its own, read off the same client, which is
  // the point of handing it the client rather than a state prop.
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => {
      setActivity("idle");
      setWorking(null);
    }, []),
  );

  // Mic on once the call is live, the clock starts, and the brain is told the
  // page is listening.
  //
  // That last one is load-bearing rather than a nicety. A brain is dialled at
  // pipeline start, which is before this data channel exists — so a gesture sent
  // from its greeting would be dropped here, invisibly, while the greeting audio
  // played normally because the transport queues audio. The opening wave answers
  // this message instead, which is the first moment one can arrive.
  useEffect(() => {
    if (!isConnected) return;
    enableMic(true);
    startedAt.current = Date.now();
    client?.sendClientMessage("ready", {});
  }, [isConnected, enableMic, client]);

  useEffect(() => {
    if (!isConnected || ended) return;
    const tick = setInterval(() => {
      const started = startedAt.current;
      if (started === null) return;
      setLeft(Math.max(0, LIMIT_S - Math.round((Date.now() - started) / 1000)));
    }, 1000);
    return () => clearInterval(tick);
  }, [isConnected, ended]);

  // Screen → brain. The drawing swaps here and now; the voice and the model's
  // context are the brain's to move, and it is told so it can do both.
  const pick = useCallback(
    (key: string) => {
      if (key === avatarKey) return;
      setAvatarKey(key);
      client?.sendClientMessage("pick_avatar", { key });
    },
    [avatarKey, client],
  );

  const hangUp = async () => {
    await onEnd?.();
    setEnded((reason) => reason ?? "hung_up");
  };

  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;

  return (
    <>
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />

      <main className="av-stage">
        <div className="av-column">
          <div className="av-tile">
            <Face avatarKey={avatarKey} client={client} />
            {working ? (
              <div className="av-working">
                <span className="av-working-dot" aria-hidden />
                working — {working}
              </div>
            ) : (
              <div className={`av-chip is-${activity}`}>
                <span className="av-chip-dot" aria-hidden />
                {isMicEnabled ? ACTIVITY_LABEL[activity] : "Muted"}
                <span className="av-chip-clock">{clock}</span>
              </div>
            )}
          </div>

          <div className="av-controls">
            <button
              type="button"
              className={`av-mic ${isMicEnabled ? "" : "is-muted"}`}
              onClick={() => enableMic(!isMicEnabled)}
              aria-label={isMicEnabled ? "Mute" : "Unmute"}
            >
              {isMicEnabled ? <Mic size={16} /> : <MicOff size={16} />}
            </button>
            <button type="button" className="av-hangup" onClick={() => void hangUp()} aria-label="End call">
              <PhoneOff size={14} />
            </button>
          </div>

          {/* The picker is the second authority on the face, and deliberately so:
              a visitor whose microphone fails still gets to see all nine. */}
          <div className="av-strip" role="group" aria-label="Choose an avatar">
            {ROSTER.map((entry) => (
              <button
                key={entry.key}
                type="button"
                className={`av-pick${entry.key === avatarKey ? " is-on" : ""}`}
                onClick={() => pick(entry.key)}
                aria-pressed={entry.key === avatarKey}
              >
                <span className="av-pick-name">{entry.name}</span>
                <span className="av-pick-kind">{entry.kind}</span>
              </button>
            ))}
          </div>
        </div>

        <Panel slide={slide} opener={isConnected} />
      </main>

      {isConnecting ? (
        <div className="av-connecting">
          <Loader2 size={18} className="av-spin" /> connecting…
        </div>
      ) : null}
      {error ? <div className="av-error">{error}</div> : null}
      {ended ? <EndCard reason={ended} onAgain={() => window.location.reload()} /> : null}
      {/* Nothing opens a microphone until the visitor has read the notice. */}
      <DemoGate
        open={!isConnected && !isConnecting && !ended}
        title="The Avatar"
        blurb="Two minutes with the open-source talking head. Ask it how it works — it draws the architecture, demonstrates its own protocol, and changes its face and voice while you watch."
        accent={PRESENCE.listening}
        error={error}
        busy={isConnecting}
        onJoin={async () => {
          await onBegin?.();
        }}
      />
    </>
  );
}

/**
 * Mints the session and owns the client. `PipecatAppBase` builds the
 * `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` — with its own `BotAudioOutput` — as soon as the
 * client exists, not when the call goes live. `connectOnMount` is off.
 */
export function AvatarDemo() {
  // Memoized: a fresh object every render would re-fire the connect effect and
  // re-mint a session. No `config` — the voice belongs to the brain, which
  // changes it mid-call every time the face changes.
  const params = useMemo(() => connectRequest({ surface: "avatar-web" }), []);
  const unprovisioned = !demo.agentId || !demo.publishableKey;

  return (
    <div className="av-root">
      <style>{STYLES}</style>
      <header className="av-head">
        <span className="av-wordmark">voqalize/avatar</span>
        <span className="av-badge">MIT</span>
        <a className="av-headlink" href={LINKS.repo} target="_blank" rel="noopener noreferrer">
          <Github size={14} /> GitHub
        </a>
      </header>

      {unprovisioned ? (
        <div className="av-error av-error-block">
          This demo is not provisioned — no agent id or publishable key was baked in at build.
        </div>
      ) : (
        <PipecatAppBase
          transportType="smallwebrtc"
          noThemeProvider
          startBotParams={params}
          startBotResponseTransformer={withRealHeaders}
        >
          {({ error, handleConnect, handleDisconnect }) => (
            <Stage error={error ?? null} onBegin={handleConnect} onEnd={handleDisconnect} />
          )}
        </PipecatAppBase>
      )}
    </div>
  );
}
