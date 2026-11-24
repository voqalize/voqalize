import { persona } from "../persona";
import { useVoiceClient } from "../stage/client";
import { actions, useStore } from "../state/store";
import { useFakeCall } from "../voice/fake";

/**
 * EN / हिंदी, beside every call button. Before a call it picks the language the
 * call starts in (`init.lang`); during one, pressing the other language asks the
 * agent to switch (`language_requested`), and the toggle moves when she does
 * (`language_changed`).
 */
export function LangToggle({ compact = false }: { compact?: boolean }) {
  const lang = useStore((s) => s.lang);
  const pending = useStore((s) => s.pendingLang);
  const live = useVoiceClient((s) => s.live);
  const fake = useFakeCall((s) => s.on);
  const inCall = live || fake;
  return (
    <div className={`lang${compact ? " is-compact" : ""}`} role="radiogroup" aria-label="Call language">
      {persona.languages.map((l) => (
        <button
          key={l.code}
          type="button"
          role="radio"
          lang={l.code}
          aria-checked={lang === l.code}
          className={`lang-opt${lang === l.code ? " is-on" : ""}${pending === l.code ? " is-pending" : ""}`}
          title={l.label}
          onClick={() => {
            if (l.code === lang) return;
            if (inCall) actions.requestLang(l.code);
            else actions.setLang(l.code);
          }}
        >
          {l.short}
        </button>
      ))}
    </div>
  );
}
