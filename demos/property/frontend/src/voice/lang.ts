/**
 * The EN / हिंदी toggle's behaviour. The language itself is the store's `lang`
 * (`state/store.ts`), remembered across reloads in localStorage, so a reload
 * mid-call keeps it and the next call (or a redial) starts in it. Before a call
 * a press only changes it, and the connect `init` carries it; during one, a
 * press sends the typed app event `language_requested {language}` and the
 * toggle follows the brain's `language_changed {language}` site command.
 */
import { create } from "zustand";
import { PERSONA } from "../data/persona";
import { useStore } from "../state/store";

/** The live call's `client.sendUIEvent`, while a call is up. */
export const useLangLink = create<{ send: ((event: string, payload: unknown) => void) | null }>(() => ({ send: null }));

export function requestLanguage(tag: string) {
  const { send } = useLangLink.getState();
  if (!send) {
    useStore.getState().setLang(tag);
    return;
  }
  if (tag === useStore.getState().lang) return;
  try {
    send("language_requested", { language: tag });
  } catch (err) {
    console.warn("language_requested not sent", err);
  }
}

/** The brain's `language_changed`: the toggle follows (and is remembered). */
export function languageChanged(payload: unknown) {
  const tag = (payload as { language?: string } | null)?.language;
  if (tag && PERSONA.languages.some((l) => l.tag === tag)) useStore.getState().setLang(tag);
}
