/**
 * `?debug=1` — runs any Stage move by hand with prefilled, real arguments
 * (editable), through a local `Moves` with the same performers as a call, plus
 * fake call-tile states and the outgoing event log. Development and
 * screenshots only; it never renders without the flag.
 */
import { Bug, Play, X } from "lucide-react";
import { useEffect, useState } from "react";
import { MOVE_IDS, examples, onRunLog, runLog, runMove } from "../stage/debug";
import { eventLog, onEventLog } from "./events";
import { useFakeCall } from "./fake";

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [picked, setPicked] = useState<string>("book.slots");
  const [text, setText] = useState<string>("");
  const [, tick] = useState(0);
  useEffect(() => {
    const a = onEventLog(() => tick((n) => n + 1));
    const b = onRunLog(() => tick((n) => n + 1));
    return () => {
      a();
      b();
    };
  }, []);
  const pick = (id: string) => {
    setPicked(id);
    setText(JSON.stringify(examples()[id] ?? {}, null, 1));
  };
  useEffect(() => pick(picked), []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) {
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open move console">
        <Bug size={16} /> Moves
      </button>
    );
  }
  const last = runLog()[0];
  const events = eventLog().slice(-8).reverse();
  return (
    <aside className="debug" aria-label="Move console">
      <div className="debug-head">
        <strong>Stage moves</strong>
        <span>brain → page, by hand</span>
        <button type="button" className="icon-btn" aria-label="Close move console" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <div className="debug-moves">
        {MOVE_IDS.map((id) => (
          <button key={id} type="button" className={`debug-move${picked === id ? " is-on" : ""}`} data-move={id} onClick={() => pick(id)}>
            {id}
          </button>
        ))}
      </div>
      <textarea className="debug-args" aria-label="Arguments (JSON)" value={text} spellCheck={false} onChange={(e) => setText(e.target.value)} />
      <div className="debug-row">
        <button
          type="button"
          className="debug-run"
          data-run={picked}
          onClick={() => {
            let args: unknown = {};
            try {
              args = JSON.parse(text || "{}");
            } catch {
              return;
            }
            void runMove(picked, args);
          }}
        >
          <Play size={14} /> Run {picked}
        </button>
        <button type="button" onClick={() => pick(picked)}>
          Refill
        </button>
      </div>
      {last ? (
        <pre className="debug-result">
          {last.id}: {JSON.stringify(last.result && typeof last.result === "object" ? { outcome: (last.result as { outcome: string }).outcome, detail: (last.result as { detail: string }).detail, refused: (last.result as { refused: unknown }).refused } : last.result, null, 1)}
        </pre>
      ) : null}
      <div className="debug-row">
        <span>Fake call</span>
        <button type="button" data-fake="connect" onClick={() => useFakeCall.setState({ on: true, state: "listening" })}>
          connect
        </button>
        <button type="button" data-fake="speak" onClick={() => useFakeCall.setState({ on: true, state: "speaking", heard: "Can I move my cleaning to next week?" })}>
          speak
        </button>
        <button type="button" data-fake="end" onClick={() => useFakeCall.setState({ on: false, heard: "" })}>
          end
        </button>
      </div>
      <div className="debug-events">
        <p>Page → brain (latest)</p>
        <ul>
          {events.map((e, i) => (
            <li key={`${e.at}${i}`}>
              <code>{e.event}</code> <span>{JSON.stringify(e.payload).slice(0, 110)}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
