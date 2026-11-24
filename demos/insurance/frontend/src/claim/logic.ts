/**
 * The claim form's rules, from data/claim_form.json: which sections and fields a
 * claim type has, which `show_if` hides, what each select offers, what a value
 * must look like, and what is still missing. The form, the review and the
 * `claim.*` performers all ask here, so they never disagree.
 */
import { claimForm, customer, network, policies, policyById } from "../data";
import type { ClaimDocument, ClaimField, ClaimSection, Option, ShowIf } from "../data/types";
import { inr } from "../lib/format";

export type ClaimType = "motor" | "health";
export type Answers = Record<string, string>;

export const claimTypes = claimForm.types;
export const typeOf = (id: string) => claimTypes.find((t) => t.id === id);

export function sectionsFor(type: ClaimType): ClaimSection[] {
  return claimForm.sections.filter((s) => s.types.includes(type));
}

const allFields = (type: ClaimType) => sectionsFor(type).flatMap((s) => s.fields);

export function fieldById(type: ClaimType, id: string): ClaimField | undefined {
  return allFields(type).find((f) => f.id === id);
}

export function sectionOfField(type: ClaimType, id: string): ClaimSection | undefined {
  return sectionsFor(type).find((s) => s.fields.some((f) => f.id === id));
}

/** Does `show_if` hold? A controlling field that is itself hidden counts as empty. */
function holds(type: ClaimType, showIf: ShowIf | undefined, a: Answers, depth = 0): boolean {
  if (!showIf) return true;
  return Object.entries(showIf).every(([key, values]) => {
    const ctl = fieldById(type, key);
    if (ctl && depth < 6 && !holds(type, ctl.show_if, a, depth + 1)) return false;
    return values.includes(a[key] ?? "");
  });
}

export const fieldVisible = (type: ClaimType, f: ClaimField, a: Answers) => holds(type, f.show_if, a);

export function visibleFields(type: ClaimType, section: ClaimSection, a: Answers): ClaimField[] {
  return section.fields.filter((f) => fieldVisible(type, f, a));
}

/** "shown only when incident kind is accident or glass". */
export function hiddenWhy(type: ClaimType, f: ClaimField): string {
  const parts = Object.entries(f.show_if ?? {}).map(([key, values]) => {
    const ctl = fieldById(type, key);
    const labels = values.map((v) => ctl?.options?.find((o) => o.value === v)?.label.toLowerCase() ?? v);
    return `“${ctl?.label ?? key}” is ${labels.join(" or ")}`;
  });
  return `${f.label} is only asked when ${parts.join(" and ")}`;
}

/** Policies of this claim type. */
export function claimPolicies(type: ClaimType) {
  const products = typeOf(type)?.products ?? [];
  return policies.filter((p) => products.includes(p.product));
}

export function optionsFor(type: ClaimType, f: ClaimField, a: Answers): Option[] {
  if (f.options) return f.options;
  switch (f.options_from) {
    case "policies":
      return claimPolicies(type).map((p) => ({ value: p.id, label: `${p.title} · ${p.policy_number}` }));
    case "members": {
      const pol = policyById(a.policy_id);
      return (pol?.insured ?? []).map((m) => ({ value: m.id, label: `${m.name}${m.role ? ` · ${m.role}` : ""}` }));
    }
    case "garages":
      return [
        ...network.garages.map((g) => ({ value: g.id, label: `${g.name}, ${g.area}${g.cashless ? " · cashless" : ""}` })),
        { value: "other", label: "Another garage" },
      ];
    case "hospitals":
      return [
        ...network.hospitals.map((h) => ({ value: h.id, label: `${h.name}, ${h.area}${h.cashless ? " · cashless" : ""}` })),
        { value: "other", label: "Another hospital" },
      ];
    default:
      return [];
  }
}

export type Checked = { ok: true; value: string } | { ok: false; why: string; options?: string[] };

