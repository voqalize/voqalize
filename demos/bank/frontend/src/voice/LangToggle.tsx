import { persona } from "../persona";
import { requestLanguage, useLang } from "./lang";

/**
 * EN / हिंदी, in the persona's order: in the idle dock before a call, in the
 * call tile during one. Off a call it sets the language the call starts in; on
 * a call it asks the brain (`language_requested`), and only the brain's
 * `language_changed` moves it.
 */
export function LangToggle() {
  const lang = useLang((s) => s.lang);
  if (persona.languages.length < 2) return null;
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      {persona.languages.map((l) => (
        <button key={l} type="button" lang={l} aria-pressed={lang === l} title={persona.language_names[l]} onClick={() => requestLanguage(l)}>
          {persona.language_labels[l] ?? l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
