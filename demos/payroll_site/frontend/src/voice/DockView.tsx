/**
 * The call's look, with no client in it: the dock pill bottom centre (the
 * agent's name, what is happening, the EN / हिंदी toggle and the call button)
 * and, while a call is live, the face tile bottom left. `VoiceCall` drives it
 * from a real call; the `?debug=1` console drives it from a fake one so the
 * live look can be seen and screenshotted.
 */
import { Mic, MicOff, PhoneOff } from "lucide-react";
import type { ReactNode } from "react";
import { PERSONA } from "../persona";
import { useSite } from "../state/store";
import "@fontsource-variable/noto-sans-devanagari/index.css";
import "./voice.css";

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

const STATUS: Record<CallState, string> = {
  idle: "Sales, Tankora",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Could not connect",
};

export function DockView({
  state,
  heard,
  muted,
  error,
  disabled,
  disabledNote,
  onStart,
  onMute,
  onEnd,
  onLanguage,
  face,
}: {
  state: CallState;
  heard: string;
  muted: boolean;
  error?: string | null;
  disabled?: boolean;
  disabledNote?: string;
  onStart: () => void;
  onMute: () => void;
  onEnd: () => void;
  /** The visitor pressed a language on the toggle. */
  onLanguage: (code: string) => void;
  /** The live face (the avatar mount); only while a call is live. */
  face?: ReactNode;
}) {
  const lang = useSite((s) => s.lang);
  const live = state !== "idle" && state !== "error";
  const name = PERSONA.display_name;
  const status = error ?? (live && heard ? `“${heard}”` : state === "listening" && muted ? "Microphone off" : disabledNote ?? STATUS[state]);
  return (
    <>
      {live ? (
        <div className={`agent-tile is-${state}`} role="region" aria-label={`Call with ${name}`}>
          <div className="agent-tile-face">{face}</div>
          <div className="agent-tile-bar">
            <span className="agent-tile-name">{name}</span>
            <span className={`agent-tile-state is-${state}`}>{STATUS[state]}</span>
          </div>
        </div>
      ) : null}
      <div className={`dock is-${state}${live ? " is-live" : ""}`} role="region" aria-label={`Talk to ${name}`}>
        <div className="dock-face" aria-hidden>
          <span>{name.slice(0, 1)}</span>
        </div>
        <div className="dock-text">
          <p className="dock-name">{name}</p>
          <p className="dock-status" aria-live="polite">
            {status}
          </p>
        </div>
        <div className="dock-lang" role="group" aria-label="Language">
          {PERSONA.languages.map((l) => (
            <button
              key={l.code}
              type="button"
              lang={l.code}
              className={lang === l.code ? "is-on" : ""}
              aria-pressed={lang === l.code}
              aria-label={l.label}
              onClick={() => onLanguage(l.code)}
            >
              {l.toggle}
            </button>
          ))}
        </div>
        {live ? (
          <>
            <button type="button" className="dock-btn" aria-pressed={muted} aria-label={muted ? "Turn microphone on" : "Turn microphone off"} onClick={onMute}>
              {muted ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
            <button type="button" className="dock-btn dock-end" aria-label="End the call" onClick={onEnd}>
              <PhoneOff size={18} />
            </button>
          </>
        ) : (
          <button type="button" className="dock-cta" aria-label={`Talk to ${name}`} disabled={disabled} onClick={onStart} title={disabled ? disabledNote : undefined}>
            <Mic size={16} /> <span className="dock-cta-label">Talk to {name}</span>
          </button>
        )}
      </div>
    </>
  );
}