/** Is `raw` a value this field takes? */
export function checkClaimValue(type: ClaimType, f: ClaimField, raw: string, a: Answers): Checked {
  const v = String(raw ?? "").trim();
  if (f.type === "select") {
    const opts = optionsFor(type, f, a);
    const hit =
      opts.find((o) => o.value === v) ??
      opts.find((o) => o.value.toLowerCase() === v.toLowerCase() || o.label.toLowerCase() === v.toLowerCase());
    if (hit) return { ok: true, value: hit.value };
    return { ok: false, why: `${f.label} takes one of the listed options`, options: opts.map((o) => o.value) };
  }
  if (!v) return { ok: false, why: `${f.label} is empty` };
  if (f.type === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || Number.isNaN(Date.parse(v))) return { ok: false, why: `${f.label} is a date, YYYY-MM-DD` };
    return { ok: true, value: v };
  }
  if (f.type === "time") {
    const m = /^(\d{1,2}):(\d{2})$/.exec(v);
    if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return { ok: false, why: `${f.label} is a time, HH:MM (24 hours)` };
    return { ok: true, value: `${m[1].padStart(2, "0")}:${m[2]}` };
  }
  if (f.type === "money") {
    const d = v.replace(/[₹,\s]/g, "");
    if (!/^\d+$/.test(d)) return { ok: false, why: `${f.label} is an amount in rupees` };
    return { ok: true, value: String(Number(d)) };
  }
  if (f.pattern) {
    const up = v.toUpperCase();
    if (!new RegExp(f.pattern).test(up)) return { ok: false, why: `${f.label} looks like MRDN0000417 (4 letters, 0, then 6)` };
    return { ok: true, value: up };
  }
  return { ok: true, value: v };
}

/** True when a visible field holds a value it takes. */
export function fieldDone(type: ClaimType, f: ClaimField, a: Answers): boolean {
  const v = a[f.id];
  return !!v && checkClaimValue(type, f, v, a).ok;
}

export function displayClaimValue(type: ClaimType, f: ClaimField, v: string | undefined, a: Answers): string {
  if (!v) return "";
  if (f.type === "select") return optionsFor(type, f, a).find((o) => o.value === v)?.label ?? v;
  if (f.type === "money") return inr(Number(v));
  if (f.type === "date") {
    const d = new Date(`${v}T00:00:00`);
    return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }
  return v;
}

export function documentsFor(type: ClaimType, a: Answers): ClaimDocument[] {
  return claimForm.documents.filter((d) => d.types.includes(type) && holds(type, d.show_if, a));
}

export interface Missing {
  fields: { id: string; label: string; section: string }[];
  documents: { id: string; label: string }[];
}

export function missingFor(type: ClaimType, a: Answers, uploaded: string[]): Missing {
  const fields: Missing["fields"] = [];
  for (const s of sectionsFor(type)) {
    for (const f of visibleFields(type, s, a)) {
      if (!f.optional && !fieldDone(type, f, a)) fields.push({ id: f.id, label: f.label, section: s.id });
    }
  }
  const documents = documentsFor(type, a)
    .filter((d) => !d.optional && !uploaded.includes(d.id))
    .map((d) => ({ id: d.id, label: d.label }));
  return { fields, documents };
}

export function filledFor(type: ClaimType, a: Answers): string[] {
  return sectionsFor(type).flatMap((s) => visibleFields(type, s, a).filter((f) => fieldDone(type, f, a)).map((f) => f.id));
}

/** Section progress: required fields done of required fields shown (documents for documents). */
export function sectionProgress(type: ClaimType, s: ClaimSection, a: Answers, uploaded: string[]): { done: number; of: number } {
  if (s.id === "documents") {
    const req = documentsFor(type, a).filter((d) => !d.optional);
    return { done: req.filter((d) => uploaded.includes(d.id)).length, of: req.length };
  }
  const req = visibleFields(type, s, a).filter((f) => !f.optional);
  return { done: req.filter((f) => fieldDone(type, f, a)).length, of: req.length };
}

export function prefillValue(f: ClaimField): string | undefined {
  if (f.prefill === "profile.phone") return customer.phone;
  if (f.prefill === "profile.email") return customer.email;
  return undefined;
}

/** A sample file for the mock upload: a plausible name and size per document. */
export function sampleFile(docId: string): { name: string; size: number } {
  const names: Record<string, string> = {
    driving_licence: "driving-licence-front-back.pdf",
    rc_copy: "RC-certificate.pdf",
    damage_photos: "damage-photos.zip",
    fir_copy: "FIR-copy.pdf",
    repair_estimate: "garage-estimate.pdf",
    discharge_summary: "discharge-summary.pdf",
    hospital_bills: "final-bill-and-receipts.pdf",
    reports: "prescriptions-and-reports.pdf",
    id_proof: "patient-photo-id.jpg",
    cancelled_cheque: "cancelled-cheque.jpg",
  };
  let h = 0;
  for (const ch of docId) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return { name: names[docId] ?? `${docId}.pdf`, size: 180_000 + (h % 2_400_000) };
}
