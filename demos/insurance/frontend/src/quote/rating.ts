/**
 * The quote engine: data/products.json's `method` lines, in TypeScript.
 *
 * The brain has the same engine in Python (backend/rating.py), so a premium is
 * the same whether the visitor clicks the form full or the agent fills it by
 * voice. data/quote_cases.json holds golden cases written by that module and
 * checked here (rating.test.ts). Answers are strings, as the form stores them.
 * Every breakdown line is rounded to the rupee, half up; the net is the sum of
 * the rounded lines, so the lines on screen add up to what the agent says.
 *
 * Keep the arithmetic in the same order as rating.py: floating point is the
 * same in both languages only when the operations are.
 */
import { RATING_YEAR, cities, ncbByYears, productById } from "../data";
import type { AddonSpec, Product, ProductId } from "../data/types";
import { inr } from "../lib/format";

export interface QuoteLine {
  id: string;
  label: string;
  amount: number;
}

export interface Quote {
  product: ProductId;
  complete: boolean;
  missing: string[];
  lines: QuoteLine[];
  net: number;
  gst_percent: number;
  gst: number;
  total: number;
  idv?: number;
  unavailable: Record<string, string>;
  error?: string;
}

type Answers = Record<string, string>;
type Ctx = Record<string, number>;

/** Half up, to the rupee. */
export const rnd = (x: number): number => Math.floor(x + 0.5 + 1e-9);

/** A discount line: the rounded amount, negative (never -0). */
const neg = (x: number): number => -rnd(x) || 0;

const DISCOUNTS = new Set(["ncb", "vd", "copay", "high_cover", "security", "group", "ped"]);

class Refused extends Error {}

const spec = (p: ProductId): Product => {
  const s = productById(p);
  if (!s) throw new Error(`no product ${p}`);
  return s;
};

export const requiredFields = (p: ProductId): string[] => spec(p).fields.filter((f) => !f.optional).map((f) => f.id);

export const fieldDefaults = (p: ProductId): Answers =>
  Object.fromEntries(spec(p).fields.filter((f) => f.default !== undefined).map((f) => [f.id, String(f.default)]));

export const defaultAddons = (p: ProductId): string[] => spec(p).addons.filter((a) => a.default).map((a) => a.id);

const first = <T>(rows: [number, T][], value: number): T => {
  for (const [upper, x] of rows) if (value <= upper) return x;
  return rows[rows.length - 1][1];
};

const zone = (a: Answers): string => cities.find((c) => c.value === a.city)?.zone ?? "B";
const int = (s: string | undefined): number => parseInt(s ?? "0", 10);

type Engine = (s: Product, a: Answers) => [QuoteLine[], Ctx];

const motorAge = (a: Answers) => Math.max(0, RATING_YEAR - int(a.registration_year));

function motor(s: Product, a: Answers, odRate: number, tpIn: number): [QuoteLine[], Ctx] {
  const t = s.tables;
  const age = motorAge(a);
  const dep = t.idv_depreciation_by_age[Math.min(age, 5)];
  const raw = int(a.ex_showroom) * (1 - dep / 100);
  const idv = rnd(raw / 100) * 100;
  const od = ((idv * odRate) / 100) * t.fuel_factor[a.fuel ?? "petrol"];
  const years = Math.min(int(a.claim_free_years), 5);
  const ncbPct = ncbByYears[years];
  const ncb = (od * ncbPct) / 100;
  const vdPct: number = (t.voluntary_deductible_discount_percent ?? {})[a.voluntary_deductible ?? "0"] ?? 0;
  const vd = ((od - ncb) * vdPct) / 100;
  let tp = tpIn;
  if (a.fuel === "electric") tp *= t.third_party_electric_factor;
  return [
    [
      { id: "od", label: `Own damage (IDV ${inr(idv)})`, amount: rnd(od) },
      { id: "ncb", label: `No Claim Bonus (${ncbPct}%)`, amount: neg(ncb) },
      { id: "vd", label: `Voluntary deductible discount (${vdPct}%)`, amount: neg(vd) },
      { id: "tp", label: "Third-party cover", amount: rnd(tp) },
    ],
    { idv, age, ncb_pct: ncbPct },
  ];
}

