/**
 * `?debug=1` — every move in the scene, with editable JSON args and a Fire
 * button that runs it through Stage (`runMove`), plus the UI → brain event
 * stream and a fake call for the tile's look. Development and screenshots only.
 */
import { Bug, X } from "lucide-react";
import { useEffect, useState } from "react";
import { scene } from "../stage/scene.gen";
import { runMove } from "./debugHarness";
import { eventLog, onEventLog } from "./events";
import { useFakeCall } from "./fake";

const SAMPLES: Record<string, unknown> = {
  "ui.show": { thing: "Available balance" },
  "nav.open": { screen: "cards_compare" },
  "txn.find": { category: "food", from_days_ago: 60, to_days_ago: 0, label: "Food, last two months" },
  "txn.open": { txn_id: "T0197" },
  "insights.show": { month: new Date().toISOString().slice(0, 7), category: "food" },
  "confirm.ask": { action_id: "A1", kind: "card_block", card: "debit" },
  "confirm.answer": { action_id: "A1", yes: false },
  "form.fill": { form: "open_account", field: "full_name", value: "Priya Raghavan" },
  "form.step": { form: "open_account", step: 2 },
  "form.submit": { form: "loan_apply" },
  "cards.compare": { card_ids: ["voyage", "daily", "spark"], dining: 8000, online: 12000, travel: 15000 },
  "emi.plan": { txn_id: "T0184", tenure_months: 12 },
  "loan.calc": { loan_type: "home", amount: 6000000, tenure_months: 240 },
  "loan.eligibility": { loan_type: "home", monthly_income: 150000, existing_emis: 12000, tenure_months: 240 },
};

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [args, setArgs] = useState<Record<string, string>>(() =>
    Object.fromEntries(scene.spec.moves.map((m) => [m.id, JSON.stringify(SAMPLES[m.id] ?? {})])),
  );
  const [result, setResult] = useState<{ id: string; text: string } | null>(null);
  const [, tick] = useState(0);
  useEffect(() => {
    const off = onEventLog(() => tick((n) => n + 1));
    return () => {
      off();
    };
  }, []);
  const events = eventLog().slice(-8).reverse();

  const fire = async (id: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(args[id] || "{}");
    } catch (e) {
      setResult({ id, text: `bad JSON: ${(e as Error).message}` });
      return;
    }
    setResult({ id, text: "running…" });
    const r = await runMove(id, parsed);
    setResult({ id, text: JSON.stringify(r, null, 1) });
  };

  if (!open)
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open move console">
        <Bug size={16} /> Moves
      </button>
    );
  return (
    <aside className="debug" aria-label="Move console">
      <div className="debug-head">
        <strong>Move console</strong>
        <span className="small">brain → page, by hand</span>
        <button type="button" className="icon-btn" aria-label="Close move console" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <ul className="debug-list">
        {scene.spec.moves.map((m) => (
          <li key={m.id}>
            <button type="button" className="debug-fire" data-move={m.id} onClick={() => void fire(m.id)}>
              {m.id}
            </button>
            <input
              className="debug-args"
              aria-label={`${m.id} arguments (JSON)`}
              value={args[m.id] ?? ""}
              onChange={(e) => setArgs({ ...args, [m.id]: e.target.value })}
              spellCheck={false}
            />
            {result?.id === m.id ? <pre className="debug-pre">{result.text.slice(0, 1200)}</pre> : null}
          </li>
        ))}
      </ul>
      <div className="debug-fake">
        <p className="small">Fake call (no voice)</p>
        <div className="debug-fake-row">
          <button type="button" data-fake="connect" onClick={() => useFakeCall.setState({ on: true, state: "listening" })}>
            connect
          </button>
          <button type="button" data-fake="speak" onClick={() => useFakeCall.setState({ state: "speaking" })}>
            speak
          </button>
          <button type="button" data-fake="end" onClick={() => useFakeCall.setState({ on: false })}>
            end
          </button>
        </div>
      </div>
      <div className="debug-events">
        <p className="small">Page → brain (latest)</p>
        <ul>
          {events.map((e, i) => (
            <li key={`${e.at}${i}`}>
              <code>{e.event}</code> <span className="small">{JSON.stringify(e.payload).slice(0, 110)}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
