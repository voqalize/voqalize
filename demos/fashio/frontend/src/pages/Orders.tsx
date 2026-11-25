/**
 * /orders: every order of the signed-in customer with its tracking. Select an
 * order (or open `?order=<id>`) to see the timeline, items, address, payment
 * and what can still be done: cancel before dispatch (the shopper presses
 * Cancel order in the dialog), return an item within 7 days of delivery.
 * After an order is placed its delivery date and address cannot be changed:
 * there is no control for either.
 */
import { AlertCircle, Ban, Check, ChevronLeft, CreditCard, Info, MapPin, Package, RotateCcw, Truck, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ProductImage } from "../components/ProductCard";
import { getProduct, inr, useCatalog, productPath } from "../data/catalog";
import { CUSTOMER, POLICY, TRACK_STEPS, canCancel, fmtDate, fmtDay, refundNote, returnCheck, statusLabel, todayIST } from "../data/shop";
import { sendEvent } from "../stage/host";
import { type ViewOrder, returnedSet, useOrders, useOrdersUi } from "../state/orders";
import { useStore } from "../state/store";

export function StatusPill({ status }: { status: string }) {
  return <span className={`st-pill st-${status}`}>{statusLabel(status)}</span>;
}

const total = (o: ViewOrder) => o.items.reduce((t, i) => t + i.price * i.qty, 0);

/** One line under the status: when it arrives, arrived, or what happened. */
export function statusLine(o: ViewOrder): string {
  const today = todayIST();
  switch (o.status) {
    case "placed":
    case "packed":
    case "shipped":
      return o.eta ? (o.eta === today ? "Arriving today" : `Arriving by ${fmtDay(o.eta)}`) : statusLabel(o.status);
    case "out_for_delivery":
      return "Out for delivery, arriving today";
    case "delivered":
      return o.delivered ? `Delivered on ${fmtDay(o.delivered)}` : "Delivered";
    case "cancelled":
      return "Cancelled";
    default:
      return statusLabel(o.status);
  }
}

function Thumbs({ o }: { o: ViewOrder }) {
  return (
    <div className="ord-thumbs">
      {o.items.slice(0, 3).map((i) => (
        <div className="ord-thumb" key={`${i.product_id}|${i.size}`}>
          <ProductImage id={i.product_id} alt={getProduct(i.product_id)?.name ?? "Product"} />
        </div>
      ))}
      {o.items.length > 3 ? <span className="ord-more">+{o.items.length - 3}</span> : null}
    </div>
  );
}

function OrderCard({ o, on, pick }: { o: ViewOrder; on: boolean; pick: (id: string) => void }) {
  const n = o.items.reduce((t, i) => t + i.qty, 0);
  return (
    <button type="button" className={`ord-card${on ? " is-on" : ""}`} data-stage-thing={`order:${o.id}`} aria-pressed={on} onClick={() => pick(o.id)}>
      <div className="ord-card-top">
        <span className="ord-id">{o.id}</span>
        <StatusPill status={o.status} />
      </div>
      <p className="ord-card-line">{statusLine(o)}</p>
      <div className="ord-card-foot">
        <Thumbs o={o} />
        <div className="ord-card-meta">
          <span>Placed {fmtDate(o.placed)}</span>
          <b>
            {inr(total(o))} · {n} {n === 1 ? "item" : "items"}
          </b>
        </div>
      </div>
    </button>
  );
}

function Stepper({ o }: { o: ViewOrder }) {
  if (o.status === "cancelled") return null;
  const at = TRACK_STEPS.indexOf(o.status);
  return (
    <ol className="ord-steps" aria-label="Order progress">
      {TRACK_STEPS.map((s, i) => (
        <li key={s} className={i < at ? "is-done" : i === at ? "is-now" : ""}>
          <span className="ord-step-dot">{i <= at ? <Check size={12} strokeWidth={3} /> : null}</span>
          <span className="ord-step-label">{statusLabel(s)}</span>
        </li>
      ))}
    </ol>
  );
}

