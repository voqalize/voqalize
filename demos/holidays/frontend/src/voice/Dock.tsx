/**
 * The planner's dock, bottom right: before a call, her face slot, "Talk to
 * {name}" and the language toggle; during one, a call card with her face,
 * what she is doing, what was heard, and mute / end.
 */
import type { ReactNode } from "react";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { PERSONA } from "../persona";
import { LangToggle } from "./LangToggle";

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";
const STATUS: Record<CallState, string> = {
  idle: PERSONA.role,
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Could not connect",
};

export function Dock(props: {
  state: CallState;
  heard: string;
  muted: boolean;
  disabled?: boolean;
  note?: string | null;
  face: ReactNode;
  onStart: () => void;
  onMute: () => void;
  onEnd: () => void;
}) {
  const live = props.state !== "idle" && props.state !== "error";
  return (
    <div className={`dock is-${props.state}${live ? " is-live" : ""}`} role="region" aria-label={`Talk to ${PERSONA.name}`}>
      <div className="dock-face">{props.face}</div>
      <div className="dock-text">
        <p className="dock-name">{PERSONA.name}</p>
        <p className="dock-status" aria-live="polite">
          {props.note ?? (live && props.heard ? `“${props.heard}”` : live && props.muted ? "Microphone off" : STATUS[props.state])}
        </p>
      </div>
      <LangToggle />
      {live ? (
        <div className="dock-actions">
          <button type="button" className="dock-btn" aria-pressed={props.muted} aria-label={props.muted ? "Turn microphone on" : "Turn microphone off"} onClick={props.onMute}>
            {props.muted ? <MicOff size={17} /> : <Mic size={17} />}
          </button>
          <button type="button" className="dock-btn dock-end" aria-label="End call" onClick={props.onEnd}>
            <PhoneOff size={17} />
          </button>
        </div>
      ) : (
        <button type="button" className="dock-cta" disabled={props.disabled} onClick={props.onStart}>
          <Mic size={15} /> Talk to {PERSONA.name}
        </button>
      )}
    </div>
  );
}

export function FacePlaceholder() {
  return (
    <div className="face-placeholder" aria-hidden>
      <span>{PERSONA.initial}</span>
    </div>
  );
}
