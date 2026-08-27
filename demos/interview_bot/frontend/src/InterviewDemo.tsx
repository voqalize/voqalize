/**
 * Prototype interview voice demo — talks to the `interview_bot` brain.
 *
 * The per-session job/candidate/plan ("agent_input") is pasted in as JSON and
 * forwarded verbatim to the brain as `init` — the brain reads it back as
 * `session.init`. No persistence, no recording — a throwaway test harness.
 *
 * The whole session lifecycle — starting the call, WebRTC transport, mic
 * control, and the brain's RTVI `ui-command` server-messages — is stock
 * pipecat's `PipecatAppBase` plus the hooks in `@pipecat-ai/client-react`;
 * there is no client library beyond the one request in `src/config.ts`. This
 * file is just the paste-JSON form, the call UI, and the section/summary
 * bridge the brain drives via `section_changed` / `interview_completed`
 * `ui-command`s.
 *
 * The interviewer's state is carried by the shared `AmbientPresence` ring — the
 * catalog-wide voice treatment, painted around the whole harness rather than
 * parked in a widget. The call card keeps only the minimal controls (mute / end)
 * and the section indicator this harness exists to surface.
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { RTVIEvent, type TransportState, type UICommandData } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { PipecatAppBase, usePipecatConnectionState } from "@pipecat-ai/voice-ui-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  DemoGate,
  type AmbientPresenceActivity,
  type AmbientPresencePalette,
} from "@voqalize/demo-kit";
import { connectRequest, demo, withRealHeaders } from "./config";
import { asUiAction, unhandledUiAction, type SectionChanged } from "./actions.gen";

// This harness's reading of the shared presence ring: the indigo of its own
// primary action is the interviewer present and speaking, and it shifts to the
// cyan already used as the second waveform colour while the interviewer reasons
// — a plainly different hue at the edge of vision. Offline is a slate lifted a
// couple of steps off the card borders, because on a #0f172a page a #1e293b seam
// would simply disappear.
const PRESENCE: Partial<AmbientPresencePalette> = {
  idle: "#6366f1",
  listening: "#6366f1",
  thinking: "#22d3ee",
  speaking: "#6366f1",
  offline: "#475569",
};

const SAMPLE_AGENT_INPUT = {
  interview_id: 288,
  job: {
    id: 61,
    title: "Senior UI Engineer - React",
    description:
      "Build high-quality, accessible React UI components and design systems, and collaborate closely with product and backend teams.",
  },
  candidate: {
    id: 3,
    name: "Abhineeth Srinivasa",
    email: "abhineeth@example.com",
    resume_text:
      "Senior frontend engineer with 8 years building React applications. Led a design-system team, deep experience with hooks, performance profiling, and accessibility.",
  },
  plan: {
    id: 54,
    title: "Senior React Engineer Deep Dive",
    goal: "Assess senior React engineering depth and frontend system design.",
    sections: {
      introduction: {
        type: "introduction",
        title: "Introduction",
        max_allowed_section_time: 2,
        goal: "Build rapport and set expectations.",
      },
      "resume-deep-dive": {
        type: "resume-deep-dive",
        title: "Resume Deep Dive",
        max_allowed_section_time: 5,
        goal: "Probe the candidate's most significant React project.",
      },
      "topic-based-qa": {
        type: "topic-based-qa",
        title: "React Deep Dive",
        max_allowed_section_time: 8,
        goal: "Probe React internals and best practices.",
        topics: [{ name: "Hooks & rendering" }, { name: "Reconciliation" }, { name: "Performance" }],
      },
      "system-design": {
        type: "system-design",
        title: "Frontend System Design",
        max_allowed_section_time: 8,
        problem_statement: "Design a collaborative rich-text editor for the web.",
      },
      closing: {
        type: "closing",
        title: "Closing",
        max_allowed_section_time: 2,
        mandatory_questions: ["What questions do you have for us?"],
      },
    },
  },
};

type Step = "form" | "call-gate" | "connecting" | "call" | "ended";
type MicPermission = "idle" | "requesting" | "granted" | "denied";


const STATE_LABEL: Record<AmbientPresenceActivity, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Live call controls (inside PipecatAppBase's client provider) ──────────────
// The catalog's minimal shape: the state label, a circular mic that doubles as
// the mute toggle, and a small secondary control that ends the interview.
function LiveControls({
  botState,
  onEnd,
}: {
  botState: AmbientPresenceActivity;
  onEnd: () => void;
}) {
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const label = isMicEnabled ? STATE_LABEL[botState] : "Muted";
  return (
    <div className="iv-controls">
      <span className="iv-controls-label">{label}</span>
      <button
        className={`iv-mic state-${botState} ${isMicEnabled ? "" : "is-muted"}`}
        onClick={() => enableMic(!isMicEnabled)}
        title={isMicEnabled ? "Mute" : "Unmute"}
        aria-label={isMicEnabled ? "Mute" : "Unmute"}
      >
        {isMicEnabled ? <Mic size={17} /> : <MicOff size={17} />}
      </button>
      <button className="iv-end" onClick={onEnd} title="End interview" aria-label="End interview">
        <PhoneOff size={14} />
      </button>
    </div>
  );
}

// ── The live leg: mounted only once PipecatAppBase has started the call ───────
// (step is "connecting", "call" or "ended"). Reads the transport, the RTVI
// activity events and the brain's `ui-command`s, and reports the bits the rest
// of the page needs — section, summary, activity, transport state, connection
// and error transitions — back up through props, since the ambient ring and the
// step machine live above `PipecatAppBase` and only this subtree has a client.
function LiveCall({
  step,
  error,
  section,
  summary,
  events,
  onSection,
  onCompleted,
  onConnected,
  onConnectError,
  onActivity,
  onTransportState,
  onEnd,
  onNewInterview,
}: {
  step: Step;
  error: string | null;
  section: SectionChanged | null;
  summary: string | null;
  events: string[];
  onSection: (section: SectionChanged, logLine: string) => void;
  onCompleted: (summary: string, logLine: string) => void;
  onConnected: () => void;
  onConnectError: (message: string) => void;
  onActivity: (activity: AmbientPresenceActivity) => void;
  onTransportState: (state: TransportState) => void;
  onEnd: () => void;
  onNewInterview: () => void;
}) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { isConnected } = usePipecatConnectionState();
  const { enableMic } = usePipecatClientMicControl();
  const [activity, setActivityState] = useState<AmbientPresenceActivity>("idle");

  const setActivity = useCallback(
    (next: AmbientPresenceActivity) => {
      setActivityState(next);
      onActivity(next);
    },
    [onActivity],
  );

  useEffect(() => {
    onTransportState(transportState);
  }, [transportState, onTransportState]);

  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => setActivity("listening"), [setActivity]),
  );
  useRTVIClientEvent(
    RTVIEvent.BotLlmStarted,
    useCallback(() => setActivity("thinking"), [setActivity]),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => setActivity("speaking"), [setActivity]),
  );
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => setActivity("idle"), [setActivity]),
  );

  // The brain drives the screen via `session.dispatch(...)`, which arrives here
  // as an RTVI `ui-command`: `{ command, payload }`.
  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(
      ({ command, payload }: UICommandData) => {
        const action = asUiAction(command, payload);
        if (!action) return;
        switch (action.command) {
          case "section_changed": {
            const { title, is_last } = action.payload;
            onSection(action.payload, `➡️ section: ${title}${is_last ? " (final)" : ""}`);
            break;
          }
          case "interview_completed":
            onCompleted(action.payload.summary, "✅ interview completed");
            break;
          default:
            unhandledUiAction(action);
        }
      },
      [onSection, onCompleted],
    ),
  );

  // Drive the step machine: connected → live call.
  useEffect(() => {
    if (isConnected && step === "connecting") onConnected();
  }, [isConnected, step, onConnected]);

  // A failed connect bounces back to the call gate with the message surfaced.
  useEffect(() => {
    if (error) onConnectError(error);
  }, [error, onConnectError]);

  // Mic on once the session is live.
  useEffect(() => {
    if (!isConnected) return;
    enableMic(true);
  }, [isConnected, enableMic]);

  const hangUp = async () => {
    await client?.disconnect();
    onEnd();
  };

  const newInterview = async () => {
    await client?.disconnect();
    onNewInterview();
  };

  if (step === "connecting") {
    // The ring already carries "something is happening" — this step only
    // needs to say what, quietly.
    return (
      <div style={{ textAlign: "center", padding: "48px 0", color: "#94a3b8" }}>
        <Loader2 size={22} className="iv-spin" />
        <p style={{ marginTop: 12 }}>Connecting…</p>
      </div>
    );
  }

  return (
    <div>
      <div
        className="iv-callcard"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 20,
          background: "#020617",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 16,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "#94a3b8" }}>
            {step === "ended" ? "Interview complete" : "Live interview"}
          </div>
          {section && (
            <div style={{ marginTop: 6, fontSize: 15, fontWeight: 600 }}>
              Section {section.index + 1}: {section.title}
              {section.is_last ? " (final)" : ""}
            </div>
          )}
        </div>
        {step === "call" && <LiveControls botState={activity} onEnd={() => void hangUp()} />}
      </div>

      {step === "ended" && (
        <div
          style={{
            marginTop: 16,
            background: "#022c22",
            border: "1px solid #065f46",
            borderRadius: 12,
            padding: 16,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Summary</div>
          <div style={{ fontSize: 14, color: "#a7f3d0" }}>{summary || "(none provided)"}</div>
          <button onClick={() => void newInterview()} style={{ ...secondaryBtn, marginTop: 12 }}>
            New interview
          </button>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Event log</div>
        <div
          className="iv-log"
          style={{
            background: "#020617",
            border: "1px solid #1e293b",
            borderRadius: 10,
            padding: 12,
            height: 220,
            maxWidth: "100%",
            boxSizing: "border-box",
            overflow: "auto",
            fontFamily: "ui-monospace, monospace",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          {events.length === 0 ? (
            <span style={{ color: "#475569" }}>waiting for events…</span>
          ) : (
            events.map((e, i) => (
              <div key={i} style={{ whiteSpace: "pre" }}>
                {e}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function InterviewDemo() {
  const [joined, setJoined] = useState(false);
  const [step, setStep] = useState<Step>("form");
  const [agentInputText, setAgentInputText] = useState(() =>
    JSON.stringify(SAMPLE_AGENT_INPUT, null, 2),
  );
  const [parseError, setParseError] = useState("");
  const [callError, setCallError] = useState("");
  const [micPermission, setMicPermission] = useState<MicPermission>("idle");
  const [section, setSection] = useState<SectionChanged | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [activity, setActivity] = useState<AmbientPresenceActivity>("idle");
  const [transportState, setTransportState] = useState<TransportState | undefined>(undefined);

  const log = useCallback((line: string) => {
    setEvents((e) => [...e.slice(-200), line]);
  }, []);

  // The pasted agent_input parsed into the brain's init payload. Undefined while
  // the JSON is invalid; the form gate below blocks connecting until it parses.
  const payload = useMemo<Record<string, unknown> | undefined>(() => {
    try {
      return JSON.parse(agentInputText) as Record<string, unknown>;
    } catch {
      return undefined;
    }
  }, [agentInputText]);

  // The request that starts the call. Memoized: it is a dependency of
  // PipecatAppBase's connect-on-mount effect, so a fresh object every render
  // would re-mint a session every render. No `config`: this agent's voice and
  // language are declared on its brain (backend/brain.py), which is the only
  // place they belong.
  const params = useMemo(
    () => (payload ? connectRequest({ surface: "interview_bot-web", ...payload }) : null),
    [payload],
  );

  // Request mic on entering the call gate.
  useEffect(() => {
    if (step !== "call-gate" || micPermission !== "idle") return;
    setMicPermission("requesting");
    navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then((s) => {
        s.getTracks().forEach((t) => t.stop());
        setMicPermission("granted");
      })
      .catch(() => setMicPermission("denied"));
  }, [step, micPermission]);

  const goToCallGate = () => {
    setParseError("");
    try {
      JSON.parse(agentInputText);
    } catch (e) {
      setParseError(`Invalid JSON: ${(e as Error).message}`);
      return;
    }
    setMicPermission("idle");
    setStep("call-gate");
  };

  const startCall = () => {
    setCallError("");
    if (!payload) {
      setParseError("Invalid JSON — go back and fix the agent_input.");
      setStep("form");
      return;
    }
    if (!demo.publishableKey || !demo.agentId) {
      setCallError(
        "Interview demo is not configured (missing agent id or publishable key). Reseed the emulator.",
      );
      return;
    }
    setStep("connecting");
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0f172a",
        color: "#e2e8f0",
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <style>{STYLES}</style>
      {/* Root-level: this demo opens on a setup form and only dials once the
          interview plan is in, so joining here uncovers the harness — the
          microphone opens at the call-gate step, in the demo's own flow. */}
      <DemoGate
        open={!joined}
        title="Interview Bot"
        blurb="Paste an interview plan, then sit the screening interview out loud — the bot paces it and writes up each section on screen as you answer."
        accent={PRESENCE.listening}
        joinLabel="Start the demo"
        onJoin={() => setJoined(true)}
      />
      <AmbientPresence activity={activity} transportState={transportState} palette={PRESENCE} />

      <div className="iv-page" style={{ maxWidth: 760, margin: "0 auto", padding: "32px 24px" }}>
        <header style={{ marginBottom: 20 }}>
          <span
            style={{
              display: "inline-block",
              background: "rgba(245,158,11,.15)",
              color: "#f59e0b",
              borderRadius: 6,
              padding: "2px 8px",
              fontSize: 11,
              fontWeight: 600,
              marginBottom: 8,
            }}
          >
            prototype · interview_bot
          </span>
          <h1 className="iv-title" style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
            AI Interview (Voqalize)
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 14, marginTop: 4 }}>
            Paste the <code>agent_input</code> JSON (job + candidate + plan) and start a live voice
            interview.
          </p>
        </header>

        {step === "form" && (
          <div>
            <textarea
              className="iv-textarea"
              value={agentInputText}
              onChange={(e) => {
                setAgentInputText(e.target.value);
                setParseError("");
              }}
              spellCheck={false}
              style={{
                width: "100%",
                maxWidth: "100%",
                boxSizing: "border-box",
                height: 320,
                background: "#020617",
                color: "#e2e8f0",
                border: "1px solid #1e293b",
                borderRadius: 10,
                padding: 14,
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
                lineHeight: 1.5,
                resize: "vertical",
              }}
            />
            {parseError && (
              <div style={{ color: "#f87171", fontSize: 13, marginTop: 8 }}>{parseError}</div>
            )}
            <button onClick={goToCallGate} style={primaryBtn}>
              Continue →
            </button>
          </div>
        )}

        {step === "call-gate" && (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            {micPermission === "requesting" && <p>Allow microphone access in the browser prompt…</p>}
            {micPermission === "denied" && (
              <p style={{ color: "#fbbf24" }}>
                Microphone blocked — allow it in the address bar, then reload.
              </p>
            )}
            {micPermission === "granted" && (
              <p style={{ color: "#94a3b8" }}>
                Microphone ready. The interviewer will greet you and lead the conversation.
              </p>
            )}
            {callError && (
              <div style={{ color: "#f87171", fontSize: 13, margin: "12px 0" }}>{callError}</div>
            )}
            <div
              className="iv-gate-row"
              style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 16 }}
            >
              <button onClick={() => setStep("form")} style={secondaryBtn}>
                ← Back
              </button>
              <button
                onClick={startCall}
                disabled={micPermission !== "granted"}
                style={{ ...primaryBtn, marginTop: 0, opacity: micPermission === "granted" ? 1 : 0.4 }}
              >
                Start interview
              </button>
            </div>
          </div>
        )}

        {step !== "form" && step !== "call-gate" && params && (
          <PipecatAppBase
            transportType="smallwebrtc"
            connectOnMount
            noThemeProvider
            startBotParams={params}
            startBotResponseTransformer={withRealHeaders}
          >
            {({ error }) => (
              <LiveCall
                step={step}
                error={error ?? null}
                section={section}
                summary={summary}
                events={events}
                onSection={(s, line) => {
                  setSection(s);
                  log(line);
                }}
                onCompleted={(text, line) => {
                  setSummary(text);
                  log(line);
                  setStep("ended");
                }}
                onConnected={() => setStep((s) => (s === "connecting" ? "call" : s))}
                onConnectError={(message) => {
                  setStep("call-gate");
                  setCallError(message || "Could not connect.");
                }}
                onActivity={setActivity}
                onTransportState={setTransportState}
                onEnd={() => {
                  setStep("form");
                  setSection(null);
                }}
                onNewInterview={() => {
                  setStep("form");
                  setSection(null);
                  setEvents([]);
                  setSummary(null);
                }}
              />
            )}
          </PipecatAppBase>
        )}
      </div>
    </div>
  );
}

