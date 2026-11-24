/**
 * The confirmation sheet: every change the bank makes passes through it
 * (CONTRACT.md `confirm.ask` / `confirm.answer`). Mounted once by the app shell.
 *
 *   openConfirm(args)   puts the sheet up for a `confirm.ask` (throws an
 *                       ActionRefusal when the bank cannot do it)
 *   askConfirm(args)    the visitor's own tap: mints a `V…` action id and shows a
 *                       refusal as a toast instead of throwing
 *   answerConfirm(yes)  presses Confirm / Cancel; emits `action_done`
 */
import { Check, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { emit } from "../voice/events";
import "../styles/app.css";
import { ActionRefusal, type Applied, type ConfirmArgs, type Described, applyAction, describeAction } from "./actions";
import { Toaster, toast } from "./toast";

export type { ConfirmArgs } from "./actions";

interface Sheet {
  args: ConfirmArgs;
  view: Described;
  phase: "open" | "done";
  result?: Applied;
}

export const useConfirm = create<{ sheet: Sheet | null }>(() => ({ sheet: null }));

let visitorSeq = 0;
const nextVisitorId = () => `V${++visitorSeq}`;

/** Put the sheet up. Throws `ActionRefusal` when the bank cannot do it. */
export function openConfirm(args: Omit<ConfirmArgs, "action_id"> & { action_id?: string }): Described {
  const full = { ...args, action_id: args.action_id ?? nextVisitorId() } as ConfirmArgs;
  const view = describeAction(full);
  const cur = useConfirm.getState().sheet;
  if (cur?.phase === "open" && cur.args.action_id !== full.action_id) {
    emit("action_done", { action_id: cur.args.action_id, kind: cur.args.kind, outcome: "cancelled", summary: `${cur.view.title} (replaced)` });
  }
  useConfirm.setState({ sheet: { args: full, view, phase: "open" } });
  return view;
}

/** The visitor's tap: a refusal shows as a toast. */
export function askConfirm(args: Omit<ConfirmArgs, "action_id">) {
  try {
    openConfirm(args);
  } catch (err) {
    if (err instanceof ActionRefusal) toast(err.why.replace(/^./, (c) => c.toUpperCase()), "bad");
    else throw err;
  }
}

export type Answer = { outcome: "done" | "cancelled"; reference?: string; summary: string };

/** Press Confirm (yes) or Cancel. */
export function answerConfirm(yes: boolean): Answer | null {
  const sheet = useConfirm.getState().sheet;
  if (!sheet || sheet.phase !== "open") return null;
  const { args, view } = sheet;
  if (!yes) {
    useConfirm.setState({ sheet: null });
    const summary = `cancelled: ${view.title.replace(/\?$/, "").toLowerCase()}`;
    emit("action_done", { action_id: args.action_id, kind: args.kind, outcome: "cancelled", summary });
    return { outcome: "cancelled", summary };
  }
  let result: Applied;
  try {
    result = applyAction(args);
  } catch (err) {
    if (!(err instanceof ActionRefusal)) throw err;
    useConfirm.setState({ sheet: null });
    toast(err.why, "bad");
    emit("action_done", { action_id: args.action_id, kind: args.kind, outcome: "cancelled", summary: `not done: ${err.why}` });
    return { outcome: "cancelled", summary: `not done: ${err.why}` };
  }
  useConfirm.setState({ sheet: { ...sheet, phase: "done", result } });
  emit("action_done", { action_id: args.action_id, kind: args.kind, outcome: "done", reference: result.reference, summary: result.summary });
  return { outcome: "done", ...result };
}

export const closeConfirm = () => useConfirm.setState({ sheet: null });

const sentence = (s: string) => s.replace(/^./, (c) => c.toUpperCase());

export function ConfirmSheet() {
  const sheet = useConfirm((s) => s.sheet);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!sheet) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (sheet.phase === "open") answerConfirm(false);
      else closeConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheet]);

  useEffect(() => {
    if (sheet?.phase === "open") confirmRef.current?.focus({ preventScroll: true });
    if (sheet?.phase !== "done") return;
    const id = sheet.args.action_id;
    const t = setTimeout(() => {
      if (useConfirm.getState().sheet?.args.action_id === id) closeConfirm();
    }, 7000);
    return () => clearTimeout(t);
  }, [sheet]);

  return (
    <>
      <Toaster />
      {sheet && (
        <div className="ax-sheet-wrap" data-overlay="center" onMouseDown={(e) => e.target === e.currentTarget && (sheet.phase === "open" ? answerConfirm(false) : closeConfirm())}>
          <div
            className={`ax-sheet${sheet.view.danger ? " ax-sheet--danger" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="ax-sheet-title"
            data-stage-thing="confirm-sheet" data-stage-group=""
            data-stage-label="Confirmation"
            data-action-id={sheet.args.action_id}
          >
            {sheet.phase === "open" ? (
              <>
                <div className="ax-sheet__head">
                  <ShieldCheck size={20} aria-hidden />
                  <span>Confirm to continue</span>
                </div>
                <h2 id="ax-sheet-title" className="ax-sheet__title">
                  {sheet.view.title}
                </h2>
                <dl className="ax-sheet__lines">
                  {sheet.view.lines.map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                {sheet.view.note && <p className="ax-sheet__note">{sheet.view.note}</p>}
                <div className="ax-sheet__actions">
                  <button type="button" className="ax-btn ax-btn--ghost" data-stage-thing="confirm-cancel" data-stage-label="Cancel" onClick={() => answerConfirm(false)}>
                    Cancel
                  </button>
                  <button
                    ref={confirmRef}
                    type="button"
                    className={`ax-btn ${sheet.view.danger ? "ax-btn--danger" : "ax-btn--primary"}`}
                    data-stage-thing="confirm-yes"
                    data-stage-label="Confirm"
                    onClick={() => answerConfirm(true)}
                  >
                    {sheet.view.confirmLabel}
                  </button>
                </div>
              </>
            ) : (
              <div className="ax-sheet__done">
                <span className="ax-sheet__tick">
                  <Check size={26} strokeWidth={2.6} />
                </span>
                <h2 id="ax-sheet-title" className="ax-sheet__title">
                  Done
                </h2>
                <p className="ax-sheet__summary">{sentence(sheet.result!.summary)}.</p>
                <p className="ax-sheet__ref">
                  Reference <strong data-stage-thing="confirm-reference" data-stage-label="Reference">{sheet.result!.reference}</strong>
                </p>
                <button type="button" className="ax-btn ax-btn--primary" onClick={closeConfirm}>
                  Close
                </button>
                <button type="button" className="ax-sheet__x" aria-label="Close" onClick={closeConfirm}>
                  <X size={18} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
