import { persona } from "../persona";
import { emit } from "./events";
import { useLang } from "./lang";

/**
 * EN / हिंदी, in the persona's order. Off a call it sets the language the call
 * will start in; on a call it asks the brain (`language_requested`), and only
 * the brain's `language_changed` moves it.
 */
export function LangToggle({ live }: { live: boolean }) {
  const lang = useLang((s) => s.lang);
  const setLang = useLang((s) => s.setLang);
  if (persona.languages.length < 2) return null;
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      {persona.languages.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={lang === l}
          title={persona.language_names[l]}
          onClick={() => {
            if (l === lang) return;
            if (live) emit("language_requested", { language: l }, "visitor");
            else setLang(l);
          }}
        >
          {persona.language_labels[l] ?? l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
