/**
 * The widget's words, and how a key is looked up.
 *
 * No dependencies: the launcher reads these before anything else has loaded.
 *
 * A configuration's `words` maps a BCP-47 tag to keys and strings. A key is
 * looked up in the visitor's tag (`es-MX`), then its primary language (`es`),
 * then the built-in words for those, then English. Each string falls back on
 * its own, so a page that translates only the launcher still gets every
 * other word.
 *
 * `{name}` in a string is the agent's display name.
 */

import type { Words } from "../config/types.js";

/** The built-in English words. Every key the elements use is here. */
export const ENGLISH: Readonly<Record<string, string>> = {
  "launcher.label": "Talk to {name}",
  "launcher.tagline": "Ask me anything",
  "launcher.aria": "Start a voice call with {name}",
  "widget.region": "Voice call with {name}",
  "widget.expand": "Open the call",
  "widget.move": "Move the call. Use the arrow keys.",
  "status.idle": "Ready",
  "status.connecting": "Connecting",
  "status.listening": "Listening",
  "status.thinking": "Thinking",
  "status.speaking": "Speaking",
  "status.ended": "Call ended",
  "status.muted": "Muted",
  "status.asking": "Mic off",
  "status.blocked": "Mic blocked",
  "status.missing": "No mic",
  "mic.mute": "Mute",
  "mic.unmute": "Unmute",
  "mic.devices": "Choose microphone and speaker",
  "mic.hint": "We can't hear anything from your mic. Check it isn't muted on your device.",
  "devices.title": "Audio devices",
  "devices.mic": "Microphone",
  "devices.speaker": "Speaker",
  "devices.default": "Default",
  "devices.test": "Say something to test it",
  "devices.close": "Close",
  "controls.minimise": "Minimise",
  "controls.end": "End call",
  "captions.label": "Captions",
  "coach.asking": "Your mic is off. Click Allow in the box at the top of the window so {name} can hear you.",
  "coach.asking.safari": "Your mic is off. Click Allow in the box under the address bar so {name} can hear you.",
  "coach.asking.firefox": "Your mic is off. Click Allow in the box at the left of the address bar so {name} can hear you.",
  "coach.asking.ios": "Your mic is off. Tap Allow in the box on screen so {name} can hear you.",
  "coach.asking.android": "Your mic is off. Tap Allow in the box on screen so {name} can hear you.",
  "coach.blocked":
    "The mic is blocked for this site. Click the icon at the left of the address bar, then allow the microphone.",
  "coach.blocked.safari":
    "The mic is blocked for this site. In the Safari menu, open Settings for This Website and set Microphone to Allow.",
  "coach.blocked.firefox":
    "The mic is blocked for this site. Click the crossed-out mic at the left of the address bar and remove the block.",
  "coach.blocked.ios":
    "The mic is blocked for this site. Tap the page menu in the address bar, open Website Settings, and allow the microphone.",
  "coach.blocked.android":
    "The mic is blocked for this site. Tap the icon at the left of the address bar, open Permissions, and allow the microphone.",
  "coach.missing": "We can't find a microphone. Plug one in, or choose another one from the menu.",
  "coach.dismiss": "Dismiss",
  "end.hung_up": "You ended the call.",
  "end.ended": "The call has ended.",
  "end.mic_denied":
    "The call ended because {name} couldn't hear you. Next time, allow the microphone when your browser asks.",
  "end.connect_failed": "We couldn't connect the call. Please try again.",
  "end.again": "Call again",
  "end.close": "Close",
};

/** The built-in words per language. English only for now; other languages arrive as translated tables. */
const BUILT_IN: Readonly<Record<string, Readonly<Record<string, string>>>> = { en: ENGLISH };

/** The tags to try for a visitor's language, most specific first. */
export function tagChain(lang: string | undefined | null): string[] {
  const chain: string[] = [];
  const tag = (lang ?? "").trim();
  if (tag) {
    chain.push(tag);
    const lower = tag.toLowerCase();
    if (lower !== tag) chain.push(lower);
    const primary = lower.split("-")[0];
    if (primary && !chain.includes(primary)) chain.push(primary);
  }
  return chain;
}

export type Translate = (key: string, vars?: Record<string, string>) => string;

/** A lookup for one language over a configuration's words. */
export function translator(words: Words | undefined, lang: string | undefined | null, name: string): Translate {
  const chain = tagChain(lang);
  return (key, vars) => {
    let text: string | undefined;
    for (const tag of chain) {
      text = words?.[tag]?.[key];
      if (text !== undefined) break;
    }
    if (text === undefined) {
      for (const tag of chain) {
        text = BUILT_IN[tag]?.[key];
        if (text !== undefined) break;
      }
    }
    text ??= words?.en?.[key] ?? ENGLISH[key] ?? key;
    const all: Record<string, string> = { name, ...vars };
    return text.replace(/\{(\w+)\}/g, (match, k: string) => all[k] ?? match);
  };
}

/** The language a page is in: the element's own `lang`, the document's, then the browser's. */
export function pageLanguage(element: Element | null): string {
  const own = element?.closest?.("[lang]")?.getAttribute("lang");
  if (own) return own;
  try {
    return globalThis.navigator?.language ?? "en";
  } catch {
    return "en";
  }
}
