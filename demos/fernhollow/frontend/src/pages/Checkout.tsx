import { Info, Lock } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { money } from "../data/catalog";
import { deliveryFor } from "../data/content";
import { CartLines, Suggestion, Totals } from "../components/CartDrawer";
import { Crumbs, Photo } from "../components/bits";
import { type Line, priced, useCart } from "../state/cart";
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
            <button type="button" className="btn btn-primary btn-block" onClick={() => navigate("/checkout")}>
              Check out
            </button>
            <DemoNote compact />
          </aside>
        </div>
      )}
    </div>
  );
}

interface Address {
  email: string;
  firstName: string;
  lastName: string;
  address1: string;
  address2: string;
  city: string;
  region: string;
  postal: string;
  country: string;
  phone: string;
  notes: string;
}

const EMPTY: Address = {
  email: "",
  firstName: "",
  lastName: "",
  address1: "",
  address2: "",
  city: "",
  region: "",
  postal: "",
  country: "United States",
  phone: "",
  notes: "",
};

const REQUIRED: (keyof Address)[] = ["email", "firstName", "lastName", "address1", "city", "postal", "country"];
const LABELS: Record<keyof Address, string> = {
  email: "Email",
  firstName: "First name",
  lastName: "Last name",
  address1: "Address",
  address2: "Apartment, suite, floor (optional)",
  city: "City",
  region: "State or region",
  postal: "Postal code",
  country: "Country",
  phone: "Phone (optional)",
  notes: "Delivery notes (optional)",
};

export interface Order {
  number: string;
  placedAt: string;
  lines: Line[];
  subtotal: number;
  saved: number;
  delivery: number;
  address: Address;
}

export function CheckoutPage() {
  useTitle("Checkout");
  const lines = useCart((s) => s.lines);
  const clear = useCart((s) => s.clear);
  const navigate = useNavigate();
  const [a, setA] = useState<Address>(() => {
    try {
      return { ...EMPTY, ...JSON.parse(sessionStorage.getItem("fh-address") ?? "{}") };
    } catch {
      return EMPTY;
    }
  });
  const [step, setStep] = useState<"details" | "review">("details");
  const [errors, setErrors] = useState<Partial<Record<keyof Address, string>>>({});
  const { rows, total, saved } = priced(lines);
  const delivery = deliveryFor(total);

  if (lines.length === 0) return <Navigate to="/cart" replace />;

  const field = (k: keyof Address, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className={`field field-${k}`}>
      <label htmlFor={`co-${k}`}>{LABELS[k]}</label>
      <input
        id={`co-${k}`}
        className="input"
        value={a[k]}
        aria-invalid={!!errors[k]}
        aria-describedby={errors[k] ? `co-${k}-err` : undefined}
        onChange={(e) => setA({ ...a, [k]: e.target.value })}
        {...props}
      />
      {errors[k] ? (
        <span className="error" id={`co-${k}-err`}>
          {errors[k]}
        </span>
      ) : null}
    </div>
  );

  const validate = () => {
    const next: typeof errors = {};
    for (const k of REQUIRED) if (!a[k].trim()) next[k] = `Enter your ${LABELS[k].toLowerCase()}.`;
    if (a.email && !/^\S+@\S+\.\S+$/.test(a.email)) next.email = "Enter an email address like name@example.com.";
    setErrors(next);
    if (Object.keys(next).length) {
      document.getElementById(`co-${Object.keys(next)[0]}`)?.focus();
      return false;
    }
    return true;
  };

  const place = () => {
    const order: Order = {
      number: `FH-${String(Date.now()).slice(-6)}`,
      placedAt: new Date().toISOString(),
      lines,
      subtotal: total,
      saved,
      delivery,
      address: a,
    };
    try {
      sessionStorage.setItem("fh-order", JSON.stringify(order));
      sessionStorage.removeItem("fh-address");
    } catch {
      /* storage unavailable: the confirmation reads the state below */
    }
    clear();
    navigate("/checkout/confirmation", { state: order });
  };

  return (
    <div className="checkout">
      <div className="wrap">
        <Crumbs items={[{ label: "Cart", to: "/cart" }, { label: "Details", to: step === "review" ? "/checkout" : undefined }, { label: "Review" }]} />
        <ol className="steps" aria-label="Checkout steps">
          <li aria-current={step === "details" ? "step" : undefined}>
            <span className="step-n">1</span> Details
          </li>
          <li aria-current={step === "review" ? "step" : undefined}>
            <span className="step-n">2</span> Review and place order
          </li>
        </ol>
        <DemoNote />
        <div className="checkout-grid">
          <div className="checkout-main">
            {step === "details" ? (
              <form
                noValidate
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!validate()) return;
                  try {
                    sessionStorage.setItem("fh-address", JSON.stringify(a));
                  } catch {
                    /* ignore */
                  }
                  setStep("review");
                  window.scrollTo({ top: 0 });
                }}
              >
                <fieldset className="co-section">
                  <legend className="h3">Contact</legend>
                  {field("email", { type: "email", autoComplete: "email", inputMode: "email" })}
                </fieldset>
                <fieldset className="co-section">
                  <legend className="h3">Delivery address</legend>
                  <div className="co-grid">
                    {field("firstName", { autoComplete: "given-name" })}
                    {field("lastName", { autoComplete: "family-name" })}
                    {field("address1", { autoComplete: "address-line1" })}
                    {field("address2", { autoComplete: "address-line2" })}
                    {field("city", { autoComplete: "address-level2" })}
                    {field("region", { autoComplete: "address-level1" })}
                    {field("postal", { autoComplete: "postal-code" })}
                    <div className="field field-country">
                      <label htmlFor="co-country">{LABELS.country}</label>
                      <select id="co-country" className="select" value={a.country} onChange={(e) => setA({ ...a, country: e.target.value })} autoComplete="country-name">
                        {["United States", "Canada", "United Kingdom", "Ireland", "Australia", "New Zealand"].map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                    {field("phone", { type: "tel", autoComplete: "tel" })}
                  </div>
                  <div className="field">
                    <label htmlFor="co-notes">{LABELS.notes}</label>
                    <textarea id="co-notes" className="textarea" rows={3} value={a.notes} onChange={(e) => setA({ ...a, notes: e.target.value })} />
                  </div>
                </fieldset>
                <fieldset className="co-section">
                  <legend className="h3">Payment</legend>
                  <p className="co-nopay">
                    <Lock size={15} aria-hidden /> Nothing to enter. This demo store never asks for card or payment details.
                  </p>
                </fieldset>
                <button type="submit" className="btn btn-primary co-next">
                  Review order
                </button>
              </form>
            ) : (
              <div className="review">
                <section className="co-section">
                  <div className="review-head">
                    <h2 className="h3">Deliver to</h2>
                    <button type="button" className="link small" onClick={() => setStep("details")}>
                      Edit
                    </button>
                  </div>
                  <address className="review-address">
                    {a.firstName} {a.lastName}
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
                    {a.region ? `, ${a.region}` : ""} {a.postal}
                    <br />
                    {a.country}
                  </address>
                  <p className="small">Confirmation to {a.email}</p>
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
                <button type="button" className="btn btn-primary co-next" onClick={place}>
                  Place order, {money(total + delivery)}
                </button>
                <p className="small">No payment is taken. Placing the order shows its confirmation.</p>
              </div>
            )}
          </div>
          <aside className="summary-card checkout-summary">
            <h2 className="h3">Order summary</h2>
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
