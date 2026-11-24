import { PERSONA } from "../persona";
import { requestLanguage, useLang } from "./lang";

/** EN / हिंदी, labels from persona.json. */
export function LangToggle() {
  const lang = useLang((s) => s.lang);
  return (
    <div className="lang" role="group" aria-label="Language">
      {PERSONA.languages.map((l) => (
        <button
          key={l.code}
          type="button"
          lang={l.code}
          className={`lang-btn${lang === l.code ? " is-on" : ""}`}
          aria-pressed={lang === l.code}
          title={l.label}
          onClick={() => requestLanguage(l.code)}
        >
          {l.toggle}
        </button>
      ))}
    </div>
  );
}
