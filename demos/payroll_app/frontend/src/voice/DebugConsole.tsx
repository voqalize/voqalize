/**
 * `?debug=1`: every Stage move with sample arguments from the real data, fired
 * through `moves.run` (the same performers a call uses), each result shown,
 * and the event log. Development and screenshots only.
 */
import { useState, useSyncExternalStore } from "react";
import { Bug, ChevronDown, Play, RotateCcw, X } from "lucide-react";
import type { StageResult } from "@voqalize/stage";
import { NEW_FIELDS } from "../lib/payroll";
import { SETUP_FIELDS } from "../lib/setup";
import { resetSession, useTk } from "../state/store";
import { eventLog, logResult, moves, onEventLog } from "../stage/runtime";
import { scene } from "../stage/scene.gen";
import { FAKE_STATES, useFakeCall } from "./fake";

const NEW_SAMPLE: Record<string, string> = {
  name: "Nandini Iyer",
  email: "nandini.iyer@banyanbay.example",
  gender: "F",
  department: "Marketing",
  title: "Brand Manager",
  grade: "G4",
  location: "Bengaluru",
  joined: "2026-02-16",
  annual_ctc: "720000",
  tax_regime: "new",
  manager_id: "BB-1022",
};

/** Sample arguments for a move, from the data and the state now. */
export function sample(id: string): unknown {
  const st = useTk.getState();
  switch (id) {
    case "app.go":
      return { page: "Leave" };
    case "app.show":
      return { thing: "TDS" };
    case "app.open":
      return { path: "/tax/regime/BB-1007" };
    case "payslip.compare":
      return { employee_id: "BB-1030", month: "2026-01", against: "2025-12" };
    case "regime.compare":
      return { employee_id: "BB-1007" };
    case "leave.decide":
      return { request_id: "LV-2412", decision: "approve" };
    case "claim.fix":
      return { claim_id: "RB-3108", amount: 4580 };
    case "claim.open":
      return { claim_id: "RB-3109" };
    case "claim.decide":
      return { claim_id: "RB-3109", decision: "approve" };
    case "employee.fill": {
      const field = NEW_FIELDS.find((f) => !st.newForm[f]) ?? "name";
      return { field, value: NEW_SAMPLE[field] };
    }
    case "regime.switch":
      return { employee_id: "BB-1007", regime: "old" };
    case "ticket.draft":
      return {
        kind: "support",
        subject: "Ravi Kumar: January net pay dropped by ₹14,415",
        summary:
          "Asked: why Ravi Kumar's (BB-1030) January net pay fell from ₹1,26,374 to ₹1,11,959.\nFound: 2 days of leave without pay (₹8,916), and TDS up ₹10,699 after proofs were verified on 21 Jan 2026 without ELSS and NPS; ₹5,200 of claims were paid.\nNeeded: confirm he can still submit the ELSS and NPS proofs before 28 Feb so March TDS comes down.",
        employee_id: "BB-1030",
      };
    case "setup.step":
      return { step: st.setup.step === "company" ? "structure" : "company" };
    case "setup.fill": {
      const f = SETUP_FIELDS.find((x) => x.step === st.setup.step && !st.setup.fields[x.name]) ?? SETUP_FIELDS.find((x) => !st.setup.fields[x.name]) ?? SETUP_FIELDS[0]!;
      return { field: f.name, value: f.preset };
    }
    case "me.view":
      return { employee_id: "BB-1030", tab: "payslips" };
    default:
      return {};
  }
}

let n = 0;
export const fire = (id: string, args: unknown) => moves.run(id, args, `debug-${++n}`);

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, StageResult | null | "running">>({});
  const log = useSyncExternalStore(onEventLog, () => eventLog().length);
  useTk(); // re-render samples as state changes
  const ids = scene.spec.moves.map((m) => m.id);
  const run = async (id: string) => {
    let args: unknown;
    try {
      args = edited[id] ? JSON.parse(edited[id]!) : sample(id);
    } catch {
      setResults((r) => ({ ...r, [id]: { call_ref: "-", move: id, outcome: "failed", detail: "arguments are not JSON", refused: [], moved: false, ms: 0 } }));
      return;
    }
    setResults((r) => ({ ...r, [id]: "running" }));
    const res = await fire(id, args);
    logResult(id, res);
    setResults((r) => ({ ...r, [id]: res }));
  };
  if (!open)
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open move console">
        <Bug size={18} />
      </button>
    );
  return (
    <aside className="debug" aria-label="Move console" data-voqalize>
      <div className="debug-head">
        <strong>Stage moves</strong>
        <span className="small">{ids.length} registered</span>
        <button type="button" className="iconbtn" aria-label="Reset session data" title="Reset session data" onClick={() => resetSession()}>
          <RotateCcw size={15} />
        </button>
        <button type="button" className="iconbtn" aria-label="Close move console" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <FakeCall />
      <ol className="debug-moves">
        {ids.map((id) => {
          const r = results[id];
          return (
            <li key={id}>
              <div className="debug-row">
                <code>{id}</code>
                <span className="small muted">{scene.move(id).class}</span>
                <button type="button" className="debug-fire" data-move={id} onClick={() => void run(id)}>
                  <Play size={12} aria-hidden /> Fire
                </button>
              </div>
              <textarea
                spellCheck={false}
                rows={1}
                value={edited[id] ?? JSON.stringify(sample(id))}
                onChange={(e) => setEdited((x) => ({ ...x, [id]: e.target.value }))}
                aria-label={`${id} arguments`}
              />
              {r ? (
                <p className={`debug-result is-${r === "running" ? "running" : (r?.outcome ?? "none")}`}>
                  {r === "running" ? "running…" : r ? `${r.outcome}: ${r.detail ?? ""}${r.refused?.[0]?.options ? ` [${r.refused[0].options.slice(0, 6).join(", ")}]` : ""}` : "moved on"}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
      <details className="debug-log">
        <summary>
          Event log ({eventLog().length}) <ChevronDown size={14} aria-hidden />
        </summary>
        <ol>
          {[...eventLog()].reverse().map((e, i) => (
            <li key={i}>
              <code>
                {e.kind === "event" ? `${e.name} by ${e.by}` : `${e.kind} ${e.name}`}
              </code>
              <span className="small">{JSON.stringify(e.data)?.slice(0, 160)}</span>
            </li>
          ))}
        </ol>
      </details>
    </aside>
  );
}

/** Fake a call (no client): the dock goes away and the face becomes the call tile, in any state. */
function FakeCall() {
  const fake = useFakeCall();
  return (
    <div className="debug-fake">
      <label>
        <input type="checkbox" checked={fake.on} onChange={(e) => useFakeCall.setState({ on: e.target.checked })} data-fake-call /> Fake a call
      </label>
      <select value={fake.state} onChange={(e) => useFakeCall.setState({ state: e.target.value as (typeof FAKE_STATES)[number] })} aria-label="Fake call state" disabled={!fake.on}>
        {FAKE_STATES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
