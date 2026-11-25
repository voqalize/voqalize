/**
 * `?debug=1`: fire every Stage move by hand, with arguments built from the stay
 * on screen, through the same performers a call uses (a local `Moves`, so it
 * works with no agent), and fake the call's states for screenshots.
 */
import { useMemo, useState } from "react";
import { Moves, Spotlight, type StageResult } from "@voqalize/stage";
import { Bug, ChevronDown } from "lucide-react";
import { bookableDates, spaSlots } from "../lib/rules";
import { SPOTLIGHT } from "../stage/host";
import { performers } from "../stage/performers";
import { scene } from "../stage/scene.gen";
import { folio, stayClock, useStay } from "../state/store";
import { type CallState, useFakeCall } from "./fake";

function samples(): Record<string, Record<string, unknown>[]> {
  const s = useStay.getState();
  const c = stayClock();
  const lines = folio().filter((l) => l.amount > 0);
  const slots = spaSlots(c, "swedish-50", c.today, "any");
  const tomorrow = bookableDates(c)[1] ?? c.today;
  const pending = s.visitors.filter((v) => v.status === "pending");
  return {
    "app.go": ["home", "dining", "bar", "spa", "activities", "meetings", "requests", "visitors", "stay", "checkin", "checkout", "info"].map((page) => ({ page })),
    "app.show": [{ target: "total" }, { target: "key" }, ...(lines[0] ? [{ target: lines[0].label }] : [])],
    "sheet.close": [{}],
    "info.open": [{ topic: "pets" }, { topic: "smoking" }, { topic: "wifi" }, { topic: "parking" }],
    "checkin.open": [{ step: "reservation" }, { step: "room" }, { step: "review" }],
    "checkin.confirm": [{}],
    "checkin.prefs": [{ arrival: "now", floor: "high", bed: "king", quiet: "yes" }, { arrival: "17:00" }],
    "checkin.early": [{ want: "yes" }, { want: "no" }],
    "checkout.open": [{ part: "folio" }, { part: "late" }, { part: "express" }],
    "folio.dispute": lines.slice(-2).map((l) => ({ line_id: l.id, reason: "I don't think we had this", send: false })),
    "late.pick": [{ time: "12:00" }, { time: "13:00" }, { time: "16:00" }],
    "menu.open": [{ outlet: "dining", section: "all_day" }, { outlet: "bar", section: "cocktails" }, { outlet: "bar", section: "wine" }],
    "menu.item": [
      { outlet: "dining", item_id: "belmonte-burger", qty: 2, choices: ["burger_cook:medium", "side:sweet_fries", "burger_mods:no_onions"], add: true },
      { outlet: "dining", item_id: "kale-caesar", qty: 1, choices: ["salad_protein:salmon"], add: true },
      { outlet: "bar", item_id: "halcyon-spritz", qty: 2, choices: [], add: true },
      { outlet: "bar", item_id: "pinot-noir", qty: 1, choices: ["size:bottle"], add: true },
    ],
    "cart.remove": (["dining", "bar"] as const).flatMap((o) => s.carts[o].slice(0, 1).map((l) => ({ outlet: o, item_id: l.item_id }))),
    "cart.open": [{ outlet: "dining", tip: 15 }, { outlet: "bar", tip: 20, deliver_to: "cabana", cabana: "4" }, { outlet: "bar", deliver_to: "room" }],
    "spa.open": [{ category: "massage" }, { category: "facial" }],
    "spa.treatment": [{ treatment_id: "swedish-50", date: c.today, therapist: "any" }, { treatment_id: "deep-80", date: tomorrow, therapist: "male" }, { treatment_id: "couples-80", date: tomorrow }],
    "spa.slot": slots.slice(0, 2).map(([time, th]) => ({ treatment_id: "swedish-50", date: c.today, time, therapist_id: th })),
    "activity.show": [{ activity_id: "kayak-tour", map: true }, { activity_id: "jazz-trio", map: false }],
    "activity.pick": [{ activity_id: "kayak-tour", date: tomorrow, time: "10:00", guests: 2 }, { activity_id: "tennis", date: tomorrow, time: "08:00", guests: 2 }],
    "meeting.filter": [{ headcount: 30, layout: "classroom", date: "2026-11-30" }],
    "meeting.pick": [{ room_id: "marina", date: "2026-11-30", block: "morning", headcount: 30, layout: "classroom", catering: ["coffee", "lunch"], av: ["mics"] }],
    "visitor.open": pending.slice(0, 2).map((v) => ({ visitor_id: v.id, meet: "lobby" })),
    "visitor.expect": [{ name: "Sam Ortiz", arrive_from: "18:00", arrive_to: "19:00", meet: "room", note: "Dinner guest" }],
    "request.fill": [
      { kind: "housekeeping", items: ["towels", "pillows"], send: false },
      { kind: "wakeup", date: tomorrow, time: "06:30", send: false },
      { kind: "maintenance", issue: "ac", details: "The room is too warm", send: false },
      { kind: "transport", option: "airport", time: "10:00", send: false },
    ],
  };
}

export default function DebugConsole() {
  const moves = useMemo(() => {
    const m = new Moves(new Spotlight(SPOTLIGHT));
    scene.registerAll(m, performers);
    return m;
  }, []);
  const [open, setOpen] = useState(true);
  const [last, setLast] = useState<StageResult | null>(null);
  useStay((s) => s); // re-render so samples follow the stay
  const fake = useFakeCall();
  const run = async (id: string, args: Record<string, unknown>) => {
    const r = await moves.run(id, args, `dbg-${Date.now()}`);
    setLast(r);
    (window as unknown as { __bmLast?: unknown }).__bmLast = r;
  };
  (window as unknown as { __bmRun?: typeof run }).__bmRun = run;
  const all = samples();
  return (
    <div className={`debug${open ? " is-open" : ""}`}>
      <button type="button" className="debug-toggle" onClick={() => setOpen(!open)}>
        <Bug size={14} /> Moves <ChevronDown size={14} />
      </button>
      {open && (
        <div className="debug-body">
          <div className="debug-row">
            <b>Call</b>
            <button type="button" className={fake.on ? "" : "is-on"} onClick={() => useFakeCall.setState({ on: false })}>
              idle
            </button>
            {(["connecting", "listening", "thinking", "speaking"] as CallState[]).map((s) => (
              <button key={s} type="button" className={fake.on && fake.state === s ? "is-on" : ""} onClick={() => useFakeCall.setState({ on: true, state: s })}>
                {s}
              </button>
            ))}
          </div>
          {scene.spec.moves.map((m) => (
            <div key={m.id} className="debug-row">
              <b>{m.id}</b>
              {(all[m.id] ?? []).map((a, i) => (
                <button key={i} type="button" title={JSON.stringify(a)} onClick={() => void run(m.id, a)}>
                  {Object.values(a)
                    .map((v) => (Array.isArray(v) ? `[${v.length}]` : String(v)))
                    .join(" ")
                    .slice(0, 28) || "run"}
                </button>
              ))}
            </div>
          ))}
          {last && (
            <pre className="debug-out">
              {last.outcome}
              {last.detail ? `: ${last.detail}` : ""}
              {last.refused?.length ? `\n${JSON.stringify(last.refused)}` : ""}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
