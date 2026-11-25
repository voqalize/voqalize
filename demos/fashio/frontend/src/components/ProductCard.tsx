/**
 * One product as a card: image (from the bucket, placeholder on error), brand,
 * name, price with MRP and discount, the wishlist heart. Every listing, rail,
 * the compare page, the wishlist, the gift finder and the kiosk use it, so the
 * agent's `{show: <id>}` cue finds `data-stage-thing="product:<id>"` anywhere.
 *
 * Props are a contract other pages build on: `product`, `reason?` (a line
 * under the price: the gift finder's why), `size?` ("w400" image is always
 * used), `onOpen?` (instead of linking to /p/<id>: the kiosk), `compact?`.
 */
import { Heart } from "lucide-react";
import { Link } from "react-router-dom";
import { imgUrl, placeholderUrl } from "../data/assets";
import { type Product, anyStock, discountPct, inr, productPath } from "../data/catalog";
import { useStore } from "../state/store";

export function ProductImage({ id, alt, w = 400, className, eager = false }: { id: number; alt: string; w?: 400 | 1080; className?: string; eager?: boolean }) {
  return (
    <img
      className={className}
      src={imgUrl(id, w)}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={(e) => {
        const img = e.currentTarget;
        if (!img.dataset.fallback) {
          img.dataset.fallback = "1";
          img.src = placeholderUrl(w);
        }
      }}
    />
  );
}

export function ProductCard({ product: p, reason, onOpen, compact = false }: { product: Product; reason?: string; size?: "w400"; onOpen?: (p: Product) => void; compact?: boolean }) {
  const wished = useStore((s) => s.wishlist.includes(p.id));
  const toggle = useStore((s) => s.toggleWishlist);
  const off = discountPct(p);
  const sold = !anyStock(p);
  const body = (
    <>
      <div className="pc-img">
        <ProductImage id={p.id} alt={p.name} />
        {sold ? <span className="pc-flag is-sold">Sold out</span> : off >= 40 ? <span className="pc-flag">{off}% off</span> : null}
      </div>
      <div className="pc-body">
        <p className="pc-brand">{p.brand}</p>
        <p className="pc-name">{p.name}</p>
        <p className="pc-price">
          <b>{inr(p.price)}</b>
          {off > 0 ? (
            <>
              <s>{inr(p.mrp)}</s>
              <span className="pc-off">{off}% off</span>
            </>
          ) : null}
        </p>
        {reason ? <p className="pc-reason">{reason}</p> : null}
      </div>
    </>
  );
  return (
    <article className={`pc${compact ? " is-compact" : ""}`} data-stage-thing={`product:${p.id}`}>
      {onOpen ? (
        <button type="button" className="pc-link" onClick={() => onOpen(p)}>
          {body}
        </button>
      ) : (
        <Link className="pc-link" to={productPath(p.id)}>
          {body}
        </Link>
      )}
      <button
        type="button"
        className={`pc-heart${wished ? " is-on" : ""}`}
        data-stage-part={`wishlist:${p.id}`}
        aria-pressed={wished}
        aria-label={wished ? `Remove ${p.name} from wishlist` : `Save ${p.name} to wishlist`}
        onClick={() => toggle(p.id)}
      >
        <Heart size={17} fill={wished ? "currentColor" : "none"} />
      </button>
    </article>
  );
}

/** Grey cards while the catalogue loads. */
export function CardSkeletons({ n = 8 }: { n?: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="pc pc-skeleton" aria-hidden>
          <div className="pc-img" />
          <div className="pc-body">
            <span />
            <span />
            <span />
          </div>
        </div>
      ))}
    </>
  );
}
