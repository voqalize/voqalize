/**
 * Editorial content: the journal and the store's info pages, written as
 * Markdown in `demos/fernhollow/content/` and bundled at build time.
 *
 * Frontmatter: `title, slug, dek, date (YYYY-MM-DD), room, readMinutes, hero
 * (product id), products: [ids]`. A body line `::product{id="<id>"}` becomes an
 * inline product card. Files whose names start with `_` are development samples
 * and only load in `pnpm dev`.
 */
import { parse as parseYaml } from "yaml";

export interface Doc {
  slug: string;
  title: string;
  dek: string;
  date: string;
  room: string | null;
  readMinutes: number | null;
  hero: string | null;
  products: string[];
  body: string;
  sample: boolean;
}

const journalFiles = import.meta.glob<string>(["../../../content/journal/*.md", "!../../../content/journal/_*.md"], {
  query: "?raw",
  import: "default",
  eager: true,
});
const pageFiles = import.meta.glob<string>(["../../../content/pages/*.md", "!../../../content/pages/_*.md"], {
  query: "?raw",
  import: "default",
  eager: true,
});

let devJournal: Record<string, string> = {};
let devPages: Record<string, string> = {};
if (import.meta.env.DEV) {
  devJournal = import.meta.glob<string>("../../../content/journal/_*.md", { query: "?raw", import: "default", eager: true });
  devPages = import.meta.glob<string>("../../../content/pages/_*.md", { query: "?raw", import: "default", eager: true });
}

function parse(path: string, raw: string): Doc {
  const file = path.split("/").pop()!.replace(/\.md$/, "");
  let meta: Record<string, unknown> = {};
  let body = raw;
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
  if (m) {
    try {
      meta = (parseYaml(m[1]) as Record<string, unknown>) ?? {};
    } catch (err) {
      console.warn(`content: ${path}: bad frontmatter`, err);
    }
    body = raw.slice(m[0].length);
  }
  const str = (k: string) => (meta[k] == null ? "" : String(meta[k]));
  const products = Array.isArray(meta.products) ? meta.products.map(String) : [];
  // A date written bare in YAML parses as a Date; keep it as YYYY-MM-DD.
  const date = meta.date instanceof Date ? meta.date.toISOString().slice(0, 10) : str("date");
  return {
    slug: str("slug") || file.replace(/^_/, ""),
    title: str("title") || file,
    dek: str("dek"),
    date,
    room: str("room") || null,
    readMinutes: meta.readMinutes == null ? null : Number(meta.readMinutes),
    hero: str("hero") || null,
    products,
    body,
    sample: file.startsWith("_"),
  };
}

const load = (files: Record<string, string>) => Object.entries(files).map(([path, raw]) => parse(path, raw));

export const journal: Doc[] = [...load(journalFiles), ...load(devJournal)].sort((a, b) => b.date.localeCompare(a.date));
export const pages: Doc[] = (() => {
  const real = load(pageFiles);
  // A sample never shadows the real page of the same slug.
  const samples = load(devPages).filter((s) => !real.some((r) => r.slug === s.slug));
  return [...real, ...samples];
})();

export const getArticle = (slug?: string) => journal.find((d) => d.slug === slug);
export const getPage = (slug?: string) => pages.find((d) => d.slug === slug);

/** Info pages, the order the footer lists them, and where each lives. */
export const INFO_PAGES: { slug: string; label: string; path: string }[] = [
  { slug: "about", label: "About Fernhollow", path: "/about" },
  { slug: "delivery", label: "Delivery", path: "/policy/delivery" },
  { slug: "returns", label: "Returns", path: "/policy/returns" },
  { slug: "assembly", label: "Assembly", path: "/policy/assembly" },
  { slug: "care", label: "Care guides", path: "/policy/care" },
  { slug: "faq", label: "Questions", path: "/faq" },
];
export const POLICY_TOPICS = ["returns", "delivery", "assembly", "care"] as const;
export type PolicyTopic = (typeof POLICY_TOPICS)[number];

export const pagePath = (slug: string) => INFO_PAGES.find((p) => p.slug === slug)?.path ?? `/policy/${slug}`;

const DATE = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
export const formatDate = (d: string) => {
  const t = Date.parse(`${d}T00:00:00Z`);
  return Number.isNaN(t) ? d : DATE.format(t);
};

/** Split a body into Markdown runs and product directives. */
export type Segment = { kind: "md"; text: string } | { kind: "product"; id: string };
export function segments(body: string): Segment[] {
  const out: Segment[] = [];
  let buf: string[] = [];
  const flush = () => {
    if (buf.join("").trim()) out.push({ kind: "md", text: buf.join("\n") });
    buf = [];
  };
  for (const line of body.split(/\r?\n/)) {
    const m = /^\s*::product\{\s*id\s*=\s*"([^"]+)"\s*\}\s*$/.exec(line);
    if (m) {
      flush();
      out.push({ kind: "product", id: m[1] });
    } else buf.push(line);
  }
  flush();
  return out;
}

// ── Site copy and the policy summary (content/site.json, content/policies.json) ──
import siteJson from "../../../content/site.json";
import policiesJson from "../../../content/policies.json";

export interface SiteCopy {
  hero: { headline: string; subline: string; cta: { label: string; href: string } };
  rooms: Record<string, string>;
  categories: Record<string, string>;
  promises: { title: string; text: string }[];
  newsletter: string;
  footerTagline: string;
}
export const site = siteJson as SiteCopy;
export const policies = policiesJson as Record<string, Record<string, string | number>>;

export const DELIVERY_FREE_OVER = Number(policies.delivery?.freeThreshold ?? 500);
export const DELIVERY_FEE = Number(policies.delivery?.flatFee ?? 49);
export const deliveryFor = (subtotal: number) => (subtotal === 0 || subtotal > DELIVERY_FREE_OVER ? 0 : DELIVERY_FEE);