function Actions({ o }: { o: ViewOrder }) {
  const openCancel = useOrdersUi((s) => s.openCancel);
  const returns = useStore((s) => s.returns);
  if (o.status === "cancelled") {
    return (
      <div className="ord-actions is-note" data-stage-thing={`order-actions:${o.id}`}>
        <Ban size={18} aria-hidden />
        <div>
          <b>This order was cancelled.</b>
          <p>{refundNote(o)}</p>
        </div>
      </div>
    );
  }
  if (canCancel(o)) {
    return (
      <div className="ord-actions" data-stage-thing={`order-actions:${o.id}`}>
        <div>
          <b>Not dispatched yet</b>
          <p>You can cancel this order while it is {statusLabel(o.status).toLowerCase()}. Once it ships it can only be returned after delivery.</p>
        </div>
        <button type="button" className="btn btn-danger-outline" data-cancel-open={o.id} data-dock-avoid onClick={() => openCancel(o.id)}>
          Cancel order
        </button>
      </div>
    );
  }
  if (o.status === "shipped" || o.status === "out_for_delivery") {
    return (
      <div className="ord-actions is-note" data-stage-thing={`order-actions:${o.id}`}>
        <Truck size={18} aria-hidden />
        <div>
          <b>Already dispatched, so it can't be cancelled.</b>
          <p>Once it is delivered you can return it within {POLICY.returns.window_days} days, unused with the tags on.</p>
        </div>
      </div>
    );
  }
  if (o.status === "delivered") {
    const window = returnCheck(o, null, returnedSet(returns));
    return (
      <div className="ord-actions is-col" data-stage-thing={`order-actions:${o.id}`}>
        {window.ok ? (
          <p className="ord-window">
            <RotateCcw size={16} aria-hidden /> Return window open: <b>{window.daysLeft === 0 ? "last day today" : `${window.daysLeft} ${window.daysLeft === 1 ? "day" : "days"} left`}</b>
          </p>
        ) : (
          <p className="ord-window is-closed">
            <Info size={16} aria-hidden /> {window.why}
          </p>
        )}
      </div>
    );
  }
  return null;
}

