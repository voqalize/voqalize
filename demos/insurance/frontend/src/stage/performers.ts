/**
 * A performer for every move in scene.json. Each one goes to its page if it
 * must, waits for its target, scrolls to it and rings it BEFORE anything
 * changes, then calls the same store action a click calls, and returns one
 * short line the agent can repeat. Anything the page cannot do is refused,
 * with the options it does offer.
 */
import { type MoveContext, type Performers, waitFor } from "@voqalize/stage";
import { PRODUCT_IDS, customer, isProductId, policies, policyById, productById } from "../data";
import type { ProductId } from "../data/types";
import {
  type ClaimType,
  checkClaimValue,
  claimPolicies,
  displayClaimValue,
  fieldById,
  fieldVisible,
  hiddenWhy,
  sectionOfField,
  sectionProgress,
  sectionsFor,
  typeOf,
  visibleFields,
} from "../claim/logic";
import { inrPlain as inr } from "../lib/format";
import { persona } from "../persona";
import { claimMissing, openSection, setClaimField, startClaim, uploadedIds, useClaim } from "../state/claim";
import { VERDICT_LABEL, markClause, viewPolicy } from "../state/policyView";
import { checkValue, displayValue, openQuote, quoteFor, setAddon, setAnswer, useQuote } from "../state/quote";
import { appPath, go, setLanguageFromAgent } from "../state/ui";
import { scene } from "./scene.gen";

const sel = (part: string) => `[data-stage-part="${CSS.escape(part)}"]`;

const shown = (el: Element | null): el is HTMLElement => {
  if (!el) return false;
  const r = (el as HTMLElement).getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** The element marked `data-stage-part=part`, once it is on screen (3 s at most). */
async function part(c: MoveContext, name: string, ms = 3000): Promise<HTMLElement> {
  const el = await waitFor(() => {
    const e = document.querySelector(sel(name));
    return shown(e) ? (e as HTMLElement) : null;
  }, ms);
  if (!el) throw new Error(`${name} did not come up on the page`);
  return el;
}

/** Scroll to it and ring it: before every change. */
async function point(c: MoveContext, el: Element, label: string) {
  await c.scrollTo(el);
  await c.ring(el, label);
}

/**
 * Ring what leads to the next page (a nav link, a card), if it is on screen at
 * all; it is brought fully into view first (X1), so a ring is never cut off.
 */
async function ringIfShown(c: MoveContext, names: string[], label: string) {
  for (const n of names) {
    const el = document.querySelector(sel(n));
    if (shown(el)) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < window.innerHeight) {
        await point(c, el, label);
        return;
      }
    }
  }
}

const productName = (p: ProductId) => productById(p)!.name;

/** The product whose builder is on screen: /quote/<p> or /insurance/<p>. */
function builderOnScreen(): ProductId | null {
  const m = /^\/(?:quote|insurance)\/([^/]+)$/.exec(appPath());
  return m && isProductId(m[1]) ? m[1] : null;
}

function needBuilder(c: MoveContext, arg: string): ProductId {
  const p = builderOnScreen();
  if (!p) return c.refuse(arg, "no quote builder is on screen; open one with quote.open first", PRODUCT_IDS);
  return p;
}

/** "; total now ₹21,840 for 1 year" / "; still needed: Fuel, City" / "; <error>". */
function quoteTail(p: ProductId): string {
  const q = quoteFor(p);
  if (q.error) return `; the quote cannot be priced: ${q.error}`;
  if (q.complete) return `; total now ${inr(q.total)} for 1 year${q.gst ? ` incl. ${inr(q.gst)} GST` : ""}`;
  const spec = productById(p)!;
  const labels = q.missing.map((id) => spec.fields.find((f) => f.id === id)?.label ?? id);
  return `; still needed: ${labels.join(", ")}`;
}

// ─── site.go ──────────────────────────────────────────────────────────────

const PAGES = [
  "home",
  "quote",
  ...PRODUCT_IDS.map((p) => `quote/${p}`),
  ...PRODUCT_IDS.map((p) => `insurance/${p}`),
  "my-policies",
  ...policies.map((p) => `my-policies/${p.id}`),
  "claim",
];

