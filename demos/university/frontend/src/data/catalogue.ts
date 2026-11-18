/**
 * The catalogue (`demos/university/data/catalogue.json`), typed, with the
 * finder's facets as CONTRACT.md names them. The brain reads the same file.
 */
import raw from "../../../data/catalogue.json";

export type Level = "ug" | "pg" | "diploma" | "certificate";
export type Mode = "full_time" | "online" | "weekend" | "hybrid";

export interface School {
  id: string;
  name: string;
  short: string;
  dean: string;
  founded: number;
  campuses: string[];
  blurb: string;
  accent: string;
}

export interface Campus {
  id: string;
  name: string;
  label: string;
  address: string;
  acres: number;
}

export interface Round {
  name: string;
  deadline: string;
  note?: string;
}

export interface Intake {
  label: string;
  starts: string;
  rounds: Round[];
}

export interface Scholarship {
  id: string;
  name: string;
  for: string;
  basis: string;
  tiers: { rule: string; waiver: number }[];
}

export interface Program {
  id: string;
  name: string;
  award: string;
  school: string;
  level: Level;
  mode: Mode;
  campuses: string[];
  duration_months: number;
  duration_label: string;
  hours_per_week: number;
  fee_per_year: number;
  fee_total: number;
  application_fee: number;
  seats: number;
  intake: string;
  eligibility: { requires: string; min_percent: number; needs: string; streams: string[]; min_experience_years?: number };
  entrance: string[];
  selection: string[];
  scholarships: string[];
  outcomes: { placement_pct?: number; median_ctc_lpa?: number; highest_ctc_lpa?: number; note?: string; roles: string[] };
  highlights: string[];
  modules: string[];
  interests: string[];
  specialisations: string[];
}

interface Band {
  id: string;
  label: string;
  min: number;
  max: number;
}

export interface Catalogue {
  university: { name: string; short: string; founded: number; students: number; faculty: number; recruiters: number; campus_count: number; motto: string };
  schools: School[];
  campuses: Campus[];
  levels: { id: Level; label: string }[];
  modes: { id: Mode; label: string }[];
  fee_bands: Band[];
  hour_bands: Band[];
  intakes: Record<string, Intake>;
  scholarships: Scholarship[];
  programs: Program[];
}

export const CATALOGUE = raw as unknown as Catalogue;
export const UNIVERSITY = CATALOGUE.university;
export const SCHOOLS = CATALOGUE.schools;
export const CAMPUSES = CATALOGUE.campuses;
export const PROGRAMS = CATALOGUE.programs;
export const SCHOLARSHIPS = CATALOGUE.scholarships;
export const INTAKES = CATALOGUE.intakes;

export const programById = (id: string | null | undefined) => PROGRAMS.find((p) => p.id === id) ?? null;
export const schoolById = (id: string | null | undefined) => SCHOOLS.find((s) => s.id === id) ?? null;
export const campusById = (id: string) => CAMPUSES.find((c) => c.id === id) ?? null;
export const scholarshipById = (id: string) => SCHOLARSHIPS.find((s) => s.id === id) ?? null;
export const levelLabel = (l: Level) => CATALOGUE.levels.find((x) => x.id === l)?.label ?? l;
export const modeLabel = (m: Mode) => CATALOGUE.modes.find((x) => x.id === m)?.label ?? m;
export const campusNames = (p: Program) => p.campuses.map((c) => campusById(c)?.name ?? c).join(", ");
export const programsOf = (school: string) => PROGRAMS.filter((p) => p.school === school);

// ─── Money and dates ───────────────────────────────────────────────────────

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
/** ₹3,40,000 */
export const rupees = (n: number) => `₹${INR.format(n)}`;
/** 8.4 LPA → "₹8.4 lakh a year" */
export const lpa = (n: number) => `₹${n} lakh a year`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "31 Jan 2027" → a Date at the end of that day. */
export function parseDate(s: string): Date | null {
  const m = /^(\d{1,2}) (\w{3}) (\d{4})$/.exec(s.trim());
  if (!m) return null;
  const month = MONTHS.indexOf(m[2]);
  if (month < 0) return null;
  return new Date(Number(m[3]), month, Number(m[1]), 23, 59, 59);
}

/** The first round of an intake whose deadline has not passed (the last one when all have). */
export function nextRound(intakeId: string, now: Date = new Date()): (Round & { intake: Intake }) | null {
  const intake = INTAKES[intakeId];
  if (!intake) return null;
  const open = intake.rounds.find((r) => (parseDate(r.deadline)?.getTime() ?? 0) >= now.getTime());
  const r = open ?? intake.rounds[intake.rounds.length - 1];
  return r ? { ...r, intake } : null;
}

export const nextDeadline = (p: Program) => {
  const r = nextRound(p.intake);
  return r ? `${r.deadline} (${r.name})` : "—";
};

