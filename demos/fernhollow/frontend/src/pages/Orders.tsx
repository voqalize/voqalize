/**
 * /orders — the account's orders page: the three sample orders with a
 * tracking block (data/demo_orders.json), each with a timeline of its
 * authored events, the booked delivery slot and, where it can still move,
 * Change delivery day (only to the order's own authored slots). A delivered
 * order hands off to the returns form. Works by tap; the agent opens an order
 * with `orders.open` and moves a day with `orders.reschedule`.
 */
import { ArrowRight, Check, Package, PackageCheck, RotateCcw, Truck, X } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Crumbs, EmilyTag, Photo } from "../components/bits";
import { getProduct, money } from "../data/catalog";
import { STAGES, STAGE_LABEL, type TrackedOrder, TRACKED, bookedSlot, cap, dayLabel, getTracked, relDay, useDelivery, useOrderView } from "../orders/tracking";
import { persona } from "../persona";
import { navigatedBy } from "../voice/controller";
import { useTitle } from "./usePage";

const ACCOUNT = TRACKED[0]?.name ?? "";

export function Orders() {
  useTitle("Your orders");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const asked = params.get("order");
  const open = useOrderView((s) => s.open);

  // The URL is the source: ?order=FH-31207 opens that order.
  useEffect(() => {
    const o = getTracked(asked);
    const now = useOrderView.getState().open;
    if (o && now !== o.number) useOrderView.getState().setOpen(o.number, navigatedBy());
    if (!o && now) useOrderView.getState().setOpen(null);
  }, [asked]);

  const shown = getTracked(open) ?? null;
  const choose = (n: string) => navigate(`/orders?order=${n}`);

  return (
    <div className="wrap page-pad frontdesk orders">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Account" }, { label: "Orders" }]} />
      <header className="fd-hero fd-hero-tight">
        <div>
          <p className="fd-eyebrow">
            <Package size={15} aria-hidden /> Signed in as {ACCOUNT}
          </p>
          <h1 className="h1">Your orders</h1>
          <p className="lede">Where each order is, and when it arrives. Ask {persona.name} “where’s my bed frame?” or “can it come on Thursday instead?”.</p>
        </div>
      </header>

      <div className={`fd-orders${shown ? " has-open" : ""}`}>
        <ol className="fd-order-list" aria-label="Orders">
          {TRACKED.map((o) => (
            <OrderCard key={o.number} o={o} active={shown?.number === o.number} onOpen={() => choose(o.number)} />
          ))}
        </ol>
        <div className="fd-order-detail" data-emily-start>
          {shown ? (
            <OrderDetail o={shown} />
          ) : (
            <div className="fd-order-empty">
              <Truck size={28} strokeWidth={1.3} aria-hidden />
              <p className="h3">Choose an order to track it</p>
              <p className="small">You will see where it is, the delivery day, and what you can still change.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusPill({ o }: { o: TrackedOrder }) {
  const s = o.tracking.stage;
  return <span className={`fd-status is-${s}`}>{STAGE_LABEL[s]}</span>;
}

function OrderCard({ o, active, onOpen }: { o: TrackedOrder; active: boolean; onOpen: () => void }) {
  const moved = useDelivery((s) => s.moved);
  const slot = bookedSlot(o, moved);
  const when =
    o.tracking.stage === "delivered"
      ? `Delivered ${dayLabel(-(o.delivered_days_ago ?? 0))}`
      : slot
        ? `Arriving ${relDay(slot.days_from_now).replace(/^T/, "t")}, ${slot.window}`
        : "";
  return (
    <li>
      <button type="button" className={`fd-order-card${active ? " is-active" : ""}`} aria-current={active ? "true" : undefined} onClick={onOpen} data-stage-part={`order-card:${o.number}`}>
        <span className="fd-order-top">
          <span className="fd-order-no">{o.number}</span>
          <StatusPill o={o} />
        </span>
        <span className="fd-order-when">{when}</span>
        <span className="fd-order-thumbs">
          {o.lines.map((l) => {
            const p = getProduct(l.product_id);
            return p ? <Photo key={l.product_id} file={p.images[0]} alt="" sizes="56px" /> : null;
          })}
        </span>
        <span className="small">
          Placed {dayLabel(-o.placed_days_ago)} · {o.lines.reduce((n, l) => n + l.qty, 0)} items · {money(o.total)}
        </span>
      </button>
    </li>
  );
}

function OrderDetail({ o }: { o: TrackedOrder }) {
  const moved = useDelivery((s) => s.moved);
  const changed = useDelivery((s) => s.changed);
  const picking = useOrderView((s) => s.picking);
  const pending = useOrderView((s) => s.pending);
  const opened = useOrderView((s) => s.opened);
  const slot = bookedSlot(o, moved);
  const t = o.tracking;
  const reached = STAGES.findIndex((s) => s.id === t.stage);
  const byAgent = changed?.order_number === o.number && changed.by === "emily";
  const eventOf = (stage: string) => t.events.find((e) => e.stage === stage);

  const summary =
    t.stage === "packed"
      ? `Packed at our warehouse and waiting for its van.${t.two_person ? " A two-person team brings it in." : ""}`
      : t.stage === "out_for_delivery"
        ? `On the van today${slot ? `, due ${slot.hours}` : ""}.${t.delivery.stops_before ? ` ${t.delivery.stops_before} stops before yours.` : ""}`
        : `Delivered ${dayLabel(-(o.delivered_days_ago ?? 0))} and signed for at the front door.`;

  return (
    <article className="fd-order" data-stage-thing={`order:${o.number}`} aria-labelledby={`h-${o.number}`}>
      <header className="fd-order-head">
        <div>
          <h2 className="h2" id={`h-${o.number}`}>
            {o.number} {opened?.order_number === o.number && opened.by === "emily" ? <EmilyTag /> : null}
          </h2>
          <p className="small">
            Placed {dayLabel(-o.placed_days_ago)} · {money(o.total)}
            {o.delivery_fee ? ` incl. ${money(o.delivery_fee)} delivery` : " · free delivery"}
          </p>
        </div>
        <StatusPill o={o} />
      </header>
      <p className="fd-order-summary">{summary}</p>

      <ol className="fd-timeline" aria-label="Tracking">
        {STAGES.map((s, i) => {
          const e = eventOf(s.id);
          const state = i < reached ? "done" : i === reached ? "now" : "next";
          return (
            <li key={s.id} className={`is-${state}`}>
              <span className="fd-dot" aria-hidden>
                {state !== "next" ? <Check size={11} strokeWidth={3} /> : null}
              </span>
              <div>
                <p className="fd-tl-label">{s.label}</p>
                {e ? (
                  <p className="small">
                    {dayLabel(-e.days_ago)}, {e.time} · {e.text}
                  </p>
                ) : s.id === "delivered" && slot ? (
                  <p className="small">
                    Booked for {relDay(slot.days_from_now).toLowerCase() === "today" ? "today" : dayLabel(slot.days_from_now)}, {slot.window} ({slot.hours})
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {t.stage !== "delivered" ? (
        <section className="fd-delivery" aria-label="Delivery day">
          <div className="fd-delivery-row">
            <Truck size={20} strokeWidth={1.5} aria-hidden />
            <div>
              <p className="fd-delivery-k">Delivery {byAgent ? <EmilyTag /> : null}</p>
              <p className="fd-delivery-v">{slot ? `${cap(relDay(slot.days_from_now))}${slot.days_from_now > 1 ? "" : ` (${dayLabel(slot.days_from_now)})`}, ${slot.window} · ${slot.hours}` : "We will agree a day with you"}</p>
            </div>
            {t.can_reschedule && !picking ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                data-stage-part={`order:${o.number}:change`}
                onClick={() => useOrderView.getState().setPicking(true, slot?.id ?? null)}
              >
                Change delivery day
              </button>
            ) : null}
          </div>
          {!t.can_reschedule ? <p className="small fd-why">{t.why_not}</p> : null}
          {picking && t.can_reschedule ? (
            <div className="fd-slots" role="radiogroup" aria-label="Delivery days">
              {t.slots.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={pending === s.id}
                  className={`fd-slot${pending === s.id ? " is-on" : ""}`}
                  data-stage-part={`slot:${s.id}`}
                  onClick={() => useOrderView.getState().setPending(s.id)}
                >
                  <span className="fd-slot-day">{dayLabel(s.days_from_now)}</span>
                  <span className="fd-slot-win">{cap(s.window)}</span>
                  <span className="small">{s.hours}</span>
                </button>
              ))}
              <div className="fd-slot-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  data-stage-part={`order:${o.number}:save`}
                  disabled={!pending}
                  onClick={() => {
                    if (pending) useDelivery.getState().move(o.number, pending);
                    useOrderView.getState().setPicking(false);
                  }}
                >
                  Save
                </button>
                <button type="button" className="btn btn-quiet btn-sm" onClick={() => useOrderView.getState().setPicking(false)}>
                  <X size={14} aria-hidden /> Cancel
                </button>
              </div>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="fd-delivery is-done" aria-label="Returns">
          <div className="fd-delivery-row">
            <PackageCheck size={20} strokeWidth={1.5} aria-hidden />
            <div>
              <p className="fd-delivery-k">Not quite right?</p>
              <p className="fd-delivery-v">Unused pieces can go back within 30 days of delivery.</p>
            </div>
            <Link className="btn btn-primary btn-sm" to={`/returns/start?order=${o.number}`} data-stage-part={`order:${o.number}:return`}>
              <RotateCcw size={14} aria-hidden /> Return or exchange an item
            </Link>
          </div>
        </section>
      )}

      <ul className="fd-order-lines">
        {o.lines.map((l) => {
          const p = getProduct(l.product_id);
          return (
            <li key={l.product_id}>
              {p ? <Photo file={p.images[0]} alt="" sizes="72px" /> : null}
              <div>
                <Link to={`/product/${l.product_id}?variant=${l.variant_id}`} className="fd-line-title">
                  {l.title}
                </Link>
                <p className="small">
                  {l.variant} · Qty {l.qty}
                </p>
              </div>
              <span className="price">{money(l.unit_price * l.qty)}</span>
            </li>
          );
        })}
      </ul>
      <Link to="/policy/delivery" className="link small">
        How delivery works <ArrowRight size={12} aria-hidden />
      </Link>
    </article>
  );
}
