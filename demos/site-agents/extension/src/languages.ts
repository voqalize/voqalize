/**
 * A language as the Site Agent's settings name it ("spanish", "english", or an
 * ISO code), as the toggle's code. The settings' names are the platform's one
 * map (the snippet's `codeOf`); Spanish is added here until that map has it.
 */

import { codeOf as snippetCode } from "@snippet/loader/languages";

const MORE: Record<string, string> = { spanish: "es", "español": "es", espanol: "es", castellano: "es", es: "es" };

export function codeOf(name: string): string | null {
  const key = name.trim().toLowerCase();
  return MORE[key] ?? snippetCode(key);
}
