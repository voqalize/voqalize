/**
 * The claim form's state and actions. A click and a `claim.*` move call the
 * same functions; each change goes to the brain as `claim.changed` (field
 * names only, never values), an upload as `claim.document_uploaded`, the
 * customer's Submit as `claim.submitted`.
 */
import { create } from "zustand";
import { customer } from "../data";
import {
  type Answers,
  type ClaimType,
  filledFor,
  missingFor,
  prefillValue,
  sectionsFor,
} from "../claim/logic";
import { emit } from "../stage/events";

export interface Upload {
  name: string;
  size: number;
  /** 0–100 while the mock upload runs; 100 when done. */
  progress: number;
}

interface ClaimState {
  type: ClaimType | null;
  answers: Answers;
  uploads: Record<string, Upload>;
  /** The section open in front. */
  section: string;
  declaration: boolean;
  /** The last claim submitted (for /claim/submitted). */
  submitted: { reference: string; type: ClaimType; policy_id: string; mode: string; documents: string[]; at: string } | null;
  /** Bumped when a move or Review wants the missing items shown. */
  showMissing: number;
}

export const useClaim = create<ClaimState>(() => ({
  type: null,
  answers: {},
  uploads: {},
  section: "policy",
  declaration: false,
  submitted: null,
  showMissing: 0,
}));

const doneUploads = (s: ClaimState) => Object.entries(s.uploads).filter(([, u]) => u.progress >= 100).map(([id]) => id);

function changed(field: string) {
  const s = useClaim.getState();
  if (!s.type) return;
  const m = missingFor(s.type, s.answers, doneUploads(s));
  emit("claim.changed", {
    claim_type: s.type,
    policy_id: s.answers.policy_id ?? null,
    section: s.section,
    field,
    filled: filledFor(s.type, s.answers),
    missing: [...m.fields.map((f) => f.id), ...m.documents.map((d) => d.id)],
    documents: doneUploads(s),
  });
}

/** Choose the claim type (and policy). Keeps what is filled when the type is the same. */
export function startClaim(type: ClaimType, policyId?: string | null) {
  const s = useClaim.getState();
  const same = s.type === type;
  const answers: Answers = same ? { ...s.answers } : {};
  for (const sec of sectionsFor(type)) {
    for (const f of sec.fields) {
      const pre = prefillValue(f);
      if (pre && !answers[f.id]) answers[f.id] = pre;
    }
  }
  if (policyId) {
    if (answers.policy_id !== policyId) delete answers.patient_member;
    answers.policy_id = policyId;
  }
  useClaim.setState({
    type,
    answers,
    uploads: same ? s.uploads : {},
    section: same ? s.section : "policy",
    declaration: same ? s.declaration : false,
  });
  changed("claim_type");
}

export function setClaimField(field: string, value: string) {
  const s = useClaim.getState();
  if (s.answers[field] === value) return;
  const answers = { ...s.answers, [field]: value };
  // A new health policy has other members.
  if (field === "policy_id" && s.answers.patient_member) delete answers.patient_member;
  useClaim.setState({ answers, declaration: false });
  changed(field);
}

export function openSection(section: string) {
  if (useClaim.getState().section === section) return;
  useClaim.setState({ section });
  changed("section");
}

export function applyAccountOnFile() {
  const b = customer.bank_on_file;
  const s = useClaim.getState();
  useClaim.setState({
    answers: { ...s.answers, account_holder: b.account_holder, bank_name: b.bank_name, account_number: b.account_number, ifsc: b.ifsc },
  });
  changed("account_number");
}

const timers = new Map<string, ReturnType<typeof setInterval>>();

/** The mock upload: a short progress bar, then the file name and size. */
export function uploadDocument(docId: string, file: { name: string; size: number }, ms = 1100) {
  clearInterval(timers.get(docId));
  const set = (progress: number) => {
    const s = useClaim.getState();
    useClaim.setState({ uploads: { ...s.uploads, [docId]: { ...file, progress } } });
  };
  set(ms <= 0 ? 100 : 4);
  if (ms <= 0) {
    finishUpload(docId);
    return;
  }
  const started = Date.now();
  timers.set(
    docId,
    setInterval(() => {
      const p = Math.min(100, Math.round(((Date.now() - started) / ms) * 100));
      set(p);
      if (p >= 100) {
        clearInterval(timers.get(docId));
        timers.delete(docId);
        finishUpload(docId);
      }
    }, 60),
  );
}

function finishUpload(docId: string) {
  const s = useClaim.getState();
  emit("claim.document_uploaded", { field: docId, documents: doneUploads(s) });
  changed(docId);
}

export function removeDocument(docId: string) {
  clearInterval(timers.get(docId));
  const s = useClaim.getState();
  const { [docId]: _, ...rest } = s.uploads;
  useClaim.setState({ uploads: rest, declaration: false });
  changed(docId);
}

export function setDeclaration(on: boolean) {
  useClaim.setState({ declaration: on });
}

export function flagMissing() {
  useClaim.setState((s) => ({ showMissing: s.showMissing + 1 }));
}

export function claimMissing(s: ClaimState = useClaim.getState()) {
  return s.type ? missingFor(s.type, s.answers, doneUploads(s)) : { fields: [], documents: [] };
}

export const uploadedIds = doneUploads;

/** The customer pressed Submit claim. Returns the reference. */
export function submitClaim(): string | null {
  const s = useClaim.getState();
  if (!s.type || !s.declaration) return null;
  const m = claimMissing(s);
  if (m.fields.length || m.documents.length) return null;
  const digits = String(Math.floor(100000 + Math.random() * 900000));
  const reference = `CLM-${s.type === "motor" ? "M" : "H"}-${digits}`;
  const filled = filledFor(s.type, s.answers);
  const documents = doneUploads(s);
  useClaim.setState({
    submitted: { reference, type: s.type, policy_id: s.answers.policy_id ?? "", mode: s.answers.claim_mode ?? "", documents, at: new Date().toISOString() },
    type: null,
    answers: {},
    uploads: {},
    section: "policy",
    declaration: false,
  });
  emit("claim.submitted", { reference, filled, documents });
  return reference;
}
