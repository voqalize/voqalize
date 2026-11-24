import { nameIn } from "../persona";

/** The call button's words, in the language the call will start in. */
export function callLabel(lang: string): string {
  return lang === "hi" ? `${nameIn("hi")} से बात करें` : `Talk to ${nameIn(lang)}`;
}
