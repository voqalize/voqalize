/**
 * The call's look, with no client in it. One control surface at a time:
 *
 * - no call: the dock pill bottom centre — the agent's face, name and role on
 *   this page, the EN / हिंदी toggle and "Talk to {name}";
 * - a call: the pill fades out and the face moves out of it into the floating
 *   tile (`CallTile`), which carries the language toggle, mute, minimise and
 *   end.
 *
 * Nothing here shows what the visitor said. `VoiceCall` drives it from a real
 * call; the `?debug=1` console drives it from a fake one so the live look can
 * be seen and screenshotted.
 */
import { Mic } from "lucide-react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { PERSONA, roleFor } from "../persona";
import { useSite } from "../state/store";
import { type CallState, CallTile } from "./CallTile";
import { useDockMode } from "./useDockMode";
import "@fontsource-variable/noto-sans-devanagari/index.css";
import "./voice.css";

export type { CallState };

export function DockView({
  state,
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
  muted: boolean;
  error?: string | null;
  disabled?: boolean;
  disabledNote?: string;
  onStart: () => void;
  onMute: () => void;
  onEnd: () => void;
  /** The visitor pressed a language, on the pill before a call or on the tile during one. */
  onLanguage: (code: string) => void;
  /** The face: the avatar mount (or a placeholder), kept for the page's whole life. */
  face: ReactNode;
}) {
  const lang = useSite((s) => s.lang);
  const live = state !== "idle" && state !== "error";
  const mode = useDockMode(live);
  const role = roleFor(useLocation().pathname);
  const name = PERSONA.display_name;
  const status = error ?? disabledNote ?? role;
  return (
    <>
      <CallTile live={live} state={state} muted={muted} onMute={onMute} onEnd={onEnd} onLanguage={onLanguage}>
        {face}
      </CallTile>
      <div
        className={`dock is-${state}${live ? " is-calling" : ""}${mode.classes}`}
        role="region"
        aria-label={`Talk to ${name}`}
        aria-hidden={live || undefined}
        inert={live || undefined}
      >
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{name}</p>
          <p className={`dock-status${error ? " is-error" : ""}`} aria-live="polite" title={status}>
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
        <button type="button" className="dock-cta" aria-label={`Talk to ${name}`} disabled={disabled} onClick={onStart} title={disabled ? disabledNote : undefined}>
          <Mic size={16} /> <span className="dock-cta-label">Talk to {name}</span>
        </button>
      </div>
    </>
  );
}
