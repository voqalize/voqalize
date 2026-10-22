/**
 * HTML as plain text, where there is no DOM to read it with: the service
 * worker's copy of the site's records (`acf.aranceles_carrera`,
 * `acf.requisitos_program`) arrives as small, plain WordPress markup.
 */

const ENTITIES: Record<string, string> = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", aacute: "á", eacute: "é", iacute: "í",
  oacute: "ó", uacute: "ú", ntilde: "ñ", Aacute: "Á", Eacute: "É", Iacute: "Í", Oacute: "Ó", Uacute: "Ú",
  Ntilde: "Ñ", uuml: "ü", ordm: "º", ordf: "ª", middot: "·", ndash: "–", mdash: "—", hellip: "…",
};

/** ACF's HTML as plain text, one line per paragraph, list item or break. The
 *  worker has no DOM parser, and the fields are small, plain markup. */
export function htmlText(html: string): string {
  return html
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h[1-6]|tr|ul|ol|table)>/gi, "\n")
    .replace(/<li[^>]*>/gi, "- ")
    .replace(/<\/t[dh]>/gi, " | ")
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_, n: string) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n: string) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&([a-z]+);/gi, (m, name: string) => ENTITIES[name] ?? m)
    .split("\n")
    .map((line) => line.replace(/[ \t\u00a0]+/g, " ").replace(/\s*\|\s*$/, "").trim())
    .filter(Boolean)
    .join("\n");
}

