/**
 * `?debug=1`: fire any Stage move by hand, with editable JSON arguments, through
 * the same `Moves` runtime the call uses (rings and all), and watch the state
 * events the page sends. Works with no call. "Fake a call" shows the call tile
 * in any state without a client, to see and screenshot it.
 */
import { useState } from "react";
import { addDays, todayIST, visitDays, weekdayOf } from "../data/homes";
import { runByHand, useStageLog } from "../stage/host";
import { scene } from "../stage/scene.gen";
import { FAKE_STATES, type CallState, useFakeCall } from "./fake";

const nextSaturday = () => visitDays().find((d) => weekdayOf(d) === "sat") ?? addDays(todayIST(), 1);

/** A worked example for each move. */
export function examples(): Record<string, unknown> {
  const sat = nextSaturday();
  return {
    "site.go": { path: "/listing/BLR-101" },
    "listings.filter": { city: "bengaluru", deal: "buy", bhk: ["2", "3"], budget_max: 15000000, office: "cedarline", max_km: 8 },
    "listings.show": { listing_id: "BLR-101" },
    "compare.show": { ids: ["BLR-101", "BLR-105"] },
    "emi.show": { listing_id: "BLR-101", down_pct: 25, tenure_years: 20, lender: "kosha-partner" },
    "shortlist.set": { listing_id: "BLR-101", on: true },
    "visit.slots": { listing_id: "BLR-101", day: sat, part: "morning" },
    "visit.book": { listing_id: "BLR-101", slot: `${sat}T12:15`, name: "Priya Sharma", visitors: 2 },
  };
}

export function DebugConsole() {
  const ids = scene.spec.moves.map((m) => m.id);
  const [move, setMove] = useState<string>(ids[1]);
  const [args, setArgs] = useState(() => JSON.stringify(examples()[ids[1]], null, 1));
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(true);
  const lines = useStageLog((s) => s.lines);
  if (!open) {
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)}>
        Stage
      </button>
    );
  }
  return (
    <div className="debug" role="region" aria-label="Debug console">
      <div className="debug-head">
        <b>Stage console</b>
        <button type="button" onClick={() => setOpen(false)}>
          Hide
        </button>
      </div>
      <FakeCall />
      <select
        aria-label="Move"
        value={move}
        onChange={(e) => {
          setMove(e.target.value);
          setArgs(JSON.stringify(examples()[e.target.value] ?? {}, null, 1));
        }}
      >
        {ids.map((id) => (
          <option key={id}>{id}</option>
        ))}
      </select>
      <textarea aria-label="Arguments" value={args} onChange={(e) => setArgs(e.target.value)} rows={6} spellCheck={false} />
      {err ? <p className="debug-err">{err}</p> : null}
      <button
        type="button"
        className="btn primary"
        data-debug-run
        onClick={() => {
          try {
            const parsed = JSON.parse(args);
            setErr("");
            void runByHand(move, parsed);
          } catch (e) {
            setErr(String(e));
          }
        }}
      >
        Run move
      </button>
      <ol className="debug-log">
        {[...lines].reverse().slice(0, 14).map((l, i) => (
          <li key={i} className={`is-${l.kind}`}>
            {l.text}
          </li>
        ))}
      </ol>
    </div>
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
      <select value={fake.state} onChange={(e) => useFakeCall.setState({ state: e.target.value as CallState })} aria-label="Fake call state" disabled={!fake.on}>
        {FAKE_STATES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
