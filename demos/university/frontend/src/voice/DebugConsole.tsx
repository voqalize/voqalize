/**
 * `?debug=1`: every move of the scene with its arguments, run through the
 * same app-wide `Moves` the call uses (rings and all), its `StageResult`, and
 * the events the page sent. Development and screenshots only.
 */
import { Bug, ChevronDown, Play, X } from "lucide-react";
import { useState } from "react";
import type { StageResult } from "@voqalize/stage";
import { runByHand, useStageLog } from "../stage/host";
import { scene } from "../stage/scene.gen";

const EXAMPLES: Record<string, Record<string, string>> = {
  "catalogue.filter": { facet: "Level", value: "Postgraduate" },
  "catalogue.clear": { facet: "" },
  "catalogue.pick": { first: "online-mba", second: "pgd-data-analytics", third: "" },
  "catalogue.compare": { first: "online-mba", second: "emba", third: "" },
  "site.open": { program: "mba" },
  "site.go": { page: "admissions" },
  "site.show": { target: "fees" },
  "apply.fill": { field: "class12_percent", value: "92.4" },
  "apply.step": { step: "3" },
  "apply.next": {},
};

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [args, setArgs] = useState<Record<string, Record<string, string>>>(EXAMPLES);
  const [results, setResults] = useState<Record<string, StageResult | null>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const lines = useStageLog((s) => s.lines);

  if (!open) {
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open the Stage console">
        <Bug size={18} />
      </button>
    );
  }

  const run = async (id: string) => {
    const spec = scene.move(id as never) as { args?: readonly { name: string; type?: string }[] };
    const a: Record<string, unknown> = {};
    for (const arg of spec.args ?? []) {
      const v = args[id]?.[arg.name] ?? "";
      a[arg.name] = v === "" ? null : arg.type === "integer" ? Number(v) : v;
    }
    setBusy(id);
    const r = await runByHand(id, a);
    setBusy(null);
    setResults((s) => ({ ...s, [id]: r }));
  };

  return (
    <section className="debug" aria-label="Stage console">
      <header className="debug-head">
        <strong>Stage console</strong>
        <span>{scene.spec.moves.length} moves</span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close the console">
          <X size={16} />
        </button>
      </header>
      <div className="debug-moves">
        {scene.spec.moves.map((m) => {
          const r = results[m.id];
          return (
            <details key={m.id} className="debug-move">
              <summary>
                <code>{m.id}</code>
                <span className="debug-class">{m.class}</span>
                <ChevronDown size={14} />
              </summary>
              <div className="debug-args">
                {(("args" in m ? m.args : []) as readonly { name: string; optional?: boolean }[]).map((a) => (
                  <label key={a.name}>
                    <span>
                      {a.name}
                      {"optional" in a && a.optional ? "?" : ""}
                    </span>
                    <input
                      value={args[m.id]?.[a.name] ?? ""}
                      onChange={(e) => setArgs((s) => ({ ...s, [m.id]: { ...s[m.id], [a.name]: e.target.value } }))}
                    />
                  </label>
                ))}
                <button type="button" className="debug-run" disabled={busy !== null} onClick={() => void run(m.id)}>
                  <Play size={13} /> {busy === m.id ? "Running…" : "Run"}
                </button>
                {r !== undefined ? (
                  <pre className={`debug-result is-${r?.outcome ?? "none"}`}>
                    {r ? `${r.outcome}${r.detail ? `: ${r.detail}` : ""}${r.refused?.length ? `\nrefused ${JSON.stringify(r.refused, null, 1)}` : ""}\n${r.ms} ms` : "carried on"}
                  </pre>
                ) : null}
              </div>
            </details>
          );
        })}
      </div>
      <div className="debug-log">
        <strong>Recent events</strong>
        <ol>
          {lines
            .slice(-14)
            .reverse()
            .map((l) => (
              <li key={`${l.at}-${l.text}`} className={`is-${l.kind}`}>
                {l.text}
              </li>
            ))}
        </ol>
      </div>
    </section>
  );
}