function route(page: string): { path: string; label: string; ring: string[] } | null {
  const pg = page.trim().replace(/^\/+|\/+$/g, "").toLowerCase();
  if (pg === "" || pg === "home") return { path: "/", label: "the home page", ring: ["nav:home"] };
  if (pg === "quote") return { path: "/quote", label: "the quote page", ring: ["nav:quote"] };
  if (pg === "my-policies") return { path: "/my-policies", label: "your policies", ring: ["nav:my-policies"] };
  if (pg === "claim") return { path: "/claim", label: "the claim form", ring: ["nav:claim"] };
  let m = /^quote\/(.+)$/.exec(pg);
  if (m && isProductId(m[1])) return { path: `/quote/${m[1]}`, label: `the ${productName(m[1]).toLowerCase()} quote`, ring: [`quote-tab:${m[1]}`, `product:${m[1]}`, "nav:quote"] };
  m = /^insurance\/(.+)$/.exec(pg);
  if (m && isProductId(m[1])) return { path: `/insurance/${m[1]}`, label: `the ${productName(m[1]).toLowerCase()} page`, ring: [`product:${m[1]}`, `nav:product:${m[1]}`] };
  m = /^my-policies\/(.+)$/.exec(pg);
  if (m) {
    const pol = policyById(m[1]);
    if (pol) return { path: `/my-policies/${pol.id}`, label: `your ${pol.title} (${pol.policy_number})`, ring: [`policy-card:${pol.id}`, "nav:my-policies"] };
  }
  return null;
}

async function navigateTo(c: MoveContext, path: string, ring: string[], label: string, waitPart: string) {
  if (appPath() !== path) {
    await ringIfShown(c, ring, label);
    go(path);
  }
  return part(c, waitPart, 4000);
}

// ─── policy helpers ───────────────────────────────────────────────────────

function needPolicy(c: MoveContext, id: string) {
  const pol = policyById(id);
  if (!pol || !customer.policies.includes(pol.id)) {
    return c.refuse("policy_id", `${customer.first_name} has no policy ${id}`, policies.map((p) => p.id));
  }
  return pol;
}

async function openPolicyDoc(c: MoveContext, id: string) {
  const pol = policyById(id)!;
  return navigateTo(c, `/my-policies/${id}`, [`policy-card:${id}`, "nav:my-policies"], `${pol.title}`, `policy-doc:${id}`);
}

// ─── claim helpers ────────────────────────────────────────────────────────

function needClaim(c: MoveContext, arg: string): ClaimType {
  const t = useClaim.getState().type;
  if (!t) return c.refuse(arg, "no claim is started; start one with claim.start", ["motor", "health"]);
  return t;
}

async function onClaimPage(c: MoveContext) {
  if (appPath() !== "/claim") {
    await ringIfShown(c, ["nav:claim"], "Make a claim");
    go("/claim");
  }
  await part(c, "claim-form", 4000);
}

const short = (s: string) => (s.length > 60 ? `${s.slice(0, 57)}…` : s);

// ─── the performers ───────────────────────────────────────────────────────

