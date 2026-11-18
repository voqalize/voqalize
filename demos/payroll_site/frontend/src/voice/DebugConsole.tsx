/**
 * `?debug=1`: fires any of the agent's moves by hand, through the same Stage
 * runtime a call uses (rings and all), plus one scripted run per agent and a
 * fake call for the live look. Development and screenshots only; App renders
 * it only with the flag.
 */
import { Bug, ChevronDown, Play } from "lucide-react";
import { useState } from "react";
import { businessDays, slotsOn, todayIst } from "../lib/calendar";
import { actions, useSite } from "../state/store";
import { runByHand, useStageLog } from "../stage/host";
import { scene } from "../stage/scene.gen";
import { useFakeCall } from "./VoiceDock";
import type { CallState } from "./DockView";

function firstFree(): { day: string; slot: string } {
  for (const day of businessDays(todayIst())) {
    const booked = useSite.getState().booked;
    const s = slotsOn(day).find((x) => !x.taken && !booked.includes(x.id));
    if (s) return { day, slot: s.id };
  }
  return { day: businessDays(todayIst())[0], slot: "" };
}

/** A sample for every move, from the real data. */
function samples(): Record<string, unknown> {
  const { day, slot } = firstFree();
  return {
    "site.go": { path: "/pricing" },
    "site.show": { thing: "tax showcase" },
    "modules.show": { id: "declarations" },
    "modules.highlight": { ids: ["tax", "declarations"] },
    "lead.fill": { field: "headcount", value: "56" },
    "pricing.set": { headcount: 56, modules: ["reimbursements"], billing: "monthly", filing: false },
    "pricing.line": { item: "minimum" },
    "calendar.show": { day },
    "booking.pick": { slot_id: slot },
    "booking.fill": { field: "name", value: "Meghna Rao" },
    "booking.confirm": {},
  };
}

type Step = [string, unknown];

/** One scripted run per agent: the moves the agent makes in its main flow. */
export const SCRIPTS: Record<string, () => Step[]> = {
  "Sales rep on /": () => [
    ["site.go", { path: "/" }],
    ["lead.fill", { field: "company", value: "Banyan & Bay Foods" }],
    ["lead.fill", { field: "name", value: "Meghna Rao" }],
    ["lead.fill", { field: "headcount", value: "56" }],
    ["lead.fill", { field: "states", items: ["Karnataka", "Maharashtra", "Tamil Nadu", "Telangana"] }],
    ["lead.fill", { field: "current_tool", value: "spreadsheets" }],
    ["lead.fill", { field: "pains", items: ["tax_proofs", "statutory"] }],
    ["modules.highlight", { ids: ["tax", "declarations", "compliance"] }],
    ["lead.fill", { field: "recommended_plan", value: "growth" }],
    ["modules.show", { id: "declarations" }],
  ],
  "Pricing on /pricing": () => [
    ["pricing.set", { headcount: 56, modules: ["reimbursements"], billing: "annual", filing: true }],
    ["pricing.line", { item: "discount" }],
  ],
  "Booker on /book-demo": () => {
    const { day, slot } = firstFree();
    return [
      ["calendar.show", { day }],
      ["booking.pick", { slot_id: slot }],
      ["booking.fill", { field: "name", value: "Meghna Rao" }],
      ["booking.fill", { field: "company", value: "Banyan & Bay Foods" }],
      ["booking.fill", { field: "headcount", value: "56" }],
      ["booking.fill", { field: "email", value: "meghna@banyanbay.example" }],
    ];
  },
};

export async function runScript(name: string): Promise<void> {
  for (const [id, args] of SCRIPTS[name]()) await runByHand(id, args);
}

const CALL_STATES: CallState[] = ["idle", "listening", "speaking", "thinking"];

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [move, setMove] = useState<string>(scene.spec.moves[0].id);
  const [args, setArgs] = useState(() => JSON.stringify(samples()[scene.spec.moves[0].id]));
  const [busy, setBusy] = useState(false);
  const lines = useStageLog((s) => s.lines);
  const fake = useFakeCall();

  const pick = (id: string) => {
    setMove(id);
    setArgs(JSON.stringify(samples()[id] ?? {}));
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className={`debug${open ? " is-open" : ""}`} aria-label="Debug console" data-debug-console>
      <button type="button" className="debug-head" onClick={() => setOpen(!open)}>
        <Bug size={14} /> Debug moves <ChevronDown size={14} className="debug-chev" />
      </button>
      {open ? (
        <div className="debug-body">
          <div className="debug-row">
            <select value={move} onChange={(e) => pick(e.target.value)} aria-label="Move">
              {scene.spec.moves.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
            <button type="button" disabled={busy} onClick={() => run(() => runByHand(move, JSON.parse(args)))}>
              <Play size={12} /> Run
            </button>
          </div>
          <textarea value={args} onChange={(e) => setArgs(e.target.value)} rows={3} spellCheck={false} aria-label="Arguments (JSON)" />
          <div className="debug-scripts">
            {Object.keys(SCRIPTS).map((name) => (
              <button key={name} type="button" disabled={busy} onClick={() => run(() => runScript(name))}>
                {name}
              </button>
            ))}
            <button type="button" onClick={() => actions.reset()}>
              Reset
            </button>
          </div>
          <div className="debug-scripts">
            <span>Fake call:</span>
            {CALL_STATES.map((s) => (
              <button
                key={s}
                type="button"
                className={fake.state === s ? "is-on" : ""}
                onClick={() => useFakeCall.setState({ state: s, heard: s === "listening" ? "We're about 56 people across four states" : "" })}
              >
                {s}
              </button>
            ))}
          </div>
          <ol className="debug-log">
            {lines.slice(-8).map((l) => (
              <li key={l.at + l.text} className={`is-${l.kind}`}>
                {l.text}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </aside>
  );
}