const ENGINES: Record<ProductId, Engine> = {
  car(s, a) {
    const t = s.tables;
    const age = motorAge(a);
    const band = age <= 4 ? 0 : age <= 9 ? 1 : 2;
    const rate = t.od_rate_percent[a.vehicle_class][zone(a)][band];
    return motor(s, a, rate, t.third_party[a.vehicle_class]);
  },
  bike(s, a) {
    const t = s.tables;
    return motor(s, a, t.od_rate_percent[a.engine_cc][zone(a)], t.third_party[a.engine_cc]);
  },
  health(s, a) {
    const t = s.tables;
    const adults = int(a.adults);
    const children = int(a.children ?? "0");
    if (a.cover_type === "individual" && (adults !== 1 || children !== 0)) {
      throw new Refused("an individual policy covers one adult and no children; choose a family floater");
    }
    const eldest = int(a.eldest_age);
    const band = (t.age_bands as [number, string][]).findIndex(([upper]) => eldest <= upper);
    const one: number = t.base_by_band[a.sum_insured][band];
    const base = one * (1 + t.second_adult_factor * (adults - 1) + t.child_factor * children) * t.zone_factor[zone(a)];
    const ped = a.pre_existing === "yes" ? (base * t.pre_existing_loading_percent) / 100 : 0;
    const copayPct: number = t.copay_discount_percent[a.voluntary_copay ?? "0"];
    const copay = ((base + ped) * copayPct) / 100;
    return [
      [
        { id: "base", label: "Base premium", amount: rnd(base) },
        { id: "ped", label: "Pre-existing illness loading (10%)", amount: rnd(ped) },
        { id: "copay", label: `Voluntary co-pay discount (${copayPct}%)`, amount: neg(copay) },
      ],
      { base, adults },
    ];
  },
  term(s, a) {
    const t = s.tables;
    const age = int(a.age);
    const till = int(a.cover_till_age);
    if (till - age < t.min_term_years) {
      throw new Refused(`cover must run at least ${t.min_term_years} years; choose a later end age`);
    }
    const cover = int(a.cover_amount);
    const rate = first(t.rate_per_thousand.bands as [number, number][], age);
    let base = (cover / 1000) * rate * t.term_factor[a.cover_till_age];
    if (a.smoker === "yes") base *= t.smoker_factor;
    if (a.gender === "female") base *= t.female_factor;
    const pct = (t.high_cover_discount_percent as [number, number][]).find(([threshold]) => cover >= threshold)![1];
    return [
      [
        { id: "base", label: "Base premium", amount: rnd(base) },
        { id: "high_cover", label: `High-cover discount (${pct}%)`, amount: neg((base * pct) / 100) },
      ],
      { base, age },
    ];
  },
  home(s, a) {
    const t = s.tables;
    const buildingValue = int(a.building_value);
    if (a.ownership === "tenant" && buildingValue) {
      throw new Refused("a tenant insures contents only; set the building value to zero");
    }
    const z: number = t.zone_factor[zone(a)];
    let building = (buildingValue / 1000) * t.building_rate_per_thousand[a.property_type] * z;
    if (int(a.building_age) > t.old_building_years) building *= 1 + t.old_building_loading_percent / 100;
    const contents = (int(a.contents_value) / 1000) * t.contents_rate_per_thousand * z;
    const security = a.security_system === "yes" ? ((building + contents) * t.security_discount_percent) / 100 : 0;
    return [
      [
        { id: "building", label: "Building", amount: rnd(building) },
        { id: "contents", label: "Contents", amount: rnd(contents) },
        { id: "security", label: `Security discount (${t.security_discount_percent}%)`, amount: neg(security) },
      ],
      { building_value: buildingValue },
    ];
  },
  travel(s, a) {
    const t = s.tables;
    const travellers = int(a.travellers);
    const per = t.per_day_per_traveller[a.region][a.plan ?? "essential"] * int(a.trip_days);
    const base = Math.max(per, t.min_per_traveller) * travellers * first(t.age_loading as [number, number][], int(a.eldest_age));
    const group = travellers >= t.group_size ? (base * t.group_discount_percent) / 100 : 0;
    return [
      [
        { id: "base", label: "Base premium", amount: rnd(base) },
        { id: "group", label: `Group discount (${t.group_discount_percent}%)`, amount: neg(group) },
      ],
      { base, travellers },
    ];
  },
};

