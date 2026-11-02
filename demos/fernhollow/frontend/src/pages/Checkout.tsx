import { Check, Info, Lock } from "lucide-react";
import { useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { money } from "../data/catalog";
import { deliveryFor } from "../data/content";
import { CartLines, Suggestion, Totals } from "../components/CartDrawer";
import { Crumbs, EmilyTag, Photo } from "../components/bits";
import { priced, useCart } from "../state/cart";
import { CHECKOUT_STEPS, COUNTRIES, type CheckoutField, type CheckoutStep, LABELS, missingIn, placeOrder, useCheckout } from "../state/checkout";
import { emit } from "../voice/events";
import { useTitle } from "./usePage";

export function DemoNote({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`demo-note${compact ? " is-compact" : ""}`} role="note">
      <Info size={17} aria-hidden />
      <p>
        <strong>Demo store — no payment is taken.</strong> Fernhollow is a fictional shop. Placing an order shows you the confirmation and
        nothing is charged, shipped or stored beyond this browser.
      </p>
    </div>
  );
}

export function CartPage() {
  useTitle("Cart");
  const lines = useCart((s) => s.lines);
  const navigate = useNavigate();
  return (
    <div className="wrap page-pad">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Cart" }]} />
      <h1 className="h1">Your cart</h1>
      {lines.length === 0 ? (
        <div className="empty empty-page">
          <p className="h3">Your cart is empty.</p>
          <p className="small">Find something for the room you are working on.</p>
          <Link to="/shop" className="btn btn-ghost">
            Browse all pieces
          </Link>
        </div>
      ) : (
        <div className="cart-page">
          <div>
            <Suggestion />
            <CartLines />
          </div>
          <aside className="summary-card">
            <Totals />
            <button type="button" className="btn btn-primary btn-block" data-dock-avoid onClick={() => navigate("/checkout")}>
              Check out
            </button>
            <DemoNote compact />
          </aside>
        </div>
      )}
    </div>
  );
}

export type { Order } from "../state/checkout";

const STEP_TITLE: Record<CheckoutStep, string> = { contact: "Contact", shipping: "Delivery address", review: "Review and place order" };

