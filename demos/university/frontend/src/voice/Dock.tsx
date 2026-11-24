/**
 * The idle dock, the agent's one entry point: a pill at the bottom right with
 * the character's still photo (the face slot the call tile sits on), the name,
 * the job on this page (persona.json `roles`), the EN / हिंदी toggle and
 * "Talk to {name}". In a call the pill goes away and the face becomes the
 * floating call tile (`CallTile`), which holds the language toggle, mute,
 * minimise and end. No transcript is shown anywhere.
 */
import { Loader2, Mic } from "lucide-react";
import { useLocation } from "react-router-dom";
import { PERSONA, roleFor } from "../data/persona";
import { LangToggle } from "./LangToggle";
import { useDockMode } from "./useDockMode";

export type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

/** `calling` hides the pill (the tile has the call); `status` replaces the role line (an error, or "voice is off"). */
export function DockBar({
  calling,
  activity,
  status,
  onTalk,
  disabled = false,
  title,
}: {
  calling: boolean;
  activity: Activity;
  status?: string | null;
  onTalk?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  const mode = useDockMode();
  const role = roleFor(useLocation().pathname);
  const connecting = activity === "connecting";
  return (
    <div
      className={`dock is-${activity}${calling ? " is-calling" : ""}${mode.classes}`}
      role="region"
      aria-label={`Talk to ${PERSONA.name}`}
      aria-hidden={calling || undefined}
    >
      <div className="dock-face dock-face-slot" aria-hidden />
      <div className="dock-text">
        <p className="dock-name">{PERSONA.name}</p>
        <p className="dock-status" aria-live="polite" title={status ?? role}>
          {status ?? role}
        </p>
      </div>
      <LangToggle />
      <button
        type="button"
        className="dock-cta"
        aria-label={`Talk to ${PERSONA.name}`}
        disabled={disabled || connecting}
        title={title}
        onClick={onTalk}
        tabIndex={calling ? -1 : undefined}
      >
        {connecting ? <Loader2 size={16} className="spin" aria-hidden /> : <Mic size={16} aria-hidden />}
        <span className="dock-cta-long">Talk to {PERSONA.name}</span>
        <span className="dock-cta-short" aria-hidden>
          Talk
        </span>
      </button>
    </div>
  );
}
