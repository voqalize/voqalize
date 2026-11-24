/**
 * The application form as data (`demos/university/data/application.json`):
 * the page renders it, and validates against it, field by field.
 */
import raw from "../../../data/application.json";
import { INTAKES, type Program, programById, scholarshipById } from "./catalogue";
import { ADMISSIONS } from "./admissions";

export type FieldType = "text" | "percent" | "choice" | "program" | "intake" | "scholarship" | "document";

export interface FormField {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  private?: boolean;
  placeholder?: string;
  help?: string;
  options?: [string, string][];
}

export interface FormStep {
  step: number;
  id: string;
  title: string;
  fields: FormField[];
}

interface FormSpec {
  steps: FormStep[];
  document_values: [string, string][];
  reference_prefix: string;
}

export const FORM = raw as unknown as FormSpec;
export const STEPS = FORM.steps;
export const ALL_FIELDS = STEPS.flatMap((s) => s.fields);
export const fieldByName = (name: string) => ALL_FIELDS.find((f) => f.name === name) ?? null;
export const stepOf = (name: string) => STEPS.find((s) => s.fields.some((f) => f.name === name))?.step ?? null;
export const PRIVATE_FIELDS = new Set(ALL_FIELDS.filter((f) => f.private).map((f) => f.name));

/** The options a field offers right now, given the rest of the form: campus
 *  by the programme's campuses, intake by its intake, scholarship by its
 *  schemes, room type by the campus's rooms. */
export function optionsFor(field: FormField, values: Record<string, string>): [string, string][] {
  const program: Program | null = programById(values.program);
  switch (field.type) {
    case "choice": {
      const all = field.options ?? [];
      if (field.name === "campus" && program) return all.filter(([id]) => program.campuses.includes(id));
      if (field.name === "room_type" && values.campus) {
        const ids = new Set(ADMISSIONS.hostel.rooms.filter((r) => r.campus === values.campus).map((r) => r.id));
        return ids.size ? all.filter(([id]) => ids.has(id)) : all;
      }
      return all;
    }
    case "intake": {
      const intake = program ? INTAKES[program.intake] : null;
      return intake ? [[intake.label, `${intake.label} (classes from ${intake.starts})`]] : [];
    }
    case "scholarship": {
      const ids = program?.scholarships ?? [];
      return [...ids.map((id): [string, string] => [id, scholarshipById(id)?.name ?? id]), ["none", "None for now"]];
    }
    case "document":
      return FORM.document_values;
    default:
      return [];
  }
}

/** Whether a field is shown at all, given the rest of the form. */
export function shown(field: FormField, values: Record<string, string>): boolean {
  if (field.name === "room_type") return values.hostel === "yes";
  return true;
}

/** A percent as typed or said: "92.4", "92.4%", "92.4 percent". */
export function parsePercent(v: string): number | null {
  const m = /^\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|per ?cent)?\s*$/i.exec(v);
  if (!m) return null;
  const n = Number(m[1]);
  return n >= 0 && n <= 100 ? n : null;
}

/** What is wrong with one value, or null when it is fine. */
export function invalid(field: FormField, value: string): string | null {
  if (!value) return null;
  if (field.type === "percent" && parsePercent(value) === null) return "Enter marks between 0 and 100";
  if (field.name === "email" && !/^\S+@\S+\.\S+$/.test(value)) return "Enter an email address like name@example.com";
  if (field.name === "mobile" && value.replace(/\D/g, "").length < 10) return "Enter a 10-digit mobile number";
  return null;
}

/** Required fields of `step` still empty (or not valid), in form order. */
export function missingIn(step: number, values: Record<string, string>): string[] {
  const s = STEPS.find((x) => x.step === step);
  if (!s) return [];
  return s.fields.filter((f) => f.required && shown(f, values) && (!values[f.name] || invalid(f, values[f.name]))).map((f) => f.name);
}

export const labelOfField = (name: string) => fieldByName(name)?.label ?? name;
