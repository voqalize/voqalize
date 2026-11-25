/**
 * /returns: without an order, every ordered item with whether it can be
 * returned (delivered date, days left, or why not). With `?order=<id>` (and
 * optionally `&item=<product id>`), that order's return form: the item, the
 * reason, the two declarations the shopper confirms (unused, tags intact), the
 * pickup address and refund note, and Submit return, which only the shopper's
 * own click sends. Nothing is chosen until the shopper (or the agent, on their
 * word) chooses it.
 */
import { CheckCircle2, ChevronLeft, Info, MapPin, PackageCheck, RotateCcw, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ProductImage } from "../components/ProductCard";
import { getProduct, inr, useCatalog } from "../data/catalog";
import { POLICY, RETURN_REASONS, fmtDate, fmtDay, pickupDate, reasonLabel, returnCheck, returnRef } from "../data/shop";
import { sendEvent } from "../stage/host";
import { type ViewOrder, formReady, returnedSet, useOrders, useReturnForm } from "../state/orders";
import { useStore } from "../state/store";
import { StatusPill } from "./Orders";

function PolicyBox() {
  return (
    <aside className="svc-policy" aria-label="Returns policy">
      <h2>
        <ShieldCheck size={18} aria-hidden /> Returns in short
      </h2>
      <ul>
        <li>
          Within <b>{POLICY.returns.window_days} days</b> of delivery.
        </li>
        {POLICY.returns.conditions.map((c) => (
          <li key={c}>{c[0].toUpperCase() + c.slice(1)}.</li>
        ))}
        <li>Fragrances cannot be returned.</li>
        <li>{POLICY.returns.pickup}</li>
        <li>{POLICY.returns.refund}</li>
      </ul>
    </aside>
  );
}

