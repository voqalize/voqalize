/**
 * `?debug=1`: fire any Stage move by hand, with editable JSON arguments, through
 * the same `Moves` runtime the call uses (rings and all), and watch the state
 * events the page sends. Works with no call. "Fake a call" shows the call tile
 * in any state without a client, to see and screenshot it.
 */
import { useState } from "react";
import { runByHand, useStageLog } from "../stage/host";
import { scene } from "../stage/scene.gen";
import { FAKE_STATES, type CallState, useFakeCall } from "./fake";

/**
 * A worked example for every move in scene.json, on real catalogue products
 * (data/catalog.json) and the sample orders (data/orders.json):
 * 7412 is W's pink kurta (M out of stock, so Find my size swaps to S),
 * 14395 Enroute's pink flats (UK 5 and 6 out of stock), 4664 an Adidas watch
 * (one size). FSH-48711 is packed (can be cancelled), FSH-48213 delivered 3
 * days ago (returnable), FSH-47920 delivered 11 days ago (window closed).
 */
export function examples(): Record<string, unknown> {
  return {
    "site.go": { path: "/p/7412" },
    "shop.filter": { dept: "women", types: ["kurtas"], brands: ["W", "Biba"], sizes: ["M"], price_max: 2000, sort: "price_asc" },
    "shop.show": { product_id: "7412" },
    "compare.show": { ids: ["7411", "7412", "7420"] },
    "product.size": { product_id: "7412", size: "S" },
    "size_chart.open": { product_id: "7412", size: "M" },
    "fit.fill": { product_id: "7412", height_cm: 165, usual_size: "M", fit: "regular" },
    "fit.recommend": { product_id: "7412", size: "S", wanted: "M", reason: "M is out of stock; this kurta runs true to size and S is the nearest in stock." },
    "wishlist.set": { product_id: "7412", on: true },
    "bag.add": { product_id: "14395", size: "UK 7", qty: 1 },
    "bag.gift": { product_id: "14395", size: "UK 7", on: true, note: "Happy birthday, Didi! Love, Neha" },
    "checkout.focus": { field: "address" },
    "gifts.brief": { recipient: "Sister", occasion: "Raksha Bandhan", budget_max: 1999, colours: ["Pink"], material: "Silk" },
    "gifts.show": { ids: ["4664", "4666", "4690"], reasons: ["A classic white watch", "Black goes with everything", "A playful digital pick"] },
    "orders.open": { order_id: "FSH-48602" },
    "orders.cancel_open": { order_id: "FSH-48711" },
    "returns.fill": { order_id: "FSH-48213", product_id: "7421", reason: "size_small", unused: true, tags: true },
    "kiosk.search": { query: "sneakers", genders: ["men"], sizes: ["UK 9"], price_max: 3000 },
    "kiosk.show": { product_id: "4664" },
    "kiosk.qr": { product_id: "4664" },
    "kiosk.shortlist": { product_id: "4664", on: true },
    "kiosk.assist": {},
  };
}

export function DebugConsole() {
  const ids = scene.spec.moves.map((m) => m.id);
  const [move, setMove] = useState<string>(ids[1] ?? ids[0]);
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
