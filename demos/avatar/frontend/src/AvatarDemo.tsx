/**
 * The avatar demo — the open-source talking head explaining itself.
 *
 * This page is the link target from the library's README, so it has two jobs and
 * the layout is the answer to both. The **right two-thirds is the documentation**
 * (`docs.tsx`): a reader who never turns on a microphone gets the whole library —
 * install, integration, the wire, the lipsync, the limits — on one screen. The
 * **left third is a live call** with the thing being documented, and as you talk
 * to it, it scrolls you to the section it is answering from. The voice is a fast
 * path through the page rather than the only way in.
 *
 * **The whole browser half of a call is pipecat's.** `PipecatAppBase` does
 * pipecat's two-step connect and owns the client; everything below it is a stock
 * `PipecatClient`. The only Voqalize-specific code on the page is the request
 * that starts the call and the one line over its answer, both in `src/config.ts`.
 * The avatar is `@voqalize/avatar` from npm, handed that same client and nothing
 * else — it reads the state, the gestures and the visemes off the data channel
 * that is already open. The bot's captions are `voice-ui-kit`'s own
 * `TranscriptOverlay`, driven by the same events.
 *
 * Two directions of traffic reach this file:
 *
 *   * **brain → screen**, as RTVI `ui-command`s: the section to scroll to, the
 *     avatar switch, the working strip, the end card (`actions.gen.ts` is the
 *     generated shape). A section command carries an id and a heading, not prose
 *     — the page already holds every word, and two copies of a paragraph is how a
 *     page linked from a README stops being readable on its own.
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
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import {
  PipecatAppBase,
  TranscriptOverlay,
  usePipecatConnectionState,
} from "@pipecat-ai/voice-ui-kit";
import "@pipecat-ai/voice-ui-kit/styles.scoped";
import { Avatar } from "@voqalize/avatar/react";
import type { AvatarFactory, AvatarOptions } from "@voqalize/avatar";
import { Github, Mic, MicOff, PhoneOff } from "lucide-react";
import { asUiAction, unhandledUiAction } from "./actions.gen";
import { connectRequest, demo, withRealHeaders } from "./config";
import { DOC_SECTIONS } from "./docs";
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
  pypi: "https://pypi.org/project/voqalize-avatar/",
  voqalize: "https://voqalize.com",
};

/** What to ask, for a visitor who has never met a voice demo and has two
 *  minutes. Each one lands a different mechanism, and each one moves the page. */
const OPENERS = [
  "How does the lipsync work?",
  "Show me what working looks like.",
  "What else can you look like?",
  "What are the limits?",
];

type Activity = "offline" | "listening" | "thinking" | "speaking" | "working";

const ACTIVITY_LABEL: Record<Activity, string> = {
  offline: "Not connected",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  working: "Working",
};

// ── The face ────────────────────────────────────────────────────────────────

/**
 * The mounted avatar. Every entry in the roster resolves to the same published
 * interface — `createAvatar({mount, client}) -> {destroy()}` — so swapping one
 * is a remount and nothing else. `key` forces that remount: `<Avatar>` reads its
 * options once, at mount, which is the interface being honest about what an
 * avatar is rather than a limitation to work around.
 */
