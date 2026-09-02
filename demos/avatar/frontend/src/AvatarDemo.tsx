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
 *     It also carries the face, which every call resets to the default at that
 *     moment: the opener is spoken before this page can say anything, so a face
 *     chosen beforehand would get one line in the other speaker's voice, and
 *     two recorded speakers means that reads immediately as the wrong gender.
 *     `pick_avatar` says the visitor chose a face mid-call: the page
 *     swaps the drawing immediately — it owns its own rendering and should not
 *     wait a round trip to redraw — and tells the brain, which is the only end
 *     that can move the voice and the model's context.
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
  BotAudioControl,
  ControlBar,
  ControlBarDivider,
  PipecatAppBase,
  TranscriptOverlayComponent,
  UserAudioControl,
  usePipecatConnectionState,
} from "@pipecat-ai/voice-ui-kit";
import "@pipecat-ai/voice-ui-kit/styles.scoped";
import { Avatar } from "@voqalize/avatar/react";
import type { AvatarFactory, AvatarOptions } from "@voqalize/avatar";
import { Github, PhoneOff } from "lucide-react";
import { asUiAction, unhandledUiAction } from "./actions.gen";
import { connectRequest, demo, withRealHeaders } from "./config";
import { DOC_SECTIONS } from "./docs";
import { DEFAULT_AVATAR, ROSTER, ROSTER_BY_KEY } from "./roster";
import { STYLES } from "./styles";

/** Two minutes, and the page only *reports* it — the brain enforces it. Kept
 *  here so the clock reads the same as the one that will actually hang up. */
const LIMIT_S = 120;

/** How many finished sentences stay on screen behind the one being spoken.
 *  Two is what fits under the tile without pushing the controls down. */
const CAPTION_HISTORY = 2;

/** How long a finished sentence takes to fade to nothing. Long enough to read
 *  a sentence you only half-heard; short enough that the band is empty again
 *  by the time the next answer starts. */
const CAPTION_LIFE_MS = 11000;

/** A chunk that ends a sentence retires the line and starts a new one. The
 *  synthesiser is fed sentence by sentence, so this fires on the boundary the
 *  audio actually has. */
