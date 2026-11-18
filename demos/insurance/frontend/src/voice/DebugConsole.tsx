/**
 * `?debug=1` only (lazy): every move in the scene with its arguments, presets
 * that drive whole flows, and the result line each move returns. Moves run
 * through `moves.run` (src/stage/host.ts), the same path the agent's take, so
 * rings and refusals show as they would in a call. Also fakes a connected call
 * tile for screenshots, and exposes `window.__chhatri` for Playwright.
 */
import { Bug, Phone, Play, X } from "lucide-react";
import { useEffect, useState } from "react";
import { network, policyById } from "../data";
import { documentsFor, sampleFile } from "../claim/logic";
import { runMove } from "../stage/host";
import { eventLog, onEventLog } from "../stage/events";
import { scene } from "../stage/scene.gen";
import { uploadDocument, useClaim } from "../state/claim";
import { useFakeCall } from "./VoiceDock";

type Step = [string, Record<string, unknown>];

function carClause(): string {
  const pol = policyById("car-2026");
  const all = pol?.sections.flatMap((s) => s.clauses) ?? [];
  return (all.find((c) => /water|flood/i.test(c.title)) ?? all.find((c) => c.kind === "covered") ?? all[0])?.id ?? "3.4";
}

/** Upload every document the claim asks for, at once (the customer's job; a shortcut for screenshots). */
export function uploadAll(sampleMs = 0) {
  const s = useClaim.getState();
  if (!s.type) return;
  for (const d of documentsFor(s.type, s.answers)) if (!d.optional && !s.uploads[d.id]) uploadDocument(d.id, sampleFile(d.id), sampleMs);
}

export const PRESETS: Record<string, () => Step[]> = {
  "Car quote, full, zero dep on": () => [
    ["quote.open", { product: "car" }],
    ["quote.fill", { field: "vehicle_class", value: "suv" }],
    ["quote.fill", { field: "fuel", value: "diesel" }],
    ["quote.fill", { field: "make_model", value: "Tarang Vega VX" }],
    ["quote.fill", { field: "registration_year", value: "2023" }],
    ["quote.fill", { field: "ex_showroom", value: "1450000" }],
    ["quote.fill", { field: "city", value: "pune" }],
    ["quote.fill", { field: "claim_free_years", value: "2" }],
    ["quote.addon", { addon: "zero_dep", on: true }],
    ["quote.show", {}],
  ],
  "Health quote, family": () => [
    ["quote.open", { product: "health" }],
    ["quote.fill", { field: "cover_type", value: "family_floater" }],
    ["quote.fill", { field: "adults", value: "2" }],
    ["quote.fill", { field: "children", value: "1" }],
    ["quote.fill", { field: "eldest_age", value: "38" }],
    ["quote.fill", { field: "sum_insured", value: "1000000" }],
    ["quote.fill", { field: "city", value: "pune" }],
    ["quote.fill", { field: "pre_existing", value: "no" }],
    ["quote.addon", { addon: "maternity", on: true }],
  ],
  "Mark a clause on the car policy": () => [["policy.mark", { policy_id: "car-2026", clause_id: carClause(), verdict: "covered_with_limits" }]],
  "Motor claim, several sections": () => [
    ["claim.start", { claim_type: "motor", policy_id: "car-2026" }],
    ["claim.fill", { field: "incident_kind", value: "accident" }],
    ["claim.fill", { field: "incident_date", value: "2026-11-14" }],
    ["claim.fill", { field: "incident_time", value: "19:40" }],
    ["claim.fill", { field: "incident_city", value: "Pune" }],
    ["claim.fill", { field: "incident_location", value: "Baner Road, near the Balewadi Phata signal" }],
    ["claim.fill", { field: "description", value: "A scooter cut across at the signal, I braked hard and the car behind hit my rear bumper." }],
    ["claim.fill", { field: "vehicle_drivable", value: "yes" }],
    ["claim.fill", { field: "driver_is_policyholder", value: "yes" }],
    ["claim.fill", { field: "driver_licence", value: "MH12 2015 0034821" }],
    ["claim.fill", { field: "other_party_involved", value: "no" }],
    ["claim.fill", { field: "injuries", value: "none" }],
    ["claim.fill", { field: "police_reported", value: "no" }],
    ["claim.section", { section: "garage" }],
  ],
  "Health claim to review": () => [
    ["claim.start", { claim_type: "health", policy_id: "health-2026" }],
    ["claim.fill", { field: "patient_member", value: "aarav" }],
    ["claim.fill", { field: "claim_mode", value: "cashless" }],
    ["claim.fill", { field: "hospital_id", value: network.hospitals[0]?.id ?? "other" }],
    ...(network.hospitals.length ? [] : ([["claim.fill", { field: "hospital_other_name", value: "City hospital, Pune" }]] as Step[])),
    ["claim.fill", { field: "admission_date", value: "2026-11-10" }],
    ["claim.fill", { field: "discharge_date", value: "2026-11-13" }],
    ["claim.fill", { field: "ailment", value: "Dengue fever" }],
    ["claim.fill", { field: "treatment_kind", value: "medical" }],
    ["claim.fill", { field: "treating_doctor", value: "Dr. Sneha Patwardhan" }],
    ["claim.fill", { field: "claim_amount", value: "62000" }],
    ["claim.fill", { field: "account_holder", value: "Rohan Kulkarni" }],
    ["claim.fill", { field: "bank_name", value: "Meridian Bank" }],
    ["claim.fill", { field: "account_number", value: "50100417234821" }],
    ["claim.fill", { field: "ifsc", value: "MRDN0000417" }],
    ["debug.upload_all", {}],
    ["claim.review", {}],
  ],
  "Refusals": () => [
    ["claim.fill", { field: "fir_number", value: "123" }],
    ["quote.fill", { field: "vehicle_class", value: "truck" }],
    ["site.go", { page: "pricing" }],
  ],
};