/** Why an add-on cannot be had with these answers, or null. */
function unavailableWhy(product: ProductId, ad: AddonSpec, a: Answers, ctx: Ctx): string | null {
  if (ad.max_age !== undefined && (ctx.age ?? 0) > ad.max_age) return `only for vehicles up to ${ad.max_age} years old`;
  if (ad.min_ncb !== undefined && (ctx.ncb_pct ?? 0) < ad.min_ncb) return `needs a No Claim Bonus of at least ${ad.min_ncb}%`;
  if (product === "health" && ad.id === "maternity") {
    if (a.cover_type !== "family_floater" || int(a.adults) !== 2 || int(a.eldest_age) > 45) {
      return "only on a family floater with two adults, the eldest 45 or younger";
    }
  }
  if (product === "home" && ad.id === "rent_loss" && a.ownership !== "owner") return "only for owners";
  if (product === "home" && ad.id === "earthquake" && int(a.building_value) <= 0) return "needs a building value";
  return null;
}

function addonPrice(ad: AddonSpec, a: Answers, ctx: Ctx): number {
  const p = ad.price as Record<string, any>;
  if ("flat" in p) return p.flat;
  if ("idv_percent" in p) return (ctx.idv * p.idv_percent) / 100;
  if ("idv_percent_by_age" in p) return (ctx.idv * first<number>(p.idv_percent_by_age, ctx.age)) / 100;
  if ("base_percent" in p) return (ctx.base * p.base_percent) / 100;
  if ("flat_per_adult" in p) return p.flat_per_adult * ctx.adults;
  if ("flat_per_traveller" in p) return p.flat_per_traveller * ctx.travellers;
  if ("flat_by_age" in p) return first<number>(p.flat_by_age, ctx.age);
  if ("per_thousand_of" in p) return (int(a[p.per_thousand_of]) / 1000) * p.rate;
  throw new Error(`unknown price shape ${JSON.stringify(p)}`);
}

/** The premium for these answers and add-ons (null: the product's defaults), or what is still missing. */
export function quote(product: ProductId, answers: Answers, addons: string[] | null = null): Quote {
  const s = spec(product);
  const a: Answers = { ...fieldDefaults(product) };
  for (const [k, v] of Object.entries(answers)) if (v !== undefined && v !== null && v !== "") a[k] = String(v);
  const on = addons ?? defaultAddons(product);
  const missing = requiredFields(product).filter((f) => !(f in a));
  const q: Quote = {
    product,
    complete: false,
    missing,
    lines: [],
    net: 0,
    gst_percent: s.gst_percent,
    gst: 0,
    total: 0,
    unavailable: {},
  };
  if (missing.length) return q;
  let base: QuoteLine[];
  let ctx: Ctx;
  try {
    [base, ctx] = ENGINES[product](s, a);
  } catch (e) {
    if (e instanceof Refused) {
      q.error = e.message;
      return q;
    }
    throw e;
  }
  if (ctx.idv !== undefined) q.idv = ctx.idv;
  const lines = [...base];
  for (const ad of s.addons) {
    const why = unavailableWhy(product, ad, a, ctx);
    if (why) {
      q.unavailable[ad.id] = why;
      continue;
    }
    if (on.includes(ad.id)) lines.push({ id: `addon:${ad.id}`, label: ad.label, amount: rnd(addonPrice(ad, a, ctx)) });
  }
  q.lines = lines.filter((l) => l.amount !== 0 || !DISCOUNTS.has(l.id));
  q.net = q.lines.reduce((sum, l) => sum + l.amount, 0);
  q.gst = rnd((q.net * s.gst_percent) / 100);
  q.total = q.net + q.gst;
  q.complete = true;
  return q;
}
