/**
 * The bag: each line with its size, a quantity stepper, remove, and gift wrap
 * with a note (`data-stage-part="gift:<id>|<size>"`); totals by the shared
 * rule (`bagTotals`), the free-delivery progress, and Checkout.
 */
import { Gift, Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ProductImage } from "../components/ProductCard";
import { discountPct, inr, useCatalog, productPath } from "../data/catalog";
import { type BagLine, POLICY, addDays, bagTotals, fmtDay, todayIST } from "../data/shop";
import { lineProduct, useStore } from "../state/store";

export function Totals({ lines }: { lines: BagLine[] }) {
  const t = bagTotals(lines);
  return (
    <dl className="totals">
      <div>
        <dt>Total MRP</dt>
        <dd>{inr(t.mrp)}</dd>
      </div>
      {t.mrp > t.subtotal ? (
        <div className="is-save">
          <dt>Discount on MRP</dt>
          <dd>−{inr(t.mrp - t.subtotal)}</dd>
        </div>
      ) : null}
      <div>
        <dt>Delivery</dt>
        <dd>{t.delivery ? inr(t.delivery) : <span className="free">Free</span>}</dd>
      </div>
      {t.wrap ? (
        <div>
          <dt>Gift wrap</dt>
          <dd>{inr(t.wrap)}</dd>
        </div>
      ) : null}
      <div className="is-total">
        <dt>Total</dt>
        <dd>{inr(t.total)}</dd>
      </div>
    </dl>
  );
}

function Line({ l }: { l: BagLine }) {
  const p = lineProduct(l);
  const s = useStore.getState();
  if (!p) return null;
  const off = discountPct(p);
  const max = Math.min(5, p.sizes.find(([x]) => x === l.size)?.[1] ?? 5);
  return (
    <li className="bline" data-stage-thing={`product:${p.id}`}>
      <Link to={productPath(p.id)} className="bline-img">
        <ProductImage id={p.id} alt={p.name} />
      </Link>
      <div className="bline-body">
        <p className="pc-brand">{p.brand}</p>
        <Link to={productPath(p.id)} className="bline-name">
          {p.name}
        </Link>
        <p className="bline-meta">
          Size <b>{l.size === "Onesize" ? "One size" : l.size}</b>
        </p>
        <div className="bline-row">
          <div className="stepper" role="group" aria-label="Quantity">
            <button type="button" aria-label="One fewer" onClick={() => s.setQty(p.id, l.size, l.qty - 1)}>
              <Minus size={14} />
            </button>
            <span aria-live="polite">{l.qty}</span>
            <button type="button" aria-label="One more" disabled={l.qty >= max} onClick={() => s.setQty(p.id, l.size, l.qty + 1)}>
              <Plus size={14} />
            </button>
          </div>
          <button type="button" className="link-btn bline-remove" onClick={() => s.removeLine(p.id, l.size)}>
            <Trash2 size={14} aria-hidden /> Remove
          </button>
        </div>
        <div className={`gift${l.gift ? " is-on" : ""}`} data-stage-part={`gift:${p.id}|${l.size}`} data-stage-group>
          <label className="gift-toggle">
            <input type="checkbox" checked={l.gift} onChange={(e) => s.setGift(p.id, l.size, e.target.checked)} />
            <Gift size={15} aria-hidden /> Gift wrap this for {inr(POLICY.gift_wrap.price)}
            {l.qty > 1 ? ` each` : ""}
          </label>
          {l.gift ? (
            <label className="gift-note">
              <span>Note on the card</span>
              <textarea
                rows={2}
                maxLength={POLICY.gift_wrap.note_max}
                value={l.note}
                placeholder="Happy birthday, Didi!"
                onChange={(e) => s.setGift(p.id, l.size, true, e.target.value)}
              />
              <span className="gift-count">
                {l.note.length}/{POLICY.gift_wrap.note_max}
              </span>
            </label>
          ) : null}
        </div>
      </div>
      <div className="bline-price">
        <b>{inr(p.price * l.qty)}</b>
        {off ? <s>{inr(p.mrp * l.qty)}</s> : null}
        {off ? <span className="pc-off">{off}% off</span> : null}
      </div>
    </li>
  );
}

export function BagPage() {
  const ready = useCatalog((s) => !!s.index);
  const bag = useStore((s) => s.bag);
  const navigate = useNavigate();
  const t = bagTotals(bag);
  const toFree = POLICY.delivery.free_over - t.subtotal;
  return (
    <div className="wrap bag">
      <Breadcrumbs trail={[{ label: "Bag" }]} />
      <h1 className="page-title">
        Bag <span className="muted title-count">{t.count ? `${t.count} ${t.count === 1 ? "item" : "items"}` : ""}</span>
      </h1>
      {!ready ? (
        <p className="muted">Loading…</p>
      ) : bag.length === 0 ? (
        <div className="empty">
          <ShoppingBag size={32} aria-hidden />
          <h2>Your bag is empty</h2>
          <p>Find something you like and add it in your size.</p>
          <Link className="btn primary" to="/shop">
            Browse the store
          </Link>
        </div>
      ) : (
        <div className="bag-grid">
          <div>
            <div className="free-bar" role="status">
              {toFree > 0 ? (
                <p>
                  Add <b>{inr(toFree)}</b> more for free delivery.
                </p>
              ) : (
                <p>
                  <b>Free delivery</b> on this order.
                </p>
              )}
              <div className="free-track" aria-hidden>
                <span style={{ width: `${Math.min(100, (t.subtotal / POLICY.delivery.free_over) * 100)}%` }} />
              </div>
            </div>
            <ul className="blines">
              {bag.map((l) => (
                <Line key={`${l.product_id}|${l.size}`} l={l} />
              ))}
            </ul>
          </div>
          <aside className="summary">
            <h2>Order summary</h2>
            <Totals lines={bag} />
            <p className="summary-eta">
              Arrives by <b>{fmtDay(addDays(todayIST(), POLICY.delivery.days_max))}</b>
            </p>
            <button type="button" className="btn primary big wide" data-dock-avoid onClick={() => navigate("/checkout")}>
              Checkout
            </button>
            <p className="summary-small">{POLICY.gift_wrap.summary}</p>
          </aside>
        </div>
      )}
    </div>
  );
}
