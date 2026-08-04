/**
 * Prototype interview voice demo — talks to the `interview_bot` brain.
 *
 * The per-session job/candidate/plan ("agent_input") is pasted in as JSON and
 * forwarded verbatim to the brain as the session payload (the brain receives it
 * as `init_payload`). No persistence, no recording — a throwaway test harness.
 *
 * The whole session lifecycle — mint against the control plane, WebRTC transport,
 * mic control, bot-state, and the agent's `ui_command` server-messages — is the
 * public SDK's {@link useVoqalSession} from `@voqalize/client-react`, driven by a
 * publishable (`pk_`) key. This file is just the paste-JSON form, the call UI, and
 * the section/summary bridge the brain drives via `section_changed` /
 * `interview_completed`.
 *
 * The interviewer's state is carried by the shared `AmbientPresence` ring — the
 * catalog-wide voice treatment, painted around the whole harness rather than
 * parked in a widget. The call card keeps only the minimal controls (mute / end)
 * and the section indicator this harness exists to surface.
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { PipecatClientProvider, usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { BotAudioOutput } from "@pipecat-ai/voice-ui-kit";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import {
  AmbientPresence,
  useVoqalSession,
  type AmbientPresencePalette,
  type VoqalBotState,
} from "@voqalize/client-react";
import { config } from "./config";

// Tenant + agent + pk resolve per-environment from this demo's local config
// (src/config.ts), driven by Vite env vars.
const INTERVIEW = config;

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

interface SectionState {
  index: number;
  key: string;
  title: string;
  isLast: boolean;
}

const STATE_LABEL: Record<VoqalBotState, string> = {
  idle: "Live",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── Live call controls (inside the PipecatClientProvider) ─────────────────────
// The catalog's minimal shape: the state label, a circular mic that doubles as
// the mute toggle, and a small secondary control that ends the interview.
function LiveControls({ botState, onEnd }: { botState: VoqalBotState; onEnd: () => void }) {
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

export function InterviewDemo() {
  const [step, setStep] = useState<Step>("form");
  const [agentInputText, setAgentInputText] = useState(() =>
    JSON.stringify(SAMPLE_AGENT_INPUT, null, 2),
  );
  const [parseError, setParseError] = useState("");
  const [callError, setCallError] = useState("");
  const [micPermission, setMicPermission] = useState<MicPermission>("idle");
  const [section, setSection] = useState<SectionState | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [summary, setSummary] = useState<string | null>(null);

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

  // The entire session lifecycle in one hook. `onServerMessage` is pre-unwrapped
  // (past the `{ data }` quirk), so we read `type`/`action` directly — the brain
  // drives the UI via section_changed / interview_completed ui_commands.
  const session = useVoqalSession({
    apiBase: INTERVIEW.apiBase,
    tenantSlug: INTERVIEW.tenantSlug,
    // Empty when unprovisioned — the SDK surfaces a clear "publishableKey is
    // required" error, shown in the call error state.
    publishableKey: INTERVIEW.publishableKey ?? "",
    agentId: INTERVIEW.agentId,
    // No pipeline override: this agent's voice and language are declared on
    // its brain (backend/brain.py), which is the only place they belong.
    // The opaque agent_input the brain receives as init_payload.
    payload,
    onServerMessage: useCallback(
      (msg: Record<string, unknown>) => {
        if (msg.type !== "ui_command") return;
        if (msg.action === "section_changed") {
          const title = (msg.title as string) ?? "";
          setSection({
            index: (msg.index as number) ?? 0,
            key: (msg.key as string) ?? "",
            title,
            isLast: !!msg.is_last,
          });
          log(`➡️ section: ${title}${msg.is_last ? " (final)" : ""}`);
        } else if (msg.action === "interview_completed") {
          setSummary((msg.summary as string) ?? "");
          log("✅ interview completed");
          setStep("ended");
        }
      },
      [log],
    ),
  });

  const { client, connectionState, botState, error, connect, disconnect, enableMic } = session;

  // Drive the step machine off the transport state: connected → live call;
  // error → back to the gate with the message surfaced.
  useEffect(() => {
    if (connectionState === "connected") {
      setStep((s) => (s === "ended" ? s : "call"));
    } else if (connectionState === "error") {
      setStep((s) => (s === "ended" ? s : "call-gate"));
      setCallError(error || "Could not connect.");
    }
  }, [connectionState, error]);

  // Mic on once the session is live.
  useEffect(() => {
    if (connectionState !== "connected") return;
    enableMic(true);
  }, [connectionState, enableMic]);

  // Tear the session down on unmount.
  useEffect(() => () => void disconnect(), [disconnect]);

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
    if (!INTERVIEW.publishableKey || !INTERVIEW.agentId) {
      setCallError(
        "Interview demo is not configured (missing agent id or publishable key). Reseed the emulator.",
      );
      return;
    }
    setStep("connecting");
    connect();
  };

  const hangUp = async () => {
    await disconnect();
    setStep("form");
    setSection(null);
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
      <AmbientPresence botState={botState} connectionState={connectionState} palette={PRESENCE} />

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

        {/* The ring already carries "something is happening" — this step only
            needs to say what, quietly. */}
        {step === "connecting" && (
          <div style={{ textAlign: "center", padding: "48px 0", color: "#94a3b8" }}>
            <Loader2 size={22} className="iv-spin" />
            <p style={{ marginTop: 12 }}>Connecting…</p>
          </div>
        )}

        {(step === "call" || step === "ended") && (
          <div>
            {client && (
              <PipecatClientProvider client={client}>
                <BotAudioOutput />
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
                        {section.isLast ? " (final)" : ""}
                      </div>
                    )}
                  </div>
                  {step === "call" && (
                    <LiveControls botState={botState} onEnd={() => void hangUp()} />
                  )}
                </div>
              </PipecatClientProvider>
            )}

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
                <button
                  onClick={() => {
                    void disconnect();
                    setStep("form");
                    setSection(null);
                    setEvents([]);
                    setSummary(null);
                  }}
                  style={{ ...secondaryBtn, marginTop: 12 }}
                >
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