function Face({
  avatarKey,
  client,
}: {
  avatarKey: string;
  client: ReturnType<typeof usePipecatClient>;
}) {
  const [factory, setFactory] = useState<{
    key: string;
    create: AvatarFactory<AvatarOptions>;
  } | null>(null);

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

// ── The documentation, and the rail beside it ───────────────────────────────

/**
 * One tick per section, top to bottom, the current one filled — a dope sheet,
 * which is the drawing this library is actually made of. It is a real control:
 * click a tick and the page goes there. It is also the only thing on the page
 * that moves without the reader touching anything, and it moves because the
 * conversation moved the page.
 */
function Rail({ current, onGo }: { current: string; onGo: (id: string) => void }) {
  return (
    <nav className="av-rail" aria-label="Sections">
      <div className="av-rail-track">
        {DOC_SECTIONS.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`av-tick${section.id === current ? " is-on" : ""}`}
            onClick={() => onGo(section.id)}
            aria-current={section.id === current ? "true" : undefined}
          >
            <span className="av-tick-label">{section.rail}</span>
            <span className="av-sr">{section.title}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

/** Where to go next. It closes the documentation rather than covering it — a
 *  reader who scrolled here is finished reading, not interrupted. */
function Outro() {
  return (
    <section className="av-outro">
      <h2>Get it</h2>
      <p>
        The face, the wire format and the lipsync are one MIT-licensed library. Install both halves,
        put the processor after your TTS service, mount the face in your call tile.
      </p>
      <div className="av-outro-links">
        <a href={LINKS.repo} target="_blank" rel="noopener noreferrer">
          Source on GitHub
        </a>
        <a href={LINKS.npm} target="_blank" rel="noopener noreferrer">
          @voqalize/avatar on npm
        </a>
        <a href={LINKS.pypi} target="_blank" rel="noopener noreferrer">
          voqalize-avatar on PyPI
        </a>
      </div>
      <p style={{ marginTop: 22 }}>
        The voice carrying this call is <a href={LINKS.voqalize}>Voqalize</a> — the voice tier for
        an agent you already have. The avatar library is yours either way.
      </p>
    </section>
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
  const { isConnected, isConnecting } = usePipecatConnectionState();
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();

  const [avatarKey, setAvatarKey] = useState<string>(DEFAULT_AVATAR);
  const [current, setCurrent] = useState<string>(DOC_SECTIONS[0].id);
  const [working, setWorking] = useState<string | null>(null);
  const [ended, setEnded] = useState<string | null>(null);
  const [activity, setActivity] = useState<Activity>("offline");
  const [left, setLeft] = useState(LIMIT_S);
  const startedAt = useRef<number | null>(null);

  /** Scroll the documentation to a section. The one thing the brain can do to
   *  the reader's screen, and the same thing a click on the rail does. */
  const goTo = useCallback((id: string) => {
    setCurrent(id);
    document.getElementById(`doc-${id}`)?.scrollIntoView({ block: "start" });
  }, []);

  // Screen ← brain. One subscription rather than four `useUICommandHandler`s:
  // the page is one small state machine, and a command it does not know is a
  // no-op here by design (a page and a brain ship separately).
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => {
        const action = asUiAction(command, payload);
        if (!action) return;
        switch (action.command) {
          case "show_section":
            setWorking(null);
            goTo(action.payload.id);
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
      },
      [goTo],
    ),
  );

  // Presence, derived from pipecat's own events and never stored twice. This is
  // the page's copy; the face has its own, read off the same client, which is
  // the point of handing it the client rather than a state prop.
  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => setActivity("listening"), []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotLlmStarted,
    useCallback(() => setActivity("thinking"), []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => setActivity("speaking"), []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => {
      setActivity("listening");
      setWorking(null);
    }, []),
  );

  // Reading the page is the other half of using it, so the rail follows the
  // scroll as well as the conversation. Whichever moved last is what it shows.
  useEffect(() => {
    const seen = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          seen.set(
            entry.target.id.replace(/^doc-/, ""),
            entry.isIntersecting ? entry.intersectionRatio : 0,
          );
        }
        let best: string | null = null;
        let bestRatio = 0;
        for (const [id, ratio] of seen) {
          if (ratio > bestRatio) {
            best = id;
            bestRatio = ratio;
          }
        }
        if (best) setCurrent(best);
      },
      { rootMargin: "-88px 0px -55% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    for (const section of DOC_SECTIONS) {
      const el = document.getElementById(`doc-${section.id}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

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
    setActivity("listening");
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

  const shown: Activity = working ? "working" : isConnected ? activity : "offline";
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  const live = isConnected && !ended;

  return (
    <main className="av-main">
      <div className="av-call">
        <div className="av-tile">
          <Face avatarKey={avatarKey} client={client} />

          {/* The bot's own words, arriving a word at a time as they are spoken.
              `voice-ui-kit`'s stylesheet is Tailwind and 132 KB, so this imports
              `styles.scoped` — every rule scoped under `.vkui-root` — and only
              the caption strip wears that class. */}
          {live ? (
            <div className="av-captions">
              <div className="vkui-root">
                <TranscriptOverlay participant="remote" size="sm" />
              </div>
            </div>
          ) : null}

          {ended ? (
            <div className="av-end">
              <h2>{ended === "time_limit" ? "That’s the two minutes." : "Call ended."}</h2>
              <p>
                The documentation is still here — everything it said is written out beside you. The
                library is <a href={LINKS.repo}>MIT on GitHub</a>.
              </p>
              <button type="button" className="av-again" onClick={() => window.location.reload()}>
                Call again
              </button>
            </div>
          ) : null}
        </div>

        {!isConnected && !ended ? (
          <div className="av-invite">
            <button
              type="button"
              className="av-start"
              onClick={() => void onBegin?.()}
              disabled={isConnecting}
            >
              {isConnecting ? "Connecting…" : "Talk to it"}
            </button>
            <p>
              Two minutes, in your browser, using your microphone. Ask it anything on this page and
              it scrolls you to the answer as it speaks.
            </p>
          </div>
        ) : null}

        {isConnected || ended ? (
          <div className={`av-status is-${shown}`}>
            <span className="av-dot" aria-hidden />
            <span className="av-status-label">
              {working
                ? `Working — ${working}`
                : isMicEnabled || !live
                  ? ACTIVITY_LABEL[shown]
                  : "Muted"}
            </span>
            {live ? (
              <>
                <span className="av-clock">{clock}</span>
                <span className="av-ctl">
                  <button
                    type="button"
                    className={isMicEnabled ? "" : "is-muted"}
                    onClick={() => enableMic(!isMicEnabled)}
                    aria-label={isMicEnabled ? "Mute the microphone" : "Unmute the microphone"}
                  >
                    {isMicEnabled ? <Mic size={14} /> : <MicOff size={14} />}
                  </button>
                  <button type="button" onClick={() => void hangUp()} aria-label="End the call">
                    <PhoneOff size={13} />
                  </button>
                </span>
              </>
            ) : null}
          </div>
        ) : null}

        {error ? <p className="av-error">{error}</p> : null}

        {/* The picker is the second authority on the face, and deliberately so:
            a visitor whose microphone fails still gets to see all nine. */}
        <div className="av-picker">
          <div className="av-picker-head">
            <span>Nine avatars ship. Pick one.</span>
            <span className="av-picker-kind">{ROSTER_BY_KEY[avatarKey]?.kind}</span>
          </div>
          <div className="av-strip" role="group" aria-label="Choose an avatar">
            {ROSTER.map((entry) => (
              <button
                key={entry.key}
                type="button"
                className={`av-pick${entry.key === avatarKey ? " is-on" : ""}`}
                onClick={() => pick(entry.key)}
                aria-pressed={entry.key === avatarKey}
              >
                {entry.name}
              </button>
            ))}
          </div>
        </div>

        <div className="av-openers">
          <p>Try asking</p>
          <ul>
            {OPENERS.map((line) => (
              <li key={line}>“{line}”</li>
            ))}
          </ul>
        </div>
      </div>

      <Rail current={current} onGo={goTo} />

      <div className="av-docs">
        {DOC_SECTIONS.map((section) => (
          <section
            key={section.id}
            id={`doc-${section.id}`}
            className={`doc-section${section.id === current ? " is-current" : ""}`}
          >
            <h2>{section.title}</h2>
            {section.body}
          </section>
        ))}
        <Outro />
      </div>
    </main>
  );
}

/**
 * Mints the session and owns the client. `PipecatAppBase` builds the
 * `PipecatClient`, does pipecat's two-step connect (`startBot` against the
 * control plane, then `connect` the transport it returns) and mounts
 * `PipecatClientProvider` — with its own `BotAudioOutput` — as soon as the
 * client exists, not when the call goes live. `connectOnMount` is off: nothing
 * opens a microphone until the visitor asks for it.
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
        <a className="av-wordmark" href={LINKS.repo}>
          voqalize/avatar
        </a>
        <span className="av-licence">MIT</span>
        <nav className="av-headnav">
          <a href={LINKS.npm} target="_blank" rel="noopener noreferrer">
            npm
          </a>
          <a href={LINKS.pypi} target="_blank" rel="noopener noreferrer">
            PyPI
          </a>
          <a href={LINKS.repo} target="_blank" rel="noopener noreferrer">
            <Github size={14} /> GitHub
          </a>
        </nav>
      </header>

      {unprovisioned ? (
        <div className="av-main">
          <p className="av-error">
            This demo is not provisioned — no agent id or publishable key was baked in at build.
          </p>
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
