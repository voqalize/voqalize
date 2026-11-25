import { PERSONA } from "../data/persona";
import { useStore } from "../state/store";
import { requestLanguage } from "./lang";

/** EN / हिंदी, labels from persona.json. */
export function LangToggle() {
  const lang = useStore((s) => s.lang);
  return (
    <div className="lang" role="group" aria-label="Language">
      {PERSONA.languages.map((l) => (
        <button
          key={l.tag}
          type="button"
          lang={l.tag}
          className={`lang-btn${lang === l.tag ? " is-on" : ""}`}
          aria-pressed={lang === l.tag}
          title={`Talk in ${l.name}`}
          onClick={() => requestLanguage(l.tag)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
