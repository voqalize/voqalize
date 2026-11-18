/**
 * The voice dock, bottom right: the face, who it is, the status line, the
 * EN / हिंदी toggle and the call button (mute and end while live). The live
 * call and the no-voice build both draw this.
 */
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import type { ReactNode } from "react";
import { type Lang, PERSONA } from "../data/persona";
import { useLanguage } from "./language";

export type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

export function LanguageToggle({ live }: { live: boolean }) {
  const lang = useLanguage((s) => s.lang);
  const choose = useLanguage((s) => s.choose);
  return (
    <div className={`lang-toggle${live ? " is-live" : ""}`} role="group" aria-label="Conversation language">
      {PERSONA.languages.map((l: Lang) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={lang === l}
          title={live ? `Ask to switch to ${PERSONA.language_names[l]}` : `Talk in ${PERSONA.language_names[l]}`}
          onClick={() => choose(l)}
        >
          {PERSONA.language_labels[l]}
        </button>
      ))}
    </div>
  );
}

export function Dock(props: {
  face: ReactNode;
  activity: Activity;
  status: string;
  muted: boolean;
  onCall(): void;
  onMute(): void;
  onEnd(): void;
}) {
  const { activity, muted } = props;
  const live = activity !== "idle" && activity !== "error";
  return (
    <aside className={`dock is-${activity}${live ? " is-live" : ""}`} aria-label={`Talk to ${PERSONA.name}`}>
      <div className="dock-face">{props.face}</div>
      <div className="dock-body">
        <div className="dock-who">
          <p className="dock-name">{PERSONA.name}</p>
          <p className="dock-status" aria-live="polite">
            {props.status}
          </p>
        </div>
        <div className="dock-actions">
          <LanguageToggle live={live} />
          {live ? (
            <>
              <button type="button" className="dock-btn" aria-pressed={muted} aria-label={muted ? "Turn microphone on" : "Turn microphone off"} onClick={props.onMute}>
                {muted ? <MicOff size={17} /> : <Mic size={17} />}
              </button>
              <button type="button" className="dock-btn dock-end" aria-label="End the call" onClick={props.onEnd}>
                <PhoneOff size={17} />
              </button>
            </>
          ) : (
            <button type="button" className="dock-cta" aria-label={`Talk to ${PERSONA.name}`} onClick={props.onCall} disabled={(activity as string) === "connecting"}>
              {(activity as string) === "connecting" ? <Loader2 size={16} className="spin" /> : <Mic size={16} />}
              <span className="dock-cta-long">Talk to {PERSONA.name}</span>
              <span className="dock-cta-short" aria-hidden>
                Talk
              </span>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}

/** The face before a call can load: the persona's initial in a ring. */
export function FacePlaceholder() {
  return (
    <div className="face-placeholder" aria-hidden>
      <span>{PERSONA.name.slice(0, 1)}</span>
    </div>
  );
}
