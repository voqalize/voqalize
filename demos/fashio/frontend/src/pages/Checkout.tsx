/**
 * Checkout: contact (name and phone), address, payment (UPI, card or cash on
 * delivery), then Place order. Everything here is typed and picked by the
 * shopper; the agent only rings a section (`checkout.focus`). What was typed
 * never leaves the page: the brain hears only whether each section is complete
 * (`checkout.changed`, see stage/report.ts). Placing the order adds it to this
 * browser's orders, clears the bag, shows the confirmation and tells the brain
 * (`order.placed`).
 */
import { CheckCircle2, Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ProductImage } from "../components/ProductCard";
import { inr, useCatalog } from "../data/catalog";
import { type Order, POLICY, bagTotals, fmtDay } from "../data/shop";
import { sendEvent } from "../stage/host";
import { useCheckoutFlags } from "../stage/report";
import { lineProduct, useStore } from "../state/store";
import { Totals } from "./Bag";

const PAYMENTS = [
  { id: "UPI", label: "UPI", note: "Pay with any UPI app" },
  { id: "Card", label: "Credit or debit card", note: "Visa, Mastercard, RuPay" },
  { id: "Cash on delivery", label: "Cash on delivery", note: "Pay when it arrives" },
];

export function Checkout() {
  const ready = useCatalog((s) => !!s.index);
  const bag = useStore((s) => s.bag);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [line, setLine] = useState("");
  const [city, setCity] = useState("");
  const [pin, setPin] = useState("");
  const [payment, setPayment] = useState("");
  const [done, setDone] = useState<{ order: Order; total: number } | null>(null);

  const contact = name.trim().length >= 2 && /^[6-9]\d{9}$/.test(phone.replace(/\D/g, "").slice(-10)) && phone.replace(/\D/g, "").length >= 10;
  const address = line.trim().length >= 6 && city.trim().length >= 2 && /^\d{6}$/.test(pin.trim());
  const paid = !!payment && (payment !== "Cash on delivery" || POLICY.delivery.cod);
  const t = bagTotals(bag);

  useEffect(() => {
    useCheckoutFlags.setState({ contact, address, payment: paid });
  }, [contact, address, paid]);
  useEffect(() => () => useCheckoutFlags.setState({ contact: false, address: false, payment: false }), []);

  const place = () => {
    if (!contact || !address || !paid || !bag.length) return;
    const total = t.total;
    const order = useStore.getState().placeOrder({
      payment,
      address: { name: name.trim(), line: line.trim(), city: city.trim(), pin: pin.trim() },
      items: bag.map((l) => ({ product_id: l.product_id, size: l.size, qty: l.qty, price: lineProduct(l)?.price ?? 0, gift: l.gift || undefined, note: l.gift && l.note ? l.note : undefined })),
    });
    useStore.getState().clearBag();
    setDone({ order, total });
    window.scrollTo({ top: 0 });
    sendEvent("order.placed", { order_id: order.id, total });
  };

  if (done) {
    return (
      <div className="wrap checkout">
        <div className="placed" data-stage-thing={`order:${done.order.id}`}>
          <CheckCircle2 size={44} aria-hidden className="placed-icon" />
          <h1 className="page-title">Order placed</h1>
          <p className="placed-id">
            Order <b>{done.order.id}</b> for {inr(done.total)}
          </p>
          <p>
            Arriving by <b>{done.order.eta ? fmtDay(done.order.eta) : ""}</b>. We'll update its tracking as it moves.
          </p>
          <p className="muted">{POLICY.changes.summary.split(". ")[0]}.</p>
          <div className="notfound-links">
            <Link className="btn primary" to={`/orders?order=${done.order.id}`}>
              Track this order
            </Link>
            <Link className="btn ghost" to="/shop">
              Keep shopping
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap checkout">
      <Breadcrumbs trail={[{ label: "Bag", to: "/bag" }, { label: "Checkout" }]} />
      <h1 className="page-title">Checkout</h1>
      {!ready ? (
        <p className="muted">Loading…</p>
      ) : bag.length === 0 ? (
        <div className="empty">
          <h2>Your bag is empty</h2>
          <p>Add something to your bag first.</p>
          <Link className="btn primary" to="/shop">
            Browse the store
          </Link>
        </div>
      ) : (
        <div className="bag-grid">
          <form
            className="co-form"
            onSubmit={(e) => {
              e.preventDefault();
              place();
            }}
          >
            <section className={`co-step${contact ? " is-done" : ""}`} data-stage-part="checkout:contact" data-stage-group>
              <h2>
                <span className="co-num">1</span> Contact
              </h2>
              <div className="co-fields">
                <label className="field">
                  <span>Full name</span>
                  <input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="field">
                  <span>Mobile number</span>
                  <input type="tel" inputMode="numeric" autoComplete="tel-national" maxLength={14} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="10 digits" />
                </label>
              </div>
            </section>
            <section className={`co-step${address ? " is-done" : ""}`} data-stage-part="checkout:address" data-stage-group>
              <h2>
                <span className="co-num">2</span> Delivery address
              </h2>
              <div className="co-fields">
                <label className="field is-wide">
                  <span>Flat, building, street, area</span>
                  <input autoComplete="street-address" value={line} onChange={(e) => setLine(e.target.value)} />
                </label>
                <label className="field">
                  <span>City</span>
                  <input autoComplete="address-level2" value={city} onChange={(e) => setCity(e.target.value)} />
                </label>
                <label className="field">
                  <span>PIN code</span>
                  <input inputMode="numeric" autoComplete="postal-code" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />
                </label>
              </div>
              <p className="co-small">Once an order is placed its delivery address cannot be changed, so check it now.</p>
            </section>
            <section className={`co-step${paid ? " is-done" : ""}`} data-stage-part="checkout:payment" data-stage-group>
              <h2>
                <span className="co-num">3</span> Payment
              </h2>
              <div className="pay-options" role="radiogroup" aria-label="Payment">
                {PAYMENTS.filter((p) => p.id !== "Cash on delivery" || POLICY.delivery.cod).map((p) => (
                  <label key={p.id} className={`pay${payment === p.id ? " is-on" : ""}`}>
                    <input type="radio" name="payment" value={p.id} checked={payment === p.id} onChange={() => setPayment(p.id)} />
                    <span>
                      <b>{p.label}</b>
                      <small>{p.note}</small>
                    </span>
                  </label>
                ))}
              </div>
              <p className="co-small">
                <Lock size={13} aria-hidden /> A demo store: no payment is taken.
              </p>
            </section>
          </form>
          <aside className="summary">
            <h2>Order summary</h2>
            <ul className="co-items">
              {bag.map((l) => {
                const p = lineProduct(l);
                return p ? (
                  <li key={`${l.product_id}|${l.size}`}>
                    <ProductImage id={p.id} alt="" />
                    <span>
                      {p.name}
                      <small>
                        Size {l.size === "Onesize" ? "one size" : l.size}, qty {l.qty}
                        {l.gift ? ", gift wrapped" : ""}
                      </small>
                    </span>
                  </li>
                ) : null;
              })}
            </ul>
            <Totals lines={bag} />
            <div data-stage-part="checkout:place">
              <button type="button" className="btn primary big wide" data-dock-avoid disabled={!contact || !address || !paid} onClick={place}>
                Place order, {inr(t.total)}
              </button>
              {!contact || !address || !paid ? <p className="summary-small">Fill {[!contact && "contact", !address && "address", !paid && "payment"].filter(Boolean).join(", ")} to place the order.</p> : null}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
