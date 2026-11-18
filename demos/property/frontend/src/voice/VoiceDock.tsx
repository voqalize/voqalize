/**
 * The call dock: the guide's name and role, the language toggle, and "Talk to
 * {name}". The live call (pipecat, the transport, the avatar) is a separate
 * chunk loaded only when this build carries an agent id and a publishable key,
 * so a site without voice never downloads it.
 */
import { Mic } from "lucide-react";
import { Suspense, lazy, useState } from "react";
import { demo } from "../config";
import { PERSONA } from "../data/persona";
import { useStore } from "../state/store";

const VoiceCall = lazy(() => import("./VoiceCall"));
export const voiceConfigured = Boolean(demo.agentId && demo.publishableKey);

export function LanguageToggle({ disabled }: { disabled?: boolean }) {
  const lang = useStore((s) => s.lang);
  return (
    <div className="lang" role="radiogroup" aria-label="Language">
      {PERSONA.languages.map((l) => (
        <button
          key={l.tag}
          type="button"
          role="radio"
          aria-checked={lang === l.tag}
          className={lang === l.tag ? "is-on" : ""}
          disabled={disabled}
          lang={l.tag}
          onClick={() => useStore.getState().setLang(l.tag)}
          title={`Talk in ${l.name}`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

export function VoiceDock() {
  if (voiceConfigured) {
    return (
      <Suspense fallback={<OfflineDock loading />}>
        <VoiceCall />
      </Suspense>
    );
  }
  return <OfflineDock />;
}

function OfflineDock({ loading }: { loading?: boolean }) {
  const [told, setTold] = useState(false);
  return (
    <div className="dock" role="region" aria-label={`Talk to ${PERSONA.name}`}>
      <div className="dock-face is-placeholder" aria-hidden>
        {PERSONA.name[0]}
      </div>
      <div className="dock-text">
        <p className="dock-name">{PERSONA.name}</p>
        <p className="dock-status">{told ? "Voice is not connected in this build" : PERSONA.role}</p>
      </div>
      <LanguageToggle />
      <button type="button" className="dock-cta" disabled={loading} onClick={() => setTold(true)}>
        <Mic size={16} /> <span>Talk to {PERSONA.name}</span>
      </button>
    </div>
  );
}
