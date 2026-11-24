/**
 * `?debug=1`: fire every Stage move by hand, with arguments built from the trip
 * on screen, through the same performers a call uses (a local `Moves`, so it
 * works with no agent), and fake the call's states for screenshots.
 */
import { useMemo, useState } from "react";
import { Moves, Spotlight, type StageResult } from "@voqalize/stage";
import { Bug, ChevronDown } from "lucide-react";
import { DESTINATIONS, flightsFor } from "../data";
import { cannotPlace, days, defaultStartForMonth, recommend, splitOf, stays, validSplit } from "../engine";
import { SPOTLIGHT } from "../stage/host";
import { performers } from "../stage/performers";
import { scene } from "../stage/scene.gen";
import { useTrip } from "../state/trip";
import { type CallState, useFakeCall } from "./fake";

function samples(): Record<string, Record<string, unknown>[]> {
  const t = useTrip.getState().trip;
  const b = t.brief;
  const st = stays(t);
  const fl = flightsFor(b.from_city, b.destination);
  const rec = b.destination && b.from_city && b.start_date && b.nights ? recommend({ ...t, split: splitOf(t) }) : null;
  const split = splitOf(t) ?? [];
  const alt: number[][] = [];
  for (let i = 0; i < split.length; i++)
    for (let j = 0; j < split.length; j++) {
      if (i === j) continue;
      const s = [...split];
      s[i]++;
      s[j]--;
      if (validSplit(t, s)) alt.push(s);
    }
  const fit = days(t).flatMap((day) => day.city.activities.filter((a) => cannotPlace(t, a.id, day.day) === null).map((a) => ({ activity_id: a.id, day: day.day })));
  return {
    "trip.go": [{ page: "home" }, { page: "plan" }, { page: "checkout" }],
    "trip.step": ["brief", "flights", "hotels", "days", "package"].map((step) => ({ step })),
    "trip.show": [{ target: "total" }, { target: "flight 2" }, { target: "day 3" }, ...(st[0] ? [{ target: st[0].city.hotels[0].name }] : [])],
    "trip.brief": [
      { from_city: "DEL", destination: "bali", start_date: defaultStartForMonth(2), nights: 6, adults: 2, kids: [], style: "honeymoon" },
      { from_city: "BOM", destination: "kerala", start_date: defaultStartForMonth(12), nights: 5, adults: 2, kids: ["6", "1"], style: "family", budget: 150000 },
      { destination: DESTINATIONS[(DESTINATIONS.findIndex((x) => x.id === b.destination) + 1) % DESTINATIONS.length].id },
    ],
    "trip.flights": [{ sort: "price" }, { sort: "recommended" }],
    "trip.flight": fl.slice(0, 3).map((f) => ({ flight_id: f.id })),
    "trip.hotels": st.flatMap((s) => [{ city: s.city.id }, { city: s.city.id, want: "beach" }]),
    "trip.hotel": st.map((s) => ({ city: s.city.id, hotel_id: s.city.hotels[s.city.hotels.length - 1].id, room_id: s.city.hotels[s.city.hotels.length - 1].rooms[0].id })),
    "trip.nights": alt.slice(0, 2).map((s) => ({ split: s.map(String) })),
    "trip.add": fit.slice(0, 3),
    "trip.remove": t.activities.slice(0, 2).map((p) => ({ ...p })),
    "trip.build": rec
      ? [
          {
            flight_id: rec.flight_id,
            hotels: Object.entries(rec.hotels).map(([c, h]) => `${c}:${h.hotel_id}:${h.room_id}`),
            activities: rec.activities.map((p) => `${p.day}:${p.activity_id}`),
          },
        ]
      : [],
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
  useTrip((s) => s.trip); // re-render so samples follow the trip
  const fake = useFakeCall();
  const run = async (id: string, args: Record<string, unknown>) => {
    const r = await moves.run(id, args, `dbg-${Date.now()}`);
    setLast(r);
    (window as unknown as { __wlLast?: unknown }).__wlLast = r;
  };
  (window as unknown as { __wlRun?: typeof run }).__wlRun = run;
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
