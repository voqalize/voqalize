import { PERSONA } from "../persona";
import { chooseLang, useLang } from "./lang";

/**
 * EN / हिंदी, in the persona's order: in the idle bar before a call, in the
 * call tile during one (see `lang.ts` for what a press does in each).
 */
export function LangToggle() {
  const lang = useLang((s) => s.lang);
  if (PERSONA.languages.length < 2) return null;
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      {PERSONA.languages.map((l) => (
        <button key={l.tag} type="button" lang={l.tag} aria-pressed={lang === l.tag} title={l.name} onClick={() => chooseLang(l.tag)}>
          {l.label}
        </button>
      ))}
    </div>
  );
}
