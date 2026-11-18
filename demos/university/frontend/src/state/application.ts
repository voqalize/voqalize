/**
 * The application form: values by field name, the step in front, and the
 * submission. The form's own controls and Stage's `apply.*` performers call
 * the same actions. Paying is only ever the applicant's own press.
 */
import { create } from "zustand";
import { INTAKES, programById } from "../data/catalogue";
import { FORM, STEPS, missingIn, optionsFor, fieldByName } from "../data/application";
import { readJSON, writeJSON } from "./storage";

export const STORE_KEY = "anvaya.applications";

export interface Submitted {
  reference: string;
  program: string;
  fee: number;
  pay_method: string;
  at: string;
}

export interface ApplicationState {
  values: Record<string, string>;
  /** Mock file names for documents marked uploaded. */
  files: Record<string, string>;
  step: number;
  reached: number;
  /** The field that changed last, for the event that reports it. */
  lastField: string | null;
  /** Required fields Continue found empty on the step in front. */
  flagged: string[];
  paying: boolean;
  submitted: Submitted | null;
  set(field: string, value: string): void;
  setStep(step: number): void;
  /** As Continue: the missing required fields, or [] after moving on. */
  next(): string[];
  back(): void;
  submit(): Promise<Submitted | null>;
  reset(): void;
}

const FAKE_FILES: Record<string, string> = {
  doc_class10: "class10_marksheet.pdf",
  doc_class12: "class12_marksheet.pdf",
  doc_graduation: "graduation_marksheets.pdf",
  doc_score: "entrance_scorecard.pdf",
  doc_photo_id: "aadhaar_card.pdf",
  doc_photo: "passport_photo.jpg",
  doc_income: "income_certificate.pdf",
};

const initial = () => ({ values: {}, files: {}, step: 1, reached: 1, lastField: null, flagged: [], paying: false, submitted: null });

export const useApplication = create<ApplicationState>((set, get) => ({
  ...initial(),
  set(field, value) {
    const s = get();
    const values = { ...s.values, [field]: value };
    const files = { ...s.files };
    if (field === "program") {
      // Campus, intake and scholarship belong to the programme: keep them only if the new one offers them.
      const p = programById(value);
      if (values.campus && !p?.campuses.includes(values.campus)) delete values.campus;
      if (values.intake && (!p || INTAKES[p.intake]?.label !== values.intake)) delete values.intake;
      if (values.scholarship && values.scholarship !== "none" && !p?.scholarships.includes(values.scholarship)) delete values.scholarship;
    }
    if (field === "hostel" && value !== "yes") delete values.room_type;
    if (field === "campus" && values.room_type) {
      const room = fieldByName("room_type");
      if (room && !optionsFor(room, values).some(([id]) => id === values.room_type)) delete values.room_type;
    }
    if (fieldByName(field)?.type === "document") {
      if (value === "uploaded") files[field] = FAKE_FILES[field] ?? `${field}.pdf`;
      else delete files[field];
    }
    if (!value) delete values[field];
    set({ values, files, lastField: field, flagged: s.flagged.filter((f) => f !== field) });
  },
  setStep(step) {
    if (step < 1 || step > STEPS.length) return;
    set((s) => ({ step, reached: Math.max(s.reached, step), flagged: [] }));
  },
  next() {
    const s = get();
    const missing = missingIn(s.step, s.values);
    if (missing.length) {
      set({ flagged: missing });
      return missing;
    }
    if (s.step < STEPS.length) set({ step: s.step + 1, reached: Math.max(s.reached, s.step + 1), flagged: [] });
    return [];
  },
  back() {
    const s = get();
    if (s.step > 1) set({ step: s.step - 1, flagged: [] });
  },
  async submit() {
    const s = get();
    if (s.paying || s.submitted) return s.submitted;
    for (const st of STEPS) {
      const missing = missingIn(st.step, s.values);
      if (missing.length) {
        set({ step: st.step, flagged: missing });
        return null;
      }
    }
    set({ paying: true });
    await new Promise((r) => setTimeout(r, 1000));
    const p = programById(s.values.program);
    const reference = `${FORM.reference_prefix}${String(Math.floor(10000 + Math.random() * 90000))}`;
    const done: Submitted = { reference, program: p?.id ?? "", fee: p?.application_fee ?? 0, pay_method: s.values.pay_method ?? "", at: new Date().toISOString() };
    writeJSON(STORE_KEY, [...readJSON<Submitted[]>(STORE_KEY, []), done]);
    set({ paying: false, submitted: done });
    return done;
  },
  reset: () => set(initial()),
}));

/** Field names that hold something, in form order. */
export const filledFields = (values: Record<string, string>) => STEPS.flatMap((s) => s.fields.map((f) => f.name)).filter((n) => !!values[n]);
