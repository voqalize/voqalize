/**
 * The EN / हिंदी toggle's state. Before a call it is only the `lang` the
 * connect `init` carries; during one, a press sends the typed app event
 * `language_requested {language}` and the toggle follows the brain's
 * `language_changed {language}` site command.
 */
import { create } from "zustand";
import { PERSONA, type Language } from "../persona";

type Code = Language["code"];
interface LangState {
  lang: Code;
  /** The live call's `client.sendUIEvent`, while a call is up. */
  send: ((event: string, payload: unknown) => void) | null;
}

export const useLang = create<LangState>(() => ({ lang: PERSONA.default_language, send: null }));

export function requestLanguage(code: Code) {
  const { send } = useLang.getState();
  if (!send) {
    useLang.setState({ lang: code });
    return;
  }
  try {
    send("language_requested", { language: code });
  } catch (err) {
    console.warn("language_requested not sent", err);
  }
}

/** The brain's `language_changed`: the toggle follows. */
export function languageChanged(payload: unknown) {
  const code = (payload as { language?: string } | null)?.language;
  if (PERSONA.languages.some((l) => l.code === code)) useLang.setState({ lang: code as Code });
}
