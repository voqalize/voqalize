/**
 * /my-picks?ids=a,b,c&from=kiosk — what the showroom kiosk's QR code opens on
 * the phone: the shopper's picks, ready to save or add to the cart.
 */
import { Heart, ShoppingBag, Smartphone } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { Crumbs, Photo, PriceLine } from "../components/bits";
import { getVariant, productsByIds } from "../data/catalog";
import { useCart } from "../state/cart";
import { useShortlist } from "../state/shortlist";
import { useTitle } from "./usePage";

export function MyPicks() {
  useTitle("Your picks");
  const [params] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean).slice(0, 12);
  const items = productsByIds(ids);
  const fromKiosk = params.get("from") === "kiosk";
  const saved = useShortlist((s) => s.ids);
  return (
    <div className="wrap page-pad frontdesk my-picks">
      <Crumbs items={[{ label: "Home", to: "/" }, { label: "Your picks" }]} />
      <header className="fd-hero fd-hero-tight">
        <div>
          <p className="fd-eyebrow">
            <Smartphone size={15} aria-hidden /> {fromKiosk ? "From the showroom" : "Shared with you"}
          </p>
          <h1 className="h1">Your picks</h1>
          <p className="lede">{fromKiosk ? "The pieces you chose at the Fernhollow showroom. Save them, or add them to your cart." : "Save these, or add them to your cart."}</p>
        </div>
        {items.length ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => useCart.getState().add(items.map((p) => ({ product_id: p.id, variant_id: getVariant(p).id, qty: 1 })))}
          >
            <ShoppingBag size={16} aria-hidden /> Add all {items.length} to cart
          </button>
        ) : null}
      </header>
      {items.length ? (
        <ol className="fd-pick-list">
          {items.map((p) => {
            const v = getVariant(p);
            const on = saved.includes(p.id);
            return (
              <li key={p.id} className="fd-pick" data-fh-thing={`product:${p.id}`}>
                <Link to={`/product/${p.id}`} className="fd-pick-photo" tabIndex={-1} aria-hidden>
                  <Photo file={p.images[0]} alt="" sizes="(min-width: 900px) 20vw, 40vw" />
                </Link>
                <div className="fd-pick-body">
                  <p className="fd-gift-cat">{p.category}</p>
                  <Link to={`/product/${p.id}`} className="fd-gift-title">
                    {p.title}
                  </Link>
                  <PriceLine price={v.price} compare={v.compareAtPrice} />
                  <div className="fd-pick-actions">
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => useCart.getState().add([{ product_id: p.id, variant_id: v.id, qty: 1 }])}>
                      <ShoppingBag size={14} aria-hidden /> Add to cart
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" aria-pressed={on} onClick={() => useShortlist.getState().toggle(p.id)}>
                      <Heart size={14} aria-hidden fill={on ? "currentColor" : "none"} /> {on ? "Saved" : "Save"}
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="lede">
          This link has no pieces in it. <Link className="link" to="/shop">Browse the store</Link>.
        </p>
      )}
    </div>
  );
}