// ─── Finder facets (CONTRACT.md "Finder facets") ──────────────────────────

export type FacetName = "Level" | "School" | "Mode" | "Campus" | "Fee" | "Hours";
export const FACET_NAMES: FacetName[] = ["Level", "School", "Mode", "Campus", "Fee", "Hours"];

export interface FacetOption {
  id: string;
  label: string;
  /** Other words a person or the agent may use for it. */
  aliases: string[];
  match: (p: Program) => boolean;
}

export interface Facet {
  name: FacetName;
  options: FacetOption[];
}

export const FACETS: Facet[] = [
  {
    name: "Level",
    options: CATALOGUE.levels.map((l) => ({
      id: l.id,
      label: l.label,
      aliases: l.id === "ug" ? ["ug", "bachelor", "bachelors", "undergrad"] : l.id === "pg" ? ["pg", "master", "masters", "postgrad"] : [],
      match: (p) => p.level === l.id,
    })),
  },
  {
    name: "School",
    options: SCHOOLS.map((s) => ({ id: s.id, label: s.short, aliases: [s.name, s.id], match: (p) => p.school === s.id })),
  },
  {
    name: "Mode",
    options: CATALOGUE.modes.map((m) => ({
      id: m.id,
      label: m.label,
      aliases: m.id === "full_time" ? ["full time", "full-time", "on campus", "campus", "regular"] : [m.id],
      match: (p) => p.mode === m.id,
    })),
  },
  {
    name: "Campus",
    options: CAMPUSES.map((c) => ({ id: c.id, label: c.name, aliases: [c.label, c.id, ...(c.id === "bengaluru" ? ["bangalore"] : [])], match: (p) => p.campuses.includes(c.id) })),
  },
  {
    name: "Fee",
    options: CATALOGUE.fee_bands.map((b) => ({ id: b.id, label: b.label, aliases: [], match: (p) => p.fee_per_year >= b.min && p.fee_per_year <= b.max })),
  },
  {
    name: "Hours",
    options: CATALOGUE.hour_bands.map((b) => ({ id: b.id, label: b.label, aliases: [], match: (p) => p.hours_per_week >= b.min && p.hours_per_week <= b.max })),
  },
];

export const facetByName = (name: FacetName) => FACETS.find((f) => f.name === name)!;

/** Loosen a said value for matching: case, dashes, rupee signs, "hours". */
export function loose(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[‐-―]/g, "-")
    .replace(/₹|\brs\.?\s*/g, "")
    .replace(/\bhours?\b/g, "hrs")
    .replace(/\b(a|per) week\b|\/ ?week|\bweekly\b/g, "")
    .replace(/\blakhs?\b|\blacs?\b/g, "lakh")
    .replace(/(\d)\s*l\b/g, "$1 lakh")
    .replace(/\s*-\s*/g, "-")
    .replace(/[_]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The facet a said name means: "level", "fees", "campuses". */
export function resolveFacet(said: string): Facet | null {
  const s = loose(said).replace(/s$/, "");
  const alias: Record<string, FacetName> = { fee: "Fee", budget: "Fee", price: "Fee", hr: "Hours", hrs: "Hours", hour: "Hours", time: "Hours", "study mode": "Mode", "programme level": "Level", "program level": "Level", location: "Campus", city: "Campus", schoo: "School" };
  const name = FACET_NAMES.find((n) => loose(n).replace(/s$/, "") === s) ?? alias[s];
  return name ? facetByName(name) : null;
}

/** The option of `facet` a said value means: its id, its label, or a known alias. */
export function resolveOption(facet: Facet, said: string): FacetOption | null {
  const s = loose(said);
  if (!s) return null;
  const exact = facet.options.find((o) => [o.id, o.label, ...o.aliases].some((x) => loose(x) === s));
  if (exact) return exact;
  // "1-2 lakh" for "₹1–2 lakh", "up to 8 hrs" for "Up to 8 hrs a week".
  const starts = facet.options.filter((o) => loose(o.label).startsWith(s) || s.startsWith(loose(o.label)));
  return starts.length === 1 ? starts[0] : null;
}

/** A programme said by id or by (close) name. */
export function resolveProgram(said: string | null | undefined): Program | null {
  if (!said) return null;
  const s = said.trim().toLowerCase();
  const byId = PROGRAMS.find((p) => p.id === s);
  if (byId) return byId;
  const norm = (x: string) => x.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const n = norm(said);
  if (!n) return null;
  const byName = PROGRAMS.find((p) => norm(p.name) === n);
  if (byName) return byName;
  const starts = PROGRAMS.filter((p) => norm(p.name).startsWith(n));
  if (starts.length === 1) return starts[0];
  const contains = PROGRAMS.filter((p) => norm(p.name).includes(n));
  return contains.length === 1 ? contains[0] : null;
}
