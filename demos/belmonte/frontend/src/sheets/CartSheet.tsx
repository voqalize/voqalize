/** The order for one outlet: lines, where to deliver, the tip, the breakdown, and Place order. */
import { BedDouble, Clock3, CreditCard, Minus, Plus, Trash2, Umbrella, Wine } from "lucide-react";
import { BAR, DINING, GUEST, getItem } from "../data";
import { money } from "../lib/format";
import { cabanaOpen, choiceLabels, orderTotals, unitPrice } from "../lib/rules";
import { BottomSheet } from "../components/Shell";
import { type Sheet, closeSheet, orderBlocked, placeOrder, removeLine, setCabana, setDeliverTo, setLineQty, setTip, stayClock, useStay } from "../state/store";
import "../styles/dining.css";

export default function CartSheet({ sheet }: { sheet: Extract<Sheet, { kind: "cart" }> }) {
  const outlet = sheet.outlet;
  const s = useStay();
  const lines = s.carts[outlet];
  const count = lines.reduce((n, l) => n + l.qty, 0);
  const tip = s.tip[outlet];
  const policy = outlet === "dining" ? DINING : BAR;
  const t = orderTotals(outlet, lines, tip ?? 0);
  const blocked = orderBlocked(outlet, s);
  const now = stayClock().now;
  const poolOpen = cabanaOpen(now);
  const pool = BAR.bars.find((b) => b.id === "pool")!;
  const alcohol = outlet === "bar" && lines.some((l) => getItem("bar", l.item_id)?.alcohol);
  const firstSection = lines[0] ? getItem(outlet, lines[0].item_id)?.section : undefined;
  const eta = outlet === "dining" ? (DINING.periods.find((p) => p.id === firstSection)?.eta ?? DINING.periods[0].eta) : BAR.eta;
  const where = outlet === "bar" && s.deliverTo === "cabana" ? `pool cabana ${s.cabana ?? ""}`.trim() : s.room ? `room ${s.room}` : "your room";

  return (
    <BottomSheet
      title={outlet === "dining" ? "Your in-room dining order" : "Your drinks order"}
      sub={lines.length ? `${count} ${count === 1 ? "item" : "items"}` : undefined}
      onClose={closeSheet}
      footer={
        lines.length ? (
          <div className="dn-foot">
            <div className="dn-foot-line">
              <span>Total, charged to {s.room ? `room ${s.room}` : "your room"}</span>
              <b>{money(t.total)}</b>
            </div>
            {blocked ? <p className="dn-why">{blocked}</p> : null}
            <button
              type="button"
              className="dn-primary"
              disabled={!!blocked}
              onClick={() => placeOrder(outlet)}
              data-stage-thing="order-place"
              data-stage-label="Place order"
              data-dock-avoid
              data-guest-only
            >
              Place order · {money(t.total)}
            </button>
          </div>
        ) : undefined
      }
    >
      <div className="dn-sheet">
        {!lines.length ? <p className="dn-empty">Your order is empty. Add something from the menu.</p> : null}

        {lines.length ? (
          <div className="dn-lines">
            {lines.map((l, i) => {
              const item = getItem(outlet, l.item_id);
              const extras = choiceLabels(outlet, l);
              return (
                <div key={i} className="dn-line" data-stage-thing={`cart-line-${i}`} data-stage-label={item?.name ?? l.item_id}>
                  <div className="dn-line-main">
                    <div className="dn-line-name">{item?.name ?? l.item_id}</div>
                    {extras.length ? <div className="dn-line-sub">{extras.join(", ")}</div> : null}
                    {l.note ? <div className="dn-line-sub">“{l.note}”</div> : null}
                    <div className="dn-line-sub">{money(unitPrice(outlet, l))} each</div>
                  </div>
                  <div className="dn-line-side">
                    <span className="dn-line-price">{money(unitPrice(outlet, l) * l.qty)}</span>
                    <div className="dn-line-tools">
                      <button type="button" className="dn-icon-btn" aria-label={`Remove ${item?.name ?? ""}`} onClick={() => removeLine(outlet, i)}>
                        <Trash2 size={16} />
                      </button>
                      <div className="dn-stepper is-small">
                        <button type="button" aria-label="One less" onClick={() => setLineQty(outlet, i, l.qty - 1)}>
                          <Minus size={14} />
                        </button>
                        <output>{l.qty}</output>
                        <button type="button" aria-label="One more" disabled={l.qty >= 20} onClick={() => setLineQty(outlet, i, l.qty + 1)}>
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}

        {lines.length && outlet === "bar" ? (
          <div className="dn-group" data-stage-thing="deliver" data-stage-label="Deliver to" data-stage-group>
            <span className="dn-label">Deliver to</span>
            <div className="dn-seg2">
              <button type="button" className={`dn-tip${s.deliverTo === "room" ? " is-on" : ""}`} aria-pressed={s.deliverTo === "room"} onClick={() => setDeliverTo("room")} data-stage-thing="deliver-room" data-stage-label="My room">
                <BedDouble size={18} />
                <small>{s.room ? `Room ${s.room}` : "My room"}</small>
              </button>
              <button
                type="button"
                className={`dn-tip${s.deliverTo === "cabana" ? " is-on" : ""}`}
                aria-pressed={s.deliverTo === "cabana"}
                disabled={!poolOpen}
                style={!poolOpen ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
                onClick={() => setDeliverTo("cabana")}
                data-stage-thing="deliver-cabana"
                data-stage-label="Pool cabana"
              >
                <Umbrella size={18} />
                <small>Pool cabana</small>
              </button>
            </div>
            {!poolOpen ? (
              <p className="dn-opt-hint">
                Cabana delivery while the {pool.name} is open, {pool.hours}.
              </p>
            ) : null}
            {s.deliverTo === "cabana" && poolOpen ? (
              <div className="dn-chips" data-stage-thing="cabanas" data-stage-label="Cabana" data-stage-group>
                {BAR.cabanas.map((n) => (
                  <button key={n} type="button" className={`dn-chip${s.cabana === n ? " is-on" : ""}`} aria-pressed={s.cabana === n} onClick={() => setCabana(n)} data-stage-thing={`cabana-${n}`} data-stage-label={`Cabana ${n}`}>
                    Cabana {n}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {lines.length ? (
          <div className="dn-group" data-stage-thing="tip" data-stage-label="Tip" data-stage-group>
            <div className="dn-group-head">
              <span className="dn-label">Extra tip</span>
              <span className="dn-opt-hint">Service charge already included</span>
            </div>
            <div className="dn-tips">
              {policy.tips.map((pct) => {
                const on = tip === pct;
                return (
                  <button key={pct} type="button" className={`dn-tip${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setTip(outlet, pct)} data-stage-thing={`tip-${pct}`} data-stage-label={pct === 0 ? "No tip" : `${pct}% tip`}>
                    {pct === 0 ? "No tip" : `${pct}%`}
                    {pct ? <small>{money((t.subtotal * pct) / 100)}</small> : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {lines.length ? (
          <div className="dn-sum">
            <div className="dn-sum-row">
              <span>Subtotal</span>
              <span>{money(t.subtotal)}</span>
            </div>
            <div className="dn-sum-row">
              <span>Service charge {policy.service_charge_pct}%</span>
              <span>{money(t.service)}</span>
            </div>
            {outlet === "dining" ? (
              <div className="dn-sum-row">
                <span>Delivery</span>
                <span>{money(t.delivery)}</span>
              </div>
            ) : null}
            <div className="dn-sum-row">
              <span>Sales tax</span>
              <span>{money(t.tax)}</span>
            </div>
            <div className="dn-sum-row">
              <span>Tip</span>
              <span>{tip === null ? "Not chosen" : money(t.tip)}</span>
            </div>
            <div className="dn-sum-row is-total" data-stage-thing="order-total" data-stage-label={`Total ${money(t.total)}`}>
              <span>Total</span>
              <b>{money(t.total)}</b>
            </div>
          </div>
        ) : null}

        {lines.length ? (
          <div className="dn-meta">
            <p>
              <Clock3 size={15} />
              <span>
                Arrives at {where} in about {eta}.
              </span>
            </p>
            <p>
              <CreditCard size={15} />
              <span>
                Charge to {s.room ? `room ${s.room}` : "your room"}, settled on your {GUEST.card} at check-out.
              </span>
            </p>
            {alcohol ? (
              <p>
                <Wine size={15} />
                <span>{BAR.age_rule}</span>
              </p>
            ) : null}
          </div>
        ) : null}

        {lines.length ? <p className="dn-policy">{policy.policy}</p> : null}
      </div>
    </BottomSheet>
  );
}