/** Every item of every order with its return eligibility. */
function ItemList({ orders }: { orders: ViewOrder[] }) {
  const returned = returnedSet(useStore((s) => s.returns));
  // Delivered orders first (the ones a return can start from), then the ones on the way.
  const rank = (o: ViewOrder) => (o.status === "delivered" ? (returnCheck(o, null, returned).ok ? 0 : 1) : 2);
  const rows = orders.filter((o) => o.status !== "cancelled").sort((a, b) => rank(a) - rank(b));
  return (
    <section className="rt-list" aria-label="Your items">
      {rows.map((o) => (
        <div key={o.id} className="rt-group">
          <header className="rt-group-head">
            <span className="ord-id">{o.id}</span>
            <StatusPill status={o.status} />
            <span className="svc-muted">{o.delivered ? `Delivered ${fmtDate(o.delivered)}` : `Placed ${fmtDate(o.placed)}`}</span>
          </header>
          {o.items.map((i) => {
            const p = getProduct(i.product_id);
            const check = returnCheck(o, i.product_id, returned);
            return (
              <div key={i.product_id} className="rt-row">
                <div className="rt-row-img">
                  <ProductImage id={i.product_id} alt={p?.name ?? "Product"} />
                </div>
                <div className="rt-row-body">
                  <p className="ord-item-name">{p?.name ?? `Product ${i.product_id}`}</p>
                  <p className="svc-muted small">
                    {i.size === "Onesize" ? "One size" : `Size ${i.size}`} · {inr(i.price)}
                  </p>
                </div>
                <div className="rt-row-state">
                  {i.returnRef ? (
                    <span className="rt-flag is-done">
                      <RotateCcw size={14} aria-hidden /> Requested · <span className="mono">{i.returnRef}</span>
                    </span>
                  ) : check.ok ? (
                    <>
                      <span className="rt-flag is-ok">{check.daysLeft === 0 ? "Last day today" : `${check.daysLeft} ${check.daysLeft === 1 ? "day" : "days"} left`}</span>
                      <Link className="btn btn-sm btn-primary" to={`/returns?order=${o.id}&item=${i.product_id}`}>
                        Start return
                      </Link>
                    </>
                  ) : (
                    <span className="rt-flag is-no">{check.why}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </section>
  );
}

function Confirmation({ o, reference, productId }: { o: ViewOrder; reference: string; productId: number }) {
  const p = getProduct(productId);
  const start = useReturnForm((s) => s.start);
  const more = o.items.some((i) => !i.returnRef && i.product_id !== productId);
  return (
    <section className="rt-done" aria-live="polite">
      <CheckCircle2 size={36} aria-hidden />
      <h2>Return requested</h2>
      <p>
        Reference <b className="mono">{reference}</b> for {p?.name ?? `product ${productId}`}.
      </p>
      <dl className="rt-done-facts">
        <div>
          <dt>Pickup</dt>
          <dd>
            By {fmtDay(pickupDate())}, from {o.address.line}, {o.address.city}
          </dd>
        </div>
        <div>
          <dt>Refund</dt>
          <dd>{POLICY.returns.refund}</dd>
        </div>
      </dl>
      <div className="rt-done-actions">
        <Link className="btn btn-outline" to={`/orders?order=${o.id}`}>
          View order
        </Link>
        {more ? (
          <button type="button" className="btn btn-ghost" onClick={() => start(o.id)}>
            Return another item
          </button>
        ) : null}
      </div>
    </section>
  );
}

function ReturnForm({ o }: { o: ViewOrder }) {
  const f = useReturnForm();
  const returned = returnedSet(useStore((s) => s.returns));
  const request = useStore((s) => s.requestReturn);
  const orderCheck = returnCheck(o, null, returned);

  if (!orderCheck.ok) {
    return (
      <div className="rt-closed" role="status">
        <Info size={20} aria-hidden />
        <div>
          <b>This order can't be returned.</b>
          <p>{orderCheck.why}</p>
          <Link className="btn btn-sm btn-outline" to={`/orders?order=${o.id}`}>
            Back to the order
          </Link>
        </div>
      </div>
    );
  }
  if (f.reference && f.product_id != null) return <Confirmation o={o} reference={f.reference} productId={f.product_id} />;

  const submit = () => {
    if (!formReady(f) || f.product_id == null) return;
    const reference = returnRef(o.id, f.product_id);
    request(o.id, f.product_id, reference);
    f.patch({ reference });
    // Only the shopper's own press on Submit return sends it.
    sendEvent("return.submitted", { order_id: o.id, product_id: String(f.product_id), reference });
  };

  return (
    <form
      className="rt-form"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <fieldset className="rt-step" data-stage-group>
        <legend>
          <span className="rt-num">1</span> Which item are you returning?
        </legend>
        <div className="rt-items">
          {o.items.map((i) => {
            const p = getProduct(i.product_id);
            const check = returnCheck(o, i.product_id, returned);
            const on = f.product_id === i.product_id;
            return (
              <button
                type="button"
                key={i.product_id}
                role="radio"
                aria-checked={on}
                disabled={!check.ok}
                className={`rt-item${on ? " is-on" : ""}`}
                data-stage-part={`return:item:${i.product_id}`}
                onClick={() => f.patch({ product_id: i.product_id })}
              >
                <div className="rt-item-img">
                  <ProductImage id={i.product_id} alt={p?.name ?? "Product"} />
                </div>
                <div className="rt-item-body">
                  <span className="ord-item-brand">{p?.brand}</span>
                  <span className="rt-item-name">{p?.name ?? `Product ${i.product_id}`}</span>
                  <span className="svc-muted small">
                    {i.size === "Onesize" ? "One size" : `Size ${i.size}`} · {inr(i.price)}
                  </span>
                  {check.ok ? null : <span className="rt-flag is-no">{i.returnRef ? `Requested · ${i.returnRef}` : check.why}</span>}
                </div>
                <span className="rt-radio" aria-hidden />
              </button>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="rt-step" data-stage-group>
        <legend>
          <span className="rt-num">2</span> Why are you returning it?
        </legend>
        <div className="rt-reasons" role="radiogroup">
          {RETURN_REASONS.map((r) => (
            <button
              type="button"
              key={r.id}
              role="radio"
              aria-checked={f.reason === r.id}
              className={`chip${f.reason === r.id ? " is-on" : ""}`}
              data-stage-part={`return:reason:${r.id}`}
              onClick={() => f.patch({ reason: r.id })}
            >
              {r.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="rt-step" data-stage-group>
        <legend>
          <span className="rt-num">3</span> Please confirm
        </legend>
        <label className={`rt-check${f.unused ? " is-on" : ""}`} data-stage-part="return:unused">
          <input type="checkbox" checked={f.unused} onChange={(e) => f.patch({ unused: e.target.checked })} />
          <span>The item is unused, unwashed and unworn</span>
        </label>
        <label className={`rt-check${f.tags ? " is-on" : ""}`} data-stage-part="return:tags">
          <input type="checkbox" checked={f.tags} onChange={(e) => f.patch({ tags: e.target.checked })} />
          <span>The original tags are intact</span>
        </label>
      </fieldset>

      <fieldset className="rt-step">
        <legend>
          <span className="rt-num">4</span> Pickup and refund
        </legend>
        <div className="rt-pickup">
          <MapPin size={18} aria-hidden />
          <div>
            <b>{o.address.name}</b>
            <p>
              {o.address.line}, {o.address.city} {o.address.pin}
            </p>
            <p className="svc-muted small">Picked up from the delivery address by {fmtDay(pickupDate())}. The address can't be changed.</p>
          </div>
        </div>
        <p className="rt-refund">
          <PackageCheck size={16} aria-hidden /> {POLICY.returns.refund}
        </p>
      </fieldset>

      <div className="rt-submit">
        <p className="svc-muted small">
          {formReady(f)
            ? `Returning ${getProduct(f.product_id!)?.name ?? "the item"}: ${reasonLabel(f.reason!).toLowerCase()}.`
            : "Choose the item and a reason, and tick both boxes to submit."}
        </p>
        <button type="submit" className="btn btn-primary btn-lg" data-stage-part="return:submit" data-dock-avoid disabled={!formReady(f)}>
          Submit return
        </button>
      </div>
    </form>
  );
}

export function Returns() {
  useCatalog((s) => s.index);
  const orders = useOrders();
  const [params] = useSearchParams();
  const orderId = params.get("order")?.toUpperCase() ?? null;
  const item = params.get("item");
  const o = orders.find((x) => x.id === orderId);

  // The URL picks the order (and, from a "Return this item" link, the item).
  useEffect(() => {
    const f = useReturnForm.getState();
    const itemId = item && o?.items.some((i) => String(i.product_id) === item) ? Number(item) : null;
    if (f.order_id !== orderId) f.start(orderId, itemId);
    else if (itemId != null && f.product_id == null && !f.reference) f.patch({ product_id: itemId });
  }, [orderId, item, o]);

  // Tell the brain what changed on the form, once per burst of changes.
  useEffect(() => {
    let timer = 0;
    const unsub = useReturnForm.subscribe((s, prev) => {
      if (!s.order_id || s.reference) return;
      if (s.product_id === prev.product_id && s.reason === prev.reason && s.unused === prev.unused && s.tags === prev.tags && s.order_id === prev.order_id) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const f = useReturnForm.getState();
        if (!f.order_id) return;
        sendEvent("return.changed", {
          order_id: f.order_id,
          product_id: f.product_id != null ? String(f.product_id) : null,
          reason: f.reason,
          unused: f.unused,
          tags: f.tags,
        });
      }, 250);
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, []);

  return (
    <div className="svc svc-returns">
      <header className="svc-head">
        <p className="svc-crumb">
          <Link to="/">Home</Link> / <Link to="/orders">Orders</Link> / Returns
        </p>
        {o ? (
          <>
            <Link to="/returns" className="ord-back is-inline">
              <ChevronLeft size={18} aria-hidden /> All returns
            </Link>
            <h1>Return from order {o.id}</h1>
            <p className="svc-muted">
              {o.delivered ? `Delivered on ${fmtDate(o.delivered)}` : `Placed on ${fmtDate(o.placed)}`} · {o.items.length} {o.items.length === 1 ? "item" : "items"}
            </p>
          </>
        ) : (
          <>
            <h1>Returns</h1>
            <p className="svc-muted">Pick an item to start a return. Returns open on delivery and close {POLICY.returns.window_days} days later.</p>
          </>
        )}
      </header>
      <div className="rt-layout">
        <div className="rt-main">
          {orderId && !o ? (
            <div className="rt-closed" role="status">
              <Info size={20} aria-hidden />
              <div>
                <b>We couldn't find order {orderId}.</b>
                <p>Pick one of your items below.</p>
              </div>
            </div>
          ) : null}
          {o ? <ReturnForm o={o} /> : <ItemList orders={orders} />}
        </div>
        <PolicyBox />
      </div>
    </div>
  );
}
