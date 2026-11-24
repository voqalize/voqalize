import { persona } from "../persona";
import { chooseLanguage, useUi } from "../state/ui";

/** EN / हिंदी by the call button: the call's language. Mid-call a flip tells the brain. */
export function LanguageToggle() {
  const lang = useUi((s) => s.lang);
  return (
    <div className="lang-toggle" role="radiogroup" aria-label="Call language" data-stage-part="lang-toggle">
      {persona.languages.map((l) => (
        <button
          key={l.code}
          type="button"
          role="radio"
          aria-checked={lang === l.code}
          lang={l.code}
          className={`lang-btn${lang === l.code ? " is-on" : ""}`}
          title={l.label}
          onClick={() => chooseLanguage(l.code)}
        >
          {l.short}
        </button>
      ))}
    </div>
  );
}
