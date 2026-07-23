/**
 * Loads the Aura L1-support knowledge base from the markdown wiki under `kb/`.
 *
 * The markdown files ARE the source of truth (the deliverable the agent reads).
 * Vite inlines them at build via `import.meta.glob(..., '?raw')`; we parse the
 * flat front-matter (and, for video files, a fenced ```json``` chapters block)
 * into typed `Article` / `VideoIndex` objects the app renders from.
 *
 * Front-matter is intentionally simple (flat `key: value`, with `[a, b, c]`
 * inline arrays and `true/false` booleans) so it needs no YAML dependency; the
 * one nested structure — video chapters — lives in the JSON block.
 */

import type { Article, Category, CategoryId, VideoChapter, VideoIndex } from './types';

export const CATEGORIES: Category[] = [
  { id: 'cards', title: 'Cards', title_hi: 'कार्ड्स', blurb: 'Debit & credit cards, PIN, limits, rewards' },
  { id: 'accounts', title: 'Accounts', title_hi: 'अकाउंट्स', blurb: 'Open account, KYC, balance, cheque book' },
  { id: 'netbanking', title: 'Aura NetBanking & App', title_hi: 'नेट बैंकिंग और ऐप', blurb: 'Register on Aura Mobile & Internet Banking, MPIN' },
  { id: 'payments', title: 'Payments', title_hi: 'पेमेंट्स', blurb: 'Send money, add payee, UPI/IMPS/NEFT limits' },
  { id: 'loans-deposits', title: 'Loans & Deposits', title_hi: 'लोन और डिपॉज़िट', blurb: 'Interest & TDS certificates, statements, FDs' },
  { id: 'support', title: 'Support', title_hi: 'सहायता', blurb: 'Helpline numbers, branch/ATM, complaints' },
];

const CATEGORY_IDS = new Set<string>(CATEGORIES.map((c) => c.id));

// ── tiny front-matter parser ───────────────────────────────────────────────
interface Parsed {
  meta: Record<string, string | string[] | boolean>;
  body: string;
}

function parseScalar(raw: string): string | string[] | boolean {
  const v = raw.trim();
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v.startsWith('[') && v.endsWith(']')) {
    return v
      .slice(1, -1)
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }
  // Strip surrounding quotes if present.
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    return v.slice(1, -1);
  }
  return v;
}

function parseFrontmatter(text: string): Parsed {
  const m = /^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/.exec(text);
  if (!m) return { meta: {}, body: text };
  const meta: Record<string, string | string[] | boolean> = {};
  for (const line of m[1].split('\n')) {
    const idx = line.indexOf(':');
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    if (!key) continue;
    meta[key] = parseScalar(line.slice(idx + 1));
  }
  return { meta, body: m[2].trim() };
}

function asStr(v: string | string[] | boolean | undefined): string | undefined {
  return typeof v === 'string' ? v : undefined;
}
function asArr(v: string | string[] | boolean | undefined): string[] {
  return Array.isArray(v) ? v : [];
}
function asBool(v: string | string[] | boolean | undefined): boolean {
  return v === true;
}

/** Pull the first fenced ```json block out of a markdown body. */
function extractJsonBlock<T>(body: string): { data: T | null; rest: string } {
  const m = /```json\s*\n([\s\S]*?)\n```/.exec(body);
  if (!m) return { data: null, rest: body };
  let data: T | null = null;
  try {
    data = JSON.parse(m[1]) as T;
  } catch {
    data = null;
  }
  const rest = (body.slice(0, m.index) + body.slice(m.index + m[0].length)).trim();
  return { data, rest };
}

// ── load the wiki ───────────────────────────────────────────────────────────
const RAW = import.meta.glob('./kb/**/*.md', { query: '?raw', eager: true, import: 'default' }) as Record<
  string,
  string
>;

function buildKb(): { articles: Article[]; videos: Record<string, VideoIndex> } {
  const articles: Article[] = [];
  const videos: Record<string, VideoIndex> = {};

  for (const [path, text] of Object.entries(RAW)) {
    const { meta, body } = parseFrontmatter(text);

    if (path.includes('/videos/')) {
      const youtube_id = asStr(meta.youtube_id);
      if (!youtube_id) continue;
      const { data, rest } = extractJsonBlock<{ chapters: VideoChapter[] }>(body);
      videos[youtube_id] = {
        youtube_id,
        title: asStr(meta.title) ?? youtube_id,
        title_hi: asStr(meta.title_hi),
        channel: asStr(meta.channel),
        duration_sec: Number(asStr(meta.duration_sec) ?? '0') || undefined,
        topics: asArr(meta.topics),
        article: asStr(meta.article),
        default_start: Number(asStr(meta.default_start) ?? '0') || 0,
        chapters: data?.chapters ?? [],
        description: rest,
      };
      continue;
    }

    const category = asStr(meta.category);
    const id = asStr(meta.id);
    // Skip the index page and anything not in a real category.
    if (!id || !category || !CATEGORY_IDS.has(category)) continue;
    articles.push({
      id,
      title: asStr(meta.title) ?? id,
      title_en: asStr(meta.title_en),
      category: category as CategoryId,
      tags: asArr(meta.tags),
      video: asStr(meta.video),
      needs_login: asBool(meta.needs_login),
      hero: asBool(meta.hero),
      related: asArr(meta.related),
      helpline: asStr(meta.helpline),
      body,
    });
  }

  return { articles, videos };
}

const KB = buildKb();

export const ARTICLES: Article[] = KB.articles;
export const VIDEOS: Record<string, VideoIndex> = KB.videos;

const ARTICLE_BY_ID = new Map(ARTICLES.map((a) => [a.id, a]));

export function getArticle(id: string): Article | undefined {
  return ARTICLE_BY_ID.get(id);
}
export function getVideo(id: string | undefined): VideoIndex | undefined {
  return id ? VIDEOS[id] : undefined;
}
export function articlesIn(category: CategoryId): Article[] {
  // Hero flows first, then the rest.
  return ARTICLES.filter((a) => a.category === category).sort(
    (a, b) => Number(b.hero) - Number(a.hero),
  );
}
export function heroArticles(): Article[] {
  return ARTICLES.filter((a) => a.hero);
}

/** Index of the chapter whose [start, end) contains `t` (or the last one). */
export function chapterAt(video: VideoIndex, t: number): number {
  for (let i = 0; i < video.chapters.length; i++) {
    const c = video.chapters[i];
    if (t >= c.start && t < c.end) return i;
  }
  // Before the first chapter → first; after the last → last.
  if (video.chapters.length && t < video.chapters[0].start) return 0;
  return Math.max(0, video.chapters.length - 1);
}
