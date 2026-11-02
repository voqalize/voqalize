import { Minus, Plus, Sparkles, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getProduct, money } from "../data/catalog";
import { DELIVERY_FREE_OVER, deliveryFor } from "../data/content";
import { priced, useCart } from "../state/cart";
import { emily, useMarked, useEmily } from "../voice/controller";
import { EmilyTag, Photo, PriceLine } from "./bits";

export function useFocusTrap(active: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    el?.querySelector<HTMLElement>("[data-autofocus], button, a, input")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !el) return;
      const items = [...el.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input, select, textarea")];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("no-scroll");
      prev?.focus?.();
    };
  }, [active]);
  return ref;
}

export function CartLines({ compact = false }: { compact?: boolean }) {
  const lines = useCart((s) => s.lines);
  const setQty = useCart((s) => s.setQty);
  const remove = useCart((s) => s.remove);
  const { rows } = priced(lines);
  return (
    <ul className={`cart-lines${compact ? " is-compact" : ""}`}>
      {rows.map(({ line, product, variant }) => (
        <li key={`${line.product_id}:${line.variant_id}`} className="cart-line" data-spot={`product:${product.id}`} data-fh-thing={`product:${product.id}`}>
          <Link to={`/product/${product.id}`} className="cart-thumb">
            <Photo file={product.images[0]} alt={product.title} sizes="96px" />
          </Link>
          <div className="cart-line-body">
            <div className="cart-line-top">
              <Link to={`/product/${product.id}`} className="cart-line-title">
                {product.title}
              </Link>
              <PriceLine price={variant.price * line.qty} compare={variant.compareAtPrice ? variant.compareAtPrice * line.qty : null} />
            </div>
            <p className="small">
              {Object.values(variant.options).join(", ")}
              {line.by === "emily" ? (
                <>
                  {" "}
                  <EmilyTag label="Added by Emily" />
                </>
              ) : null}
            </p>
            <div className="cart-line-actions">
              <div className="qty" role="group" aria-label={`Quantity of ${product.title}`}>
                <button type="button" aria-label="One fewer" onClick={() => setQty(line.product_id, line.variant_id, line.qty - 1)}>
                  <Minus size={14} />
                </button>
                <span aria-live="polite">{line.qty}</span>
                <button type="button" aria-label="One more" onClick={() => setQty(line.product_id, line.variant_id, line.qty + 1)}>
                  <Plus size={14} />
                </button>
              </div>
              <button type="button" className="link small" onClick={() => remove(line.product_id, line.variant_id)}>
                Remove
              </button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Suggestion() {
  const s = useEmily((x) => x.suggestion);
  const p = getProduct(s?.product_id);
  if (!s || !p) return null;
  return (
    <div className="suggestion" data-spot="section:suggestion">
      <Photo file={p.images[0]} alt="" sizes="64px" />
      <div>
        <p className="suggestion-head">
          <Sparkles size={14} aria-hidden /> <EmilyTag label="Emily suggests" />
        </p>
        <p className="suggestion-title">{p.title}</p>
        <p className="small">{s.reason}</p>
        <div className="suggestion-actions">
          <Link to={`/product/${p.id}`} className="link small">
            View finishes
          </Link>
          <button type="button" className="link small" onClick={() => emily.dismissSuggestion()}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

export function Totals() {
  const lines = useCart((s) => s.lines);
  const { total, saved } = priced(lines);
  const delivery = deliveryFor(total);
  return (
    <dl className="totals">
      <div>
        <dt>Subtotal</dt>
        <dd className="price">{money(total)}</dd>
      </div>
      {saved > 0 ? (
        <div className="totals-saved">
          <dt>You save</dt>
          <dd className="price">{money(saved)}</dd>
        </div>
      ) : null}
      <div>
        <dt>Delivery</dt>
        <dd className="price">{delivery ? money(delivery) : "Free"}</dd>
      </div>
      {delivery ? (
        <p className="small totals-note">Standard delivery is free on orders over {money(DELIVERY_FREE_OVER)}.</p>
      ) : null}
      <div className="totals-grand">
        <dt>Total</dt>
        <dd className="price">{money(total + delivery)}</dd>
      </div>
    </dl>
  );
}

export function CartDrawer() {
  const open = useCart((s) => s.open);
  const setOpen = useCart((s) => s.setOpen);
  const lines = useCart((s) => s.lines);
  const navigate = useNavigate();
  const marked = useMarked("cart");
  const ref = useFocusTrap(open);
  if (!open) return null;
  return (
    <div className="drawer-root" role="dialog" aria-modal="true" aria-label="Your cart" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button type="button" className="scrim" aria-label="Close cart" onClick={() => setOpen(false)} />
      <div className="drawer drawer-right" ref={ref}>
        <div className="drawer-head">
          <h2 className="h3">
            Your cart {marked ? <EmilyTag label="Updated by Emily" /> : null}
          </h2>
          <button type="button" className="icon-btn" aria-label="Close cart" onClick={() => setOpen(false)} data-autofocus>
            <X size={20} strokeWidth={1.6} />
          </button>
        </div>
        {lines.length === 0 ? (
          <div className="drawer-body cart-empty">
            <p className="h3">Nothing here yet.</p>
            <p className="small">Start with a room and find the pieces that suit it.</p>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setOpen(false);
                navigate("/room/living");
              }}
            >
              Shop the living room
            </button>
          </div>
        ) : (
          <>
            <div className="drawer-body">
              <Suggestion />
              <CartLines compact />
            </div>
            <div className="drawer-foot">
              <Totals />
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => {
                  setOpen(false);
                  navigate("/checkout");
                }}
              >
                Check out
              </button>
              <button
                type="button"
                className="btn btn-quiet btn-block"
                onClick={() => {
                  setOpen(false);
                  navigate("/cart");
                }}
              >
                View cart
              </button>
              <p className="small demo-note-inline">Demo store: no payment is taken at checkout.</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
