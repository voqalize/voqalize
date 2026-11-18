import { PERSONA } from "../persona";
import { chooseLang, useLang } from "./lang";

export function LangToggle() {
  const lang = useLang((s) => s.lang);
  if (PERSONA.languages.length < 2) return null;
  return (
    <div className="lang" role="radiogroup" aria-label="Language">
      {PERSONA.languages.map((l) => (
        <button key={l.tag} type="button" role="radio" aria-checked={lang === l.tag} lang={l.tag} className={lang === l.tag ? "is-on" : ""} onClick={() => chooseLang(l.tag)} title={l.name}>
          {l.label}
        </button>
      ))}
    </div>
  );
}