export const performers: Performers<typeof scene.spec> = {
  async "site.go"({ page }, c) {
    const r = route(page);
    if (!r) return c.refuse("page", `there is no page ${page}`, PAGES);
    if (appPath() === r.path) return `already on ${r.label}`;
    await ringIfShown(c, r.ring, `Opening ${r.label}`);
    go(r.path);
    await part(c, `page:${r.path}`, 4000).catch(() => null);
    return `opened ${r.label}`;
  },

  async "site.language"({ language }, c) {
    const lang = persona.languages.find((l) => l.code === language);
    if (!lang) return c.refuse("language", `the toggle offers ${persona.languages.map((l) => l.label).join(" and ")}`, persona.languages.map((l) => l.code));
    const el = document.querySelector(sel("lang-toggle"));
    if (shown(el)) await point(c, el, lang.label);
    setLanguageFromAgent(lang.code);
    return `language toggle set to ${lang.label} (${lang.code})`;
  },

  async "quote.open"({ product }, c) {
    if (!isProductId(product)) return c.refuse("product", `Chhatri does not sell ${product}`, PRODUCT_IDS);
    const name = productName(product);
    if (builderOnScreen() !== product) {
      const path = `/quote/${product}`;
      await ringIfShown(c, [`quote-tab:${product}`, `product:${product}`, "nav:quote"], `${name} quote`);
      go(path);
    }
    const el = document.querySelector(sel(`quote-tab:${product}`));
    const target = shown(el) ? el : await part(c, "quote-builder");
    await point(c, target, `${name} quote`);
    openQuote(product);
    return `${name.toLowerCase()} quote builder open${quoteTail(product)}`;
  },

  async "quote.fill"({ field, value }, c) {
    const p = needBuilder(c, "field");
    const spec = productById(p)!;
    const f = spec.fields.find((x) => x.id === field);
    if (!f) return c.refuse("field", `the ${spec.name.toLowerCase()} quote has no field ${field}`, spec.fields.map((x) => x.id));
    const checked = checkValue(f, String(value));
    if (!checked.ok) return c.refuse("value", checked.why, checked.options);
    const el = await part(c, `quote-field:${f.id}`);
    await point(c, el, f.label);
    setAnswer(p, f.id, checked.value);
    return `${f.label} set to ${displayValue(f, checked.value)}${quoteTail(p)}`;
  },

  async "quote.addon"({ addon, on }, c) {
    const p = needBuilder(c, "addon");
    const spec = productById(p)!;
    const ad = spec.addons.find((a) => a.id === addon);
    if (!ad) return c.refuse("addon", `the ${spec.name.toLowerCase()} quote has no add-on ${addon}`, spec.addons.map((a) => a.id));
    const q = quoteFor(p);
    const why = q.unavailable[ad.id];
    if (on && why) {
      return c.refuse("addon", `${ad.label} is ${why}`, spec.addons.filter((a) => !q.unavailable[a.id]).map((a) => a.id));
    }
    const el = await part(c, `addon:${ad.id}`);
    await point(c, el, ad.label);
    const was = useQuote.getState().addons[p].includes(ad.id);
    if (was === on) return `${ad.label} was already ${on ? "on" : "off"}${quoteTail(p)}`;
    setAddon(p, ad.id, on);
    return `${ad.label} ${on ? "on" : "off"}${quoteTail(p)}`;
  },

  async "quote.show"(_args, c) {
    const p = needBuilder(c, "breakdown");
    const el = await part(c, "breakdown");
    await point(c, el, "Premium breakdown");
    const q = quoteFor(p);
    if (q.error) return `breakdown on screen; it cannot be priced: ${q.error}`;
    if (!q.complete) return `breakdown on screen${quoteTail(p)}`;
    const lines = q.lines.map((l) => `${l.label} ${inr(l.amount)}`).join(", ");
    return `breakdown on screen: ${lines}; net ${inr(q.net)}, GST ${inr(q.gst)}, total ${inr(q.total)} for 1 year`;
  },

  async "policy.open"({ policy_id, section }, c) {
    const pol = needPolicy(c, policy_id);
    const sec = section ? pol.sections.find((s) => s.id === section || s.number === section) : null;
    if (section && !sec) return c.refuse("section", `${pol.title} has no section ${section}`, pol.sections.map((s) => s.id));
    const doc = await openPolicyDoc(c, pol.id);
    if (sec) {
      const el = await part(c, `section:${sec.id}`);
      await point(c, el, `${sec.number}. ${sec.title}`);
    } else {
      await point(c, doc.querySelector(sel("policy-head")) ?? doc, pol.title);
    }
    viewPolicy(pol.id, sec?.id ?? null);
    return `opened ${pol.title} ${pol.policy_number}${sec ? `, at section ${sec.number} ${sec.title}` : ""}`;
  },

  async "policy.mark"({ policy_id, clause_id, verdict }, c) {
    const pol = needPolicy(c, policy_id);
    const sec = pol.sections.find((s) => s.clauses.some((cl) => cl.id === clause_id));
    const clause = sec?.clauses.find((cl) => cl.id === clause_id);
    if (!sec || !clause) {
      return c.refuse("clause_id", `${pol.title} has no clause ${clause_id}`, pol.sections.flatMap((s) => s.clauses.map((cl) => cl.id)));
    }
    await openPolicyDoc(c, pol.id);
    const el = await part(c, `clause:${clause.id}`);
    await point(c, el, `Clause ${clause.id}`);
    markClause(pol.id, clause.id, verdict);
    viewPolicy(pol.id, sec.id);
    return `clause ${clause.id} “${clause.title}” marked ${VERDICT_LABEL[verdict]}`;
  },

  async "claim.start"({ claim_type, policy_id }, c) {
    const type = typeOf(claim_type)!;
    const own = claimPolicies(claim_type);
    let pol = policy_id ? own.find((p) => p.id === policy_id) : undefined;
    if (policy_id && !pol) return c.refuse("policy_id", `${policy_id} is not one of ${customer.first_name}'s ${claim_type} policies`, own.map((p) => p.id));
    if (!pol && own.length === 1) pol = own[0];
    if (appPath() !== "/claim") {
      await ringIfShown(c, ["nav:claim"], "Make a claim");
      go("/claim");
    }
    const card = await part(c, "claim-types", 4000);
    const choice = card.querySelector(sel(`claim-type:${claim_type}`)) ?? card;
    await point(c, choice, type.label);
    startClaim(claim_type, pol?.id ?? null);
    const first = sectionsFor(claim_type)[0];
    return `${type.label.toLowerCase()} started${pol ? ` on ${pol.title} ${pol.policy_number}` : ""}; open at ${first.title}`;
  },

  async "claim.fill"({ field, value }, c) {
    const type = needClaim(c, "field");
    const s = useClaim.getState();
    const f = fieldById(type, field);
    const visibleIds = sectionsFor(type).flatMap((sec) => visibleFields(type, sec, s.answers).map((x) => x.id));
    if (!f) return c.refuse("field", `the ${type} claim form has no field ${field}`, visibleIds);
    if (!fieldVisible(type, f, s.answers)) return c.refuse("field", hiddenWhy(type, f), visibleIds);
    const checked = checkClaimValue(type, f, String(value), s.answers);
    if (!checked.ok) return c.refuse("value", checked.why, checked.options);
    const sec = sectionOfField(type, f.id)!;
    await onClaimPage(c);
    openSection(sec.id);
    const el = await part(c, `claim-field:${f.id}`);
    await point(c, el, f.label);
    const before = new Set(visibleIds);
    setClaimField(f.id, checked.value);
    const after = useClaim.getState();
    const added = sectionsFor(type)
      .flatMap((x) => visibleFields(type, x, after.answers))
      .filter((x) => !before.has(x.id))
      .map((x) => x.label);
    const left = claimMissing(after);
    const n = left.fields.length + left.documents.length;
    return `${f.label} set to ${short(displayClaimValue(type, f, checked.value, after.answers))}${added.length ? `; the form now also asks: ${added.join(", ")}` : ""}; ${n} required ${n === 1 ? "item" : "items"} left`;
  },

  async "claim.section"({ section }, c) {
    const type = needClaim(c, "section");
    const secs = sectionsFor(type);
    const sec = secs.find((x) => x.id === section);
    if (!sec) return c.refuse("section", `the ${type} claim has no section ${section}`, secs.map((x) => x.id));
    await onClaimPage(c);
    const s = useClaim.getState();
    // Opened first, so what is shown whole (X1) is the section as it will be.
    openSection(sec.id);
    const el = await part(c, `claim-section:${sec.id}`);
    await new Promise((r) => requestAnimationFrame(r));
    await point(c, el, sec.title);
    if (sec.id === "documents") {
      const missing = claimMissing(s).documents;
      // The uploads still owed, ringed once the section has opened.
      c.after(async () => {
        await waitFor(() => document.querySelector(sel("doc-list")), 1500);
        const rows = missing.map((d) => document.querySelector(sel(`doc:${d.id}`))).filter(shown);
        if (rows.length) {
          await c.scrollTo(rows[0]);
          await c.ring(rows, { label: "Still to upload", separate: true });
        }
      });
      return missing.length ? `${sec.title} open; still to upload: ${missing.map((d) => d.label).join(", ")}` : `${sec.title} open; every required document is uploaded`;
    }
    const pr = sectionProgress(type, sec, s.answers, uploadedIds(s));
    return `${sec.title} open; ${pr.done} of ${pr.of} required filled`;
  },

  async "claim.review"(_args, c) {
    const type = needClaim(c, "review");
    const m = claimMissing();
    if (m.fields.length || m.documents.length) {
      const names = [...m.fields.map((f) => f.label), ...m.documents.map((d) => d.label)];
      return c.refuse("review", `still missing: ${names.join(", ")}`, [...m.fields.map((f) => f.id), ...m.documents.map((d) => d.id)]);
    }
    await onClaimPage(c);
    openSection("review");
    const el = await part(c, "claim-section:review");
    await point(c, el, "Review and submit");
    return `review open for the ${type} claim: every section and document is complete; the customer ticks the declaration and presses Submit claim`;
  },
};
