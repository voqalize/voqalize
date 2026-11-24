import { type Lang, PERSONA } from "../data/persona";
import { useLanguage } from "./language";

/** EN / हिंदी, labels from persona.json: before a call it picks the call's language, during one it asks the brain to switch. */
export function LangToggle() {
  const lang = useLanguage((s) => s.lang);
  const choose = useLanguage((s) => s.choose);
  return (
    <div className="lang" role="group" aria-label="Conversation language">
      {PERSONA.languages.map((l: Lang) => (
        <button
          key={l}
          type="button"
          lang={l}
          className={`lang-btn${lang === l ? " is-on" : ""}`}
          aria-pressed={lang === l}
          title={PERSONA.language_names[l]}
          onClick={() => choose(l)}
        >
          {PERSONA.language_labels[l]}
        </button>
      ))}
    </div>
  );
}