function Detail({ o, back }: { o: ViewOrder; back: () => void }) {
  const returns = useStore((s) => s.returns);
  const returned = returnedSet(returns);
  const events = [...o.events].reverse();
  const windowOpen = o.status === "delivered" && returnCheck(o, null, returned).ok;
  return (
    <article className="ord-detail-card" data-stage-thing={`order-detail:${o.id}`}>
      <button type="button" className="ord-back" onClick={back}>
        <ChevronLeft size={18} aria-hidden /> All orders
      </button>
      <header className="ord-detail-head">
        <div>
          <p className="svc-kicker">Order {o.id}</p>
          <h2>{statusLine(o)}</h2>
          <p className="svc-muted">
            Placed on {fmtDate(o.placed)} · {inr(total(o))}
          </p>
        </div>
        <StatusPill status={o.status} />
      </header>

      <Stepper o={o} />
      <Actions o={o} />

      <section className="ord-sec" data-stage-group>
        <h3>
          <Truck size={16} aria-hidden /> Tracking
        </h3>
        {o.courier ? (
          <p className="ord-courier">
            {o.courier.name} · AWB <span className="mono">{o.courier.awb}</span>
          </p>
        ) : o.status !== "cancelled" ? (
          <p className="ord-courier svc-muted">Courier details appear once the order ships.</p>
        ) : null}
        <ol className="ord-timeline">
          {o.eta && o.status !== "delivered" && o.status !== "cancelled" ? (
            <li className="is-next">
              <span className="tl-dot" />
              <div>
                <b>{o.status === "out_for_delivery" ? "Arriving today" : "Expected delivery"}</b>
                <span className="tl-when">{fmtDate(o.eta)}</span>
              </div>
            </li>
          ) : null}
          {events.map((e, i) => (
            <li key={`${e.date}${e.time}${i}`} className={i === 0 ? "is-latest" : ""}>
              <span className="tl-dot" />
              <div>
                <b>{e.text}</b>
                <span className="tl-when">
                  {fmtDate(e.date)}
                  {e.time ? `, ${e.time}` : ""}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="ord-sec" data-stage-group>
        <h3>
          <Package size={16} aria-hidden /> Items
        </h3>
        <ul className="ord-items">
          {o.items.map((i) => {
            const p = getProduct(i.product_id);
            const check = o.status === "delivered" ? returnCheck(o, i.product_id, returned) : null;
            return (
              <li key={`${i.product_id}|${i.size}`} className="ord-item">
                <Link to={productPath(i.product_id)} className="ord-item-img">
                  <ProductImage id={i.product_id} alt={p?.name ?? "Product"} />
                </Link>
                <div className="ord-item-body">
                  <p className="ord-item-brand">{p?.brand ?? ""}</p>
                  <Link to={productPath(i.product_id)} className="ord-item-name">
                    {p?.name ?? `Product ${i.product_id}`}
                  </Link>
                  <p className="svc-muted">
                    {i.size === "Onesize" ? "One size" : `Size ${i.size}`} · Qty {i.qty}
                  </p>
                  {i.returnRef ? (
                    <p className="ord-item-flag">
                      <RotateCcw size={14} aria-hidden /> Return requested · <span className="mono">{i.returnRef}</span>
                    </p>
                  ) : check && check.ok ? (
                    <Link className="btn btn-sm btn-outline" data-dock-avoid to={`/returns?order=${o.id}&item=${i.product_id}`}>
                      Return this item
                    </Link>
                  ) : check && !check.ok && windowOpen ? (
                    <p className="svc-muted small">{check.why}</p>
                  ) : null}
                </div>
                <b className="ord-item-price">{inr(i.price * i.qty)}</b>
              </li>
            );
          })}
        </ul>
      </section>

      <div className="ord-two">
        <section className="ord-sec">
          <h3>
            <MapPin size={16} aria-hidden /> Delivery address
          </h3>
          <address className="ord-address">
            <b>{o.address.name}</b>
            <br />
            {o.address.line}
            <br />
            {o.address.city} {o.address.pin}
          </address>
          <p className="ord-lock">
            <AlertCircle size={14} aria-hidden /> Delivery date and address can't be changed after an order is placed.
          </p>
        </section>
        <section className="ord-sec">
          <h3>
            <CreditCard size={16} aria-hidden /> Payment
          </h3>
          <dl className="ord-pay">
            <div>
              <dt>Items</dt>
              <dd>{inr(total(o))}</dd>
            </div>
            <div>
              <dt>Delivery</dt>
              <dd>{total(o) >= POLICY.delivery.free_over ? "Free" : inr(POLICY.delivery.fee)}</dd>
            </div>
            <div className="is-total">
              <dt>{o.status === "cancelled" ? "Refund" : "Paid"}</dt>
              <dd>{inr(total(o) + (total(o) >= POLICY.delivery.free_over ? 0 : POLICY.delivery.fee))}</dd>
            </div>
          </dl>
          <p className="svc-muted">{o.payment}</p>
        </section>
      </div>
    </article>
  );
}

function CancelDialog({ orders }: { orders: ViewOrder[] }) {
  const id = useOrdersUi((s) => s.cancelFor);
  const close = () => useOrdersUi.getState().openCancel(null);
  const cancel = useStore((s) => s.cancelOrder);
  const o = orders.find((x) => x.id === id);
  useEffect(() => {
    if (!o) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [o]);
  if (!o || !canCancel(o)) return null;
  const confirm = () => {
    cancel(o.id);
    close();
    // Only the shopper's own press on this button cancels; the agent only opens the dialog.
    sendEvent("order.cancelled", { order_id: o.id, status: "cancelled" });
  };
  return (
    <div className="svc-dialog-back" data-overlay="center" onClick={(e) => e.target === e.currentTarget && close()}>
      <div className="svc-dialog" role="dialog" aria-modal="true" aria-labelledby="cancel-h">
        <button type="button" className="svc-dialog-x" aria-label="Close" onClick={close}>
          <X size={18} />
        </button>
        <h2 id="cancel-h">Cancel order {o.id}?</h2>
        <p>
          {o.items.length} {o.items.length === 1 ? "item" : "items"}, {inr(total(o))}. It is {statusLabel(o.status).toLowerCase()} and not yet dispatched.
        </p>
        <p className="svc-dialog-note">{refundNote(o)}</p>
        <div className="svc-dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={close}>
            Keep order
          </button>
          <button type="button" className="btn btn-danger" data-stage-part={`cancel:${o.id}`} data-dock-avoid onClick={confirm}>
            Cancel order
          </button>
        </div>
      </div>
    </div>
  );
}

export function Orders() {
  useCatalog((s) => s.index);
  const orders = useOrders();
  const [params, setParams] = useSearchParams();
  const selected = useOrdersUi((s) => s.selected);
  const select = useOrdersUi((s) => s.select);
  const param = params.get("order");

  // The URL preselects (a link, or a move landing here); a pick updates it.
  useEffect(() => {
    if (param && param.toUpperCase() !== useOrdersUi.getState().selected) select(param.toUpperCase());
    if (!param && useOrdersUi.getState().selected) select(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param]);
  useEffect(() => {
    // Read the store, not this render's value: the effect above may have just set it.
    const now = useOrdersUi.getState().selected;
    if ((now ?? null) !== (param?.toUpperCase() ?? null)) {
      const next = new URLSearchParams(params);
      if (now) next.set("order", now);
      else next.delete("order");
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const order = orders.find((o) => o.id === selected);
  const sent = useRef<string | null>(null);
  useEffect(() => {
    const key = order ? `${order.id}|${order.status}` : null;
    if (!order || sent.current === key) return;
    sent.current = key;
    sendEvent("order.selected", { order_id: order.id, status: order.status });
  }, [order]);

  useEffect(() => () => useOrdersUi.setState({ cancelFor: null }), []);

  const pick = (id: string) => {
    select(id);
    if (window.matchMedia("(max-width: 899px)").matches) window.scrollTo({ top: 0 });
  };
  const active = orders.filter((o) => ["placed", "packed", "shipped", "out_for_delivery"].includes(o.status)).length;

  return (
    <div className="svc svc-orders">
      <header className="svc-head">
        <p className="svc-crumb">
          <Link to="/">Home</Link> / Account / Orders
        </p>
        <h1>Your orders</h1>
        <p className="svc-muted">
          Signed in as {CUSTOMER.name} · {orders.length} orders · {active} on the way
        </p>
      </header>
      <div className={`ord-layout${order ? " has-selected" : ""}`}>
        <section className="ord-list" aria-label="Orders" data-stage-group>
          {orders.map((o) => (
            <OrderCard key={o.id} o={o} on={o.id === selected} pick={pick} />
          ))}
        </section>
        <section className="ord-detail" aria-live="polite">
          {order ? (
            <Detail o={order} back={() => select(null)} />
          ) : (
            <div className="ord-empty">
              <Package size={28} aria-hidden />
              <h2>Select an order</h2>
              <p>Pick an order on the left to see where it is, what's in it and what you can still do.</p>
              <ul className="ord-policy">
                <li>Cancel any time before dispatch (while Placed or Packed).</li>
                <li>Delivery date and address can't be changed once an order is placed.</li>
                <li>{POLICY.returns.summary}</li>
              </ul>
            </div>
          )}
        </section>
      </div>
      <CancelDialog orders={orders} />
    </div>
  );
}