const primaryBtn: CSSProperties = {
  marginTop: 14,
  padding: "11px 20px",
  background: "#6366f1",
  color: "white",
  border: "none",
  borderRadius: 10,
  fontSize: 15,
  fontWeight: 600,
  cursor: "pointer",
};
const secondaryBtn: CSSProperties = {
  padding: "9px 16px",
  background: "transparent",
  color: "#e2e8f0",
  border: "1px solid #334155",
  borderRadius: 10,
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
};

// The harness owns its own baseline now that the voice-ui-kit stylesheet (and its
// reset) is gone, plus the one narrow-viewport pass. Desktop is untouched: every
// override below is inside the 640px query.
const STYLES = `
  html, body { margin: 0; padding: 0; background: #0f172a; -webkit-text-size-adjust: 100%; }

  .iv-spin { animation: iv-spin 0.9s linear infinite; }
  @keyframes iv-spin { to { transform: rotate(360deg); } }

  .iv-controls { display: flex; align-items: center; gap: 10px; flex: none; }
  .iv-controls-label {
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
    letter-spacing: 0.01em;
    min-width: 62px;
    text-align: right;
  }
  .iv-mic {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 1.5px solid #6366f1;
    background: #6366f1;
    color: #ffffff;
    cursor: pointer;
    flex: none;
    box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.16);
    transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  }
  .iv-mic:hover { transform: scale(1.05); }
  .iv-mic:active { transform: scale(0.97); }
  .iv-mic.state-thinking {
    border-color: #22d3ee;
    background: #22d3ee;
    color: #0f172a;
    box-shadow: 0 0 0 5px rgba(34, 211, 238, 0.22);
  }
  .iv-mic.state-speaking { box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.28); }
  .iv-mic.is-muted {
    background: transparent;
    border-color: #334155;
    color: #94a3b8;
    box-shadow: none;
  }
  .iv-end {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: #64748b;
    cursor: pointer;
    flex: none;
    transition: color 0.15s ease, background 0.15s ease;
  }
  .iv-end:hover { color: #f87171; background: #1e293b; }

  @media (max-width: 640px) {
    .iv-page { padding: 20px 14px !important; }
    .iv-title { font-size: 20px !important; }
    .iv-textarea { height: 240px !important; }
    .iv-gate-row { flex-wrap: wrap; }
    .iv-callcard {
      flex-direction: column !important;
      align-items: stretch !important;
      gap: 12px !important;
    }
    .iv-controls { justify-content: space-between; }
    .iv-controls-label { min-width: 0; text-align: left; }
    .iv-end { width: 36px; height: 36px; }
    .iv-log { height: 180px !important; }
  }
`;