interface Logged {
  n: number;
  move: string;
  args: unknown;
  outcome: string;
  detail: string;
}

const listeners = new Set<() => void>();
const results: Logged[] = [];
let count = 0;

export async function run(id: string, args: Record<string, unknown> = {}): Promise<Logged> {
  if (id === "debug.upload_all") {
    uploadAll();
    await new Promise((r) => setTimeout(r, 50));
    const l = { n: ++count, move: id, args, outcome: "applied", detail: "every required document uploaded (sample files)" };
    results.unshift(l);
    listeners.forEach((f) => f());
    return l;
  }
  const r = await runMove(id, args);
  const l: Logged = {
    n: ++count,
    move: id,
    args,
    outcome: r?.outcome ?? "none",
    detail: r ? (r.detail ?? "") + (r.refused?.length ? ` [options: ${(r.refused[0].options ?? []).slice(0, 12).join(", ")}]` : "") : "moved on",
  };
  results.unshift(l);
  if (results.length > 40) results.pop();
  listeners.forEach((f) => f());
  return l;
}

export async function preset(name: string): Promise<Logged[]> {
  const steps = PRESETS[name]?.() ?? [];
  const out: Logged[] = [];
  for (const [id, args] of steps) out.push(await run(id, args));
  return out;
}

declare global {
  interface Window {
    __chhatri?: { run: typeof run; preset: typeof preset; uploadAll: typeof uploadAll; presets: string[] };
  }
}
window.__chhatri = { run, preset, uploadAll, presets: Object.keys(PRESETS) };

export default function DebugConsole() {
  const [open, setOpen] = useState(() => !new URLSearchParams(location.search).has("closed"));
  const [, tick] = useState(0);
  const fake = useFakeCall();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const f = () => tick((n) => n + 1);
    listeners.add(f);
    const off = onEventLog(f);
    return () => {
      listeners.delete(f);
      off();
    };
  }, []);
  if (!open) {
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open move console">
        <Bug size={16} /> Moves
      </button>
    );
  }
  const go = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };
  const events = eventLog().slice(-5).reverse();
  return (
    <aside className="debug" aria-label="Move console">
      <div className="debug-head">
        <strong>Move console</strong>
        <span className="small muted">{busy ? "running…" : "brain → page, by hand"}</span>
        <button
          type="button"
          className={`debug-chip${fake.on ? " is-on" : ""}`}
          onClick={() => useFakeCall.setState({ on: !fake.on, heard: fake.on ? "" : "Is flood damage to my engine covered?" })}
        >
          <Phone size={12} /> Fake call
        </button>
        <button type="button" className="icon-btn" aria-label="Close move console" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <div className="debug-body">
        <p className="debug-h">Presets</p>
        <div className="debug-presets">
          {Object.keys(PRESETS).map((name) => (
            <button key={name} type="button" className="debug-preset" disabled={busy} onClick={() => void go(() => preset(name))}>
              <Play size={11} /> {name}
            </button>
          ))}
        </div>
        <p className="debug-h">Moves</p>
        <ul className="debug-moves">
          {scene.spec.moves.map((m) => (
            <MoveRow key={m.id} move={m} busy={busy} go={go} />
          ))}
        </ul>
        <p className="debug-h">Results</p>
        <ol className="debug-results">
          {results.slice(0, 8).map((r) => (
            <li key={r.n} className={`o-${r.outcome}`}>
              <span className="mono">{r.move}</span> <b>{r.outcome}</b> {r.detail}
            </li>
          ))}
        </ol>
        <p className="debug-h">Events (page → brain)</p>
        <ol className="debug-results">
          {events.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <span className="mono">{e.id}</span> {e.sent ? "sent" : "no call"} {JSON.stringify(e.data).slice(0, 140)}
            </li>
          ))}
        </ol>
      </div>
    </aside>
  );
}

type MoveSpecLite = (typeof scene.spec.moves)[number];

function MoveRow({ move, busy, go }: { move: MoveSpecLite; busy: boolean; go: (fn: () => Promise<unknown>) => Promise<void> }) {
  const args = ("args" in move ? (move.args ?? []) : []) as readonly { name: string; enum?: readonly string[]; type?: string; optional?: boolean }[];
  const [vals, setVals] = useState<Record<string, string>>({});
  return (
    <li className="debug-move">
      <span className="mono debug-move-id">{move.id}</span>
      {args.map((a) =>
        a.enum ? (
          <select key={a.name} aria-label={a.name} value={vals[a.name] ?? ""} onChange={(e) => setVals({ ...vals, [a.name]: e.target.value })}>
            <option value="">{a.name}</option>
            {a.enum.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        ) : a.type === "boolean" ? (
          <select key={a.name} aria-label={a.name} value={vals[a.name] ?? "true"} onChange={(e) => setVals({ ...vals, [a.name]: e.target.value })}>
            <option value="true">on</option>
            <option value="false">off</option>
          </select>
        ) : (
          <input key={a.name} aria-label={a.name} placeholder={a.name + (a.optional ? "?" : "")} value={vals[a.name] ?? ""} onChange={(e) => setVals({ ...vals, [a.name]: e.target.value })} />
        ),
      )}
      <button
        type="button"
        className="debug-run"
        disabled={busy}
        onClick={() =>
          void go(() => {
            const out: Record<string, unknown> = {};
            for (const a of args) {
              const v = vals[a.name] ?? (a.type === "boolean" ? "true" : "");
              if (v === "" && a.optional) continue;
              out[a.name] = a.type === "boolean" ? v === "true" : v;
            }
            return run(move.id, out);
          })
        }
      >
        Run
      </button>
    </li>
  );
}