export function CheckoutPage() {
  useTitle("Checkout");
  const lines = useCart((s) => s.lines);
  const navigate = useNavigate();
  const { address: a, step, by, confirm } = useCheckout();
  const [errors, setErrors] = useState<Partial<Record<CheckoutField, string>>>({});
  const [showSummary, setShowSummary] = useState(false);
  const placed = useRef(false);
  const { rows, total } = priced(lines);
  const delivery = deliveryFor(total);

  if (lines.length === 0) return placed.current ? null : <Navigate to="/cart" replace />;

  const set = (k: CheckoutField, v: string) => useCheckout.getState().set(k, v);
  const tag = (k: CheckoutField) => (by[k] === "emily" ? <EmilyTag /> : null);

  const field = (k: CheckoutField, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className={`field field-${k}`} data-spot={`field:${k}`}>
      <label htmlFor={`co-${k}`}>
        {LABELS[k]} {tag(k)}
      </label>
      <input
        id={`co-${k}`}
        name={k}
        className="input"
        value={a[k]}
        aria-invalid={!!errors[k]}
        aria-describedby={errors[k] ? `co-${k}-err` : undefined}
        onChange={(e) => set(k, e.target.value)}
        {...props}
      />
      {errors[k] ? (
        <span className="error" id={`co-${k}-err`}>
          {errors[k]}
        </span>
      ) : null}
    </div>
  );

  const goTo = (next: CheckoutStep) => {
    const order = CHECKOUT_STEPS.indexOf(next);
    for (const s of CHECKOUT_STEPS.slice(0, order)) {
      const missing = missingIn(s, a);
      if (missing.length) {
        setErrors(Object.fromEntries(missing.map((m) => [m.field, m.why])));
        useCheckout.getState().setStep(s);
        requestAnimationFrame(() => document.getElementById(`co-${missing[0].field}`)?.focus());
        return;
      }
    }
    setErrors({});
    useCheckout.getState().setStep(next);
    window.scrollTo({ top: 0 });
  };

  const place = () => {
    const order = placeOrder();
    if (!order) return;
    placed.current = true;
    navigate("/checkout/confirmation", { state: order });
    useCart.getState().clear();
  };

  const stepBody = () => {
    if (step === "contact")
      return (
        <form
          noValidate
          data-spot="section:checkout-contact"
          onSubmit={(e) => {
            e.preventDefault();
            goTo("shipping");
          }}
        >
          <fieldset className="co-section">
            <legend className="h3">Contact</legend>
            {field("email", { type: "email", autoComplete: "email", inputMode: "email" })}
            {field("phone", { type: "tel", autoComplete: "tel" })}
          </fieldset>
          <button type="submit" className="btn btn-primary co-next" data-dock-avoid>
            Continue to delivery
          </button>
        </form>
      );
    if (step === "shipping")
      return (
        <form
          noValidate
          data-spot="section:checkout-shipping"
          onSubmit={(e) => {
            e.preventDefault();
            goTo("review");
          }}
        >
          <fieldset className="co-section">
            <legend className="h3">Delivery address</legend>
            <div className="co-grid">
              {field("first_name", { autoComplete: "given-name" })}
              {field("last_name", { autoComplete: "family-name" })}
              {field("address1", { autoComplete: "address-line1" })}
              {field("address2", { autoComplete: "address-line2" })}
              {field("city", { autoComplete: "address-level2" })}
              {field("region", { autoComplete: "address-level1" })}
              {field("postcode", { autoComplete: "postal-code" })}
              <div className="field field-country" data-spot="field:country">
                <label htmlFor="co-country">
                  {LABELS.country} {tag("country")}
                </label>
                <select id="co-country" name="country" className="select" value={a.country} onChange={(e) => set("country", e.target.value)} autoComplete="country-name">
                  {(COUNTRIES.includes(a.country) ? COUNTRIES : [...COUNTRIES, a.country]).map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field" data-spot="field:delivery">
              <label htmlFor="co-delivery">
                {LABELS.delivery} {tag("delivery")}
              </label>
              <textarea id="co-delivery" name="delivery" className="textarea" rows={3} value={a.delivery} onChange={(e) => set("delivery", e.target.value)} />
            </div>
          </fieldset>
          <fieldset className="co-section">
            <legend className="h3">Payment</legend>
            <p className="co-nopay">
              <Lock size={15} aria-hidden /> Nothing to enter. This demo store never asks for card or payment details.
            </p>
          </fieldset>
          <div className="co-actions">
            <button type="button" className="btn btn-ghost" onClick={() => goTo("contact")}>
              Back
            </button>
            <button type="submit" className="btn btn-primary co-next" data-dock-avoid>
              Review order
            </button>
          </div>
        </form>
      );
    return (
      <div className="review" data-spot="section:checkout-review">
        <section className="co-section">
          <div className="review-head">
            <h2 className="h3">Contact</h2>
            <button type="button" className="link small" onClick={() => goTo("contact")}>
              Edit
            </button>
          </div>
          <p className="review-address">
            {a.email}
            {a.phone ? (
              <>
                <br />
                {a.phone}
              </>
            ) : null}
          </p>
        </section>
        <section className="co-section">
          <div className="review-head">
            <h2 className="h3">Deliver to</h2>
            <button type="button" className="link small" onClick={() => goTo("shipping")}>
              Edit
            </button>
          </div>
          <address className="review-address">
            {a.first_name} {a.last_name}
            <br />
            {a.address1}
            {a.address2 ? (
              <>
                <br />
                {a.address2}
              </>
            ) : null}
            <br />
            {a.city}
            {a.region ? `, ${a.region}` : ""} {a.postcode}
            <br />
            {a.country}
          </address>
          {a.delivery ? <p className="small">Notes: {a.delivery}</p> : null}
        </section>
        <section className="co-section">
          <h2 className="h3">Items</h2>
          <ul className="review-lines">
            {rows.map(({ line, product, variant }) => (
              <li key={`${line.product_id}:${line.variant_id}`}>
                <Photo file={product.images[0]} alt="" sizes="64px" />
                <span>
                  <span className="review-title">{product.title}</span>
                  <span className="small">
                    {Object.values(variant.options).join(", ")}, qty {line.qty}
                  </span>
                </span>
                <span className="price">{money(variant.price * line.qty)}</span>
              </li>
            ))}
          </ul>
        </section>
        <div className="add-wrap place-wrap">
          {confirm ? (
            <div className="confirm is-inline" role="alertdialog" aria-label="Confirm placing the order">
              <p className="confirm-q">
                <EmilyTag /> {confirm.label || `Place the order for ${money(confirm.total)}?`}
              </p>
              <div className="confirm-actions">
                <button type="button" className="btn btn-primary btn-sm" autoFocus onClick={() => {
                  useCheckout.setState({ confirm: null });
                  emit("confirm_result", { confirmed: true });
                  place();
                }}>
                  <Check size={15} /> Place order
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
                  useCheckout.setState({ confirm: null });
                  emit("confirm_result", { confirmed: false });
                }}>
                  Not now
                </button>
              </div>
            </div>
          ) : null}
          <button type="button" className="btn btn-primary co-next" data-dock-avoid data-spot="button:place-order" onClick={() => (CHECKOUT_STEPS.slice(0, 2).some((st) => missingIn(st, a).length) ? goTo("review") : place())}>
            Place order, {money(total + delivery)}
          </button>
        </div>
        <p className="small">No payment is taken. Placing the order shows its confirmation.</p>
      </div>
    );
  };

  return (
    <div className="checkout">
      <div className="wrap">
        <Crumbs items={[{ label: "Cart", to: "/cart" }, { label: "Checkout" }]} />
        <ol className="steps" aria-label="Checkout steps">
          {CHECKOUT_STEPS.map((s, i) => (
            <li key={s} aria-current={step === s ? "step" : undefined}>
              <button type="button" onClick={() => goTo(s)}>
                <span className="step-n">{i + 1}</span> {STEP_TITLE[s]}
              </button>
            </li>
          ))}
        </ol>
        <DemoNote />
        <div className="checkout-grid">
          <div className="checkout-main">{stepBody()}</div>
          <aside className={`summary-card checkout-summary${showSummary ? " is-open" : ""}`}>
            <h2 className="h3 summary-heading">
              <span>Order summary</span>
              <button type="button" className="summary-toggle only-mobile" aria-expanded={showSummary} onClick={() => setShowSummary(!showSummary)}>
                {showSummary ? "Hide" : "Show"} <span className="price">{money(total + delivery)}</span>
              </button>
            </h2>
            <ul className="summary-lines">
              {rows.map(({ line, product, variant }) => (
                <li key={`${line.product_id}:${line.variant_id}`}>
                  <span className="summary-thumb">
                    <Photo file={product.images[0]} alt="" sizes="56px" />
                    <span className="summary-qty">{line.qty}</span>
                  </span>
                  <span className="summary-title">
                    {product.title}
                    <span className="small">{Object.values(variant.options).join(", ")}</span>
                  </span>
                  <span className="price">{money(variant.price * line.qty)}</span>
                </li>
              ))}
            </ul>
            <Totals />
          </aside>
        </div>
      </div>
    </div>
  );
}