const SENTENCE_END = /[.!?…]["')\]]?\s*$/;

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

/**
 * The bot's own words, under the picture, arriving as they are spoken.
 *
 * The words come off `bot-tts-text`, which is the text the runtime handed the
 * synthesiser: it is the only feed that is word-for-word what you are hearing,
 * chunk by chunk, and it arrives whatever RTVI protocol version the two ends
 * negotiate. `voice-ui-kit`'s own `TranscriptOverlay` reads a different feed
 * whose shape moved between protocol versions, so this page drives the kit's
 * headless `TranscriptOverlayComponent` with the words instead — the same
 * karaoke rendering, fed from the durable event.
 *
 * **A sentence does not vanish when the next one starts; it dims.** Speech is
 * gone the moment it is said, and a caption that is replaced mid-thought is
 * worse than none — a visitor who half-heard a clause has nowhere to look. So
 * a finished sentence retires behind the live one and fades out over eleven
 * seconds, and the band is empty again before the next answer needs it. Two
 * are kept: three pushes the controls off the fold.
 */
interface RetiredLine {
  id: number;
  text: string;
  at: number;
}

function Captions() {
  const [retired, setRetired] = useState<RetiredLine[]>([]);
  const [words, setWords] = useState<string[]>([]);
  const [turnEnd, setTurnEnd] = useState(false);
  // The chunks of the sentence currently being spoken. A ref rather than state
  // because two handlers append to it and both need to read what the other
  // just wrote, in the same tick.
  const live = useRef<string[]>([]);
  const seq = useRef(0);

  /** Move the sentence in flight into the fading stack. */
  const retire = useCallback(() => {
    const text = live.current.join("").trim();
    live.current = [];
    setWords([]);
    if (!text) return;
    seq.current += 1;
    const line = { id: seq.current, text, at: Date.now() };
    setRetired((prev) => [...prev, line].slice(-CAPTION_HISTORY));
  }, []);

  useRTVIClientEvent(
    RTVIEvent.BotTtsText,
    useCallback(
      (data: { text: string }) => {
        if (!data.text) return;
        live.current = [...live.current, data.text];
        setWords(live.current);
        setTurnEnd(false);
        if (SENTENCE_END.test(data.text)) retire();
      },
      [retire],
    ),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => {
      retire();
      setTurnEnd(true);
    }, [retire]),
  );

  // One timer, always for the oldest line — the CSS animation has already taken
  // it to zero by the time this fires, so removal is invisible rather than a cut.
  useEffect(() => {
    if (retired.length === 0) return;
    const oldest = retired[0];
    const timer = window.setTimeout(
      () => setRetired((prev) => prev.filter((line) => line.id !== oldest.id)),
      Math.max(0, oldest.at + CAPTION_LIFE_MS - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [retired]);

  // Always mounted, even empty: the band reserves its own height so the
  // controls under it never move while the bot is talking.
  return (
    <div className="av-captions" aria-live="polite">
      {retired.map((line) => (
        <p key={line.id} className="av-caption-past">
          {line.text}
        </p>
      ))}
      {words.length > 0 ? (
        <div className="vkui-root av-caption-live">
          <TranscriptOverlayComponent words={words} size="sm" turnEnd={turnEnd} />
        </div>
      ) : null}
    </div>
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
  //
  // **The face resets here, and that is the fix for the one mismatch this demo
  // could not otherwise avoid.** There are two recorded speakers, so a face is
  // paired to one of them by gender, and a face wearing the other one's voice is
  // the first thing anybody notices. The opener is spoken before this page can
  // say anything at all: the brain is dialled at pipeline start, `greet` is
  // awaited before any client message can be delivered, and waiting for one
  // there would deadlock the session rather than delay it. So a face chosen
  // before dialling could not be corrected in time — it would speak one line in
  // the wrong voice. Opening every call on the default is the version of this
  // with no race in it. The strip stays a gallery before the call and becomes a
  // control during it.
  useEffect(() => {
    if (!isConnected) return;
    setAvatarKey(DEFAULT_AVATAR);
    enableMic(true);
    setActivity("listening");
    startedAt.current = Date.now();
    client?.sendClientMessage("ready", { key: DEFAULT_AVATAR });
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
  //
  // Before the call there is nobody to tell, and the call will open on the
  // default anyway — so a click is a preview of the drawing and nothing more.
  const pick = useCallback(
    (key: string) => {
      if (key === avatarKey) return;
      setAvatarKey(key);
      if (isConnected) client?.sendClientMessage("pick_avatar", { key });
    },
    [avatarKey, client, isConnected],
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
        {/* The tile is a video call: who is on it and what is happening in the
            corner, the caption track across the bottom, the meeting controls
            directly beneath the picture. `voice-ui-kit`'s stylesheet is
            Tailwind and 132 KB, so this imports `styles.scoped` — every rule
            scoped under `.vkui-root` — and only the two islands that hold kit
            components wear that class. */}
        <div className="av-tile">
          <Face avatarKey={avatarKey} client={client} />

          {isConnected && !ended ? (
            <div className={`av-chip is-${shown}`}>
              <span className="av-dot" aria-hidden />
              <span>
                {working ? `Working — ${working}` : isMicEnabled ? ACTIVITY_LABEL[shown] : "Muted"}
              </span>
              <span className="av-clock">{clock}</span>
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

        {/* Under the picture, where a video call puts its captions. Mounted for
            the whole call rather than once something has been said: the greeting
            starts synthesising at the same moment the call connects, and a
            listener registered a beat later loses the opening words. */}
        {!ended ? <Captions /> : null}

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

        {/* Mute, the bot's own volume, and hang up — the three a two-minute
            call actually needs, in the row a decade of video calls has taught
            everyone to look for. The mic control carries its own level meter,
            which is the answer to "is it hearing me". */}
        {live ? (
          <div className="av-bar vkui-root">
            <ControlBar noAnimateIn className="av-controls">
              <UserAudioControl
                size="sm"
                variant="outline"
                noSpeakers
                visualizerProps={{ barCount: 5 }}
              />
              <BotAudioControl size="sm" variant="outline" />
              <ControlBarDivider />
              <button
                type="button"
                className="av-hangup"
                onClick={() => void hangUp()}
                aria-label="End the call"
                title="End the call"
              >
                <PhoneOff size={15} />
              </button>
            </ControlBar>
          </div>
        ) : null}

        {error ? <p className="av-error">{error}</p> : null}

        {/* The picker is the second authority on the face, and deliberately so:
            a visitor whose microphone fails still gets to see all nine. Before
            the call it previews a drawing; during one it moves the voice too. */}
        <div className="av-picker">
          <div className="av-picker-head">
            <span>{live ? "Pick a face. The voice moves with it." : "Nine avatars ship."}</span>
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
